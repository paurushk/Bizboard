from django.utils import timezone
from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer, Product

from .models import Contract, ContractProduct, ContractServiceEvent
from .status import effective_contract_status


class ContractSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all())
    product = CompanyPrimaryKeyRelatedField(
        queryset=Product.objects.all(), allow_null=True, required=False
    )
    products = serializers.ListField(child=serializers.IntegerField(), required=False)

    class Meta:
        model = Contract
        fields = [
            "id", "number", "customer", "product", "products", "contract_type", "start_date", "end_date",
            "renewal_reminder_days", "value", "recurring_schedule", "status", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["number", "recurring_schedule", "created_at", "updated_at"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot be before the start date."})
        product_ids = attrs.get("products")
        request = self.context.get("request")
        company = None
        if request is not None:
            from core.permissions import get_company_user

            membership = get_company_user(request)
            company = membership.company if membership is not None else None
        if company is None and self.instance is not None:
            company = self.instance.company
        if product_ids is not None and company is not None:
            found = set(Product.objects.filter(company=company, pk__in=product_ids).values_list("pk", flat=True))
            missing = [pid for pid in product_ids if pid not in found]
            if missing:
                raise serializers.ValidationError({"products": "Every product must belong to this company."})
        if "serial" in self.initial_data:
            raise serializers.ValidationError({"serial": "A contract does not cover a serial."})
        return attrs

    def create(self, validated_data):
        product_ids = validated_data.pop("products", None)
        instance = super().create(validated_data)
        self._sync_products(instance, product_ids)
        return instance

    def update(self, instance, validated_data):
        product_ids = validated_data.pop("products", None)
        instance = super().update(instance, validated_data)
        if product_ids is not None or "product" in self.initial_data:
            self._sync_products(instance, product_ids)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["products"] = list(instance.covered_products.order_by("id").values_list("product_id", flat=True))
        data["status"] = effective_contract_status(
            instance.status, instance.end_date, instance.renewal_reminder_days, timezone.localdate(),
        )
        return data

    def _sync_products(self, instance, product_ids):
        if product_ids is None:
            product_ids = [instance.product_id] if instance.product_id else []
        else:
            seen = []
            for pid in product_ids:
                if pid not in seen:
                    seen.append(pid)
            product_ids = seen
            instance.product_id = product_ids[0] if product_ids else None
            instance.save(update_fields=["product", "updated_at"])
        instance.covered_products.exclude(product_id__in=product_ids).delete()
        for pid in product_ids:
            ContractProduct.objects.get_or_create(
                company=instance.company,
                contract=instance,
                product_id=pid,
            )

    def validate_status(self, value):
        if self.instance is None:
            return value
        if value == Contract.Status.CANCELLED:
            return value
        if self.instance.status == Contract.Status.CANCELLED and value == Contract.Status.ACTIVE:
            return value
        if value == self.instance.status:
            return value
        raise serializers.ValidationError("Status is maintained by the system. You can cancel or un-cancel.")


class ContractServiceEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractServiceEvent
        fields = ["id", "contract", "ticket", "occurred_at", "notes", "created_at"]
        read_only_fields = ["id", "contract", "created_at"]
