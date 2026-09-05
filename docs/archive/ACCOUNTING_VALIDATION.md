# BizBoard — ACCOUNTING VALIDATION

**Date:** 2026-07-24  
**Perspective:** Chartered Accountant reviewing Indian GST SMB billing software  

---

## Architecture assessment (positive)

BizBoard correctly implements several accounting-safe invariants for an MVP:

1. **Documents are source of truth** — no mutable customer/supplier ledger tables that can drift.  
2. **Stock movements append-only** — cancellations restore via ADJUSTMENT, not deleted SALE rows.  
3. **Completion is transactional** with inventory effects (covered by tests).  
4. **Outstanding** = grand_total − completed returns − allocations.  
5. **Payment allocations capped** to receipt/payment and invoice outstanding; party must match.  
6. **Blocked customers / inactive products** enforced on complete.  
7. **Document numbers** assigned on Complete with row locks — good anti-gap practice.

These choices are appropriate for a billing-first MVP.

---

## What a CA expects vs what exists

| Expectation | Status | Risk |
|-------------|--------|------|
| Tax Invoice with CGST/SGST or IGST | Present | Preview paise mismatch |
| HSN/SAC on lines | Present | Need summary reports |
| Consecutive invoice series | Present on Complete | UI editable preview numbers confuse |
| Credit Note / Debit Note | **Absent (Phase 2)** | High for corrections |
| Sales / Purchase Return | Present | OK substitute only sometimes |
| GSTR-1 / GSTR-3B extracts | **Absent** | High for GST-registered |
| e-Invoice / IRN / e-Way | **Absent (Phase 2)** | Required above thresholds |
| Reverse charge | **Absent** | Medium |
| Tax-inclusive MRP billing | **Absent** | Medium for retail |
| Place of supply explicit | Implicit via state | Medium |
| Input tax credit register | **Absent** | High for regular dealers |
| Output tax liability register | Partial via sales register | Medium |
| Receivables aging (0–30/30–60/90+) | **Absent** (due date exists) | Medium |
| Advances / unearned | Receipts credit ledger; not labeled | Medium |
| Trial Balance / Journal | **Out of scope** | OK if marketed as billing-not-books |
| P&L / Balance Sheet | **Out of scope** | Do not claim full accounting |
| Inventory valuation (FIFO/WAVG) | Stock qty focus; valuation report thin | Medium |
| Audit trail | Activity audit + created/updated by | Owner-only view |

---

## Ledger integrity checks

| Rule | Result |
|------|--------|
| Cancelled invoices excluded from outstanding | Pass (status gate) |
| Draft invoices not in statements | Pass |
| Returns credit customer / debit supplier | Pass |
| Receipts reduce customer balance | Pass (including unallocated = advance behavior) |
| Allocations cannot exceed outstanding | Pass (tests) |
| Sales RETURNED still in open set | Pass |
| Purchase RETURNED in open set | **Gap** — purchase outstanding only COMPLETED |

**Issue:** Sales and purchase open-status sets differ — can understate supplier payables after purchase returns workflow if status model diverges.

---

## GST filing readiness

**Not ready** for unsupervised GSTR filing:

- No export of B2B/B2C/HSN summaries in GSTR shapes.  
- Document discount after tax can distort taxable value understanding.  
- Missing state → forced intrastate.  
- No credit notes for rate/value corrections after complete (edits allowed on completed lines with stock delta — powerful but dangerous without CN paper trail).

**Completed invoice line edits** (allowed by design) require strict audit + CA policy: prefer Credit Note in Phase 2.

---

## Profit / loss / cash

| Metric | Available? |
|--------|------------|
| Sales totals | Yes (dashboard/register) |
| Purchase totals | Yes |
| Gross margin by product | Limited (`product-sales` report) |
| Cash/bank book | No — payments recorded but not full cash book |
| Cash flow statement | No |

---

## Semantic CA verdict

> Would this pass an accountant review for **pilot billing**?  
> **Conditionally**, after fixing CGST residual parity, clarifying discounts, and CA-signing the PDF layout.

> Would this pass for **full GST compliance + books** for regular dealers?  
> **No** — missing CN/DN, GSTR extracts, ITC registers, and filing aids.

**Accounting module score: 3.5 / 10** (by full books standard) · **7 / 10** (by declared MVP billing+ledger standard).
