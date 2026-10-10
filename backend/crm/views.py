from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import CanCreateSales, CanViewFinancialReports, HasCompany, get_company_user
from core.throttles import CompanyRateThrottle
from core.viewsets import CompanyScopedViewSet

from .models import Lead, LeadActivity, Opportunity
from .permissions import assert_crm_enabled
from .pipeline import PENDING_REVIEW, DedupePrompt, capture_lead, next_assignee
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
        if params.get("campaign"):
            qs = qs.filter(campaign_id=params.get("campaign"))
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
                campaign=request.data.get("campaign") or None,
                referral_code=request.data.get("referral_code") or "",
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
        changed = any(request.data.get(field) for field in ("state", "gstin", "address", "status"))
        customer_id = request.data.get("customer")
        if customer_id:
            # capture_lead() and the loop above never touch `customer` — a
            # lead created already pointing at an existing Customer must not
            # be silently dropped (convert_lead() would otherwise create a
            # duplicate Customer for it later).
            from masters.models import Customer as CustomerModel

            customer = CustomerModel.objects.filter(company=company, pk=customer_id).first()
            if customer is None:
                return Response({"detail": "customer must belong to this company."}, status=400)
            lead.customer = customer
            changed = True
        if changed:
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

    @action(detail=True, methods=["post"], url_path="resolve-dedupe")
    def resolve_dedupe(self, request, pk=None):
        """The only path that can clear PENDING_REVIEW — it had none before."""
        lead = self.get_object()
        if lead.dedupe_review != PENDING_REVIEW:
            return Response({"detail": "This lead is not pending dedupe review."}, status=400)
        decision = (request.data.get("decision") or "").strip().lower()
        candidates = lead.dedupe_candidates or {}
        if decision == "match":
            try:
                raw_customer = request.data.get("customer_id")
                raw_lead = request.data.get("lead_id")
                customer_id = int(raw_customer) if raw_customer not in (None, "") else None
                lead_id = int(raw_lead) if raw_lead not in (None, "") else None
            except (TypeError, ValueError):
                return Response({"detail": "customer_id and lead_id must be integers."}, status=400)
            if customer_id and customer_id not in (candidates.get("customers") or []):
                return Response({"detail": "customer_id must be one of the recorded candidates."}, status=400)
            if lead_id and lead_id not in (candidates.get("leads") or []):
                return Response({"detail": "lead_id must be one of the recorded candidates."}, status=400)
            lead.dedupe_matched_customer_id = customer_id
            lead.dedupe_matched_lead_id = lead_id
            if customer_id:
                lead.customer_id = customer_id
        elif decision == "new":
            # Confirmed distinct — clear the recorded match so the lead
            # doesn't keep pointing at a party staff just rejected.
            lead.dedupe_matched_customer_id = None
            lead.dedupe_matched_lead_id = None
        else:
            return Response({"detail": "decision must be 'new' or 'match'."}, status=400)
        lead.dedupe_review = ""
        with transaction.atomic():
            # next_assignee() takes its own row lock internally and must not
            # release it before this save persists assigned_to — otherwise
            # two resolve-dedupe calls racing on different leads can both
            # read the same "least loaded" snapshot and double-assign, the
            # exact bug the round-robin lock exists to prevent.
            if lead.assigned_to_id is None:
                lead.assigned_to = next_assignee(lead.company)
            lead.updated_by = request.user
            lead.save(update_fields=[
                "dedupe_matched_customer", "dedupe_matched_lead", "dedupe_review",
                "customer", "assigned_to", "updated_by", "updated_at",
            ])
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
                "campaign": raw.get("campaign") or raw.get("Campaign") or "",
                "referral_code": raw.get("referral_code") or raw.get("Referral Code") or "",
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
        process_lead_ingest.delay(job.id, company_id=job.company_id)
        job.refresh_from_db()
        return Response(_ingest_job_payload(job), status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="form-token")
    def form_token(self, request):
        from crm.pipeline import ensure_lead_form_token

        company = get_company_user(request).company
        return Response({"token": ensure_lead_form_token(company)})

    @action(detail=False, methods=["post"], url_path="whatsapp-token")
    def whatsapp_token(self, request):
        from accounts.models import CompanyUser
        from crm.pipeline import ensure_whatsapp_webhook_token

        membership = get_company_user(request)
        if membership.role != CompanyUser.Role.OWNER:
            return Response({"detail": "Owner role required."}, status=status.HTTP_403_FORBIDDEN)
        rotate = request.data.get("rotate") in (True, "true", "1", 1)
        return Response({"token": ensure_whatsapp_webhook_token(membership.company, rotate=rotate)})

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

    @extend_schema(
        methods=["GET"],
        request=None,
        responses=LeadActivitySerializer(many=True),
    )
    @extend_schema(
        methods=["POST"],
        request=LeadActivitySerializer,
        responses={201: LeadActivitySerializer},
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
        # Per-caller within the company's form, not one bucket shared by
        # every visitor — a single caller keyed only on `token` could
        # otherwise exhaust the whole company's quota for everyone else.
        caller = self.get_ident(request) or "anon"
        ident = f"leadform-{token}-{caller}" if token else caller
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
        from core.rls import set_rls_company

        company = Company.objects.filter(lead_form_token=token).first()
        if company is None or not flag_enabled(company, "ENABLE_CRM"):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        set_rls_company(company.id)
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
                campaign=request.data.get("campaign") or None,
                referral_code=request.data.get("referral_code") or "",
                attribution_quiet=True,
            )
        except (BusinessRuleError, ValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)


class WhatsAppWebhookThrottle(SimpleRateThrottle):
    scope = "whatsapp_webhook"

    def get_cache_key(self, request, view):
        token = (getattr(view, "kwargs", None) or {}).get("token") or ""
        caller = self.get_ident(request) or "anon"
        ident = f"wa-{token}-{caller}" if token else caller
        return self.cache_format % {"scope": self.scope, "ident": ident}


class WhatsAppInboundView(APIView):
    permission_classes = []
    authentication_classes = []
    throttle_classes = [WhatsAppWebhookThrottle]
    throttle_scope = "whatsapp_webhook"

    def get(self, request, token):
        """Meta's webhook handshake. Echo hub.challenge when the verify token matches.

        This does not require the inbound flag. Registration has to succeed
        before that flag is turned on. Message delivery stays on POST.
        """
        from django.http import HttpResponse

        from accounts.models import Company

        company = Company.objects.filter(whatsapp_webhook_token=token).first()
        if company is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        mode = request.query_params.get("hub.mode") or ""
        verify = request.query_params.get("hub.verify_token") or ""
        challenge = request.query_params.get("hub.challenge") or ""
        if mode != "subscribe" or verify != token or not challenge:
            return Response({"detail": "Invalid verification."}, status=status.HTTP_403_FORBIDDEN)
        return HttpResponse(challenge, content_type="text/plain")

    def post(self, request, token):
        from django.conf import settings

        from accounts.models import Company
        from core.services.feature_flags import flag_enabled
        from crm.pipeline import verify_whatsapp_signature

        from core.rls import set_rls_company

        company = Company.objects.filter(whatsapp_webhook_token=token).first()
        enabled = (
            company is not None
            and flag_enabled(company, "ENABLE_CRM")
            and flag_enabled(company, "ENABLE_CRM_WHATSAPP_INBOUND")
        )
        if not enabled:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        set_rls_company(company.id)
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
        process_lead_ingest.delay(job.id, company_id=job.company_id)
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

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "draft_invoice":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action == "won_versus_invoices":
            return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]
        return [IsAuthenticated(), HasCompany(), CanCreateSales()]

    @action(detail=False, methods=["get"])
    def forecast(self, request):
        from .forecast import pipeline_forecast

        return Response(pipeline_forecast(get_company_user(request).company))

    @action(detail=False, methods=["get"], url_path="won-versus-invoices")
    def won_versus_invoices(self, request):
        from .forecast import won_versus_invoices

        month = request.query_params.get("month") or ""
        if len(month) != 7 or month[4] != "-":
            return Response({"detail": "Pass month as YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            body = won_versus_invoices(get_company_user(request).company, month)
        except ValueError:
            return Response({"detail": "Pass month as YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(body)

    @action(detail=True, methods=["post"], url_path="draft-invoice")
    def draft_invoice(self, request, pk=None):
        from sales.serializers import SalesInvoiceSerializer

        def _build():
            opportunity = self.get_object()
            if opportunity.stage != Opportunity.Stage.WON:
                return Response(
                    {"detail": "A draft invoice can be created from a won opportunity."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if opportunity.customer_id is None:
                return Response(
                    {"detail": "This opportunity has no customer yet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items = request.data.get("items")
            if not items:
                items = [
                    {
                        "product": line.product_id,
                        "quantity": str(line.quantity),
                        "unit_price": str(line.unit_price),
                    }
                    for line in opportunity.lines.all()
                ]
            if not items:
                return Response(
                    {"detail": "Add a product before creating the invoice."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer = SalesInvoiceSerializer(
                data={"customer": opportunity.customer_id, "invoice_type": "GST", "items": items},
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)
            invoice = serializer.save(
                company=opportunity.company,
                created_by=request.user,
                updated_by=request.user,
            )
            return Response(
                {"id": invoice.id, "customer": invoice.customer_id, "status": invoice.status},
                status=status.HTTP_201_CREATED,
            )

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="sales_invoice_create",
            build=_build,
        )

    @action(detail=True, methods=["post"])
    def quotation(self, request, pk=None):
        """Quote a won opportunity through the same create path as every other quote.

        An open quote for this opportunity is returned instead of a second one, so a
        double click cannot duplicate it; a cancelled or fully converted one does not
        block a new quote.
        """
        from sales.models import Quotation
        from sales.services import SalesService

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

        def _payload(quotation, *, already_exists):
            return {
                "id": quotation.id,
                "number": quotation.number,
                "customer": quotation.customer_id,
                "opportunity": opportunity.id,
                "grand_total": str(quotation.grand_total),
                "already_exists": already_exists,
            }

        def _build():
            with transaction.atomic():
                existing = (
                    Quotation.objects.select_for_update()
                    .filter(
                        company=opportunity.company,
                        opportunity=opportunity,
                        status__in=Quotation.OPEN_STATUSES,
                    )
                    .order_by("-id")
                    .first()
                )
                if existing is not None:
                    return Response(_payload(existing, already_exists=True), status=status.HTTP_200_OK)
                items_data = [
                    {
                        "product": line.product,
                        "description": line.description,
                        "quantity": line.quantity,
                        "unit_price": line.unit_price,
                        "gst_rate": line.product.gst_rate,
                        "hsn_code": line.product.hsn_code,
                    }
                    for line in opportunity.lines.select_related("product")
                ]
                quotation = SalesService.create_quotation(
                    opportunity.company,
                    request.user,
                    {
                        "customer": opportunity.customer,
                        "opportunity": opportunity,
                        "notes": opportunity.title,
                    },
                    items_data,
                    allow_empty_lines=True,
                )
                return Response(_payload(quotation, already_exists=False), status=status.HTTP_201_CREATED)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope=f"crm_opportunity_quotation:{opportunity.pk}",
            build=_build,
        )
