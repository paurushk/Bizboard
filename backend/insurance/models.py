from django.db import models

from core.models import CompanyScopedModel


class PolicyProduct(CompanyScopedModel):
    """An insurer's product. Not a stock SKU."""

    class Line(models.TextChoices):
        MOTOR = "MOTOR"
        HEALTH = "HEALTH"
        LIFE = "LIFE"
        OTHER = "OTHER"

    name = models.CharField(max_length=200)
    insurer_name = models.CharField(max_length=200)
    line = models.CharField(max_length=8, choices=Line.choices)
    tenure_months = models.PositiveIntegerField()
    sum_insured = models.DecimalField(max_digits=14, decimal_places=2)
    premium = models.DecimalField(max_digits=14, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["insurer_name", "name"]


class PolicyOptionSet(CompanyScopedModel):
    lead = models.ForeignKey("crm.Lead", on_delete=models.PROTECT, related_name="policy_option_sets")
    name = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PolicyOption(CompanyScopedModel):
    option_set = models.ForeignKey(PolicyOptionSet, on_delete=models.CASCADE, related_name="options")
    product = models.ForeignKey(PolicyProduct, on_delete=models.PROTECT, related_name="options")
    chosen = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["option_set", "product"], name="uniq_option_product"),
        ]


class Policy(CompanyScopedModel):
    class Status(models.TextChoices):
        IN_FORCE = "IN_FORCE"
        CANCELLED = "CANCELLED"
        EXPIRED = "EXPIRED"

    number = models.CharField(max_length=32, blank=True)
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="policies")
    product = models.ForeignKey(PolicyProduct, on_delete=models.PROTECT, related_name="policies")
    option = models.ForeignKey(PolicyOption, null=True, blank=True, on_delete=models.PROTECT, related_name="policies")
    lead = models.ForeignKey("crm.Lead", null=True, blank=True, on_delete=models.SET_NULL, related_name="policies")
    campaign = models.ForeignKey("crm.Campaign", null=True, blank=True, on_delete=models.SET_NULL, related_name="policies")
    advisor = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="policies",
    )
    nominee = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_FORCE)
    premium = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_policy_number_per_company",
            ),
        ]


class PolicyEndorsement(CompanyScopedModel):
    class Kind(models.TextChoices):
        ENDORSE = "ENDORSE"
        CANCEL = "CANCEL"

    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="endorsements")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    note = models.TextField()


class CommissionReceivable(CompanyScopedModel):
    """Insurer commission. Separate from the customer premium receipt."""

    class Status(models.TextChoices):
        OPEN = "OPEN"
        RECEIVED = "RECEIVED"

    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="commissions")
    insurer_name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["-created_at"]


class PolicyClaim(CompanyScopedModel):
    """Claim intake linked to a ticket. Does not post the ledger."""

    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="claims")
    ticket = models.ForeignKey("support.Ticket", on_delete=models.PROTECT, related_name="policy_claims")
    summary = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["policy", "ticket"], name="uniq_policy_claim_ticket"),
        ]


class PolicyKyc(CompanyScopedModel):
    class Kind(models.TextChoices):
        AADHAAR = "AADHAAR"
        PAN = "PAN"
        OTHER = "OTHER"

    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="kyc_files")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.OTHER)
    file = models.ForeignKey("core.FileAsset", on_delete=models.PROTECT, related_name="policy_kyc")


class PolicyRenewalLead(CompanyScopedModel):
    """One system-generated renewal lead per policy. The unique policy link is
    the dedupe key; customer name and message text are not."""

    policy = models.OneToOneField(Policy, on_delete=models.CASCADE, related_name="renewal_lead_link")
    lead = models.ForeignKey("crm.Lead", on_delete=models.CASCADE, related_name="policy_renewals")
