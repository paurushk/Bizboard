from decimal import Decimal

from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField

from .models import (
    Brand, Category, Customer, ExpenseCategory, PaymentMode, PriceList, PriceListItem, Product, Supplier, TaxRate, Unit,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name", "short_name", "uqc_code"]

    def validate(self, attrs):
        from core.services.uqc import normalize_uqc

        name = attrs.get("name") or getattr(self.instance, "name", "") or ""
        short = attrs.get("short_name") or getattr(self.instance, "short_name", "") or ""
        explicit = attrs.get("uqc_code")
        if explicit is None and self.instance is not None:
            explicit = self.instance.uqc_code
        code = normalize_uqc(explicit) or normalize_uqc(short) or normalize_uqc(name)
        attrs["uqc_code"] = code or (explicit or "")
        return attrs


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = ["id", "name", "rate"]


class PaymentModeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMode
        fields = ["id", "name", "code", "is_active"]


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "code", "description", "is_active"]


class CustomerSerializer(serializers.ModelSerializer):
    price_list = CompanyPrimaryKeyRelatedField(
        queryset=PriceList.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "email", "gstin", "billing_address",
            "shipping_address", "state", "status", "credit_limit",
            "credit_days", "notes", "created_at", "updated_at",
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "price_list", "taxpayer_type", "whatsapp_opt_in", "dunning_opt_out",
        ]
        read_only_fields = [
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
        ]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id", "name", "phone", "email", "gstin", "address", "state",
            "is_active", "notes", "created_at", "updated_at",
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "taxpayer_type",
        ]
        read_only_fields = [
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
        ]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    unit_name = serializers.CharField(source="unit.short_name", read_only=True)
    alternate_unit_name = serializers.CharField(source="alternate_unit.short_name", read_only=True)
    has_movements = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "barcode", "hsn_code", "description",
            "category", "category_name", "brand", "brand_name", "unit", "unit_name",
            "gst_rate", "purchase_price", "selling_price", "mrp", "wholesale_price",
            "reorder_level", "product_type", "track_inventory",
            "track_batch", "track_serial", "selling_tax_inclusive", "purchase_tax_inclusive",
            "custom_fields", "alternate_unit", "alternate_unit_name", "conversion_rate",
            "default_discount_percent", "has_movements", "status", "created_at", "updated_at",
        ]

    def _check_company(self, attrs):
        request = self.context.get("request")
        if not request:
            return
        from core.permissions import get_company_user

        company = get_company_user(request).company
        for field in ("category", "brand", "unit", "alternate_unit"):
            obj = attrs.get(field)
            if obj is not None and obj.company_id != company.id:
                raise serializers.ValidationError({field: "Invalid reference."})

    def validate(self, attrs):
        self._check_company(attrs)
        request = self.context.get("request")
        if not request:
            return attrs
        from core.exceptions import BusinessRuleError
        from core.permissions import get_company_user
        from inventory.item_stock import apply_product_type_matrix, assert_tracking_unlocked

        company = get_company_user(request).company
        raw = self.initial_data.get("unit_name") or self.initial_data.get("unitName")
        if attrs.get("unit") is None and (self.instance is None or raw):
            short = str(raw or "PCS").strip().upper() or "PCS"
            unit = Unit.objects.filter(company=company, short_name__iexact=short).first()
            if unit is None:
                unit = Unit.objects.create(
                    company=company, short_name=short, name=short, uqc_code=short[:8],
                )
            attrs["unit"] = unit
        alt_raw = self.initial_data.get("alternate_unit_name") or self.initial_data.get("alternateUnitName")
        if alt_raw and not attrs.get("alternate_unit"):
            alt_short = str(alt_raw).strip().upper()
            if alt_short:
                alt = Unit.objects.filter(company=company, short_name__iexact=alt_short).first()
                if alt is None:
                    alt = Unit.objects.create(
                        company=company, short_name=alt_short, name=alt_short, uqc_code=alt_short[:8],
                    )
                attrs["alternate_unit"] = alt
        try:
            assert_tracking_unlocked(self.instance, attrs)
            attrs = apply_product_type_matrix(attrs, self.instance)
        except BusinessRuleError as exc:
            raise serializers.ValidationError(exc.detail)
        rate = attrs.get("conversion_rate", getattr(self.instance, "conversion_rate", None))
        if rate is not None and Decimal(str(rate)) <= 0:
            raise serializers.ValidationError({"conversion_rate": "Must be greater than zero."})
        current_unit = attrs.get("unit", getattr(self.instance, "unit", None))
        if attrs.get("alternate_unit") and attrs.get("alternate_unit") == current_unit:
            raise serializers.ValidationError({"alternate_unit": "Alternate unit must differ from the base unit."})
        if self.instance is None:
            sku_raw = attrs.get("sku", self.initial_data.get("sku") or "")
            if not str(sku_raw).strip():
                raise serializers.ValidationError({"sku": "Item code is required."})
        cat_raw = self.initial_data.get("category_name") or self.initial_data.get("categoryName")
        if cat_raw and not attrs.get("category"):
            cat_name = str(cat_raw).strip()
            if cat_name:
                cat = Category.objects.filter(company=company, name__iexact=cat_name).first()
                if cat is None:
                    cat = Category.objects.create(company=company, name=cat_name)
                attrs["category"] = cat
        brand_raw = self.initial_data.get("brand_name") or self.initial_data.get("brandName")
        if brand_raw and not attrs.get("brand"):
            brand_name = str(brand_raw).strip()
            if brand_name:
                brand = Brand.objects.filter(company=company, name__iexact=brand_name).first()
                if brand is None:
                    brand = Brand.objects.create(company=company, name=brand_name)
                attrs["brand"] = brand
        return attrs

    def validate_sku(self, value):
        sku = (value or "").strip()
        if not sku:
            raise serializers.ValidationError("Item code is required.")
        return sku

    def validate_custom_fields(self, value):
        from core.permissions import get_company_user
        from masters.custom_fields import coerce_values, defs_for_company, omit_empty

        request = self.context.get("request")
        if not request:
            return omit_empty(value)
        company = get_company_user(request).company
        existing = getattr(self.instance, "custom_fields", None) if self.instance else {}
        return coerce_values(value, defs_for_company(company), existing)

    def _active_custom_field_defs(self):
        cached = getattr(self, "_cached_cf_defs", None)
        if cached is not None:
            return cached
        request = self.context.get("request")
        defs = None
        if request:
            from core.permissions import get_company_user
            from masters.custom_fields import defs_for_company

            try:
                defs = defs_for_company(get_company_user(request).company)
            except Exception:
                defs = []
        self._cached_cf_defs = defs
        return defs

    def to_representation(self, instance):
        from masters.custom_fields import surface_values

        data = super().to_representation(instance)
        data["custom_fields"] = surface_values(getattr(instance, "custom_fields", None), self._active_custom_field_defs())
        return data


class PriceListItemSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = PriceListItem
        fields = ["id", "product", "unit_price", "min_qty", "max_qty", "discount_pct"]

    def validate(self, attrs):
        from core.exceptions import BusinessRuleError
        from masters.pricing import assert_slab_bounds, ranges_overlap

        min_q = attrs.get("min_qty", getattr(self.instance, "min_qty", 1) if self.instance else 1)
        max_q = attrs.get("max_qty", getattr(self.instance, "max_qty", None) if self.instance else None)
        try:
            assert_slab_bounds(min_q, max_q)
        except BusinessRuleError as exc:
            raise serializers.ValidationError(exc.detail) from exc
        product = attrs.get("product") or getattr(self.instance, "product", None)
        price_list = None
        if self.instance is not None:
            price_list = self.instance.price_list
        elif self.parent is not None and getattr(self.parent, "instance", None) is not None:
            price_list = self.parent.instance
        if product is not None and price_list is not None:
            siblings = PriceListItem.objects.filter(price_list=price_list, product=product)
            if self.instance is not None:
                siblings = siblings.exclude(pk=self.instance.pk)
            for other in siblings:
                if ranges_overlap(min_q, max_q, other.min_qty, other.max_qty):
                    raise serializers.ValidationError(
                        "Quantity slabs for this product overlap on the same price list."
                    )
        return attrs


class PriceListSerializer(serializers.ModelSerializer):
    items = PriceListItemSerializer(many=True, required=False)

    class Meta:
        model = PriceList
        fields = ["id", "name", "is_active", "items", "created_at", "updated_at"]

    def validate(self, attrs):
        items = attrs.get("items")
        if items is not None:
            from core.exceptions import BusinessRuleError
            from masters.pricing import assert_slab_payloads

            try:
                assert_slab_payloads(items)
            except BusinessRuleError as exc:
                raise serializers.ValidationError({"items": exc.detail})
        return attrs

    def create(self, validated_data):
        from django.db import transaction

        items = validated_data.pop("items", [])
        # B8-002: validate() above already runs assert_slab_payloads on the
        # whole items list before this is ever called, but a DB-level
        # IntegrityError from uniq_product_slab_per_list (a case that check
        # doesn't catch, or a race) mid-bulk_create should not leave a
        # PriceList with a partial item set — wrap the writes.
        with transaction.atomic():
            price_list = super().create(validated_data)
            PriceListItem.objects.bulk_create([
                PriceListItem(company=price_list.company, price_list=price_list, **item)
                for item in items
            ])
        return price_list

    def update(self, instance, validated_data):
        from django.db import transaction

        items = validated_data.pop("items", None)
        # B8-002: same reasoning as create() — an IntegrityError from
        # bulk_create after delete() previously left the list empty with no
        # rollback (ATOMIC_REQUESTS is off).
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if items is not None:
                PriceListItem.objects.filter(price_list=instance).delete()
                PriceListItem.objects.bulk_create([
                    PriceListItem(company=instance.company, price_list=instance, **item)
                    for item in items
                ])
        return instance
