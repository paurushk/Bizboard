# Help error codes (M1 — 15 raise sites)

**Rule:** do **not** retrofit the ~687 `raise BusinessRuleError(...)` sites. Add `code=` only at the sites below. Constants live in `backend/core/help_codes.py`. The API handler must emit the instance code (DRF already accepts `code=`; today it ignores it and always sends `business_rule_violation`).

**Mechanism:**

1. `backend/core/help_codes.py` — one string constant per code.
2. `BusinessRuleError(message, code=HelpCode.INSUFFICIENT_STOCK)` at the listed sites.
3. `api_exception_handler` emits `exc.get_codes()` (or the instance code), not only `default_code`.
4. Frontend `getErrorCode(error)` beside `getErrorMessage`. **"Why?" is on the page's existing inline `Alert`.** No global toast.
5. CI later (HR-8.3) generates `helpCodes.json` from `help_codes.py`. Not in M1.

Sales and purchase Complete share a code when the fix is the same. Split into two intents only when the fix genuinely differs (e.g. a purchase-only RCM gate).

`permission_denied` is **not** a `BusinessRuleError` site. Map HTTP 403 from DRF permission classes (`IsOwner`, capability gates) → `login-cant-do-this`.

---

## The 15 sites

| # | Code | Intent | File (approx) | Current message (truncated) |
|---|---|---|---|---|
| 1 | `insufficient_stock` | `stock-in-another-godown` | `inventory/services.py` — the raise that already names other godowns | `Insufficient stock for '{name}' in godown '{wh}': available … Available in other godowns — …` |
| 2 | `inactive_product` | `sell-blocked` | `sales/services.py` `_validate_lines` | `Cannot sell inactive product '{name}'.` |
| 3 | `blocked_customer` | `sell-blocked` | `sales/services.py` Complete | `Cannot create an invoice for a blocked customer.` |
| 4 | `completed_immutable` | `edit-completed-invoice` | `sales/services.py` `set_items` **or** `sales/serializers.py` completed edit | `Cannot edit invoice in status …` / `Cancelled/returned invoice cannot be edited.` |
| 5 | `registration_gate` | `cannot-complete-invoice` | `core/services/registration_gates.py` UNREGISTERED | `Unregistered companies cannot issue GST/TAX invoices…` |
| 6 | `registration_gate` | `cannot-complete-invoice` | `core/services/registration_gates.py` COMPOSITION | `Composition dealers cannot issue regular GST tax invoices…` |
| 7 | `place_of_supply_unresolved` | `cannot-complete-invoice` | `core/services/place_of_supply.py` | `Customer/supplier state or GSTIN is required for GST invoices.` |
| 8 | `credit_limit_exceeded` | `cannot-complete-invoice` | `sales/services.py` Complete | `Credit limit exceeded. Exposure …` |
| 9 | `closed_period` | `cannot-complete-invoice` | `reporting/gst_periods.py` `assert_period_allows_money_amend` | `Cannot amend money fields: GST period …` / `accounting period covering …` |
| 10 | `company_gstin_required` | `add-gstin` | `sales/services.py` Complete | `company_gstin is required when multiple GSTINs are active.` |
| 11 | `sales_rcm_unconfirmed` | `cannot-complete-invoice` | `sales/services.py` Complete | `Sales reverse charge must be explicitly confirmed (confirm_sales_rcm=true)…` |
| 12 | `invalid_gst_rate` | `wrong-gst-on-invoice` | `sales/services.py` `_validate_lines` | `Invalid GST rate {n}. Allowed: …` |
| 13 | `allocation_exceeds_unallocated` | `payment-wont-allocate` | `payments/services.py` `allocate_receipt` | `Allocation {n} exceeds unallocated receipt amount {m}.` |
| 14 | `import_invalid_rows` | `import-row-errors` | `imports/services.py` `commit` | `Fix all errors before commit. Any invalid row blocks the entire job.` |
| 15 | `pdf_or_share_unavailable` | `pdf-or-share-unavailable` | `sales/views.py` share **or** pdf | `Only completed invoices can be shared.` / `PDF is not ready for this invoice.` |

Sites 5 and 6 share one code. That is 14 unique codes + `permission_denied` on the FE 403 path = 15 user-facing codes.

Sibling raises (purchase Complete stock check, `allocate_supplier_payment` party mismatch, second PDF raise) **may** take the same `code=` in the same PR if they are one-line additions next to a listed site. They must not expand the PR into a 687-site refactor.

## Frontend mapping

```
error.code  →  intentId          →  /help?intent=<id>  or  /help#<id>
unmapped    →  /help?q=<message>     (HR-2.5; M1 resolver)
403         →  login-cant-do-this
success     →  no "Why?" link
```

## Not in the 15 (on purpose)

- GSP / e-invoice / e-way adapter errors (operator-facing; later).
- SMS/OTP/gateway credential misses (ops, not shop-floor).
- Import CSV header / UTF-8 hints (stay as the existing message until import diagnosis lands).
- `get_codes()` sprawl across notes/challan/order status machines.
