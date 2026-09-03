from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel
from core.validators import validate_gstin, validate_pan, validate_udyam


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    full_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    push_token = models.CharField(max_length=512, blank=True, default="")
    active_company = models.ForeignKey(
        "Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_users",
        help_text="Selected company for multi-membership users (Wave 17G).",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        raw = (self.phone or "").strip()
        if raw:
            from accounts.otp_utils import canonicalize_user_phone

            try:
                self.phone = canonicalize_user_phone(raw)
            except ValueError:
                import re

                digits = re.sub(r"\D", "", raw)
                if digits.startswith("0") and len(digits) == 11:
                    self.phone = canonicalize_user_phone(digits[1:])
                else:
                    from django.core.exceptions import ValidationError

                    raise ValidationError({"phone": "Enter a valid mobile number (E.164 or 10-digit Indian)."})
        else:
            self.phone = ""
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    class Meta:
        constraints = [
            # BUG-108: two active users sharing a phone number crashed OTP
            # verification's User.objects.get(phone=...) with
            # MultipleObjectsReturned. Blank phones (users who never set one)
            # are exempt from the constraint.
            models.UniqueConstraint(
                fields=["phone"], condition=~Q(phone=""), name="uniq_user_phone_when_set",
            ),
        ]


class Company(TimeStampedModel):
    """One legal company (tenant). Multiple warehouses are stock locations;
    legal GSTIN branches are CompanyGstin rows — not the same as warehouses.
    """

    class RegistrationType(models.TextChoices):
        REGULAR = "REGULAR"
        COMPOSITION = "COMPOSITION"
        UNREGISTERED = "UNREGISTERED"

    class NegativeStockPolicy(models.TextChoices):
        BLOCK = "BLOCK"
        WARN = "WARN"

    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[validate_gstin])
    registration_type = models.CharField(
        max_length=16, choices=RegistrationType.choices, default=RegistrationType.REGULAR
    )
    state = models.CharField(max_length=64, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=32, blank=True)
    bank_ifsc = models.CharField(max_length=16, blank=True)
    logo = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    signature = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    fy_start_month = models.PositiveSmallIntegerField(default=4)
    negative_stock_policy = models.CharField(
        max_length=8, choices=NegativeStockPolicy.choices, default=NegativeStockPolicy.BLOCK
    )
    invoice_terms = models.TextField(blank=True)
    assume_local_state_for_blank_party = models.BooleanField(
        default=True,
        help_text="When party state/GSTIN is blank, treat as local (intra-state) for GST tax.",
    )
    # Phase 2 GST compliance settings
    einvoice_enabled = models.BooleanField(default=False)
    eway_enabled = models.BooleanField(default=False)
    eway_threshold_amount = models.DecimalField(max_digits=14, decimal_places=2, default=50000)
    aato_turnover = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    gsp_provider = models.CharField(max_length=32, blank=True, default="")
    # Encrypted JSON blob for GSP credentials (Fernet); never expose in list serializers.
    gsp_credentials_encrypted = models.TextField(blank=True)
    gstin_verification_status = models.CharField(max_length=16, blank=True, default="UNVERIFIED")
    gstin_legal_name = models.CharField(max_length=255, blank=True)
    gstin_verified_at = models.DateTimeField(null=True, blank=True)
    gstin_raw_payload = models.JSONField(null=True, blank=True)
    # Phase 7.4 — India Stack identity (PAN / UDYAM). Soft-fail: save is never
    # blocked by verification status; Health alerts when pending/invalid.
    pan = models.CharField(max_length=10, blank=True, validators=[validate_pan])
    pan_verification_status = models.CharField(max_length=16, blank=True, default="UNVERIFIED")
    pan_legal_name = models.CharField(max_length=255, blank=True)
    pan_verified_at = models.DateTimeField(null=True, blank=True)
    pan_raw_payload = models.JSONField(null=True, blank=True)
    udyam = models.CharField(max_length=32, blank=True, validators=[validate_udyam])
    udyam_verification_status = models.CharField(max_length=16, blank=True, default="UNVERIFIED")
    udyam_enterprise_name = models.CharField(max_length=255, blank=True)
    udyam_verified_at = models.DateTimeField(null=True, blank=True)
    udyam_raw_payload = models.JSONField(null=True, blank=True)
    # Phase 6 AI / insights
    ai_features_enabled = models.BooleanField(default=False)
    ai_monthly_token_budget = models.PositiveIntegerField(null=True, blank=True)
    opening_cash_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    opening_cash_as_of = models.DateField(null=True, blank=True)
    daily_summary_email_enabled = models.BooleanField(default=False)
    # Phase 3 — payments & cash ops
    require_payment_reference = models.BooleanField(default=False)
    payment_gateway_provider = models.CharField(max_length=32, blank=True, default="razorpay")
    payment_gateway_credentials_encrypted = models.TextField(blank=True)
    payment_gateway_test_mode = models.BooleanField(default=False)
    auto_match_bank_exact = models.BooleanField(default=False)
    # Phase 4 — inventory depth
    inventory_valuation_method = models.CharField(
        max_length=8,
        # BB-000465 / Wave 16B: FIFO re-enabled once perpetual layers drive COGS.
        choices=[("WAVG", "Weighted Average"), ("FIFO", "FIFO")],
        default="WAVG",
        help_text=(
            "WAVG uses blended remaining unit cost. FIFO consumes InventoryCostLayer "
            "rows in creation order for outbound COGS."
        ),
    )
    valuation_business_date_order = models.BooleanField(
        default=False,
        help_text=(
            "W0-06: order historical valuation by movement_date instead of insert time. "
            "Default off for existing companies — turning this on can restate inventory/COGS. Take a backup."
        ),
    )
    recompute_tax_on_complete = models.BooleanField(
        default=False,
        help_text=(
            "W0-02: after Complete stamps the filing GSTIN, recompute tax for that GSTIN's state. "
            "Default off for existing companies. If grand total changes by more than ₹0.01, Complete "
            "requires confirm_gstin_total_change. Turning this on can change CGST/SGST vs IGST on Complete."
        ),
    )
    block_expired_stock = models.BooleanField(default=True)
    # When True, completing a delivery challan posts outbound stock (SALE movements).
    stock_on_delivery_challan = models.BooleanField(default=False)
    # Phase 5 — light accounting
    accounting_enabled = models.BooleanField(default=False)
    # ACC-04: when on, PostingService.post / assert_period_allows_money_amend
    # reject a date that is not inside an OPEN AccountingPeriod (not just one
    # that is explicitly CLOSED). Off by default for back-compat.
    require_open_period_for_posting = models.BooleanField(default=False)
    # R3-017: effective date for opening-balance journals (opening stock, opening
    # AR/AP). Falls back to the current FY start when unset.
    books_start_date = models.DateField(null=True, blank=True)
    # R1-013: how document number series are partitioned. COMPANY = one series
    # per doc type (legacy default). GSTIN_FY = a separate series per filing
    # GSTIN and financial year (Rule 46 style). Decided once at company level so
    # it never depends on whether a call site happened to pass a gstin.
    class DocNumberScope(models.TextChoices):
        COMPANY = "COMPANY"
        GSTIN_FY = "GSTIN_FY"

    doc_number_scope = models.CharField(
        max_length=16, choices=DocNumberScope.choices, default=DocNumberScope.COMPANY
    )
    class OutstandingBasis(models.TextChoices):
        GL_WHEN_BOOKS = "GL_WHEN_BOOKS"
        DOCUMENTS_ALWAYS = "DOCUMENTS_ALWAYS"

    outstanding_basis = models.CharField(
        max_length=20,
        choices=OutstandingBasis.choices,
        default=OutstandingBasis.GL_WHEN_BOOKS,
        help_text=(
            "W0-07 / PD-02: GL_WHEN_BOOKS uses AR 1200 net of advances 2300 when "
            "accounting_enabled. DOCUMENTS_ALWAYS keeps the document-derived figure."
        ),
    )
    # Wave 17G — per-company runtime feature overrides (merged with env flags at API)
    feature_flags = models.JSONField(default=dict, blank=True)
    # BB-000671: ops escape hatch — treat SaaS subscription as active/compliant.
    billing_override_active = models.BooleanField(default=False)
    # Wave B onboarding — progress is derived; only user choices/analytics persist.
    onboarding_dismissed_at = models.DateTimeField(null=True, blank=True)
    tax_profile_confirmed_at = models.DateTimeField(null=True, blank=True)
    onboarding_started_at = models.DateTimeField(null=True, blank=True)
    # Sprint B — professional-tax slabs. Empty → Karnataka-like default in payroll services.
    # Example: [{"min": "15000.01", "max": null, "amount": "200"}]
    # Or keyed by state: {"Karnataka": [{"min": "15000.01", "max": null, "amount": "200"}]}
    payroll_pt_slabs = models.JSONField(default=list, blank=True)
    # Extra keys shown on the item form Custom tab (Brand code / form by default).
    item_custom_field_defs = models.JSONField(default=list, blank=True)
    # A-07 — AR dunning. Default off (DPDP / spam). Owner must opt in.
    dunning_enabled = models.BooleanField(default=False)
    dunning_days = models.JSONField(default=list, blank=True)
    dunning_max_reminders = models.PositiveSmallIntegerField(default=3)
    dunning_quiet_hours_start = models.PositiveSmallIntegerField(default=21)
    dunning_quiet_hours_end = models.PositiveSmallIntegerField(default=8)
    dunning_channel_whatsapp = models.BooleanField(default=True)
    dunning_channel_sms = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    @property
    def is_gst_registered(self):
        if self.registration_type == self.RegistrationType.UNREGISTERED:
            return False
        if self.gstin:
            return True
        return self.gstins.filter(is_active=True).exclude(gstin="").exists()


class CompanyGstin(TimeStampedModel):
    """Wave 16D: additional GSTIN registrations / branches (document stamp source)."""

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="gstins")
    gstin = models.CharField(max_length=15)
    legal_name = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=64, blank=True)
    address = models.CharField(max_length=512, blank=True)
    city = models.CharField(max_length=64, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "gstin"], name="uniq_company_gstin"),
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(is_primary=True),
                name="uniq_company_one_primary_gstin",
            ),
        ]
        ordering = ["-is_primary", "gstin"]

    def __str__(self):
        return self.gstin or f"CompanyGstin#{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._mirror_primary_to_company()

    def delete(self, *args, **kwargs):
        company_id, was_primary = self.company_id, self.is_primary
        super().delete(*args, **kwargs)
        if was_primary:
            CompanyGstin._resync_company_scalar(company_id)

    def _mirror_primary_to_company(self):
        # ACCT-02: `Company.gstin` / `Company.state` are read directly by
        # billing, document_numbers and the GSTR builders. Keep the scalar in
        # step with the primary CompanyGstin row so a multi-GSTIN tenant that
        # manages registrations only through this model never breaks the
        # scalar readers.
        if self.is_primary and self.is_active:
            fields = {"gstin": self.gstin}
            if self.state:
                fields["state"] = self.state
            Company.objects.filter(pk=self.company_id).update(**fields)
        else:
            CompanyGstin._resync_company_scalar(self.company_id)

    @staticmethod
    def _resync_company_scalar(company_id):
        primary = (
            CompanyGstin.objects.filter(
                company_id=company_id, is_primary=True, is_active=True
            )
            .exclude(gstin="")
            .first()
        )
        if primary is not None:
            fields = {"gstin": primary.gstin}
            if primary.state:
                fields["state"] = primary.state
            Company.objects.filter(pk=company_id).update(**fields)


class CompanyUser(TimeStampedModel):
    """RBAC membership — Owner/Admin or Sales Staff with permission flags (E0.8)."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner/Admin"
        SALES_STAFF = "SALES_STAFF", "Sales Staff"
        ACCOUNTANT = "ACCOUNTANT", "Accountant"
        VIEWER = "VIEWER", "Viewer"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="company_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.SALES_STAFF)

    @classmethod
    def capability_defaults_for_role(cls, role: str) -> dict | None:
        """Fixed capability defaults applied on invite for ACCOUNTANT / VIEWER."""
        if role == cls.Role.ACCOUNTANT:
            return {
                "can_manage_inventory": False,
                "can_import": False,
                "can_cancel_documents": False,
                "can_view_financial_reports": True,
                "can_export": True,
                "can_view_ai_insights": False,
                "can_use_ai_assistant": False,
                "can_create_sales": False,
                "can_create_purchases": True,
                "can_create_payments": True,
                "can_post_journals": True,
            }
        if role == cls.Role.VIEWER:
            return {
                "can_manage_inventory": False,
                "can_import": False,
                "can_cancel_documents": False,
                # Wave 12B: least privilege — VIEWER no longer defaults into
                # financial reports visibility; grant explicitly if needed.
                "can_view_financial_reports": False,
                "can_export": False,
                "can_view_ai_insights": False,
                "can_use_ai_assistant": False,
                "can_create_sales": False,
                "can_create_purchases": False,
                "can_create_payments": False,
                "can_post_journals": False,
            }
        if role == cls.Role.SALES_STAFF:
            return {
                "can_manage_inventory": False,
                "can_import": False,
                "can_cancel_documents": False,
                "can_view_financial_reports": False,
                "can_export": False,
                "can_view_ai_insights": False,
                "can_use_ai_assistant": False,
                "can_create_sales": True,
                "can_create_purchases": False,
                "can_create_payments": True,
                "can_post_journals": False,
            }
        return None
    can_manage_inventory = models.BooleanField(default=False)
    can_import = models.BooleanField(default=False)
    can_cancel_documents = models.BooleanField(default=False)
    # BUG-319: every other capability flag defaults False (least privilege);
    # this one alone defaulted True, silently granting every new SALES_STAFF
    # member visibility into revenue/margins/who-owes-what unless an owner
    # remembered to explicitly revoke it.
    can_view_financial_reports = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_view_ai_insights = models.BooleanField(default=False)
    can_use_ai_assistant = models.BooleanField(default=False)
    # BB-000227: write gates default False (least privilege); grant explicitly.
    can_create_sales = models.BooleanField(default=False)
    can_create_purchases = models.BooleanField(default=False)
    can_create_payments = models.BooleanField(default=False)
    # BB-000316: journal / CoA / period mutate (Owner or ACCOUNTANT preset).
    can_post_journals = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("company", "user")]

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role})"


class InviteJti(TimeStampedModel):
    """BB-000616: durable invite single-use tokens (not cache-only)."""

    jti = models.CharField(max_length=64, unique=True)
    membership = models.ForeignKey(
        "accounts.CompanyUser", on_delete=models.CASCADE, related_name="invite_jtis",
    )
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_consumed(self):
        return self.consumed_at is not None


class PasswordResetJti(TimeStampedModel):
    """Single-use password-reset tokens (mirrors InviteJti)."""

    jti = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="password_reset_jtis")
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_consumed(self):
        return self.consumed_at is not None


class OtpChallenge(TimeStampedModel):
    phone = models.CharField(max_length=20, db_index=True)
    # Stores HMAC-SHA256 hex digest (see accounts.otp_utils.hash_otp), not plaintext.
    code = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    consumed = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["phone", "consumed", "-created_at"])]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
