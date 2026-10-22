"""Standard-cost revaluation runs (QOS-0146): preview, post, reverse."""

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.idempotency import wrap_idempotent
from core.permissions import HasCompany, get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Product

from .models import StandardRevaluation, StandardRevaluationLine
from .permissions import (
    BadInputIs400,
    CLOSE_ROLES, COST_ROLES, REVERSE_ROLES, MfgRolePermission, assert_manufacturing_enabled, assert_sub_flag,
    can_backdate,
)
from .serializers_docs import ReasonIn
from .services import revaluation


class RevaluationLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default=None)
    change = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = StandardRevaluationLine
        fields = [
            "id", "product", "product_name", "warehouse", "warehouse_name", "batch", "batch_no", "qty",
            "old_unit_cost", "new_unit_cost", "old_value", "new_value", "change",
        ]
        read_only_fields = fields


class RevaluationSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)
    total_change = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    lines = RevaluationLineSerializer(many=True, read_only=True)

    class Meta:
        model = StandardRevaluation
        fields = [
            "id", "number", "status", "as_of", "product", "product_name", "notes", "total_before", "total_after",
            "total_change", "lines", "posted_at", "reversed_at", "reverse_reason", "created_at",
        ]
        read_only_fields = fields


class RevaluationIn(serializers.Serializer):
    as_of = serializers.DateField(required=False)
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class StandardRevaluationViewSet(BadInputIs400, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = RevaluationSerializer
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {
        "list": COST_ROLES, "retrieve": COST_ROLES, "create": CLOSE_ROLES, "post": CLOSE_ROLES,
        "reverse": REVERSE_ROLES, "discard": CLOSE_ROLES,
    }

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        company = get_company_user(request).company
        assert_manufacturing_enabled(company)
        assert_sub_flag(company, "MFG_COSTING_GL")

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        qs = StandardRevaluation.objects.filter(company=self.company).select_related("product").prefetch_related(
            "lines__product", "lines__warehouse", "lines__batch",
        )
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs.order_by("-id")

    def create(self, request, *args, **kwargs):
        """Preview: nothing moves. The run lists every lot that would change and by how much."""
        data = RevaluationIn(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        v = data.validated_data
        run = revaluation.preview(
            self.company, request.user, as_of=v.get("as_of"), product=v.get("product"), notes=v.get("notes", ""),
        )
        return Response(self.get_serializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        run = self.get_object()

        def build():
            done = revaluation.post(run, request.user, can_backdate=can_backdate(request))
            return Response(self.get_serializer(done).data)

        return wrap_idempotent(request=request, company=self.company, scope="mfg.revaluation.post", build=build)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        run = self.get_object()
        reason = ReasonIn(data=request.data)
        reason.is_valid(raise_exception=True)

        def build():
            done = revaluation.reverse(
                run, request.user, reason.validated_data["reason"], can_backdate=can_backdate(request),
            )
            return Response(self.get_serializer(done).data)

        return wrap_idempotent(request=request, company=self.company, scope="mfg.revaluation.reverse", build=build)

    @action(detail=True, methods=["delete"], url_path="discard")
    def discard(self, request, pk=None):
        run = self.get_object()
        if run.status != "DRAFT":
            from .services.common import rule

            raise rule("Only a preview can be discarded. Reverse a posted run instead.", "MFG_DOC_NOT_DRAFT")
        run.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
