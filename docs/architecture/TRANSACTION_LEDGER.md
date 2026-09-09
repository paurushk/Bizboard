# Transaction Ledger Architecture & Concurrency Model (FR-014)

## 1. Overview & Core Invariants

Bizboard implements a statutory-grade, append-only transaction ledger designed to comply with Indian Accounting Standards and GST Rules (CGST Rules 2017):

1. **Documents as Ledger of Record (ADR-A01)**:
   - Primary business documents (`SalesInvoice`, `PurchaseInvoice`, `SalesReturn`, `PurchaseReturn`, `CustomerReceipt`, `SupplierPayment`, `StockMovement`, `GoodsReceipt`) constitute the permanent financial and inventory ledger.
   - Party balances (Accounts Receivable and Accounts Payable) are dynamically computed projections rather than mutable accumulator columns.
   - `LedgerService.bulk_sales_invoice_outstanding` and `LedgerService.bulk_purchase_invoice_outstanding` derive outstanding balances from completed documents minus active allocations.

2. **Append-Only Stock Ledger (ADR-A02)**:
   - Inventory changes are recorded strictly via append-only `StockMovement` rows typed by `MovementType` (`PURCHASE`, `SALE`, `PURCHASE_RETURN`, `SALES_RETURN`, `ADJUSTMENT`, `TRANSFER_IN`, `TRANSFER_OUT`, `MANUFACTURE_ISSUE`, `MANUFACTURE_RECEIPT`, `OPENING_STOCK`).
   - `StockBalance` acts as a materialized balance cache that can be fully rebuilt from `StockMovement` history.
   - Voiding or adjustments append reversing entries; prior movements are never deleted or rewritten.

3. **Concurrency-Safe Sequence Generation**:
   - Number series allocation occurs at the atomic point of document completion via `DocumentNumberService.next_number`.
   - Sequence generation utilizes PostgreSQL row-level locks (`SELECT ... FOR UPDATE` on `DocumentSeries`) to guarantee monotonic, gap-free statutory numbering without race conditions.
   - Draft deletion never consumes or burns sequence numbers.

4. **Multi-Tenant Isolation**:
   - Every transactional model inherits `CompanyScopedModel`.
   - Multi-tenant isolation is enforced at three levels:
     1. Automatic Django ORM query filtering via `CompanyScopedViewSet`.
     2. PostgreSQL Row-Level Security (RLS) policies as a database backstop.
     3. Strict tenancy validation in serializers and foreign key lookups (`check_company_ref`).

---

## 2. Automatic Synchronization Matrix

All 7 core transactional flows are synchronized atomically inside `@transaction.atomic` boundaries:

| Transaction Flow | Primary Trigger | Inventory Movement | Financial / Ledger Projection | Audit & Event Bus |
|---|---|---|---|---|
| **Purchase Completion** | `POST /purchases/invoices/{id}/complete/` | Inward `MovementType.PURCHASE` at line purchase price into warehouse | AP increased (`LedgerService.supplier_outstanding`); GL 5100/2100 posted | `purchase_invoice.completed`, `StatutoryDocumentEvent` logged |
| **Purchase Return Completion** | `POST /purchases/returns/{id}/complete/` | Outward `MovementType.PURCHASE_RETURN` reversing stock | AP decreased / Debit Note generated; GL reversed | `purchase_return.completed` emitted |
| **Sales Completion** | `POST /sales/invoices/{id}/complete/` | Outward `MovementType.SALE` deducted from warehouse stock | AR increased (`LedgerService.customer_outstanding`); GL 1200/4100 posted | `sales_invoice.completed`, statutory event logged |
| **Sales Return Completion** | `POST /sales/returns/{id}/complete/` | Inward `MovementType.SALES_RETURN` restored to warehouse | AR decreased / Credit Note generated; GL reversed | `sales_return.completed` emitted |
| **Customer Receipt** | `POST /payments/receipts/{id}/post/` | N/A | AR reduced via `PaymentAllocation` locked against invoice balance | `customer_receipt.posted` emitted |
| **Supplier Payment** | `POST /payments/supplier-payments/{id}/post/` | N/A | AP reduced via `PaymentAllocation` locked against bill balance | `supplier_payment.posted` emitted |
| **Stock Adjustment** | `POST /inventory/adjustments/{id}/complete/` | Signed `MovementType.ADJUSTMENT` (+/- delta) | Inventory valuation updated; GL 5120 (Inventory Loss/Gain) posted | `stock_adjustment.completed` emitted |
| **Goods Receipt (GRN)** | `POST /purchases/grns/{id}/complete/` | Inward `MovementType.PURCHASE` for accepted quantities | Warehouse stock incremented; ready for bill conversion | `goods_receipt.completed` emitted |

---

## 3. Concurrency Protection & Over-Allocation Prevention

Payment allocations use pessimistic locking:
```python
# Locked row evaluation prevents concurrent over-allocation
invoice = SalesInvoice.objects.select_for_update().get(pk=invoice_id)
allocated = PaymentAllocation.objects.filter(
    sales_invoice=invoice, reversed_at__isnull=True
).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

if allocated + new_amount > invoice.grand_total:
    raise BusinessRuleError("Payment exceeds invoice outstanding balance.")
```
This guarantees that two concurrent payments cannot over-allocate a single invoice.
