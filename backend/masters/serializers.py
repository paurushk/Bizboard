from decimal import Decimal

from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField

from .models import (
    Brand, Category, Customer, CustomerShippingAddress, ExpenseCategory, PaymentMode, PriceList, PriceListItem, Product, Supplier, TaxRate, Unit,
)


# CUS-23: roles allowed to change credit_limit / credit_days on a customer.
CREDIT_TERM_EDITOR_ROLES = frozenset({"OWNER", "MANAGER"})
# Lifting a block or archiving a customer is the same owner/manager call (founder decision 2026-10-12).
STATUS_ESCALATION_ROLES = CREDIT_TERM_EDITOR_ROLES


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
        fields = ["id", "name", "short_name", "uqc_code", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        from core.services.uqc import normalize_uqc

        name = attrs.get("name") or getattr(self.instance, "name", "") or ""
        short = attrs.get("short_name") or getattr(self.instance, "short_name", "") or ""
        explicit = attrs.get("uqc_code")
        if explicit is None and self.instance is not None:
            explicit = self.instance.uqc_code
        # SET-09: a code typed by hand must be a real GSTN unit code. It used to be saved as given
        # whenever it could not be matched, and then failed later in a GSTR-1 file.
        if attrs.get("uqc_code") and not normalize_uqc(attrs["uqc_code"]):
            raise serializers.ValidationError(
                {"uqc_code": "Choose a GSTN unit code (for example PCS, KGS, NOS, LTR, BOX)."}
            )
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
        fields = ["id", "name", "code", "description", "is_active", "sort_order"]


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
    # Filled by CustomerViewSet.retrieve only (when the company's auto credit hold is on); absent on lists.
    collection_status = serializers.CharField(read_only=True, required=False)
    # WP-CM1: filled by CustomerViewSet.retrieve only; mail to this address bounced or was marked spam.
    email_suppressed = serializers.BooleanField(read_only=True, required=False)

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
        self._validate_gstin_and_state(attrs, instance)
        self._validate_walk_in(attrs, instance)
        self._validate_credit_terms(attrs, instance)
        self._validate_status_change(attrs, instance)
        self._validate_phone(attrs, instance)
        return attrs

    def _party_company(self, instance):
        if self.context.get("company") is not None:
            return self.context["company"]
        view = self.context.get("view")
        company = getattr(view, "company", None) if view is not None else None
        return company or getattr(instance, "company", None)

    def _validate_gstin_and_state(self, attrs, instance):
        """CUS-05/07/10/21: one place where a GSTIN change has its side-effects."""
        from django.conf import settings

        from . import gstin_rules as rules

        if "gstin" not in attrs and "state" not in attrs:
            return
        previous = rules.normalise(getattr(instance, "gstin", ""))
        gstin = rules.normalise(attrs["gstin"]) if "gstin" in attrs else previous
        changed_gstin = "gstin" in attrs and gstin != previous
        if "gstin" in attrs:
            attrs["gstin"] = gstin
            if changed_gstin:
                # The stored verification described the old number, not this one.
                attrs.update(rules.VERIFICATION_RESET)
            if gstin:
                company = self._party_company(instance)
                clash = Customer.objects.filter(company=company, gstin=gstin)
                if instance is not None:
                    clash = clash.exclude(pk=instance.pk)
                other = clash.only("name").first() if company is not None else None
                if other is not None:
                    raise serializers.ValidationError(
                        {"gstin": f"GSTIN {gstin} is already registered to customer '{other.name}'."}
                    )
                stored_pan = getattr(instance, "pan", "") or ""
                if "pan" not in attrs and (not stored_pan or (changed_gstin and stored_pan == rules.derive_pan(previous))):
                    # Blank, or the PAN that came from the old GSTIN: take the new number's. A PAN typed
                    # by hand (an unregistered customer can have one) is kept.
                    attrs["pan"] = rules.derive_pan(gstin)
        if not gstin:
            return
        expected = rules.derive_state(gstin)
        if changed_gstin and expected and "state" not in attrs:
            # A new GSTIN from another state moves the customer with it; a blank state is filled too.
            attrs["state"] = expected
        state = attrs["state"] if "state" in attrs else getattr(instance, "state", "")
        if expected and not (state or "").strip():
            attrs["state"] = expected
        elif getattr(settings, "CUSTOMER_STRICT_VALIDATION", False):
            wanted = rules.state_conflicts(gstin, state)
            if wanted:
                raise serializers.ValidationError(
                    {"state": f"GSTIN {gstin} belongs to {wanted}, not {state}."}
                )

    def _validate_walk_in(self, attrs, instance):
        """CUS-04: the POS walk-in party is an anonymous cash buyer; keep it that way."""
        if instance is None or not instance.is_pos_walk_in:
            return
        errors = {}
        if (attrs["gstin"] if "gstin" in attrs else instance.gstin or ""):
            errors["gstin"] = "The POS walk-in party cannot have a GSTIN."
        credit = attrs["credit_limit"] if "credit_limit" in attrs else instance.credit_limit
        if Decimal(str(credit or 0)) > 0:
            errors["credit_limit"] = "The POS walk-in party cannot have a credit limit."
        status = attrs["status"] if "status" in attrs else instance.status
        if status != Customer.Status.ACTIVE:
            errors["status"] = "The POS walk-in party must stay Active."
        if errors:
            raise serializers.ValidationError(errors)

    def _validate_credit_terms(self, attrs, instance):
        """CUS-23: credit limit and days drive holds, so only owners and managers change them."""
        from core.permissions import get_company_user

        request = self.context.get("request")
        if request is None:
            return
        changed = {}
        for field, zero in (("credit_limit", Decimal("0")), ("credit_days", 0)):
            if field not in attrs:
                continue
            old = getattr(instance, field, zero) if instance is not None else zero
            if (Decimal(str(attrs[field])) if field == "credit_limit" else int(attrs[field])) != (
                Decimal(str(old)) if field == "credit_limit" else int(old)
            ):
                changed[field] = "Only an owner or manager can change credit terms."
        if not changed:
            return
        member = get_company_user(request)
        if member is None or member.role not in CREDIT_TERM_EDITOR_ROLES:
            raise serializers.ValidationError(changed)

    def _validate_status_change(self, attrs, instance):
        """M1: archiving, or lifting a block / archive, is an owner/manager decision. Blocking is open to sales."""
        from core.permissions import get_company_user

        request = self.context.get("request")
        if request is None or instance is None or "status" not in attrs or attrs["status"] == instance.status:
            return
        new, old = attrs["status"], instance.status
        archiving = new == Customer.Status.INACTIVE
        lifting = new == Customer.Status.ACTIVE and old in (Customer.Status.BLOCKED, Customer.Status.INACTIVE)
        if not (archiving or lifting):
            return
        member = get_company_user(request)
        if member is None or member.role not in STATUS_ESCALATION_ROLES:
            raise serializers.ValidationError({
                "status": "Only an owner or manager can archive a customer or lift a block.",
            })

    def validate_pan(self, value):
        """PAN is 5 letters, 4 digits, 1 letter. Blank is fine; a stored legacy value may be re-saved unchanged."""
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.validators import validate_pan

        value = (value or "").strip().upper()
        if self.instance is not None and value == (self.instance.pan or ""):
            return value
        try:
            validate_pan(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def _validate_phone(self, attrs, instance):
        """CUS-26: same Indian-mobile rule as the form, enforced for API clients when strict."""
        from django.conf import settings

        if not getattr(settings, "CUSTOMER_STRICT_VALIDATION", False) or "phone" not in attrs:
            return
        phone = (attrs["phone"] or "").strip()
        if not phone or phone == (getattr(instance, "phone", "") or ""):
            return  # blank is allowed; a legacy value may be re-saved unchanged
        from core.validators import is_valid_indian_mobile

        if not is_valid_indian_mobile(phone):
            raise serializers.ValidationError({"phone": "Enter a valid 10-digit Indian mobile number."})

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
            "collection_status",
            "email_suppressed",
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
    unit_uqc = serializers.SerializerMethodField()
    alternate_unit_name = serializers.CharField(source="alternate_unit.short_name", read_only=True)
    has_movements = serializers.BooleanField(read_only=True)
    # Set only on the response to a save that touched the GST rate; blank on reads.
    gst_rate_notice = serializers.SerializerMethodField()

    def get_unit_uqc(self, obj) -> str:
        """GSTN unit quantity code; blank when the product has no unit (so the key is always present)."""
        return getattr(getattr(obj, "unit", None), "uqc_code", "") or ""

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
            "category", "category_name", "brand", "brand_name", "unit", "unit_name", "unit_uqc",
            "gst_rate", "gst_supply_form", "gst_rate_notice", "cess_rate", "cess_amount",
            "purchase_price", "selling_price", "mrp", "wholesale_price",
            "reorder_level", "product_type", "track_inventory",
            "track_batch", "track_serial", "regulated_category",
            "mfg_role", "receive_into_quarantine", "requires_incoming_inspection",
            "selling_tax_inclusive", "purchase_tax_inclusive",
            "custom_fields", "alternate_unit", "alternate_unit_name", "conversion_rate",
            "default_discount_percent", "has_movements", "status", "created_at", "updated_at",
            "salt", "composition", "manufacturer", "drug_schedule", "rack_code",
            "needs_review",
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

    def _company_for_checks(self):
        from core.permissions import get_company_user

        request = self.context.get("request")
        cu = get_company_user(request) if request else None
        return cu.company if cu is not None else None

    def _other_with(self, field, value):
        """Another live item in this company that already has this code, or None."""
        company = self._company_for_checks()
        if company is None or not value:
            return None
        qs = Product.objects.filter(company=company, **{field: value})
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        return qs.first()

    def validate_sku(self, value):
        sku = (value or "").strip()
        if not sku:
            raise serializers.ValidationError("Item code is required.")
        other = self._other_with("sku", sku)
        if other is not None:
            raise serializers.ValidationError(f"Item code already used by {other.name}.")
        return sku

    def validate_barcode(self, value):
        barcode = (value or "").strip()
        other = self._other_with("barcode", barcode)
        if other is not None:
            raise serializers.ValidationError(f"Barcode already used by {other.name}.")
        return barcode

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
    # Read-only labels, so the slab editor can show what each row is without loading every item.
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = PriceListItem
        fields = ["id", "product", "product_name", "product_sku", "unit_price", "min_qty", "max_qty", "discount_pct"]

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
    item_count = serializers.SerializerMethodField()
    customer_count = serializers.SerializerMethodField(
        help_text="Customers assigned to this list. They are charged the normal selling price when it is off."
    )

    class Meta:
        model = PriceList
        fields = ["id", "name", "is_active", "items", "item_count", "customer_count", "created_at", "updated_at"]
        read_only_fields = ["item_count", "customer_count"]

    def get_item_count(self, obj) -> int:
        return len(obj.items.all())

    def get_customer_count(self, obj) -> int:
        annotated = getattr(obj, "customer_count_annot", None)
        return annotated if annotated is not None else obj.customers.filter(is_deleted=False).count()

    def validate(self, attrs):
        instance = self.instance
        if instance is not None and attrs.get("is_active") is False and instance.is_active:
            in_use = instance.customers.filter(is_deleted=False).count()
            request = self.context.get("request")
            confirmed = str(getattr(request, "data", {}).get("confirm_customers") or "").lower() in (
                "1", "true", "yes",
            )
            if in_use and not confirmed:
                from core.exceptions import BusinessRuleError

                raise BusinessRuleError(
                    f"{in_use} customer(s) use this price list. Switching it off charges them the normal "
                    "selling price. Confirm to switch it off.",
                    code="PRICE_LIST_IN_USE",
                    extra={"customer_count": in_use},
                )
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
