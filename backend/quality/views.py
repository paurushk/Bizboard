from html import escape

from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.idempotency import wrap_idempotent
from core.permissions import HasCompany, get_company_user
from core.services.sequences import next_number
from core.viewsets import CompanyScopedViewSet
from inventory.models import BatchLot
from masters.models import Product

from . import services
from .models import DefectCode, Inspection, InspectionTemplate, NonConformance
from manufacturing.permissions import BadInputIs400

from .permissions import SETUP_ROLES, QualityRolePermission, assert_quality_enabled, role_of
from .serializers import (
    DefectCodeSerializer, InspectionCompleteIn, InspectionCreateIn, InspectionSerializer,
    InspectionTemplateSerializer, NonConformanceSerializer,
)


class _QualityMixin(BadInputIs400):
    permission_classes = [IsAuthenticated, HasCompany, QualityRolePermission]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_quality_enabled(get_company_user(request).company)


class DefectCodeViewSet(_QualityMixin, CompanyScopedViewSet):
    queryset = DefectCode.objects.all()
    serializer_class = DefectCodeSerializer
    audit_entity = "DefectCode"
    quality_roles = {a: SETUP_ROLES for a in ("create", "update", "partial_update", "destroy")}


class InspectionTemplateViewSet(_QualityMixin, CompanyScopedViewSet):
    queryset = InspectionTemplate.objects.prefetch_related("parameters")
    serializer_class = InspectionTemplateSerializer
    audit_entity = "InspectionTemplate"
    quality_roles = {a: SETUP_ROLES for a in ("create", "update", "partial_update", "destroy")}

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("product"):
            qs = qs.filter(product_id=self.request.query_params["product"])
        if self.request.query_params.get("stage"):
            qs = qs.filter(stage=self.request.query_params["stage"])
        return qs


class InspectionViewSet(_QualityMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = InspectionSerializer
    quality_roles = {}

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        qs = Inspection.objects.filter(company=self.company).select_related("product", "batch").prefetch_related("results")
        for key in ("status", "decision", "stage", "product", "batch"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs

    def create(self, request, *args, **kwargs):
        data = InspectionCreateIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        company = self.company
        product = Product.objects.filter(pk=v["product"], company=company).first()
        if product is None:
            raise services.rule("Choose a product.", "QC_BAD_REFERENCE")
        batch = BatchLot.objects.filter(pk=v.get("batch"), company=company).first() if v.get("batch") else None
        grn_item = None
        supplier = None
        if v.get("grn_item"):
            from purchases.models import GoodsReceiptItem

            grn_item = GoodsReceiptItem.objects.select_related("goods_receipt").filter(
                pk=v["grn_item"], goods_receipt__company=company,
            ).first()
            if grn_item is None:
                raise services.rule("That goods receipt line was not found.", "QC_BAD_REFERENCE")
            supplier = grn_item.goods_receipt.supplier
        template = InspectionTemplate.objects.filter(pk=v.get("template"), company=company).first() if v.get("template") else None
        source = v.get("source_type") or (
            Inspection.Source.GRN_ITEM if grn_item else Inspection.Source.BATCH if batch else Inspection.Source.BATCH
        )

        def build():
            insp = services.create_inspection(
                company, request.user, product=product, qty=v["qty"], source_type=source, stage=v["stage"],
                template=template, batch=batch, grn_item=grn_item, supplier=supplier, notes=v.get("notes", ""),
            )
            return Response(self.get_serializer(insp).data, status=status.HTTP_201_CREATED)

        return wrap_idempotent(request=request, company=company, scope="quality.inspection.create", build=build)

    @action(detail=True, methods=["post"], url_path="record-results")
    def record_results(self, request, pk=None):
        insp = services.record_results(self.get_object(), request.user, request.data.get("results") or {})
        return Response(self.get_serializer(insp).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        body = InspectionCompleteIn(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        insp = self.get_object()

        def build():
            done = services.complete_inspection(
                insp, request.user, decision=v.get("decision"), qty_accepted=v.get("qty_accepted"),
                is_manager=role_of(request) in SETUP_ROLES, notes=v.get("notes", ""),
            )
            return Response(self.get_serializer(done).data)

        return wrap_idempotent(request=request, company=self.company, scope="quality.inspection.complete", build=build)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(self.get_serializer(services.cancel_inspection(self.get_object(), request.user)).data)

    @action(detail=True, methods=["get"])
    def certificate(self, request, pk=None):
        """Certificate of analysis: a print-ready page for a finished inspection."""
        insp = self.get_object()
        if insp.status != Inspection.Status.COMPLETED or insp.decision != "PASS":
            raise services.rule("A certificate is issued for a passed inspection.", "QC_NO_CERTIFICATE")
        return HttpResponse(_certificate_html(insp), content_type="text/html; charset=utf-8")


def _certificate_html(insp: Inspection) -> str:
    company = insp.company
    rows = []
    for r in insp.results.all():
        if r.kind == "NUMERIC":
            spec = " to ".join(
                x for x in (None if r.min_value is None else f"{r.min_value.normalize():f}",
                            None if r.max_value is None else f"{r.max_value.normalize():f}") if x
            ) or "-"
            result = "" if r.value_numeric is None else f"{r.value_numeric.normalize():f}"
        else:
            spec, result = ("Pass" if r.kind == "PASS_FAIL" else "-"), r.value_text
        verdict = {True: "Pass", False: "Fail", None: "-"}[r.passed]
        rows.append(
            f"<tr><td>{escape(r.name)}</td><td>{escape(spec)} {escape(r.unit)}</td>"
            f"<td>{escape(result)} {escape(r.unit)}</td><td>{verdict}</td></tr>"
        )
    batch = insp.batch
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Certificate of Analysis {escape(insp.number)}</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;margin:32px;color:#111}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:24px 0 8px}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #999;padding:6px 8px;text-align:left;font-size:13px}}
th{{background:#eee}} .meta td{{border:0;padding:2px 8px 2px 0}} .sign{{margin-top:56px;display:flex;justify-content:space-between}}
@media print{{body{{margin:12mm}}}}
</style></head><body>
<h1>{escape(company.name)}</h1>
<div>Certificate of Analysis</div>
<h2>{escape(insp.product.name)}</h2>
<table class="meta">
<tr><td>Inspection</td><td>{escape(insp.number)}</td><td>Date</td><td>{insp.inspected_on or ""}</td></tr>
<tr><td>Batch</td><td>{escape(batch.batch_no) if batch else "-"}</td><td>Quantity</td><td>{insp.qty_inspected.normalize():f}</td></tr>
<tr><td>Made on</td><td>{(batch.manufacturing_date if batch else "") or "-"}</td><td>Expiry</td><td>{(batch.expiry_date if batch else "") or "-"}</td></tr>
</table>
<h2>Results</h2>
<table><tr><th>Test</th><th>Specification</th><th>Result</th><th></th></tr>{"".join(rows)}</table>
<p>Decision: <strong>{insp.get_decision_display()}</strong>. {escape(insp.notes)}</p>
<div class="sign"><div>Tested by ______________</div><div>Approved by ______________</div></div>
</body></html>"""


class NonConformanceViewSet(_QualityMixin, CompanyScopedViewSet):
    queryset = NonConformance.objects.select_related("product", "defect_code")
    serializer_class = NonConformanceSerializer
    audit_entity = "NonConformance"
    quality_roles = {"destroy": SETUP_ROLES}

    def get_queryset(self):
        qs = super().get_queryset()
        for key in ("status", "supplier", "product", "batch"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs

    def perform_create(self, serializer):
        company = self.company
        source = NonConformance.Source.COMPLAINT if serializer.validated_data.get("complaint") else NonConformance.Source.INTERNAL
        instance = serializer.save(
            company=company, created_by=self.request.user, updated_by=self.request.user,
            number=next_number(company, "quality_ncr", prefix="NCR"), source_type=source,
        )
        self._audit("CREATE", instance)

    @action(detail=True, methods=["post"])
    def advance(self, request, pk=None):
        ncr = self.get_object()
        fields = {k: request.data[k] for k in ("root_cause", "action_taken", "preventive_action", "description") if k in request.data}
        if "due_date" in request.data:
            fields["due_date"] = request.data["due_date"] or None
        ncr = services.advance_ncr(ncr, request.user, status=request.data.get("status"), **fields)
        return Response(self.get_serializer(ncr).data)


class ScorecardView(_QualityMixin, APIView):
    quality_roles = {}

    def get(self, request):
        company = get_company_user(request).company
        rows = services.supplier_scorecard(
            company, request.query_params.get("from") or None, request.query_params.get("to") or None,
        )
        return Response({"suppliers": rows})


class BatchStatusView(_QualityMixin, APIView):
    """Hold or release a lot by hand. A manager's decision, always with a reason."""

    quality_roles = {}

    def post(self, request, pk):
        if role_of(request) not in SETUP_ROLES:
            return Response({"detail": "Only a manager can change a batch's quality status."}, status=403)
        company = get_company_user(request).company
        batch = BatchLot.objects.filter(pk=pk, company=company).first()
        if batch is None:
            raise services.rule("Batch not found.", "QC_BAD_REFERENCE")
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise services.rule("Say why the batch status is changing.", "QC_REASON_REQUIRED")
        services.set_batch_status(batch, request.data.get("status"), request.user, reason)
        return Response({"id": batch.pk, "batch_no": batch.batch_no, "quality_status": batch.quality_status})
