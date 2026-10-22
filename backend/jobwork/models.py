"""Job work, India (MFG-24..26): sending our material to a job worker, and processing a customer's.

Behind the MFG_JOB_WORK company flag. CGST s.143: inputs sent for job work must be back within one
year (capital goods, three), or the sending counts as a supply on the day it left. ITC-04 reports
what was sent and what came back. The numbers 365 and 1095 live in manufacturing settings.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import CompanyScopedModel


class JobWorkOrder(CompanyScopedModel):
    class Direction(models.TextChoices):
        OUT = "OUT", "We send material out"
        IN = "IN", "We process a customer's material"

    class Status(models.TextChoices):
        OPEN = "OPEN"
        CLOSED = "CLOSED"
        CANCELLED = "CANCELLED"

    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    direction = models.CharField(max_length=3, choices=Direction.choices, default=Direction.OUT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # OUT: the job worker we send to. IN: the principal whose material we process.
    supplier = models.ForeignKey(
        "masters.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="job_work_orders",
    )
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="job_work_orders",
    )
    process = models.CharField(max_length=200, blank=True, default="")
    expected_return_date = models.DateField(null=True, blank=True)
    # SAC for the job charge; 9988 is manufacturing services on physical inputs owned by others.
    service_sac = models.CharField(max_length=8, default="9988")
    # The job worker's premises are declared as our additional place of business, or the job worker
    # is registered, so goods may be supplied from there directly (ITC-04 table 5C).
    direct_supply_declared = models.BooleanField(default=False)
    # OUT: the godown that stands for the stock sitting at the job worker.
    job_worker_warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    # Raised from a routing step of a work order (QOS-0147). Plain ids: job work does not import manufacturing.
    work_order_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    job_card_id = models.PositiveBigIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], condition=~models.Q(number=""), name="uniq_jobwork_order_number",
            ),
        ]


class JobWorkChallan(CompanyScopedModel):
    """Material leaving (OUT) or arriving (IN) under a job work order."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        ISSUED = "ISSUED"
        REVERSED = "REVERSED"

    class Origin(models.TextChoices):
        OWN_PREMISES = "OWN_PREMISES", "From our premises"
        DIRECT_FROM_SUPPLIER = "DIRECT_FROM_SUPPLIER", "Straight from the supplier"
        FROM_OTHER_JOB_WORKER = "FROM_OTHER_JOB_WORKER", "From another job worker"

    order = models.ForeignKey(JobWorkOrder, on_delete=models.PROTECT, related_name="challans")
    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    challan_date = models.DateField()
    origin = models.CharField(max_length=24, choices=Origin.choices, default=Origin.OWN_PREMISES)
    # Our godown the goods leave from (OUT) or arrive in (IN).
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    source_challan = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="onward_challans",
    )
    supplier_invoice_ref = models.CharField(max_length=64, blank=True, default="")
    vehicle_no = models.CharField(max_length=20, blank=True, default="")
    eway_bill_no = models.CharField(max_length=32, blank=True, default="")
    purpose = models.CharField(max_length=120, default="Job work")
    notes = models.CharField(max_length=500, blank=True, default="")
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reverse_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-challan_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], condition=~models.Q(number=""), name="uniq_jobwork_challan_number",
            ),
        ]


class JobWorkChallanLine(models.Model):
    class GoodsKind(models.TextChoices):
        INPUT = "INPUT", "Inputs"
        CAPITAL_GOOD = "CAPITAL_GOOD", "Capital goods (moulds, dies, tools excluded)"

    challan = models.ForeignKey(JobWorkChallan, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey("inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    goods_kind = models.CharField(max_length=14, choices=GoodsKind.choices, default=GoodsKind.INPUT)
    serial_numbers = models.JSONField(default=list, blank=True)
    # OUT: the cost the stock left with (a transfer carries cost with it). IN: nil, never valued.
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    # How much of this line the job worker has accounted for (cached from settlements).
    qty_settled = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    movement_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="jw_challanline_qty_gt_0"),
            models.CheckConstraint(condition=models.Q(qty_settled__gte=0), name="jw_challanline_settled_gte_0"),
        ]

    def save(self, *args, **kwargs):
        if self.challan_id and not self.company_id:
            self.company_id = self.challan.company_id
        super().save(*args, **kwargs)

    @property
    def qty_open(self) -> Decimal:
        return Decimal(self.qty) - Decimal(self.qty_settled)


class JobWorkReceipt(CompanyScopedModel):
    """What the job worker sends back, and what became of the rest."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        POSTED = "POSTED"
        REVERSED = "REVERSED"

    order = models.ForeignKey(JobWorkOrder, on_delete=models.PROTECT, related_name="receipts")
    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    receipt_date = models.DateField()
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    notes = models.CharField(max_length=500, blank=True, default="")
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    reverse_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-receipt_date", "-id"]


class JobWorkReceiptLine(models.Model):
    class Kind(models.TextChoices):
        PROCESSED = "PROCESSED", "Processed goods back"
        UNPROCESSED_RETURN = "UNPROCESSED_RETURN", "Unprocessed material back"
        SCRAP_RETURNED = "SCRAP_RETURNED", "Scrap sent back"
        SCRAP_RETAINED = "SCRAP_RETAINED", "Scrap kept by the job worker"
        SENT_TO_OTHER = "SENT_TO_OTHER", "Sent on to another job worker"
        SUPPLIED_FROM_JW = "SUPPLIED_FROM_JW", "Supplied from the job worker's premises"

    receipt = models.ForeignKey(JobWorkReceipt, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # What came back (the processed item, the returned material, the scrap).
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    batch = models.ForeignKey("inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    # PROCESSED / SENT_TO_OTHER / SCRAP_RETAINED: the sent material this accounts for.
    input_product = models.ForeignKey("masters.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    input_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    input_batch = models.ForeignKey("inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    # Job charge for this line, taken into the cost of the goods that come back.
    charge_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # SCRAP_RETURNED: value per unit; others: filled when posted.
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cost_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    other_order = models.ForeignKey(JobWorkOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    invoice_ref = models.CharField(max_length=64, blank=True, default="")
    loss_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    movement_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.receipt_id and not self.company_id:
            self.company_id = self.receipt.company_id
        super().save(*args, **kwargs)


class JobWorkSettlement(models.Model):
    """One receipt line accounting for part of one challan line: the link ITC-04 table 5 and the ageing clock need."""

    receipt_line = models.ForeignKey(JobWorkReceiptLine, on_delete=models.CASCADE, related_name="settlements")
    challan_line = models.ForeignKey(JobWorkChallanLine, on_delete=models.PROTECT, related_name="settlements")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    settled_on = models.DateField()
    reversed = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=models.Q(qty__gt=0), name="jw_settlement_qty_gt_0")]


class PrincipalMaterialMovement(CompanyScopedModel):
    """Qty-only ledger of a customer's material in our hands (job work IN). Never valued, never in stock or GL."""

    class Kind(models.TextChoices):
        RECEIVED = "RECEIVED", "Received from the principal"
        CONSUMED = "CONSUMED", "Used in processing"
        PRODUCED = "PRODUCED", "Processed goods ready to go back"
        RETURNED = "RETURNED", "Sent back"
        LOSS = "LOSS", "Lost or scrapped in processing"

    principal = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="principal_material")
    order = models.ForeignKey(JobWorkOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="principal_moves")
    challan = models.ForeignKey(JobWorkChallan, null=True, blank=True, on_delete=models.PROTECT, related_name="principal_moves")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # Signed: + when received, - when it leaves our hands.
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    move_date = models.DateField()
    work_order_id = models.PositiveBigIntegerField(null=True, blank=True)
    reference = models.CharField(max_length=64, blank=True, default="")
    reversed = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["company", "principal", "product"], name="pm_principal_product_idx")]


class Itc04Filing(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        EXPORTED = "EXPORTED"
        FILED = "FILED"

    period_label = models.CharField(max_length=24)
    from_date = models.DateField()
    to_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    summary = models.JSONField(default=dict, blank=True)
    filed_on = models.DateField(null=True, blank=True)
    acknowledgement = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-from_date"]
        constraints = [
            models.UniqueConstraint(fields=["company", "period_label"], name="uniq_itc04_period_per_company"),
        ]
