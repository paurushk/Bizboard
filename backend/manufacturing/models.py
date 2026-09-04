"""Manufacturing MVP — BOM + work orders; not a full MES."""

from django.db import models

from core.models import CompanyScopedModel


class Bom(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        ACTIVE = "ACTIVE"
        ARCHIVED = "ARCHIVED"

    product = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="boms_as_fg",
    )
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["name"]
        verbose_name = "BOM"
        verbose_name_plural = "BOMs"


class BomLine(models.Model):
    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    component = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="bom_lines_as_component",
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        ordering = ["id"]
        constraints = [
            # B8-017: positivity previously only lived in BomLineSerializer.
            # validate_qty — imports, admin inlines, data migrations, and
            # bulk_create bypass that. A zero/negative component qty here
            # breaks _snapshot_bom (qty = 0 raises "Movement quantity must
            # be greater than zero" on release; negative slips through as
            # an inbound).
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="bomline_qty_gt_0"),
        ]

    def save(self, *args, **kwargs):
        if self.bom_id and not self.company_id:
            self.company_id = self.bom.company_id
        super().save(*args, **kwargs)


class WorkOrder(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        RELEASED = "RELEASED"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    bom = models.ForeignKey(Bom, on_delete=models.PROTECT, related_name="work_orders")
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # BB-000706: business dates for period gate + WIP JE (fallback localdate).
    released_at = models.DateField(null=True, blank=True)
    completed_at = models.DateField(null=True, blank=True)
    # BB-000723: FG serials when bom.product.track_serial.
    serial_numbers = models.JSONField(default=list, blank=True)
    # Batch tracking for manufactured finished goods
    batch_no = models.CharField(max_length=64, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]


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
