# Decimal Precision & Rounding Specification (FR-011)

## 1. Statutory Requirements (PRD §5 / GST Rules)

Indian GST and statutory accounting standards impose clear requirements on precision and rounding:
1. **Quantity Precision**: Quantities support up to **3 decimal places** (`DecimalField(max_digits=14, decimal_places=3)`), accommodating unit measurements such as grams (`0.001 KGS`), liters (`0.250 LTR`), and fractional units.
2. **Intermediate Calculation Precision**: Intermediate tax, discount, and unit cost computations maintain **4 decimal places** (`0.0001`) to eliminate rounding accumulation drift across multi-line invoices.
3. **Currency & Total Precision**: Line totals, taxes, subtotal, and grand total round to **2 decimal places** (`0.01` paise precision) using `ROUND_HALF_UP` (standard statutory rounding).
4. **Auto Round-Off Adjustment**:
   - For retail and statutory GST tax invoices, an optional `auto_round_off` flag computes the difference between the exact computed grand total and the nearest whole rupee (`round_off = rounded_rupee - exact_grand_total`).
   - The round-off delta is stored explicitly in `round_off` (`DecimalField(max_digits=5, decimal_places=2)`) and never exceeds `±₹0.50`.
   - In GL accounting, `round_off` posts to GL Account `5190` (Round-off Expense/Income).

---

## 2. Implementation Reference

In `backend/core/services/billing.py`:
```python
def compute_document_totals(items, additional_charges=0, invoice_discount=0, auto_round_off=True):
    # Quantize to 2 decimals for monetary presentation
    subtotal = sum(item.taxable_amount for item in items).quantize(Decimal("0.01"))
    tax_total = sum(item.total_tax for item in items).quantize(Decimal("0.01"))
    raw_total = subtotal + tax_total + additional_charges - invoice_discount
    
    if auto_round_off:
        grand_total = raw_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        round_off = grand_total - raw_total
    else:
        grand_total = raw_total.quantize(Decimal("0.01"))
        round_off = Decimal("0.00")
        
    return grand_total, round_off
```
