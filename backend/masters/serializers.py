from decimal import Decimal

from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField

from .models import (
    Brand, Category, Customer, CustomerShippingAddress, ExpenseCategory, PaymentMode, PriceList, PriceListItem, Product, Supplier, TaxRate, Unit,
)


def reject_unsafe_party_name(name: str) -> None:
    text = (name or "").strip()
    # Letters and digits from any script. A Latin-only check rejected names the
    # customer form already accepts (accents, other Indic scripts).
    if "<" in text or ">" in text or not any(ch.isalnum() for ch in text):
        raise serializers.ValidationError({"name": "Enter a name with a letter or number."})


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


class CustomerShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerShippingAddress
        fields = ["id", "label", "address", "is_default"]
        read_only_fields = ["id"]


class CustomerSerializer(serializers.ModelSerializer):
    price_list = CompanyPrimaryKeyRelatedField(
        queryset=PriceList.objects.all(), allow_null=True, required=False
    )
    outstanding = serializers.SerializerMethodField()
    credit_exposure = serializers.SerializerMethodField()
    shipping_addresses = CustomerShippingAddressSerializer(many=True, required=False)

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        lat = attrs["latitude"] if "latitude" in attrs else getattr(instance, "latitude", None)
        lon = attrs["longitude"] if "longitude" in attrs else getattr(instance, "longitude", None)
        if (lat is None) != (lon is None):
            raise serializers.ValidationError(
                "Latitude and longitude must both be set, or both left blank."
            )
        if lat is not None and not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
            raise serializers.ValidationError("Latitude or longitude is out of range.")
        from planwave.services import PLAIN_TEXT_FIELDS
        import re

        # Check the name as typed, before any tag stripping: stripping first turns
        # "<script>x</script>" into the harmless-looking "x" and the check never fires.
        if "name" in attrs and attrs["name"] != getattr(instance, "name", None):
            # A legacy row may be re-saved with its stored name; only a changed name is checked.
            reject_unsafe_party_name(attrs.get("name") or "")
        for key in PLAIN_TEXT_FIELDS:
            if key in attrs and isinstance(attrs[key], str):
                attrs[key] = re.sub(r"</?[A-Za-z][^>]*>|<!--.*?-->", "", attrs[key], flags=re.S)
        if "pincode" in attrs:
            from django.core.exceptions import ValidationError as DjangoValidationError

            from core.validators import assign_pincode

            try:
                assign_pincode(attrs, instance)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"pincode": list(exc.messages)}) from exc
        return attrs

    def validate_custom_fields(self, value):
        from core.permissions import get_company_user
        from masters.custom_fields import coerce_values, omit_empty, party_defs_for_company

        request = self.context.get("request")
        if not request:
            return omit_empty(value)
        membership = get_company_user(request)
        if membership is None:
            return omit_empty(value)
        existing = getattr(self.instance, "custom_fields", None) if self.instance else {}
        return coerce_values(value, party_defs_for_company(membership.company), existing)

    def validate_party_bank_account(self, value):
        # A masked echo ("****1234") sent back by a role that only sees the last digits must not
        # overwrite the real number.
        if value and value.startswith("*") and self.instance is not None:
            return self.instance.party_bank_account
        return value

    def to_representation(self, instance):
        from masters.custom_fields import party_defs_for_company, surface_values
        from planwave.crypto import reveal_bank_account

        data = super().to_representation(instance)
        # Definitions belong to the company, so read them once per serializer, not per row.
        cache = self.__dict__.setdefault("_party_defs_cache", {})
        defs = cache.get(instance.company_id)
        if defs is None:
            defs = cache[instance.company_id] = party_defs_for_company(instance.company)
        data["custom_fields"] = surface_values(getattr(instance, "custom_fields", None), defs)
        number = reveal_bank_account(data.get("party_bank_account") or "")
        request = self.context.get("request")
        role = ""
        if request is not None and getattr(request, "user", None) is not None and request.user.is_authenticated:
            from core.permissions import get_company_user

            member = get_company_user(request)
            role = getattr(member, "role", "") or ""
        # The full number only for the roles that handle bank details; others see the last digits.
        data["party_bank_account"] = number if (not request or role in ("OWNER", "ACCOUNTANT")) else (
            ("*" * max(len(number) - 4, 0) + number[-4:]) if number else ""
        )
        return data

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "email", "gstin", "billing_address",
            "shipping_address", "state", "pincode", "latitude", "longitude", "status", "credit_limit",
            "credit_days", "is_pos_walk_in", "notes", "created_at", "updated_at",
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "price_list", "taxpayer_type", "whatsapp_opt_in", "dunning_opt_out",
            "custom_fields", "pan", "party_bank_name", "party_bank_account", "party_bank_ifsc",
            "shipping_addresses",
            "outstanding",
            "credit_exposure",
            "version",
        ]
        read_only_fields = [
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "version",
            "is_pos_walk_in",
        ]

    def get_outstanding(self, obj):
        from ledgers.services import LedgerService

        outstanding_by_id = self.context.get("outstanding_by_id")
        if outstanding_by_id is not None:
            return str(outstanding_by_id.get(obj.id, 0))
        return str(LedgerService.customer_outstanding(obj.company, obj))

    def get_credit_exposure(self, obj):
        """Limit check figure: outstanding minus unallocated advances (and the GL cross-check).

        The customer list keeps the bulk outstanding map and does not run this per row.
        The invoice loads the customer detail, which is this figure.
        """
        from ledgers.services import LedgerService

        by_id = self.context.get("credit_exposure_by_id")
        if by_id is not None:
            return str(by_id.get(obj.id, 0))
        if self.context.get("outstanding_by_id") is not None:
            return self.get_outstanding(obj)
        return str(LedgerService.customer_exposure_for_credit_limit(obj.company, obj))

    def create(self, validated_data):
        addresses = validated_data.pop("shipping_addresses", None) or []
        customer = super().create(validated_data)
        self._replace_addresses(customer, addresses)
        return customer

    def update(self, instance, validated_data):
        addresses = validated_data.pop("shipping_addresses", None)
        customer = super().update(instance, validated_data)
        if addresses is not None:
            self._replace_addresses(customer, addresses)
        return customer

    def _replace_addresses(self, customer, addresses):
        customer.shipping_addresses.all().delete()
        for row in addresses:
            CustomerShippingAddress.objects.create(
                company=customer.company,
                customer=customer,
                label=row.get("label") or "",
                address=row.get("address") or "",
                is_default=bool(row.get("is_default")),
                created_by=customer.updated_by,
                updated_by=customer.updated_by,
            )


class SupplierSerializer(serializers.ModelSerializer):
    outstanding = serializers.SerializerMethodField()

    def validate(self, attrs):
        if "name" in attrs and attrs["name"] != getattr(self.instance, "name", None):
            reject_unsafe_party_name(attrs.get("name") or "")
        return attrs

    class Meta:
        model = Supplier
        fields = [
            "id", "name", "phone", "email", "gstin", "address", "state", "country",
            "is_active", "notes", "created_at", "updated_at",
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "taxpayer_type", "outstanding",
        ]
        read_only_fields = [
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
        ]

    def get_outstanding(self, obj):
        from ledgers.services import LedgerService

        outstanding_by_id = self.context.get("outstanding_by_id")
        if outstanding_by_id is not None:
            return str(outstanding_by_id.get(obj.id, 0))
        return str(LedgerService.supplier_outstanding(obj.company, obj))


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    unit_name = serializers.CharField(source="unit.short_name", read_only=True)
    alternate_unit_name = serializers.CharField(source="alternate_unit.short_name", read_only=True)
    has_movements = serializers.BooleanField(read_only=True)
    # Set only on the response to a save that touched the GST rate; blank on reads.
    gst_rate_notice = serializers.SerializerMethodField()

    def get_gst_rate_notice(self, obj) -> str:
        return getattr(self, "_hsn_notice", "") or ""

    def _may_see_cost(self) -> bool:
        request = self.context.get("request")
        if request is None:
            return True  # internal callers (imports, services) have no request
        from core.permissions import can_see_product_cost

        return can_see_product_cost(request)

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "barcode", "hsn_code", "description",
            "category", "category_name", "brand", "brand_name", "unit", "unit_name",
            "gst_rate", "gst_supply_form", "gst_rate_notice", "cess_rate", "cess_amount",
            "purchase_price", "selling_price", "mrp", "wholesale_price",
            "reorder_level", "product_type", "track_inventory",
            "track_batch", "track_serial", "regulated_category",
            "selling_tax_inclusive", "purchase_tax_inclusive",
            "custom_fields", "alternate_unit", "alternate_unit_name", "conversion_rate",
            "default_discount_percent", "has_movements", "status", "created_at", "updated_at",
            "salt", "composition", "manufacturer", "drug_schedule", "rack_code",
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
        if not self._may_see_cost():
            # A masked client echoes null. It must not overwrite the real cost, and a
            # new item made by someone who cannot see cost starts at zero.
            if self.instance is not None:
                attrs.pop("purchase_price", None)
            else:
                attrs["purchase_price"] = 0
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
        # The alternate unit's conversion_rate is only meaningful relative to
        # the base unit it was set up against ("1 CARTON = 48 PCS"). A base
        # unit change (only reachable once stock is zero -- see
        # assert_tracking_unlocked) always invalidates that pairing, so clear
        # it rather than silently reinterpreting a stale ratio under the new
        # base unit. The caller can re-pair alternate unit + rate in a
        # follow-up save once they know what it should mean under the new unit.
        if self.instance is not None and attrs.get("unit") and attrs["unit"] != self.instance.unit:
            attrs["alternate_unit"] = None
            attrs["conversion_rate"] = Decimal("1")
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
        self._align_saved_gst_rate(attrs)
        return attrs

    def _align_saved_gst_rate(self, attrs):
        from datetime import date

        from masters.hsn_catalog import line_gst_decision

        hsn = attrs.get("hsn_code", getattr(self.instance, "hsn_code", "") if self.instance else "")
        entered = attrs.get("gst_rate", getattr(self.instance, "gst_rate", 0) if self.instance else 0)
        form = attrs.get(
            "gst_supply_form",
            getattr(self.instance, "gst_supply_form", "") if self.instance else "",
        )
        price = attrs.get(
            "selling_price",
            getattr(self.instance, "selling_price", None) if self.instance else None,
        )
        decision = line_gst_decision(hsn, entered, form or "", date.today(), price)
        self._hsn_notice = decision.get("notice") or ""
        if decision.get("apply") and decision["rate"] != Decimal(str(entered or 0)):
            attrs["gst_rate"] = decision["rate"]

    def create(self, validated_data):
        product = super().create(validated_data)
        self._audit_hsn_change(product)
        return product

    def update(self, instance, validated_data):
        product = super().update(instance, validated_data)
        self._audit_hsn_change(product)
        return product

    def _audit_hsn_change(self, product):
        notice = getattr(self, "_hsn_notice", "") or ""
        if not notice.startswith("rate changed"):
            return
        request = self.context.get("request")
        if request is None:
            return
        from core.permissions import get_company_user
        from core.services.audit import AuditService

        membership = get_company_user(request)
        AuditService.log(
            company=membership.company,
            user=request.user,
            action="UPDATE",
            entity_type="Product",
            entity_id=product.id,
            description=notice,
        )

    def validate_gst_supply_form(self, value):
        value = (value or "").strip().upper()
        if value not in ("", "UNBRANDED", "BRANDED_PREPACKED"):
            raise serializers.ValidationError(
                "Choose unbranded, branded / pre-packed, or leave it blank."
            )
        return value

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
        request = self.context.get("request")
        if request is None:
            return data
        from core.permissions import get_company_user
        from planwave.services import mask_commercial

        role = getattr(get_company_user(request), "role", "")
        # The permission rule (can_see_product_cost) was a second to_representation that this
        # one replaced, so it never ran. Apply it here, through the same mask so below_cost is
        # still worked out before the cost is dropped. A role that may see money still loses
        # cost when the user has none of the cost permissions.
        mask_role = role if self._may_see_cost() else ""
        return mask_commercial(data, mask_role)


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
