from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from core.permissions import get_company_user
from core.validators import validate_upi_vpa

from .models import Company, CompanyGstin, CompanyUser, User

# Capability flags that VIEWER must not hold (BB-000227).
_VIEWER_FORBIDDEN_CAPS = (
    "can_manage_inventory",
    "can_import",
    "can_cancel_documents",
    "can_export",
    "can_view_ai_insights",
    "can_use_ai_assistant",
    "can_create_sales",
    "can_create_purchases",
    "can_create_payments",
    "can_post_journals",
)

# ACCOUNTANT may hold purchases/payments/export/reports; not sales/inventory/etc.
_ACCOUNTANT_FORBIDDEN_CAPS = (
    "can_manage_inventory",
    "can_import",
    "can_cancel_documents",
    "can_view_ai_insights",
    "can_use_ai_assistant",
    "can_create_sales",
)


def _assert_role_capability_invariants(role, caps: dict) -> None:
    """Reject illegal role/capability combinations (BB-000227)."""
    forbidden = ()
    if role == CompanyUser.Role.VIEWER:
        forbidden = _VIEWER_FORBIDDEN_CAPS
    elif role == CompanyUser.Role.ACCOUNTANT:
        forbidden = _ACCOUNTANT_FORBIDDEN_CAPS
    for field in forbidden:
        if caps.get(field) is True:
            raise serializers.ValidationError(
                {field: f"Role {role} cannot have {field}=true."}
            )


class RegisterSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    # BB-000751: state drives GSTIN structure and place-of-supply on every
    # invoice this company issues — it must not be silently skippable.
    state = serializers.CharField(max_length=64)
    # BB-000082: optional GST registration at signup; default UNREGISTERED (empty GSTIN OK).
    registration_type = serializers.ChoiceField(
        choices=Company.RegistrationType.choices,
        required=False,
        default=Company.RegistrationType.UNREGISTERED,
    )
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        # BB-000251: do not raise on existing email (enumeration). View returns
        # a generic success message without creating a second account.
        return value

    def validate_gstin(self, value):
        return (value or "").strip().upper()

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.validators import validate_gstin

        reg = attrs.get("registration_type") or Company.RegistrationType.UNREGISTERED
        gstin = attrs.get("gstin") or ""
        attrs["registration_type"] = reg
        attrs["gstin"] = gstin
        if reg in (Company.RegistrationType.REGULAR, Company.RegistrationType.COMPOSITION):
            if len(gstin) != 15:
                raise serializers.ValidationError(
                    {"gstin": "A valid 15-character GSTIN is required for REGULAR or COMPOSITION registration."}
                )
            try:
                validate_gstin(gstin)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"gstin": list(exc.messages)}) from exc
        return attrs

class CompanySerializer(serializers.ModelSerializer):
    is_gst_registered = serializers.BooleanField(read_only=True)
    gsp_credentials_configured = serializers.SerializerMethodField()
    onboarding = serializers.SerializerMethodField()
    dismiss_onboarding = serializers.BooleanField(write_only=True, required=False, default=False)
    confirm_tax_profile = serializers.BooleanField(write_only=True, required=False, default=False)
    mark_onboarding_started = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Company
        fields = [
            "id", "name", "legal_name", "gstin", "registration_type", "state",
            "address", "city", "pincode", "phone", "email", "upi_id",
            "bank_name", "bank_account", "bank_ifsc", "logo", "signature",
            "fy_start_month", "negative_stock_policy", "invoice_terms",
            "assume_local_state_for_blank_party", "is_gst_registered",
            "einvoice_enabled", "eway_enabled", "eway_threshold_amount",
            "aato_turnover", "gsp_provider",
            "gsp_credentials_configured",
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "pan", "pan_verification_status", "pan_legal_name", "pan_verified_at",
            "udyam", "udyam_verification_status", "udyam_enterprise_name", "udyam_verified_at",
            "ai_features_enabled", "ai_monthly_token_budget",
            "opening_cash_balance", "opening_cash_as_of", "daily_summary_email_enabled",
            "require_payment_reference", "payment_gateway_provider", "payment_gateway_test_mode",
            "auto_match_bank_exact", "inventory_valuation_method", "block_expired_stock",
            "stock_on_delivery_challan", "accounting_enabled",
            "payroll_pt_slabs",
            # BB-000715: Owner-readable feature flags (platform/admin write optional elsewhere).
            "feature_flags",
            "onboarding_dismissed_at", "tax_profile_confirmed_at", "onboarding_started_at",
            "onboarding", "dismiss_onboarding", "confirm_tax_profile",
            "mark_onboarding_started",
        ]
        read_only_fields = [
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "pan_verification_status", "pan_legal_name", "pan_verified_at",
            "udyam_verification_status", "udyam_enterprise_name", "udyam_verified_at",
            "gsp_credentials_configured",
            # BB-000215 / BB-000216: compliance / books enablement is not client-writable.
            "einvoice_enabled", "aato_turnover", "accounting_enabled",
            # BB-000259 / BB-000286 / BB-000573: gateway + e-Way/GSP mutate only via gated settings.
            "payment_gateway_provider", "payment_gateway_test_mode",
            "eway_enabled", "gsp_provider",
            # BB-000715: expose on GET; Owner must not mutate via company PATCH.
            "feature_flags",
            "onboarding_dismissed_at", "tax_profile_confirmed_at", "onboarding_started_at",
            "onboarding",
        ]

    def get_gsp_credentials_configured(self, obj) -> bool:
        from core.services.gsp_secrets import gsp_credentials_configured

        return gsp_credentials_configured(obj.gsp_credentials_encrypted or "")

    def get_onboarding(self, obj) -> dict:
        from .onboarding import derive_onboarding

        return derive_onboarding(obj)

    def _check_file_asset_company(self, asset):
        if asset is None:
            return asset
        cu = get_company_user(self.context["request"])
        if cu is None or asset.company_id != cu.company_id:
            raise serializers.ValidationError("Invalid reference.")
        return asset

    def validate_logo(self, logo):
        # BB-000202: FileAsset must belong to this company.
        return self._check_file_asset_company(logo)

    def validate_signature(self, signature):
        return self._check_file_asset_company(signature)

    def validate_upi_id(self, value):
        # PAY-13: reject malformed VPAs before save.
        try:
            validate_upi_vpa(value)
        except Exception as exc:
            from django.core.exceptions import ValidationError as DjangoValidationError

            if isinstance(exc, DjangoValidationError):
                raise serializers.ValidationError(list(exc.messages)) from exc
            raise
        return (value or "").strip()

    def validate_gstin(self, value):
        return (value or "").strip().upper()

    def validate_pan(self, value):
        return (value or "").strip().upper()

    def validate_udyam(self, value):
        return (value or "").strip().upper()

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.validators import validate_gstin

        instance = self.instance
        registration_type = attrs.get(
            "registration_type",
            getattr(instance, "registration_type", Company.RegistrationType.REGULAR),
        )
        gstin = attrs.get("gstin", getattr(instance, "gstin", "")) or ""

        if registration_type == Company.RegistrationType.UNREGISTERED:
            attrs["gstin"] = ""
        elif (
            registration_type == Company.RegistrationType.REGULAR
            and (
                "registration_type" in attrs
                or "gstin" in attrs
                or attrs.get("confirm_tax_profile")
            )
        ):
            if len(gstin) != 15:
                raise serializers.ValidationError(
                    {"gstin": "A valid 15-character GSTIN is required for REGULAR registration."}
                )
            try:
                validate_gstin(gstin)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"gstin": list(exc.messages)}) from exc

        return attrs

    def validate_inventory_valuation_method(self, value):
        # Wave 16B: FIFO allowed when perpetual InventoryCostLayer path is active.
        if value not in ("WAVG", "FIFO"):
            raise serializers.ValidationError("inventory_valuation_method must be WAVG or FIFO.")
        instance = getattr(self, "instance", None)
        if (
            instance is not None
            and value == "FIFO"
            and getattr(instance, "inventory_valuation_method", "WAVG") != "FIFO"
        ):
            from inventory.models import StockBalance

            if StockBalance.objects.filter(company=instance, on_hand__gt=0).exists():
                raise serializers.ValidationError(
                    "Cannot switch to FIFO while stock is on hand without cost layers. "
                    "Clear stock or contact support to seed FIFO layers."
                )
        return value

    def update(self, instance, validated_data):
        # BB-000573: GSP secrets are not writable on Company PATCH.
        validated_data.pop("gsp_credentials", None)
        validated_data.pop("clear_gsp_credentials", None)
        dismiss_onboarding = validated_data.pop("dismiss_onboarding", False)
        confirm_tax_profile = validated_data.pop("confirm_tax_profile", False)
        mark_onboarding_started = validated_data.pop("mark_onboarding_started", False)
        now = timezone.now()
        if dismiss_onboarding:
            validated_data["onboarding_dismissed_at"] = now
        if confirm_tax_profile:
            validated_data["tax_profile_confirmed_at"] = now
        if mark_onboarding_started and instance.onboarding_started_at is None:
            validated_data["onboarding_started_at"] = now
        return super().update(instance, validated_data)


class CompanySerializerStaff(serializers.ModelSerializer):
    """Non-owner read view of Company — omits bank/UPI details (BUG-111)."""

    is_gst_registered = serializers.BooleanField(read_only=True)

    class Meta:
        model = Company
        fields = [
            "id", "name", "legal_name", "gstin", "registration_type", "state",
            "address", "city", "pincode", "phone", "email", "logo", "signature",
            "fy_start_month", "negative_stock_policy", "invoice_terms",
            "assume_local_state_for_blank_party", "is_gst_registered",
            "einvoice_enabled", "eway_enabled", "eway_threshold_amount",
            "aato_turnover", "accounting_enabled",
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "ai_features_enabled",
        ]
        read_only_fields = [
            "gstin_verification_status", "gstin_legal_name", "gstin_verified_at",
            "einvoice_enabled", "eway_enabled", "eway_threshold_amount", "aato_turnover",
            "ai_features_enabled", "accounting_enabled",
        ]


class CompanyUserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    # BB-000084: company FK is never writable — membership stays on request tenant.
    company = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CompanyUser
        fields = [
            "id", "company", "user", "email", "full_name", "phone", "role",
            "can_manage_inventory", "can_import",
            "can_cancel_documents", "can_view_financial_reports", "can_export",
            "can_view_ai_insights", "can_use_ai_assistant",
            "can_create_sales", "can_create_purchases", "can_create_payments",
            "can_post_journals",
            "is_active",
        ]
        read_only_fields = ["company", "user"]

    def validate(self, attrs):
        instance = self.instance
        role = attrs.get("role", getattr(instance, "role", None))
        cap_fields = (
            "can_manage_inventory", "can_import", "can_cancel_documents",
            "can_view_financial_reports", "can_export",
            "can_view_ai_insights", "can_use_ai_assistant",
            "can_create_sales", "can_create_purchases", "can_create_payments",
            "can_post_journals",
        )
        caps = {}
        for field in cap_fields:
            if field in attrs:
                caps[field] = attrs[field]
            elif instance is not None:
                caps[field] = getattr(instance, field)
        _assert_role_capability_invariants(role, caps)
        return attrs


class InviteUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    # BB-000306: password optional for invite-without-password flow.
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default="",
    )
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=CompanyUser.Role.choices, default=CompanyUser.Role.SALES_STAFF)
    can_manage_inventory = serializers.BooleanField(default=False)
    can_import = serializers.BooleanField(default=False)
    can_cancel_documents = serializers.BooleanField(default=False)
    can_view_financial_reports = serializers.BooleanField(default=False)
    can_export = serializers.BooleanField(default=False)
    # None = omitted (role defaults apply). Explicit false stays least-privilege.
    can_create_sales = serializers.BooleanField(required=False, allow_null=True, default=None)
    can_create_purchases = serializers.BooleanField(required=False, allow_null=True, default=None)
    can_create_payments = serializers.BooleanField(required=False, allow_null=True, default=None)
    can_post_journals = serializers.BooleanField(default=False)

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value

    def validate_role(self, role):
        # BB-000227: OWNER invite blocked — use a dedicated promote-owner flow.
        if role == CompanyUser.Role.OWNER:
            raise serializers.ValidationError(
                "Cannot invite users as OWNER. Promote an existing member instead."
            )
        return role

    def validate(self, attrs):
        caps = {k: v for k, v in attrs.items() if v is not None}
        _assert_role_capability_invariants(attrs.get("role"), caps)
        return attrs


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="user.id")
    email = serializers.EmailField(source="user.email")
    full_name = serializers.CharField(source="user.full_name")
    phone = serializers.CharField(source="user.phone")
    role = serializers.CharField()
    can_manage_inventory = serializers.BooleanField()
    can_import = serializers.BooleanField()
    can_cancel_documents = serializers.BooleanField()
    can_view_financial_reports = serializers.BooleanField()
    can_export = serializers.BooleanField()
    can_view_ai_insights = serializers.BooleanField()
    can_use_ai_assistant = serializers.BooleanField()
    can_create_sales = serializers.BooleanField()
    can_create_purchases = serializers.BooleanField()
    can_create_payments = serializers.BooleanField()
    can_post_journals = serializers.BooleanField()
    company_id = serializers.IntegerField(source="company.id")
    company = serializers.SerializerMethodField()

    def get_company(self, obj):
        # Non-owners don't get bank/UPI details embedded in their own
        # session payload either (BUG-111).
        serializer_cls = CompanySerializer if obj.role == "OWNER" else CompanySerializerStaff
        return serializer_cls(obj.company).data


class CompanyGstinSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyGstin
        fields = [
            "id", "gstin", "legal_name", "state", "address", "city", "pincode",
            "is_primary", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_gstin(self, value):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.validators import validate_gstin

        gstin = (value or "").strip().upper()
        try:
            validate_gstin(gstin)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return gstin

    def create(self, validated_data):
        company = validated_data["company"]
        if validated_data.get("is_primary"):
            CompanyGstin.objects.filter(company=company, is_primary=True).update(is_primary=False)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get("is_primary"):
            CompanyGstin.objects.filter(company=instance.company, is_primary=True).exclude(
                pk=instance.pk
            ).update(is_primary=False)
        return super().update(instance, validated_data)
