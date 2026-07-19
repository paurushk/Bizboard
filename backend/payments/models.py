from django.db import models
from django.utils import timezone

from core.models import CompanyScopedModel


class PaymentMode(models.TextChoices):
    CASH = "CASH"
    UPI = "UPI"
    BANK = "BANK"
    CARD = "CARD"
    CREDIT = "CREDIT"


class CustomerReceipt(CompanyScopedModel):
    """Money received from a customer (§8.1). Record-only, no gateway."""

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="receipts")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=8, choices=PaymentMode.choices, default=PaymentMode.CASH)
    receipt_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-receipt_date", "-id"]
        indexes = [models.Index(fields=["company", "receipt_date"])]


class SupplierPayment(CompanyScopedModel):
    """Money paid to a supplier (§8.1)."""

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="payments")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=8, choices=PaymentMode.choices, default=PaymentMode.CASH)
    payment_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-payment_date", "-id"]
        indexes = [models.Index(fields=["company", "payment_date"])]


class PaymentAllocation(CompanyScopedModel):
    """Links a receipt/payment to an open invoice — partial or full (§8.1)."""

    receipt = models.ForeignKey(
        CustomerReceipt, null=True, blank=True, on_delete=models.CASCADE, related_name="allocations"
    )
    supplier_payment = models.ForeignKey(
        SupplierPayment, null=True, blank=True, on_delete=models.CASCADE, related_name="allocations"
    )
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    purchase_invoice = models.ForeignKey(
        "purchases.PurchaseInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-created_at"]
