"""Manufacturing: BOM revisions, work orders and the documents that move stock for them.

Rev 2 of the manufacturing programme (docs/MANUFACTURING_IMPLEMENTATION_PLAN.md):

* A ``Bom`` row is one *revision* of a product's recipe. A work order points at the revision
  it was made from, and a revision that any work order used is locked.
* Stock moves through documents (material issue, material return, production receipt), each
  posted once, reversed never edited. The legacy release/complete flow stays for companies
  that have not switched (``WorkOrder.issue_mode``).
* Every figure a document posts is cached on the work order (``cost_*``), so lists and
  reports never sum the stock ledger on the fly.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import CompanyScopedModel


class MfgSettings(CompanyScopedModel):
    """One row per company: how production behaves for them."""

    class IssueMode(models.TextChoices):
        # Release issues every component at once (the behaviour before rev 2).
        AUTO_AT_RELEASE = "AUTO_AT_RELEASE", "Issue everything at release"
        # Release only reserves; materials go out through issue documents.
        SEPARATE = "SEPARATE", "Issue materials separately"

    # Deviation from plan D-2 (recorded in the execution log): the default stays the one-step
    # flow until the web screens for issue/return/receipt documents ship. Companies switch in
    # settings (refused while released orders exist). Flip this default, and the data
    # migration need not change, once the UI is in place.
    default_issue_mode = models.CharField(
        max_length=16, choices=IssueMode.choices, default=IssueMode.AUTO_AT_RELEASE,
    )
    backflush_default = models.BooleanField(default=False)
    # Role godowns (MFG-02). Blank falls back to the work order's godown, then the default godown.
    rm_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    fg_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    scrap_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    quarantine_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # Entries older than this many days need a manager's approval (§4.13).
    backdate_days = models.PositiveSmallIntegerField(default=7)
    # Extra issue above this % of the planned quantity needs approval (MFG-06).
    extra_issue_approval_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10"))
    # Blank = the last receipt absorbs the whole residual. Set = anything beyond ±N % of the
    # estimate goes to the variance account at close (§4.14).
    final_receipt_tolerance_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    auto_close_days = models.PositiveSmallIntegerField(null=True, blank=True)
    # How far above the planned quantity receipts may go before they are refused.
    over_receipt_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10"))

    class Itc04Frequency(models.TextChoices):
        ANNUAL = "ANNUAL", "Once a year (turnover up to Rs 5 crore)"
        HALF_YEARLY = "HALF_YEARLY", "Every half year (turnover above Rs 5 crore)"

    # Job work (CGST s.143, ITC-04). The statutory numbers are here, not in code, so a rule change
    # is a settings change.
    itc04_frequency = models.CharField(max_length=12, choices=Itc04Frequency.choices, default=Itc04Frequency.ANNUAL)
    jw_input_limit_days = models.PositiveIntegerField(default=365)
    jw_capital_limit_days = models.PositiveIntegerField(default=1095)
    jw_input_alert_days = models.PositiveIntegerField(default=300)
    jw_capital_alert_days = models.PositiveIntegerField(default=1000)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company"], name="uniq_mfg_settings_per_company"),
        ]


class Bom(CompanyScopedModel):
    """One revision of a product's bill of materials.

    ``revision_no`` counts per product. ``is_default`` marks the revision that
    ``resolve_bom`` returns; at most one ACTIVE default exists per (product, customer).
    ``effective_from``/``effective_to`` let a new revision take over on a date.
    A revision becomes read-only (``locked_at``) the first time a work order uses it:
    to change it, make a new revision. ``WorkOrder.bom`` is always explicit, so a
    released or completed work order is never ambiguous.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        ACTIVE = "ACTIVE"
        ARCHIVED = "ARCHIVED"

    product = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="boms_as_fg",
    )
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    revision_no = models.PositiveIntegerField(default=1)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    parent_revision = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="child_revisions",
    )
    change_reason = models.CharField(max_length=500, blank=True, default="")
    locked_at = models.DateTimeField(null=True, blank=True)
    # What one batch makes: line quantities are per this much output (MFG-04).
    output_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("1"))
    yield_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100"))
    fg_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        verbose_name = "BOM"
        verbose_name_plural = "BOMs"
        constraints = [
            models.CheckConstraint(condition=models.Q(output_qty__gt=0), name="bom_output_qty_gt_0"),
            models.CheckConstraint(
                condition=models.Q(yield_pct__gt=0) & models.Q(yield_pct__lte=100),
                name="bom_yield_pct_0_100",
            ),
            # MFG-03: revision numbers count up per product; one ACTIVE default per
            # (product, customer). These arrive in a later migration than the columns,
            # after the data migration has numbered the revisions that already exist.
            models.UniqueConstraint(
                fields=["company", "product", "revision_no"], name="uniq_bom_revision_per_product",
            ),
            models.UniqueConstraint(
                fields=["company", "product"],
                condition=models.Q(is_default=True, status="ACTIVE", customer__isnull=True),
                name="uniq_bom_default_generic",
            ),
            models.UniqueConstraint(
                fields=["company", "product", "customer"],
                condition=models.Q(is_default=True, status="ACTIVE", customer__isnull=False),
                name="uniq_bom_default_customer",
            ),
        ]

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None


class BomLine(models.Model):
    class IssueMethod(models.TextChoices):
        MANUAL = "MANUAL", "Issue by hand"
        BACKFLUSH = "BACKFLUSH", "Take at completion"

    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    component = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="bom_lines_as_component",
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    # Must be the component's own unit or its alternate unit (MFG-04, D-7).
    unit = models.ForeignKey(
        "masters.Unit", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    scrap_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    issue_method = models.CharField(max_length=10, choices=IssueMethod.choices, default=IssueMethod.MANUAL)
    is_optional = models.BooleanField(default=False)
    # A phantom is a kit: planning looks through it to its own materials and it is never
    # stocked or issued as itself.
    is_phantom = models.BooleanField(default=False)
    # Lines sharing a group are substitutes for each other; lower priority is tried first.
    alternate_group = models.PositiveSmallIntegerField(null=True, blank=True)
    alternate_priority = models.PositiveSmallIntegerField(default=1)
    source_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    sequence = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["sequence", "id"]
        constraints = [
            # B8-017: positivity previously only lived in BomLineSerializer.
            # validate_qty — imports, admin inlines, data migrations, and
            # bulk_create bypass that. A zero/negative component qty here
            # breaks _snapshot_bom (qty = 0 raises "Movement quantity must
            # be greater than zero" on release; negative slips through as
            # an inbound).
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="bomline_qty_gt_0"),
            models.CheckConstraint(
                condition=models.Q(scrap_pct__gte=0) & models.Q(scrap_pct__lt=100),
                name="bomline_scrap_pct_0_100",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.bom_id and not self.company_id:
            self.company_id = self.bom.company_id
        super().save(*args, **kwargs)


class BomOutput(models.Model):
    """What a batch makes besides the main product (MFG-04, closes B8-009).

    ``cost_share_pct`` splits the batch cost across the main product and co-products
    (they must add up to 100). By-products and scrap carry no share; they are valued
    at ``recovery_rate`` per unit and that value comes off the pool first.
    """

    class Kind(models.TextChoices):
        CO_PRODUCT = "CO_PRODUCT", "Co-product"
        BY_PRODUCT = "BY_PRODUCT", "By-product"
        SCRAP = "SCRAP", "Scrap"

    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="outputs")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    cost_share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    recovery_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    target_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="bomoutput_qty_gt_0"),
            models.CheckConstraint(
                condition=models.Q(cost_share_pct__gte=0) & models.Q(cost_share_pct__lte=100),
                name="bomoutput_share_0_100",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.bom_id and not self.company_id:
            self.company_id = self.bom.company_id
        super().save(*args, **kwargs)


class BomAdditionalCost(models.Model):
    """MFG-37: a flat cost per batch or per unit (grinding, packing, labour) added to FG cost."""

    class Basis(models.TextChoices):
        PER_UNIT = "PER_UNIT", "Per unit made"
        PER_BATCH = "PER_BATCH", "Per batch"

    class Element(models.TextChoices):
        OTHER = "OTHER", "Other expense"
        LABOUR = "LABOUR", "Labour"
        OVERHEAD = "OVERHEAD", "Overhead"
        MACHINE = "MACHINE", "Machine"

    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="additional_costs")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    # MFG-28: which absorbed-cost account the amount is credited to.
    element = models.CharField(max_length=10, choices=Element.choices, default=Element.OTHER)
    label = models.CharField(max_length=100)
    basis = models.CharField(max_length=10, choices=Basis.choices, default=Basis.PER_BATCH)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="bomaddcost_amount_gte_0"),
        ]

    def save(self, *args, **kwargs):
        if self.bom_id and not self.company_id:
            self.company_id = self.bom.company_id
        super().save(*args, **kwargs)


class WorkOrder(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        RELEASED = "RELEASED"
        IN_PROGRESS = "IN_PROGRESS"
        COMPLETED = "COMPLETED"
        CLOSED = "CLOSED"
        CANCELLED = "CANCELLED"

    class Kind(models.TextChoices):
        STANDARD = "STANDARD", "Standard"
        # Rework of units a production receipt set aside. No BOM: lines are added directly.
        REWORK = "REWORK", "Rework"

    class IssueMode(models.TextChoices):
        AUTO_AT_RELEASE = "AUTO_AT_RELEASE", "Issue everything at release"
        SEPARATE = "SEPARATE", "Issue materials separately"

    class DelayReason(models.TextChoices):
        MATERIAL_SHORTAGE = "MATERIAL_SHORTAGE", "Material shortage"
        MACHINE = "MACHINE", "Machine or tool"
        LABOUR = "LABOUR", "Labour"
        QUALITY = "QUALITY", "Quality problem"
        POWER = "POWER", "Power or utilities"
        CUSTOMER = "CUSTOMER", "Customer change"
        PLANNING = "PLANNING", "Planning"
        OTHER = "OTHER", "Other"

    # Legal moves between statuses (MFG-02). One table, used by the services.
    TRANSITIONS = {
        "DRAFT": {"RELEASED", "CANCELLED"},
        "RELEASED": {"IN_PROGRESS", "COMPLETED", "CANCELLED"},
        "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
        "COMPLETED": {"CLOSED", "IN_PROGRESS", "CANCELLED"},
        "CLOSED": {"COMPLETED"},  # reopen only
        "CANCELLED": set(),
    }

    bom = models.ForeignKey(
        Bom, null=True, blank=True, on_delete=models.PROTECT, related_name="work_orders",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.STANDARD)
    # What the order makes. Equals ``bom.product`` for a standard order; set directly for rework.
    product = models.ForeignKey(
        "masters.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="work_orders",
    )
    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    fg_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    due_date = models.DateField(null=True, blank=True, db_index=True)
    planned_start = models.DateField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=3)
    delay_reason = models.CharField(max_length=20, choices=DelayReason.choices, blank=True, default="")
    sales_order = models.ForeignKey(
        "sales.SalesOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    sales_order_item = models.ForeignKey(
        "sales.SalesOrderItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    parent_work_order = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="child_work_orders",
    )
    # Job work IN (MFG-26): the customer whose material this order processes. The output belongs
    # to them, so a receipt records goods ready to go back, not stock of ours.
    principal = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    issue_mode = models.CharField(
        max_length=16, choices=IssueMode.choices, default=IssueMode.AUTO_AT_RELEASE,
    )
    # BB-000706: business dates for period gate + WIP JE (fallback localdate).
    released_at = models.DateField(null=True, blank=True)
    completed_at = models.DateField(null=True, blank=True)
    closed_at = models.DateField(null=True, blank=True)
    # BB-000723: FG serials when bom.product.track_serial.
    serial_numbers = models.JSONField(default=list, blank=True)
    # Batch tracking for manufactured finished goods
    batch_no = models.CharField(max_length=64, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # Cached from the receipts (invariant-checked against them).
    qty_completed = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_rejected = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_rework = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    # Frozen at release (§4.14): what one good unit is expected to cost.
    estimated_unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    # Cost summary cache (§3.2). Updated in the same transaction as the document that changes it.
    cost_issued = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cost_returned = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cost_absorbed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cost_received = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cost_variance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # Set by cancel/close paths that finish a work order's money story.
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status", "due_date"], name="wo_company_status_due_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], condition=~models.Q(number=""),
                name="uniq_work_order_number_per_company",
            ),
            models.CheckConstraint(
                condition=models.Q(kind="REWORK", bom__isnull=True) | models.Q(bom__isnull=False),
                name="work_order_bom_unless_rework",
            ),
        ]

    @property
    def wip_value(self) -> Decimal:
        """Cost still sitting in work in progress for this order."""
        return (
            Decimal(self.cost_issued) - Decimal(self.cost_returned) + Decimal(self.cost_absorbed)
            - Decimal(self.cost_received) - Decimal(self.cost_variance)
        )

    def can_transition(self, target: str) -> bool:
        return target in self.TRANSITIONS.get(self.status, set())

    def save(self, *args, **kwargs):
        if self.product_id is None and self.bom_id:
            self.product_id = self.bom.product_id
        super().save(*args, **kwargs)


class WorkOrderLine(models.Model):
    """BOM component snapshot.

    B8-019: taken at WO *creation* (WorkOrderSerializer.create calls
    _snapshot_bom immediately), not at release as an earlier version of this
    docstring claimed — release's own _snapshot_bom call is a no-op once
    lines already exist. This is intentional, not just uncorrected: draft-
    time component editing (WorkOrderSerializer._apply_component_lines —
    picking a batch/lot allocation/serials before release) updates these
    existing rows in place, so they must exist from creation onward for that
    to work. A BOM edit made after a WO is drafted therefore does not affect
    that WO, matching how a sales/purchase document freezes its lines at
    creation rather than tracking a live catalog price.
    """

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="component_lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    component = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="+",
    )
    qty_per_unit = models.DecimalField(max_digits=12, decimal_places=3)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    # BB-000723: explicit batch and/or FEFO lot allocations persisted at release.
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    lot_allocations = models.JSONField(default=list, blank=True)
    serial_numbers = models.JSONField(default=list, blank=True)
    unit = models.ForeignKey(
        "masters.Unit", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    scrap_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    issue_method = models.CharField(
        max_length=10, choices=BomLine.IssueMethod.choices, default=BomLine.IssueMethod.MANUAL,
    )
    is_optional = models.BooleanField(default=False)
    alternate_group = models.PositiveSmallIntegerField(null=True, blank=True)
    alternate_priority = models.PositiveSmallIntegerField(default=1)
    alternate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="alternates",
    )
    source_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # Rework lines draw from one named rework batch.
    source_batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    # Job work IN (MFG-26): drawn from the principal's unvalued ledger, never from our stock.
    principal_supplied = models.BooleanField(default=False)
    # Cached from the issue and return documents (invariant-checked against the ledger).
    qty_issued = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_returned = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))

    class Meta:
        ordering = ["id"]
        constraints = [
            # B8-017: same reasoning as BomLine above.
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="workorderline_qty_gt_0"),
            models.CheckConstraint(
                condition=models.Q(qty_per_unit__gt=0), name="workorderline_qty_per_unit_gt_0"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.work_order_id and not self.company_id:
            self.company_id = self.work_order.company_id
        super().save(*args, **kwargs)

    @property
    def qty_remaining(self) -> Decimal:
        return Decimal(self.qty) - Decimal(self.qty_issued) + Decimal(self.qty_returned)


class WorkOrderOutput(models.Model):
    """A planned output of a work order, copied from the BOM at creation."""

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="planned_outputs")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=12, choices=BomOutput.Kind.choices)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    cost_share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    recovery_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    target_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # Frozen at release: what one unit of this output is expected to cost (§4.14).
    estimated_unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.work_order_id and not self.company_id:
            self.company_id = self.work_order.company_id
        super().save(*args, **kwargs)


class DocumentStatus(models.TextChoices):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class MfgDocument(CompanyScopedModel):
    """Base for the three posting documents: draft, post once, reverse (never edit)."""

    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    status = models.CharField(max_length=10, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT)
    doc_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True, default="")
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    reverse_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        abstract = True
        ordering = ["-id"]


class MaterialIssue(MfgDocument):
    class Approval(models.TextChoices):
        NONE = "NONE", "Not needed"
        REQUESTED = "REQUESTED", "Waiting for a manager"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Turned down"

    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="issues")
    # Material beyond what the order needs is posted by a manager, or asked for and approved here.
    approval = models.CharField(max_length=10, choices=Approval.choices, default=Approval.NONE)
    approval_note = models.CharField(max_length=500, blank=True, default="")
    approval_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    approval_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    approval_decided_at = models.DateTimeField(null=True, blank=True)

    class Meta(MfgDocument.Meta):
        indexes = [models.Index(fields=["company", "work_order"], name="mfg_issue_wo_idx")]


class MaterialIssueLine(models.Model):
    issue = models.ForeignKey(MaterialIssue, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    wo_line = models.ForeignKey(
        WorkOrderLine, null=True, blank=True, on_delete=models.PROTECT, related_name="issue_lines",
    )
    component = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    lot_allocations = models.JSONField(default=list, blank=True)
    serial_numbers = models.JSONField(default=list, blank=True)
    is_extra = models.BooleanField(default=False)
    extra_reason = models.CharField(max_length=255, blank=True, default="")
    # Filled when posted: what the stock actually gave up, and the movements that did it.
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cost_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    movement_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="mfg_issueline_qty_gt_0"),
        ]

    def save(self, *args, **kwargs):
        if self.issue_id and not self.company_id:
            self.company_id = self.issue.company_id
        super().save(*args, **kwargs)


class MaterialReturn(MfgDocument):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="returns")

    class Meta(MfgDocument.Meta):
        indexes = [models.Index(fields=["company", "work_order"], name="mfg_return_wo_idx")]


class MaterialReturnLine(models.Model):
    material_return = models.ForeignKey(MaterialReturn, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    wo_line = models.ForeignKey(
        WorkOrderLine, null=True, blank=True, on_delete=models.PROTECT, related_name="return_lines",
    )
    component = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    serial_numbers = models.JSONField(default=list, blank=True)
    # The issue line this puts back (the cost it returns at).
    source_issue_line = models.ForeignKey(
        MaterialIssueLine, null=True, blank=True, on_delete=models.PROTECT, related_name="return_lines",
    )
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cost_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    movement_ids = models.JSONField(default=list, blank=True)
    # Which issue movements this put back, and at what cost: [{"move": id, "qty": "1", "unit_cost": "2"}].
    sources = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="mfg_returnline_qty_gt_0"),
        ]

    def save(self, *args, **kwargs):
        if self.material_return_id and not self.company_id:
            self.company_id = self.material_return.company_id
        super().save(*args, **kwargs)


class ProductionReceipt(MfgDocument):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="receipts")
    # The last receipt takes the whole remaining pool (§4.14).
    is_final = models.BooleanField(default=False)
    batch_no = models.CharField(max_length=64, blank=True, default="")
    exp_date = models.DateField(null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)
    # Filled when posted.
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    absorbed_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    backflush_issue = models.ForeignKey(
        MaterialIssue, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta(MfgDocument.Meta):
        indexes = [models.Index(fields=["company", "work_order"], name="mfg_receipt_wo_idx")]


class ProductionReceiptLine(models.Model):
    class Kind(models.TextChoices):
        MAIN = "MAIN", "Main product"
        CO_PRODUCT = "CO_PRODUCT", "Co-product"
        BY_PRODUCT = "BY_PRODUCT", "By-product"
        SCRAP = "SCRAP", "Scrap"

    receipt = models.ForeignKey(ProductionReceipt, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.MAIN)
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    qty_good = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_rejected = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_rework = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    reject_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    rework_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    serial_numbers = models.JSONField(default=list, blank=True)
    recovery_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cost_share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    # Filled when posted.
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cost_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    movement_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(qty_good__gte=0) & models.Q(qty_rejected__gte=0) & models.Q(qty_rework__gte=0),
                name="mfg_receiptline_qty_gte_0",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.receipt_id and not self.company_id:
            self.company_id = self.receipt.company_id
        super().save(*args, **kwargs)


class WorkOrderVariance(models.Model):
    """What a closed work order used against what its output should have used (reporting)."""

    class Kind(models.TextChoices):
        USAGE = "USAGE", "Material usage"
        SUBSTITUTION = "SUBSTITUTION", "Substitute material"
        RESIDUAL = "RESIDUAL", "Residual cost"
        TOLERANCE = "TOLERANCE", "Beyond tolerance"

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="variances")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    kind = models.CharField(max_length=14, choices=Kind.choices)
    component = models.ForeignKey(
        "masters.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    standard_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    actual_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    standard_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    actual_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    variance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    posted_to_gl = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.work_order_id and not self.company_id:
            self.company_id = self.work_order.company_id
        super().save(*args, **kwargs)


class MrpRun(CompanyScopedModel):
    """One run of material planning: what to buy and what to make, and when (MFG-16)."""

    class Status(models.TextChoices):
        DONE = "DONE"
        SUPERSEDED = "SUPERSEDED"

    number = models.CharField(max_length=32, blank=True, default="")
    as_of = models.DateField()
    horizon_days = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DONE)
    parameters = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-id"]


class MrpLine(models.Model):
    class Kind(models.TextChoices):
        PURCHASE = "PURCHASE", "Buy"
        MAKE = "MAKE", "Make"

    class LineStatus(models.TextChoices):
        OPEN = "OPEN"
        CONVERTED = "CONVERTED"
        SKIPPED = "SKIPPED"

    run = models.ForeignKey(MrpRun, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    level = models.PositiveSmallIntegerField(default=0)
    need_date = models.DateField(null=True, blank=True)
    order_by = models.DateField(null=True, blank=True)
    lead_time_days = models.PositiveIntegerField(default=0)
    gross_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    safety_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    on_hand_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    incoming_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    net_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    suggested_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    supplier = models.ForeignKey(
        "masters.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    sources = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=LineStatus.choices, default=LineStatus.OPEN)
    converted_type = models.CharField(max_length=24, blank=True, default="")
    converted_id = models.PositiveBigIntegerField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["level", "need_date", "id"]

    def save(self, *args, **kwargs):
        if self.run_id and not self.company_id:
            self.company_id = self.run.company_id
        super().save(*args, **kwargs)


class StandardCost(CompanyScopedModel):
    """MFG-29: a planned unit cost for a product, in force from a date. Opt-in; actual costing is the default.

    With a standard in force, a production receipt values the output at the standard and whatever
    the order actually cost beyond (or under) it is cleared to manufacturing variance when the
    order closes, instead of being loaded onto the last batch.
    """

    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="standard_costs")
    effective_from = models.DateField()
    material = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    labour = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    overhead = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["product_id", "-effective_from"]
        constraints = [
            models.UniqueConstraint(fields=["company", "product", "effective_from"], name="uniq_standard_cost_start"),
            models.CheckConstraint(
                condition=models.Q(material__gte=0) & models.Q(labour__gte=0) & models.Q(overhead__gte=0),
                name="standardcost_amounts_gte_0",
            ),
        ]

    @property
    def unit_cost(self) -> Decimal:
        return Decimal(self.material) + Decimal(self.labour) + Decimal(self.overhead)


# --- shop floor (Phase 6, behind MFG_SHOP_FLOOR) ------------------------------------------------

class WorkCentre(CompanyScopedModel):
    """A place where an operation is done: a machine, a bench, a team. Rates are per hour."""

    class Kind(models.TextChoices):
        MACHINE = "MACHINE", "Machine"
        MANUAL = "MANUAL", "Manual"
        OUTSIDE = "OUTSIDE", "Outside processing"

    code = models.CharField(max_length=24)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MACHINE)
    hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("8"))
    labour_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    machine_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    overhead_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_work_centre_code_per_company"),
            models.CheckConstraint(
                condition=models.Q(labour_rate__gte=0) & models.Q(machine_rate__gte=0) & models.Q(overhead_rate__gte=0),
                name="workcentre_rates_gte_0",
            ),
        ]


class RoutingOperation(models.Model):
    """One step of a BOM revision's routing: where it is done and how long it takes."""

    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="operations")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    sequence = models.PositiveSmallIntegerField(default=10)
    name = models.CharField(max_length=120)
    work_centre = models.ForeignKey(WorkCentre, on_delete=models.PROTECT, related_name="operations")
    setup_minutes = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    run_minutes_per_unit = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("0"))
    # An operation done by a job worker (MFG-27): the work in progress goes out and comes back.
    is_subcontract = models.BooleanField(default=False)
    subcontract_supplier = models.ForeignKey(
        "masters.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["sequence", "id"]

    def save(self, *args, **kwargs):
        if self.bom_id and not self.company_id:
            self.company_id = self.bom.company_id
        super().save(*args, **kwargs)


class JobCard(CompanyScopedModel):
    """One operation of one work order: who did it, for how long, how many came out right."""

    class Status(models.TextChoices):
        PLANNED = "PLANNED"
        IN_PROGRESS = "IN_PROGRESS"
        PAUSED = "PAUSED"
        DONE = "DONE"
        CANCELLED = "CANCELLED"

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="job_cards")
    operation = models.ForeignKey(RoutingOperation, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sequence = models.PositiveSmallIntegerField(default=10)
    name = models.CharField(max_length=120)
    work_centre = models.ForeignKey(WorkCentre, on_delete=models.PROTECT, related_name="job_cards")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    qty_planned = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_good = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_rejected = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    planned_minutes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    minutes_worked = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    labour_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    machine_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    overhead_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # True once the card's labour, machine and overhead cost has been added to the work order.
    absorbed = models.BooleanField(default=False)
    is_subcontract = models.BooleanField(default=False)
    jobwork_order_id = models.PositiveBigIntegerField(null=True, blank=True)
    # What the job worker charged for this step (informational: the charge is already in the cost of
    # the goods that came back, so it is never absorbed into the work order a second time).
    outside_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["work_order_id", "sequence", "id"]
        indexes = [models.Index(fields=["company", "status"], name="jobcard_company_status_idx")]


class Operator(CompanyScopedModel):
    """A floor worker who signs in on a shared tablet with a code and PIN, with no account of their own."""

    code = models.CharField(max_length=24)
    name = models.CharField(max_length=120)
    pin_hash = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_operator_code_per_company"),
        ]


class TimeLog(models.Model):
    job_card = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="time_logs")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    operator = models.ForeignKey(Operator, null=True, blank=True, on_delete=models.SET_NULL, related_name="time_logs")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    minutes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.job_card_id and not self.company_id:
            self.company_id = self.job_card.company_id
        super().save(*args, **kwargs)


class DowntimeReason(CompanyScopedModel):
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=120)
    is_planned = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_downtime_reason_code"),
        ]


class DowntimeEvent(CompanyScopedModel):
    work_centre = models.ForeignKey(WorkCentre, on_delete=models.PROTECT, related_name="downtime")
    job_card = models.ForeignKey(JobCard, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reason = models.ForeignKey(DowntimeReason, on_delete=models.PROTECT, related_name="+")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    minutes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-started_at"]


class Machine(CompanyScopedModel):
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=120)
    work_centre = models.ForeignKey(WorkCentre, null=True, blank=True, on_delete=models.SET_NULL, related_name="machines")
    run_hours = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_machine_code_per_company"),
        ]


class MaintenancePlan(CompanyScopedModel):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="plans")
    name = models.CharField(max_length=120)
    interval_days = models.PositiveIntegerField(null=True, blank=True)
    interval_hours = models.PositiveIntegerField(null=True, blank=True)
    last_done_on = models.DateField(null=True, blank=True)
    last_done_hours = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["machine_id", "name"]


class MaintenanceLog(CompanyScopedModel):
    class Kind(models.TextChoices):
        PREVENTIVE = "PREVENTIVE", "Preventive"
        BREAKDOWN = "BREAKDOWN", "Breakdown"

    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="logs")
    plan = models.ForeignKey(MaintenancePlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    reported_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    description = models.CharField(max_length=500, blank=True, default="")
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    downtime_minutes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["-reported_at"]


class StandardRevaluation(CompanyScopedModel):
    """MFG-29 / QOS-0146: stock on hand re-priced to the standard cost in force.

    A run is previewed (DRAFT, lines show the effect and nothing has moved), then posted: each lot is
    taken out at its current cost and put back at the standard through the stock ledger, and the
    difference goes to Manufacturing Variance (5420) against Inventory (1400). A posted run is reversed
    as a whole, and only while none of the lots it touched has moved since.
    """

    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    status = models.CharField(max_length=10, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT)
    as_of = models.DateField()
    product = models.ForeignKey(
        "masters.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Empty = every item that has a standard cost in force on the date.",
    )
    notes = models.CharField(max_length=500, blank=True, default="")
    total_before = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    total_after = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reverse_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-id"]

    @property
    def total_change(self) -> Decimal:
        return Decimal(self.total_after) - Decimal(self.total_before)


class StandardRevaluationLine(models.Model):
    run = models.ForeignKey(StandardRevaluation, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey("inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    old_unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    new_unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    old_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    new_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    movement_ids = models.JSONField(default=list, blank=True)
    # The newest stock movement of this lot when the run was posted; a reversal needs it to be unchanged.
    last_movement_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    @property
    def change(self) -> Decimal:
        return Decimal(self.new_value) - Decimal(self.old_value)

    def save(self, *args, **kwargs):
        if self.run_id and not self.company_id:
            self.company_id = self.run.company_id
        super().save(*args, **kwargs)
