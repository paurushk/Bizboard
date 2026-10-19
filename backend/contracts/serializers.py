from django.utils import timezone
from rest_framework import serializers

from core.exceptions import ConflictError
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer, Product

from .models import Contract, ContractProduct, ContractRenewal, ContractServiceEvent
from .ops import find_overlaps
from .status import effective_contract_status


def _covered(instance):
    """Covered products in id order, from the prefetch when there is one."""
    rows = sorted(instance.covered_products.all(), key=lambda row: row.id)
    return rows


class ContractSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all())
    product = CompanyPrimaryKeyRelatedField(
        queryset=Product.objects.all(), allow_null=True, required=False
    )
    products = serializers.ListField(child=serializers.IntegerField(), required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id", "number", "customer", "customer_name", "product", "products", "contract_type",
            "start_date", "end_date", "renewal_reminder_days", "value", "recurring_schedule", "status",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["number", "recurring_schedule", "created_at", "updated_at"]

    def _company(self):
        request = self.context.get("request")
        if request is not None:
            from core.permissions import get_company_user

            membership = get_company_user(request)
            if membership is not None:
                return membership.company
        return self.instance.company if self.instance is not None else None

    def validate_value(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Value cannot be negative.")
        return value

    def validate_renewal_reminder_days(self, value):
        if value is not None and not 0 <= value <= 365:
            raise serializers.ValidationError("Reminder days must be between 0 and 365.")
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance is not None and instance.status == Contract.Status.CANCELLED:
            changed = [name for name in attrs if name != "status"]
            if changed:
                raise serializers.ValidationError("A cancelled contract cannot be edited. Un-cancel it first.")
        start = attrs.get("start_date", getattr(instance, "start_date", None))
        end = attrs.get("end_date", getattr(instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot be before the start date."})
        product_ids = attrs.get("products")
        company = self._company()
        if product_ids is not None and company is not None:
            found = set(Product.objects.filter(company=company, pk__in=product_ids).values_list("pk", flat=True))
            missing = [pid for pid in product_ids if pid not in found]
            if missing:
                raise serializers.ValidationError({"products": "Every product must belong to this company."})
        if "serial" in self.initial_data:
            raise serializers.ValidationError({"serial": "A contract does not cover a serial."})
        self._check_overlap(attrs, company)
        return attrs

    def _check_overlap(self, attrs, company):
        request = self.context.get("request")
        if request is None or company is None:
            return
        if str(request.data.get("allow_overlap") or "").lower() in {"1", "true", "yes"}:
            return
        instance = self.instance
        keys = ("customer", "contract_type", "start_date", "end_date", "products", "product")
        if instance is not None and not any(key in attrs for key in keys):
            return
        customer = attrs.get("customer", getattr(instance, "customer", None))
        product_ids = attrs.get("products")
        if product_ids is None:
            product = attrs.get("product", getattr(instance, "product", None))
            product_ids = [product.id] if product is not None else (
                [row.product_id for row in _covered(instance)] if instance is not None else []
            )
        clashes = find_overlaps(
            company,
            customer.id if customer is not None else None,
            list(product_ids),
            attrs.get("contract_type", getattr(instance, "contract_type", None)),
            attrs.get("start_date", getattr(instance, "start_date", None)),
            attrs.get("end_date", getattr(instance, "end_date", None)),
            exclude_id=instance.pk if instance is not None else None,
        )
        numbers = [row.number or f"#{row.pk}" for row in clashes[:5]]
        if numbers:
            raise ConflictError({
                "code": "overlap",
                "message": f"This customer already has a {attrs.get('contract_type', 'contract')} covering "
                           f"the same product in these dates: {', '.join(numbers)}.",
                "overlaps": numbers,
            })

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
        today = timezone.localdate()
        rows = _covered(instance)
        data["products"] = [row.product_id for row in rows]
        data["product_names"] = [row.product.name for row in rows if getattr(row, "product", None)]
        effective = effective_contract_status(
            instance.status, instance.end_date, instance.renewal_reminder_days, today,
        )
        data["status"] = effective
        data["days_to_expiry"] = (instance.end_date - today).days if instance.end_date else None
        schedule = instance.recurring_schedule
        data["schedule"] = None if schedule is None else {
            "id": schedule.id,
            "cadence": schedule.cadence,
            "is_active": schedule.is_active,
            "paused_reason": schedule.paused_reason,
            "next_run_at": schedule.next_run_at,
        }
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
        # The prefetch cache is stale after the sync.
        if hasattr(instance, "_prefetched_objects_cache"):
            instance._prefetched_objects_cache.pop("covered_products", None)

    def validate_status(self, value):
        if self.instance is None:
            if value == Contract.Status.CANCELLED:
                raise serializers.ValidationError("A new contract cannot start cancelled.")
            return value
        if value == Contract.Status.CANCELLED:
            return value
        if self.instance.status == Contract.Status.CANCELLED and value == Contract.Status.ACTIVE:
            return value
        # A client may send back the status it was shown, which is the date-derived one.
        shown = effective_contract_status(
            self.instance.status, self.instance.end_date, self.instance.renewal_reminder_days,
            timezone.localdate(),
        )
        if value in (self.instance.status, shown):
            return self.instance.status
        raise serializers.ValidationError("Status is maintained by the system. You can cancel or un-cancel.")


class ContractServiceEventSerializer(serializers.ModelSerializer):
    ticket_number = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ContractServiceEvent
        fields = [
            "id", "contract", "ticket", "ticket_number", "occurred_at", "notes", "author_name", "created_at",
        ]
        read_only_fields = ["id", "contract", "created_at"]

    def get_ticket_number(self, obj):
        return obj.ticket.number if obj.ticket_id else ""

    def get_author_name(self, obj):
        user = obj.created_by
        return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip() if user else ""


class ContractRenewalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractRenewal
        fields = [
            "id", "previous_end_date", "new_end_date", "previous_value", "new_value", "note", "created_at",
        ]
        read_only_fields = fields
