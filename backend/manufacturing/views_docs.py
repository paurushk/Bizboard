"""Endpoints for the issue / return / receipt documents and the work-order close actions."""

from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.idempotency import wrap_idempotent
from core.permissions import HasCompany, get_company_user

from .models import MaterialIssue, MaterialReturn, ProductionReceipt
from .permissions import (
    BadInputIs400,
    PLAN_ROLES, REVERSE_ROLES, MfgRolePermission, assert_manufacturing_enabled, can_backdate, role_of,
)
from rest_framework.views import APIView

from inventory.models import Warehouse
from masters.models import Customer, Product

from .serializers import WorkOrderSerializer
from .serializers_docs import (
    IssueIn, MaterialIssueSerializer, MaterialReturnSerializer, ProductionReceiptSerializer,
    ApprovalNoteIn, QuickProductionIn, ReasonIn, ReceiptIn, ReturnIn,
)
from .services import quick_entry
from .services import issue as issue_svc
from .services import receipt as receipt_svc


class _DocViewSet(BadInputIs400, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {"reverse": REVERSE_ROLES, "approve": PLAN_ROLES, "reject": PLAN_ROLES}
    model = None
    input_serializer = None
    scope = ""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        qs = self.model.objects.filter(company=self.company).select_related("work_order").prefetch_related("lines")
        wo = self.request.query_params.get("work_order")
        if wo:
            qs = qs.filter(work_order_id=wo)
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs.order_by("-id")

    def _flags(self):
        return {"can_backdate": can_backdate(self.request), "is_manager": role_of(self.request) in PLAN_ROLES}

    def _ser(self, obj):
        return self.get_serializer(obj).data

    def create(self, request, *args, **kwargs):
        data = self.input_serializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)

        def build():
            doc = self.make_draft(data.validated_data, request.user)
            return Response(self._ser(doc), status=status.HTTP_201_CREATED)

        return wrap_idempotent(request=request, company=self.company, scope=f"{self.scope}.create", build=build)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        doc = self.get_object()

        def build():
            return Response(self._ser(self.do_post(doc, request)))

        return wrap_idempotent(request=request, company=self.company, scope=f"{self.scope}.post", build=build)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        doc = self.get_object()
        reason = ReasonIn(data=request.data)
        reason.is_valid(raise_exception=True)

        def build():
            return Response(self._ser(self.do_reverse(doc, request, reason.validated_data["reason"])))

        return wrap_idempotent(request=request, company=self.company, scope=f"{self.scope}.reverse", build=build)

    @action(detail=True, methods=["delete"], url_path="discard")
    def discard(self, request, pk=None):
        doc = self.get_object()
        if doc.status != "DRAFT":
            from .services.common import rule

            raise rule("Only a draft can be discarded. Reverse a posted document instead.", "MFG_DOC_NOT_DRAFT")
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MaterialIssueViewSet(_DocViewSet):
    model, input_serializer, scope = MaterialIssue, IssueIn, "mfg.issue"
    serializer_class = MaterialIssueSerializer

    def make_draft(self, v, user):
        return issue_svc.create_issue(
            v["work_order"], user, v.get("lines"), doc_date=v.get("doc_date"), notes=v.get("notes", ""),
        )

    def do_post(self, doc, request):
        return issue_svc.post_issue(doc, request.user, **self._flags())

    @action(detail=True, methods=["get"], url_path="print")
    def print_slip(self, request, pk=None):
        """The issue as a slip to hand over with the material."""
        from . import printing

        return HttpResponse(printing.issue_slip(self.get_object()), content_type="text/html; charset=utf-8")

    def do_reverse(self, doc, request, reason):
        return issue_svc.reverse_issue(doc, request.user, reason)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("approval"):
            qs = qs.filter(approval=self.request.query_params["approval"])
        return qs

    def _note(self, request):
        data = ApprovalNoteIn(data=request.data)
        data.is_valid(raise_exception=True)
        return data.validated_data.get("note", "")

    @action(detail=True, methods=["post"], url_path="request-approval")
    def request_approval(self, request, pk=None):
        """A floor user asks a manager to approve extra material."""
        doc, note = self.get_object(), self._note(request)
        return Response(self._ser(issue_svc.request_approval(doc, request.user, note)))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """A manager approves the request, which posts the issue."""
        doc, note = self.get_object(), self._note(request)

        def build():
            done = issue_svc.decide_approval(
                doc, request.user, approve=True, note=note, can_backdate=can_backdate(request),
            )
            return Response(self._ser(done))

        return wrap_idempotent(request=request, company=self.company, scope=f"{self.scope}.approve", build=build)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        doc, note = self.get_object(), self._note(request)
        return Response(self._ser(issue_svc.decide_approval(doc, request.user, approve=False, note=note)))


class MaterialReturnViewSet(_DocViewSet):
    model, input_serializer, scope = MaterialReturn, ReturnIn, "mfg.return"
    serializer_class = MaterialReturnSerializer

    def make_draft(self, v, user):
        return issue_svc.create_return(
            v["work_order"], user, v["lines"], doc_date=v.get("doc_date"), notes=v.get("notes", ""),
        )

    def do_post(self, doc, request):
        return issue_svc.post_return(doc, request.user, can_backdate=can_backdate(request))

    def do_reverse(self, doc, request, reason):
        return issue_svc.reverse_return(doc, request.user, reason)


class ProductionReceiptViewSet(_DocViewSet):
    model, input_serializer, scope = ProductionReceipt, ReceiptIn, "mfg.receipt"
    serializer_class = ProductionReceiptSerializer

    def make_draft(self, v, user):
        payload = {k: v[k] for k in ("doc_date", "is_final", "batch_no", "exp_date", "mfg_date", "notes") if k in v}
        if "lines" in v:
            payload["lines"] = v["lines"]
        return receipt_svc.create_receipt(v["work_order"], user, payload)

    def do_post(self, doc, request):
        override = str(request.data.get("override_wip", "")).lower() in ("1", "true", "yes")
        return receipt_svc.post_receipt(doc, request.user, override_wip=override, **self._flags())

    @action(detail=True, methods=["get"], url_path="print-label")
    def print_label(self, request, pk=None):
        """Labels for the batches this receipt made (one per batch, ``copies`` of each)."""
        from . import printing

        receipt = self.get_object()
        if receipt.status != "POSTED":
            from .services.common import rule

            raise rule("Only a posted receipt has batches to label.", "MFG_DOC_NOT_POSTED")
        copies = request.query_params.get("copies", "1")
        return HttpResponse(
            printing.batch_labels(receipt, int(copies) if copies.isdigit() else 1),
            content_type="text/html; charset=utf-8",
        )

    def do_reverse(self, doc, request, reason):
        return receipt_svc.reverse_receipt(doc, request.user, reason)


class QuickProductionView(BadInputIs400, APIView):
    """POST one request, get a closed work order with everything posted."""

    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)

    def post(self, request):
        from .services.common import rule

        company = get_company_user(request).company
        data = QuickProductionIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data

        def pick(model, pk):
            if pk in (None, ""):
                return None
            found = model.objects.filter(pk=pk, company=company).first()
            if found is None:
                raise rule("That reference does not belong to this company.", "MFG_BAD_REFERENCE")
            return found

        product = pick(Product, v["product"])
        if product is None:
            raise rule("Choose the product that was made.", "MFG_BAD_REFERENCE")
        components = {pick(Product, c["component"]): c["qty"] for c in v.get("components", [])}

        def build():
            wo = quick_entry.quick_production(
                company, request.user, product=product, qty=v["qty"], doc_date=v.get("doc_date"),
                customer=pick(Customer, v.get("customer")), warehouse=pick(Warehouse, v.get("warehouse")),
                fg_warehouse=pick(Warehouse, v.get("fg_warehouse")), batch_no=v.get("batch_no", ""),
                exp_date=v.get("exp_date"), mfg_date=v.get("mfg_date"), components=components,
                notes=v.get("notes", ""), can_backdate=can_backdate(request),
                is_manager=role_of(request) in PLAN_ROLES,
            )
            return Response(
                WorkOrderSerializer(wo, context={"request": request}).data, status=status.HTTP_201_CREATED,
            )

        return wrap_idempotent(request=request, company=company, scope="mfg.quick", build=build)


class TraceView(BadInputIs400, APIView):
    """GET ?batch=<id>&direction=back|forward: where a lot came from, or where it went."""

    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)

    def get(self, request):
        from inventory.models import BatchLot
        from .services import trace
        from .services.common import rule

        company = get_company_user(request).company
        batch = BatchLot.objects.filter(pk=request.query_params.get("batch"), company=company).first()
        if batch is None:
            raise rule("Choose a batch to trace.", "MFG_BAD_REFERENCE")
        direction = request.query_params.get("direction", "back")
        if direction == "forward":
            return Response({"batch": batch.batch_no, "direction": "forward", **trace.trace_forward(company, batch)})
        return Response({"batch": batch.batch_no, "direction": "back", "inputs": trace.trace_back(company, batch)})


class BatchSearchView(BadInputIs400, APIView):
    """GET ?q=<text>&product=<id>: lots whose number matches, for the trace and inspection pickers.

    Read-only and open to every manufacturing role. The inventory lot list needs inventory rights, which an
    accountant or auditor reading a trace does not have.
    """

    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)

    def get(self, request):
        from inventory.models import BatchLot

        company = get_company_user(request).company
        qs = BatchLot.objects.filter(company=company).select_related("product").order_by("-id")
        text = (request.query_params.get("q") or "").strip()
        if text:
            qs = qs.filter(batch_no__icontains=text)
        if request.query_params.get("product"):
            qs = qs.filter(product_id=request.query_params["product"])
        return Response({"results": [
            {"id": b.pk, "batch_no": b.batch_no, "product": b.product_id, "product_name": b.product.name,
             "expiry_date": b.expiry_date, "quality_status": b.quality_status}
            for b in qs[:20]
        ]})
