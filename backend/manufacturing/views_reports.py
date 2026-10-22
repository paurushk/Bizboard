"""Reports and standard costs (MFG-09, 29, 30, 31, 32, X2)."""

import csv
import io
from datetime import date

from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.csv_utils import csv_safe
from core.permissions import HasCompany, get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from core.viewsets import CompanyScopedViewSet
from masters.models import Product

from .models import StandardCost
from .permissions import (
    BadInputIs400,
    CLOSE_ROLES, COST_ROLES, MfgRolePermission, assert_manufacturing_enabled, assert_sub_flag, role_of,
)
from .services import reports
from .services.common import rule

# report slug -> (function, needs cost access, extra kwargs from query)
REPORTS = {
    "wip": (reports.wip_report, True),
    "work-order-cost": (reports.work_order_cost_report, True),
    "variance": (reports.variance_report, True),
    "yield-wastage": (reports.yield_wastage_report, False),
    "consumption": (reports.consumption_report, False),
    "output": (reports.output_report, False),
    "on-time": (reports.on_time_report, False),
    "scrap-register": (reports.scrap_register, True),
    "profitability": (reports.profitability, True),
    "reconciliation": (reports.reconciliation, True),
}


def _d(value):
    return date.fromisoformat(value[:10]) if value else None


def _rows_for_csv(data):
    """The first list of records in a report, flattened for a spreadsheet."""
    for key in ("orders", "items", "rows"):
        rows = data.get(key)
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows
    flat = []
    for section, value in data.items():
        if isinstance(value, dict):
            for k, v in value.items():
                flat.append({"section": section, "name": k, "value": v})
    return flat


class ReportView(BadInputIs400, APIView):
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)

    def get(self, request, slug):
        entry = REPORTS.get(slug)
        if entry is None:
            raise rule("There is no such report.", "MFG_NO_SUCH_REPORT")
        fn, needs_cost = entry
        if needs_cost and role_of(request) not in COST_ROLES:
            raise PermissionDenied("Your role cannot see costs.", code="MFG_NO_COST_ACCESS")
        company = get_company_user(request).company
        q = request.query_params
        if slug == "wip":
            data = fn(company, _d(q.get("as_of")))
        elif slug == "reconciliation":
            data = fn(company, _d(q.get("as_of")))
        elif slug == "profitability":
            data = fn(company, _d(q.get("from")), _d(q.get("to")), by=q.get("by", "product"))
        elif slug == "on-time":
            data = fn(company, _d(q.get("from")), _d(q.get("to")))
        else:
            data = fn(company, _d(q.get("from")), _d(q.get("to")))
        if q.get("export") == "csv":
            rows = _rows_for_csv(data)
            out = io.StringIO()
            if rows:
                w = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows([{k: csv_safe(v) for k, v in r.items()} for r in rows])
            resp = HttpResponse(out.getvalue(), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
            return resp
        return Response(data)


class StandardCostSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)

    class Meta:
        model = StandardCost
        fields = ["id", "product", "product_name", "effective_from", "material", "labour", "overhead", "unit_cost", "notes"]

    def validate(self, attrs):
        request = self.context.get("request")
        cu = get_company_user(request) if request else None
        product = attrs.get("product", getattr(self.instance, "product", None))
        start = attrs.get("effective_from", getattr(self.instance, "effective_from", None))
        if cu is not None and product is not None and start is not None:
            clash = StandardCost.objects.filter(company=cu.company, product=product, effective_from=start)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("This item already has a standard cost from that date.")
        for key in ("material", "labour", "overhead"):
            if attrs.get(key) is not None and attrs[key] < 0:
                raise serializers.ValidationError({key: "A cost cannot be negative."})
        return attrs


class StandardCostViewSet(BadInputIs400, CompanyScopedViewSet):
    queryset = StandardCost.objects.select_related("product")
    serializer_class = StandardCostSerializer
    audit_entity = "StandardCost"
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {a: CLOSE_ROLES for a in ("create", "update", "partial_update", "destroy")} | {
        "list": COST_ROLES, "retrieve": COST_ROLES,
    }

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        company = get_company_user(request).company
        assert_manufacturing_enabled(company)
        assert_sub_flag(company, "MFG_COSTING_GL")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("product"):
            qs = qs.filter(product_id=self.request.query_params["product"])
        return qs
