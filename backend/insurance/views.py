from django.http import Http404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.models import FileAsset
from core.permissions import CanManagePolicies, HasCompany, get_company_user
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from crm.models import Lead
from masters.models import Customer

from .models import Policy, PolicyOption, PolicyOptionSet, PolicyProduct
from .serializers import PolicyOptionSetSerializer, PolicyProductSerializer, PolicySerializer
from .services import (
    advisor_book,
    attach_kyc,
    cancel_policy,
    choose_option,
    create_option_set,
    endorse_policy,
    issue_policy,
    open_claim,
    open_commission,
    parse_commission_amount,
    renewal_diary,
)


def _gate(request):
    cu = get_company_user(request)
    if cu is None or not flag_enabled(cu.company, "ENABLE_INSURANCE"):
        raise Http404()
    return cu


class ProspectView(APIView):
    """A policy-desk prospect. The CRM module stays off; the lead row is the option-set parent."""

    permission_classes = [IsAuthenticated, HasCompany, CanManagePolicies]

    def post(self, request):
        cu = _gate(request)
        name = (request.data.get("name") or "").strip()
        if not name:
            raise BusinessRuleError("A prospect name is required.")
        lead = Lead.objects.create(
            company=cu.company, name=name[:200], created_by=request.user, updated_by=request.user,
        )
        return Response({"id": lead.id, "name": lead.name}, status=201)


class PolicyProductViewSet(CompanyScopedViewSet):
    queryset = PolicyProduct.objects.all()
    serializer_class = PolicyProductSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManagePolicies]
    audit_entity = "PolicyProduct"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_INSURANCE"):
            raise Http404()


class PolicyOptionSetViewSet(CompanyScopedViewSet):
    queryset = PolicyOptionSet.objects.prefetch_related("options")
    serializer_class = PolicyOptionSetSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManagePolicies]
    http_method_names = ["get", "post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_INSURANCE"):
            raise Http404()

    def create(self, request, *args, **kwargs):
        lead = Lead.objects.filter(company=self.company, pk=request.data.get("lead")).first()
        ids = request.data.get("products") or []
        row = create_option_set(self.company, request.user, lead=lead, product_ids=list(ids))
        return Response(self.get_serializer(row).data, status=201)

    @action(detail=True, methods=["post"], url_path="choose")
    def choose(self, request, pk=None):
        option = PolicyOption.objects.filter(company=self.company, option_set=self.get_object(), pk=request.data.get("option")).first()
        if option is None:
            raise BusinessRuleError("Option was not found on this set.")
        choose_option(option, request.user)
        return Response(self.get_serializer(self.get_object()).data)


class PolicyViewSet(CompanyScopedViewSet):
    queryset = Policy.objects.all()
    serializer_class = PolicySerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManagePolicies]
    http_method_names = ["get", "post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_INSURANCE"):
            raise Http404()

    def create(self, request, *args, **kwargs):
        from datetime import date

        option = PolicyOption.objects.filter(company=self.company, pk=request.data.get("option")).first()
        customer = Customer.objects.filter(company=self.company, pk=request.data.get("customer")).first()
        if option is None:
            raise BusinessRuleError("Option was not found.")
        try:
            start = date.fromisoformat(str(request.data.get("start_date") or ""))
        except ValueError:
            raise BusinessRuleError("Start date must be YYYY-MM-DD.") from None

        def _execute():
            policy = issue_policy(
                self.company, request.user, option=option, customer=customer,
                nominee=request.data.get("nominee") or "", start_date=start, advisor=self.company_user,
            )
            return Response(self.get_serializer(policy).data, status=201)

        return wrap_idempotent(request=request, company=self.company, scope="insurance_policy_create", build=_execute)

    @action(detail=True, methods=["post"])
    def endorse(self, request, pk=None):
        endorse_policy(self.get_object(), request.user, note=request.data.get("note") or "")
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(self.get_serializer(cancel_policy(self.get_object(), request.user, note=request.data.get("note") or "")).data)

    @action(detail=True, methods=["post"])
    def commission(self, request, pk=None):
        policy = self.get_object()
        amount = parse_commission_amount(request.data.get("amount"))

        def _execute():
            row = open_commission(policy, request.user, amount=amount)
            return Response({
                "id": row.id, "amount": str(row.amount),
                "insurer_name": row.insurer_name, "status": row.status,
            })

        return wrap_idempotent(
            request=request, company=self.company,
            scope=f"insurance_commission:{policy.pk}", build=_execute,
        )

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        row = open_claim(self.get_object(), request.user, summary=request.data.get("summary") or "")
        return Response({"id": row.id, "ticket_id": row.ticket_id, "summary": row.summary})

    @action(detail=True, methods=["post"], url_path="kyc")
    def kyc(self, request, pk=None):
        asset = FileAsset.objects.filter(company=self.company, pk=request.data.get("file")).first()
        row = attach_kyc(self.get_object(), request.user, kind=request.data.get("kind") or "OTHER", file_asset=asset)
        return Response({"id": row.id, "kind": row.kind, "file_id": row.file_id})


class AdvisorBookView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        cu = _gate(request)
        return Response(advisor_book(cu.company, cu))


class RenewalDiaryView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanManagePolicies]

    def post(self, request):
        cu = _gate(request)
        try:
            days = int(request.data.get("within_days") or 30)
        except (TypeError, ValueError):
            raise BusinessRuleError("within_days must be a whole number.") from None
        if days < 0:
            raise BusinessRuleError("within_days cannot be negative.")
        leads = renewal_diary(cu.company, request.user, within_days=days)
        return Response({"created": len(leads), "lead_ids": [row.id for row in leads]})
