# BizBoard — CALCULATION VALIDATION

**Date:** 2026-07-24  
**Sources of truth compared:** `backend/core/services/billing.py`, `web/src/utils/tax.ts`, `web/src/utils/money.ts`, pytest `test_tax_calc.py` / `test_billing_totals.py`, live API probes.

---

## Formula (backend — authoritative on save)

For each line (tax enabled):

1. `gross = q2(qty × unit_price)`  
2. `discount = q2(gross × discount_percent / 100)`  
3. `taxable = q2(gross − discount)`  
4. `tax = taxable × gst_rate / 100` (**not** quantized before split)  
5. Intra-state: `cgst = q2(tax/2)`, `sgst = q2(tax) − cgst`, `igst = 0`  
6. Inter-state: `igst = q2(tax)`, CGST/SGST = 0  
7. `line_total = q2(taxable + cgst + sgst + igst)`

Document:

8. `raw = taxable_total + cgst + sgst + igst + charges − invoice_discount` (clamped ≥ 0)  
9. If `auto_round_off`: `grand = round_half_up(raw → rupee)` else `grand = q2(raw)`  
10. `round_off = q2(grand − raw)`

`q2` = Decimal quantize 0.01, `ROUND_HALF_UP`.

---

## Automated suite results

| Test theme | Result |
|------------|--------|
| Intra CGST/SGST split (even) | Pass |
| Inter IGST | Pass |
| NON_GST zero tax | Pass |
| Line discount before tax | Pass |
| Multiple GST slabs accumulate | Pass |
| Purchase tax from supplier state | Pass |
| Additional charges + invoice discount | Pass |
| Auto round-off disable | Pass |
| CGST+SGST sum to q2(tax) residual | Pass (`test_cgst_sgst_halves_sum_to_tax`) |
| FE unit tests (even cases) | Pass — **do not cover residual odd-paise vs BE** |

---

## Live probe — odd paise (FAIL parity)

**Input:** 1 × ₹10.05, GST 18%, intra-state (Karnataka), auto round-off on.

| Field | Backend (saved) | Frontend `calculateLineTax` |
|-------|-----------------|-----------------------------|
| Taxable | 10.05 | 10.05 |
| Tax | 1.81 (effective) | 1.81 |
| CGST | **0.90** | **0.91** |
| SGST | **0.91** | **0.91** |
| Tax total | **1.81** | **1.82** |
| Line total | **11.86** | **11.87** |
| Grand (w/ round) | **12.00** (round_off +0.14) | Would round from 11.87 → 12.00 |

**Root cause:** BE splits **unrounded** `tax/2` then residuals to SGST; FE rounds tax first then equal-halves.

**Status:** **FAILED** production acceptance for billing preview trust.

---

## Discount order

| Discount type | Applied when | Affects taxable? | Affects GST? | Status |
|---------------|--------------|------------------|--------------|--------|
| Line `discount_percent` | Before tax | Yes | Yes | **Pass** |
| Document `invoice_discount` | After tax (on grand) | **No** | **No** | **Fail clarity / GST intent** |

Live: ₹100 @ 18% − ₹10 invoice discount → tax still ₹18, grand ₹108.

---

## Rounding & precision

| Topic | Assessment |
|-------|------------|
| Backend Decimal HALF_UP | Correct for INR money |
| FE `Math.round((v+EPSILON)*100)/100` | Approximate; float risk |
| Document round-off to rupee | Implemented; toggle works |
| Negative totals | Clamped to 0 — OK, document behavior |
| Large values | Not load-tested; Decimal OK in principle |
| Overflow | Unlikely in Decimal; FE JS Number unsafe for huge qty×price |

---

## GST scenarios matrix

| Scenario | Backend | FE preview | Notes |
|----------|---------|------------|-------|
| Intrastate CGST+SGST | Pass | Pass (even) / Fail (odd) | |
| Interstate IGST | Pass | Pass | |
| NON_GST | Pass | Depends on invoice type flag | |
| Multiple slabs 5%+28% | Pass | Not parity-tested odd | |
| Missing party state → intra | By design | Same | **GST risk** |
| Tax inclusive pricing | **Missing** | Missing | Phase gap |
| Reverse charge | **Missing** | Missing | Phase gap |
| Place of supply field | Implicit via state | Implicit | Weak for CA |

---

## Currency formatting

- FE `formatMoney` uses `en-IN` INR — **Pass** on Products/Dashboard (₹).  
- API returns decimal strings — good for precision.

---

## Reverse calculations

- No “tax-inclusive → exclusive” helper found.  
- Discount amount↔percent sync exists on FE — Pass for line discounts.

---

## Calculation readiness score

**6.0 / 10** — Core math is mostly correct on the server and well tested; **preview parity and document-discount semantics block CA confidence**.
