from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import CanCreateSales, HasCompany, get_company_user
from core.throttles import CompanyRateThrottle
from core.viewsets import CompanyScopedViewSet

from .models import Lead, LeadActivity, Opportunity
from .permissions import assert_crm_enabled
from .pipeline import DedupePrompt, capture_lead, import_lead_rows
from .serializers import LeadActivitySerializer, LeadSerializer, OpportunitySerializer
from .services import convert_lead


def _truthy(value) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").lower() in ("1", "true", "yes", "won")


class LeadViewSet(CompanyScopedViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Lead"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_crm_enabled(get_company_user(request).company)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("source"):
            qs = qs.filter(source=params.get("source"))
        if params.get("dedupe_review"):
            qs = qs.filter(dedupe_review=params.get("dedupe_review"))
        if params.get("assigned_to"):
            qs = qs.filter(assigned_to_id=params.get("assigned_to"))
        if str(params.get("mine") or "").lower() in {"1", "true", "yes"}:
            qs = qs.filter(assigned_to=get_company_user(self.request))
        return qs

    def create(self, request, *args, **kwargs):
        company = get_company_user(request).company
        try:
            lead = capture_lead(
                company,
                request.user,
                name=request.data.get("name") or "",
                phone=request.data.get("phone") or "",
                email=request.data.get("email") or "",
                message=request.data.get("message") or "",
                source=request.data.get("source") or None,
                manual=True,
                dedupe_decision=request.data.get("dedupe_decision") or "",
            )
        except DedupePrompt as exc:
            return Response(
                {"code": "dedupe_match", "candidates": exc.candidates},
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages if hasattr(exc, "messages") else str(exc)}, status=400)
        for field in ("state", "gstin", "address", "status"):
            value = request.data.get(field)
            if value:
                setattr(lead, field, value)
        if any(request.data.get(field) for field in ("state", "gstin", "address", "status")):
            lead.save()
        return Response(LeadSerializer(lead, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        from accounts.models import CompanyUser

        lead = self.get_object()
        assignee_id = request.data.get("assigned_to")
        if assignee_id in (None, "", 0):
            lead.assigned_to = None
        else:
            assignee = CompanyUser.objects.filter(
                company=lead.company, pk=assignee_id, user__is_active=True
            ).first()
            if assignee is None:
                return Response({"detail": "Assignee must be an active company member."}, status=400)
            lead.assigned_to = assignee
        lead.updated_by = request.user
        lead.save(update_fields=["assigned_to", "updated_by", "updated_at"])
        return Response(LeadSerializer(lead, context={"request": request}).data)

    @action(detail=False, methods=["post"], url_path="import-csv")
    def import_csv(self, request):
        import csv
        import io

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "file is required."}, status=400)
        text = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for raw in reader:
            rows.append({
                "name": raw.get("name") or raw.get("Name") or "",
                "phone": raw.get("phone") or raw.get("Phone") or "",
                "email": raw.get("email") or raw.get("Email") or "",
                "message": raw.get("message") or raw.get("Message") or "",
            })
        from crm.models import LeadIngestJob
        from crm.tasks import process_lead_ingest

        cu = get_company_user(request)
        job = LeadIngestJob.objects.create(
            company=cu.company,
            kind=LeadIngestJob.Kind.CSV,
            payload={"rows": rows},
            created_by=request.user,
            updated_by=request.user,
        )
        process_lead_ingest.delay(job.id)
        job.refresh_from_db()
        return Response(_ingest_job_payload(job), status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="form-token")
    def form_token(self, request):
        import secrets

        company = get_company_user(request).company
        if not company.lead_form_token:
            company.lead_form_token = secrets.token_urlsafe(24)
            company.save(update_fields=["lead_form_token", "updated_at"])
        return Response({"token": company.lead_form_token})

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        lead = self.get_object()
        won = _truthy(request.query_params.get("won")) or _truthy(request.data.get("won"))
        amount = request.data.get("amount")
        lead, opportunity, _customer = convert_lead(lead, request.user, won=won, amount=amount)
        return Response(
            {
                "lead": LeadSerializer(lead, context={"request": request}).data,
                "opportunity": OpportunitySerializer(opportunity, context={"request": request}).data,
            }
        )

    @action(detail=True, methods=["get", "post"], url_path="activities")
    def activities(self, request, pk=None):
        lead = self.get_object()
        if request.method.lower() == "get":
            qs = LeadActivity.objects.filter(company=self.company, lead=lead).order_by("-created_at")
            return Response(LeadActivitySerializer(qs, many=True).data)
        serializer = LeadActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            lead=lead,
            company=lead.company,
            created_by=request.user,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def _ingest_job_payload(job) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "result": job.result or {},
        "error": job.error,
    }


class LeadIngestJobView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request, job_id):
        from crm.models import LeadIngestJob

        company = get_company_user(request).company
        job = LeadIngestJob.objects.filter(company=company, pk=job_id).first()
        if job is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_ingest_job_payload(job))


class LeadFormThrottle(CompanyRateThrottle):
    def get_cache_key(self, request, view):
        token = (getattr(view, "kwargs", None) or {}).get("token") or ""
        ident = f"leadform-{token}" if token else (self.get_ident(request) or "anon")
        self.scope = getattr(view, "throttle_scope", None) or "lead_form"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class PublicLeadFormView(APIView):
    permission_classes = []
    authentication_classes = []
    throttle_classes = [LeadFormThrottle]
    throttle_scope = "lead_form"

    def post(self, request, token):
        from accounts.models import Company
        from core.services.feature_flags import flag_enabled

        if (request.data.get("website") or "").strip():
            return Response({"ok": True})
        company = Company.objects.filter(lead_form_token=token).first()
        if company is None or not flag_enabled(company, "ENABLE_CRM"):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        from django.core.exceptions import ValidationError

        try:
            capture_lead(
                company,
                None,
                name=request.data.get("name") or "",
                phone=request.data.get("phone") or "",
                email=request.data.get("email") or "",
                message=request.data.get("message") or "",
                source="website",
                manual=False,
            )
        except (BusinessRuleError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)


class WhatsAppInboundView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request, token):
        from django.conf import settings

        from accounts.models import Company
        from core.services.feature_flags import flag_enabled
        from crm.pipeline import verify_whatsapp_signature

        company = Company.objects.filter(lead_form_token=token).first()
        enabled = (
            company is not None
            and flag_enabled(company, "ENABLE_CRM")
            and flag_enabled(company, "ENABLE_CRM_WHATSAPP_INBOUND")
        )
        if not enabled:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        secret = getattr(settings, "WHATSAPP_APP_SECRET", "") or ""
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_whatsapp_signature(request.body, signature, secret):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_403_FORBIDDEN)
        payload = request.data if isinstance(request.data, dict) else {}
        message_id = str(payload.get("message_id") or payload.get("id") or "")
        sender = str(payload.get("from") or payload.get("sender") or "")
        text = str(payload.get("text") or "")
        sent_at = str(payload.get("timestamp") or "")
        if not message_id or not sender:
            return Response({"detail": "message id and sender are required."}, status=status.HTTP_400_BAD_REQUEST)
        from crm.models import LeadIngestJob
        from crm.tasks import process_lead_ingest

        job = LeadIngestJob.objects.create(
            company=company,
            kind=LeadIngestJob.Kind.WHATSAPP,
            payload={
                "message_id": message_id,
                "sender": sender,
                "text": text,
                "sent_at": sent_at,
            },
        )
        process_lead_ingest.delay(job.id)
        job.refresh_from_db()
        return Response(_ingest_job_payload(job), status=status.HTTP_202_ACCEPTED)


class OpportunityViewSet(CompanyScopedViewSet):
    queryset = Opportunity.objects.select_related("lead")
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Opportunity"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_crm_enabled(get_company_user(request).company)

    @action(detail=True, methods=["post"])
    def quotation(self, request, pk=None):
        from sales.models import Quotation

        opportunity = self.get_object()
        if opportunity.stage != Opportunity.Stage.WON:
            return Response(
                {"detail": "A quotation can be created from a won opportunity."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if opportunity.customer_id is None:
            return Response(
                {"detail": "This opportunity has no customer yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        quotation = Quotation.objects.create(
            company=opportunity.company,
            customer=opportunity.customer,
            opportunity=opportunity,
            notes=opportunity.title,
            created_by=request.user,
            updated_by=request.user,
        )
        return Response(
            {"id": quotation.id, "customer": quotation.customer_id, "opportunity": opportunity.id},
            status=status.HTTP_201_CREATED,
        )
