# Quotations Remediation — Detailed Implementation Plan

**Date:** 2026-10-10 (revision 2, after plan review)  
**Companion to:** [QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md](QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md). Issue IDs (OPEN-xx) refer to that document.  
**Baseline:** commit `9cb2acb` ("Sales history and quotations: review fixes…"). The quotation change set this plan was written against was committed unchanged in that commit. At `9cb2acb`, `QuotationsPage.tsx` still has the unused `convertQuotationChain` import, the `t('key', 'Fallback')` calls, the `Math.max(0.001, …)` clamps and the `todayIso()` create date, and none of the Phase 1 i18n keys exist. Every defect below is therefore still present.  
**Goal:** Close OPEN-01 to OPEN-16 so the quotation change set can ship. Lifecycle redesign (OPEN-14) is planned in Part IV, Phase 12.  
**Scope note:** The full-product review added OPEN-17 to OPEN-43, additions to Phases 2, 3, 5 and 7, and Phases 8–14. Those are planned in [Part IV of the review document](QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md#part-iv-full-product-review-findings--implementation-plan), which also has the updated release gate. Phases 8–12 add database migrations, so the "no migrations" ground rule below applies only to Phases 1–7.

> **Revision 2 changes.** A review of this plan found real defects in it. The main changes are listed below; the review-to-change map is in [Part IV.0 of the review document](QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md#iv0-plan-review-response-revision-2).
> - Phase 2 now updates quote lines in place instead of deleting and recreating them. The Phase 9 conversion records point at quote lines, so deleting lines would fail.
> - `recompute_quotation_totals` no longer rebuilds lines at all.
> - Locked-edit errors carry machine-readable codes so a stale browser tab can tell the user to reload.
> - Phases 2 and 3 ship as one pull request.
> - Phase 8 (delete lockdown and cost masking) ships first, before everything else.
> - Phase 5's permission contradiction is resolved.
> - `is_expired` is false for closed quotes and is the only source of truth for expiry (no stored EXPIRED status, no nightly job).

---

## Implementation status (2026-10-10, updated after the closure plan)

This plan's phases and the later phases are **built**. What the review of that work found, and how it was
closed, is in [QUOTATIONS_CLOSURE_PLAN.md](QUOTATIONS_CLOSURE_PLAN.md) (status table at its top) and
[../decisions/QUOTATIONS_DECISIONS.md](../decisions/QUOTATIONS_DECISIONS.md).

| Phase | Status |
|---|---|
| 1 Build unblocked | Done. |
| 2 Safe backend updates | Done. |
| 3 Editor fixes | Done, and the dialog became the full-page editor (phase 11). |
| 4 Filters | Done. |
| 5 Server totals preview | Done; it now sends the stored header (discount, charges, round-off, cess, HSN, inclusive price). |
| 6 Server-decided expiry | Done. |
| 7 Decisions | Recorded in the decisions document. Chain-convert answers 410 from 2026-11-28 automatically. |
| 8, 9, 10 | Done: delete lock-down, cost masking, conversion ledger with release on by default and a sweep, one create path (API and CRM), idempotency. |
| 11 Full-page editor | Done: terms, charges, discount, price lists, salesperson search, stock hint, unsaved-changes guard. |
| 12 Lifecycle | Done behind the company flag `QUOTE_LIFECYCLE`; Close remaining added. |
| 13 Sharing, PDF, navigation | Done: public link and page, WhatsApp share, PDF watermark and terms, search by number, name and phone, customer transaction list links. |
| 14 List polish | Done. |

Correction: the Day Book never lists quotations. The report link change applies to the **customer
transaction list**.

---

## 1. Summary

| Order | Phase | What it does | Closes | Size | Depends on |
|---:|---|---|---|---|---|
| 1st | 8 (Part IV) | Block deleting converted quotes; hide internal cost (backend only) | OPEN-17, OPEN-21 | 1 day | — |
| 2nd | 1 | Unblock the build | OPEN-01, OPEN-08, part of OPEN-11 | 0.5 day | — |
| 3rd | 2 + 3 (one PR) | Safe backend update path with in-place line updates, plus the matching editor fixes | OPEN-02, 03, 04, 05, 06, 07, 15, 16 (API only) | 3 days | 1 |
| 4th | 4 | Consistent list filters, plus the "Partially converted" chip | OPEN-10, most of OPEN-29 | 0.5 day | 1 |
| later | 5 | Server-calculated totals preview | OPEN-09 | 1 day | 3 |
| later | 6 | Expiry decided by the server | rest of OPEN-11 | 0.5 day | 1 |
| — | 7 | Product decisions | OPEN-13 (OPEN-14 moved to Part IV, Phase 12) | decision only | — |

Phase 8 is planned in [Part IV.4 of the review document](QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md#iv4-phase-8-lock-down-delete-and-cost-visibility). It goes first because OPEN-17 and OPEN-21 are the only issues that lose records or expose data today, they are small, and they don't depend on the editor or the build. Its backend part can ship even while the web build is broken. The UI part (hiding the cost column) travels with Phases 2 + 3.

OPEN-16 is fixed on the API only. The web editor always sends `items` today, so users see no change from that fix.

Tests are written inside each phase, not saved for the end. The full test list is in [section 9](#9-test-matrix).

**Release gate:** Phase 8 and Phases 1–4 must be merged. `npm run lint`, `npm run build`, the web tests and the backend tests (including the Postgres-only tests in CI) must all pass, and the manual QA script in [section 10](#10-manual-qa-script) must pass. Phases 5 and 6 can follow in a later release. The full-product review extends this gate with Phases 9 and 10; see the review document's release gate.

### Ground rules
- Each phase is one pull request, except **Phases 2 and 3, which are one pull request**. The backend rejects payloads the old editor sends, so they must never reach production apart. A single PR enforces that; a process rule does not.
- No database migrations are needed in Phases 1–7.
- Every phase that adds or changes a serializer field or action regenerates the OpenAPI snapshot and the generated types (Phases 2, 6 and 8 at least). CI diffs both.
- Every new table with a `company` foreign key must be added to a new `core/migrations/00xx_rls_*.py` migration's `RLS_TABLES`, following `0038_rls_roadmap_tables.py`. Otherwise `tests/test_rls_coverage.py` fails. This applies to Part IV Phases 9 and 12.
- Concurrency and rollback tests that need real row locks go in `tests/test_concurrency_races.py` style files, marked `pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]`. CI runs them against Postgres 17; they skip on SQLite.
- Every new i18n key goes into **both** `web/src/i18n/en.ts` and `web/src/i18n/hi.ts`. `fullParity.test.ts` fails otherwise.
- `t(key, vars)` takes **interpolation variables** as its second argument. Never pass fallback text.

### Commands used in this plan
```powershell
# Backend (from backend/)
python -m pytest tests/test_quotation_remediation.py tests/test_cft_cross_flow.py -q
# Postgres-only race and rollback tests (skip on SQLite; CI runs them on Postgres 17)
python -m pytest tests/test_quotation_races.py -q -m postgres

# Web (from web/)
npx vitest run src/pages/sales/QuotationsPage.test.tsx src/pages/sales/ConvertQuotationDialog.test.tsx src/utils/quotationConvert.test.ts src/utils/quotationPayload.test.ts src/i18n
npm run lint
npm run build
```

---

## 2. Phase 1 — Unblock the build

**Closes:** OPEN-01, OPEN-08, and the hard-coded English label in OPEN-11.  
**Files:** `web/src/pages/sales/QuotationsPage.tsx`, `web/src/pages/sales/ConvertQuotationDialog.tsx`, `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`.

### 2.1 Remove the unused import
Delete `convertQuotationChain` from the `@/api/resources` import in `QuotationsPage.tsx`. Leave the API function in `sales.ts` until the Phase 7 decision.

### 2.2 Replace every `t('key', 'Fallback')` call
Some calls can reuse a key that already exists; others need a new one.

| Current call in `QuotationsPage.tsx` | Replace with | New key? |
|---|---|---|
| `t('billing.selectCustomerRequired', …)` | `t('billing.customerRequired')` | No |
| `'Add at least one product'` (hard-coded) | `t('billing.addAtLeastOneItem')` | No |
| `'Quotation created'` (hard-coded) | `t('phase1.quotationCreated')` | Yes |
| `t('status.quotationCancelled', …)` | `t('phase1.quotationCancelled')` | Yes |
| `t('status.cancelled', 'Cancelled')` | `t('status.cancelled')` | No |
| `t('billing.validUntil', 'Valid Until')` | `t('billing.validUntil')` | No |
| `t('status.expired', 'Expired')` | `t('status.expired')` | Yes |
| `t('common.confirmCancelQuotation', …)` | `t('phase1.confirmCancelQuotation')` | Yes |
| `t('billing.quotationLinesLocked', …)` | `t('phase1.quotationLinesLocked')` | Yes |
| `t('common.date', 'Quotation Date')` (dialog field) | `t('phase1.quotationDate')` | Yes |
| `t('billing.expectedPrice', 'Est. Cost')` | `t('billing.expectedPrice')` (text changed below) | No |
| `t('common.subtotal', 'Subtotal')` | `t('billing.subtotal')` | Yes |
| `t('billing.estimatedTax', 'Est. GST')` | `t('billing.estimatedTax')` | Yes |
| `t('common.total', 'Total')` | `t('common.total')` | No |

In `ConvertQuotationDialog.tsx`, replace the template-string label with `t('phase1.quotationExpiredConfirm', { date: quotation?.validUntil ?? '' })`.

### 2.3 New and changed i18n strings

| Key | English (`en.ts`) | Hindi (`hi.ts`) |
|---|---|---|
| `status.expired` | Expired | अवधि समाप्त |
| `phase1.quotationDate` | Quotation date | कोटेशन तिथि |
| `phase1.quotationCreated` | Quotation created | कोटेशन बनाया गया |
| `phase1.quotationCancelled` | Quotation cancelled | कोटेशन रद्द किया गया |
| `phase1.confirmCancelQuotation` | Cancel this quotation? This cannot be undone. | यह कोटेशन रद्द करें? इसे वापस नहीं लिया जा सकता। |
| `phase1.quotationLinesLocked` | Part of this quotation has already been converted. Lines, customer and quotation date are locked. You can still change validity, salesperson, sales channel and delivery address. | इस कोटेशन का कुछ हिस्सा पहले ही बदला जा चुका है। लाइनें, ग्राहक और कोटेशन तिथि लॉक हैं। आप अभी भी वैधता, सेल्समैन, बिक्री चैनल और डिलीवरी पता बदल सकते हैं। |
| `phase1.quotationExpiredConfirm` | This quotation expired on {date}. Convert it at the quoted prices anyway. | यह कोटेशन {date} को समाप्त हो गया। फिर भी कोटेशन की कीमतों पर बदलें। |
| `billing.estimatedTax` | Estimated GST | अनुमानित GST |
| `billing.subtotal` | Subtotal | उप-योग |
| `billing.expectedPrice` *(text change)* | Est. cost (internal) | अनुमानित लागत (आंतरिक) |

**Subtotal vs taxable amount.** The dialog's figure is the sum of line amounts before any header discount, so it is a subtotal, not the taxable amount. The two differ once a header discount applies (quotes created through the API can have one). The only existing `subtotal` key is `pos.subtotal` ("SUBTOTAL", a receipt label), so add `billing.subtotal`. Phase 5 replaces this figure with the server's taxable amount, labelled `billing.taxableAmount`.

**`billing.expectedPrice` rename.** The key is also used by `SalesOrderEditorPage.tsx`, where it means the same thing (the cost basis for expected profit), so the rename is intended there too.
- No web test or Playwright spec matches the text "Expected price" at `9cb2acb` (checked in `web/src`, `web/e2e`, `web/e2e-golden`).
- Re-check before merging, and check the Hindi string on the sales order editor.

### 2.4 Phase 1 done when
- `npm run lint` passes. `npm run build` passes, which proves `tsc -b` is clean.
- `npx vitest run src/i18n` passes, which proves en/hi parity.
- The existing quotation tests still pass.

---

## 3. Phase 2 — Backend: safe quotation updates

**Closes:** OPEN-02, OPEN-03, the API side of OPEN-04, OPEN-16 (API only) and OPEN-33.  
**Files:**
- `backend/sales/serializers.py` (`QuotationSerializer`, `QuotationItemSerializer`)
- `backend/sales/services.py` (`set_quotation_items` rewritten, new `recompute_quotation_totals`)
- `backend/tests/test_quotation_remediation.py`
- new `backend/tests/test_quotation_races.py`

**Why lines are now updated in place.** Today `set_quotation_items` deletes every line and recreates it (`quotation.items.all().delete()`). That gives every line a new ID on each save, and it conflicts with Part IV Phase 9: conversion records point at quote lines. Once a quote has been converted and the conversion released, the next line edit would delete referenced lines. With a protected foreign key that is a 500 error; even with `SET_NULL`, the history loses its link. Updating lines in place, matched by ID, avoids both problems. It is decided here, before any Phase 2 code lands, so the ledger design doesn't force a rewrite later.

### 3.1 Rules
1. Only `DRAFT` quotations can be edited. This rule is unchanged.
2. If **any** line has `converted_quantity > 0`:
   - `items` must not be in the request. Its presence is rejected even if the lines are identical.
   - Only these fields may change: `valid_until`, `notes`, `terms_text`, `delivery_address`, `salesman`, `sales_channel`. Any other field is rejected with one error that lists the blocked fields.
3. If nothing has been converted:
   - If `items` is present, lines are **updated in place**:
     - A row with an `id` updates that line. The ID must belong to this quote; otherwise the request is rejected.
     - A row without an `id` creates a new line.
     - Existing lines missing from the request are deleted.
     - Clients that send no IDs at all (the current editor, the CRM path, a stale browser tab) get today's behaviour: every old line is deleted and the new ones created.
   - If `items` is absent but a field that affects totals changed, totals are recalculated from the existing lines **without rebuilding them**. This fixes OPEN-16. The fields that affect totals are `customer`, `invoice_type`, `supply_type`, `company_gstin`, `additional_charges`, `charges_hsn`, `charges_gst_rate`, `invoice_discount`, `invoice_discount_mode` and `auto_round_off`.
4. All checks run **before** any write, inside one transaction that holds a row lock on the quotation. `convert_quotation` and `convert_quotation_to_order` already lock the same row, so an edit and a conversion can't interleave. `set_quotation_items` also takes the lock itself, because the CRM path calls it without going through the serializer (OPEN-33).
5. Rejections from rules 1 and 2 carry a machine-readable `code`, so the web app can tell a user with a stale tab to reload rather than showing raw prose:
   - `quotation_not_editable` (rule 1);
   - `quotation_lines_locked` (`items` sent after partial conversion);
   - `quotation_fields_locked`, with `extra={"fields": [...]}` listing the blocked fields.
   
   `BusinessRuleError(detail, code=..., extra=...)` already supports both arguments. The messages end with "Reload the page and try again." so old clients that only show the prose still guide the user.
6. Read-only fields stay read-only. `number`, `status`, `converted_invoice`, `converted_order`, `expected_profit` and the totals are in `read_only_fields` (checked at `9cb2acb`), so they never reach `validated_data`. The whitelist in rule 2 works by exclusion, so `customer` and `quotation_date` are blocked without being listed.

### 3.2 Code shape

The block below shows the intended structure; it is not final code. Delete the existing product/quantity comparison branch entirely.

```python
POST_CONVERSION_EDITABLE = frozenset({
    "valid_until", "notes", "terms_text", "delivery_address", "salesman", "sales_channel",
})
TOTALS_AFFECTING = frozenset({
    "customer", "invoice_type", "supply_type", "company_gstin", "additional_charges",
    "charges_hsn", "charges_gst_rate", "invoice_discount", "invoice_discount_mode",
    "auto_round_off",
})

def update(self, instance, validated_data):
    from django.db import transaction

    from core.exceptions import BusinessRuleError

    user = self.context["request"].user
    items_data = validated_data.pop("items", None)
    with transaction.atomic():
        instance = Quotation.objects.select_for_update().get(pk=instance.pk)
        if instance.status != Quotation.Status.DRAFT:
            raise BusinessRuleError("Only draft quotations can be edited.")
        has_converted = instance.items.filter(converted_quantity__gt=0).exists()
        if has_converted:
            if items_data is not None:
                raise BusinessRuleError(
                    "Lines are locked because part of this quotation has been converted. "
                    "Reload the page and try again.",
                    code="quotation_lines_locked",
                )
            blocked = sorted(set(validated_data) - POST_CONVERSION_EDITABLE)
            if blocked:
                raise BusinessRuleError(
                    "Part of this quotation has been converted; these fields can no "
                    f"longer change: {', '.join(blocked)}. Reload the page and try again.",
                    code="quotation_fields_locked",
                    extra={"fields": blocked},
                )
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesService.set_quotation_items(instance, [dict(l) for l in items_data], user)
        elif not has_converted and TOTALS_AFFECTING & set(validated_data):
            SalesService.recompute_quotation_totals(instance, user)
    return instance
```

**Notes on the sketch:**
- `items` must be popped **before** `super().update()`. DRF's `ModelSerializer.update` calls `raise_errors_on_nested_writes`, which raises if a writable nested field is still in `validated_data`. The current code already pops first; keep it that way.
- `QuotationItemSerializer` needs a writable `id = serializers.IntegerField(required=False)`. A `ModelSerializer` makes `id` read-only by default, so without this the IDs never reach the service.
- The `BusinessRuleError` raised inside `transaction.atomic()` rolls back the header write. This is proven on Postgres in §3.4, not only on SQLite.

**`set_quotation_items`, rewritten for in-place updates:**

```python
@staticmethod
@transaction.atomic
def set_quotation_items(quotation, items_data, user):
    quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
    if quotation.status != Quotation.Status.DRAFT:
        raise BusinessRuleError("Only draft quotations can be edited.", code="quotation_not_editable")
    if quotation.items.filter(converted_quantity__gt=0).exists():
        raise BusinessRuleError("…", code="quotation_lines_locked")
    _validate_lines(items_data, quotation.company)
    existing = {item.id: item for item in quotation.items.all()}
    keep_ids = {row["id"] for row in items_data if row.get("id")}
    if keep_ids - existing.keys():
        raise BusinessRuleError("Unknown quotation line.", code="quotation_unknown_line")
    for row in items_data:
        if row.get("id") and "expected_price" not in row:
            row["expected_price"] = existing[row["id"]].expected_price  # see Phase 8 masking
    built = _build_items(QuotationItem, "quotation", quotation, items_data)
    for obj, row in zip(built, items_data):
        if row.get("id"):
            obj.pk = row["id"]
            obj._state.adding = False
    _compute_quotation_totals(quotation, built)  # the tax-engine call moved out of today's body
    quotation.items.exclude(pk__in=keep_ids).delete()
    QuotationItem.objects.bulk_update([o for o in built if o.pk], QUOTATION_LINE_WRITE_FIELDS)
    QuotationItem.objects.bulk_create([o for o in built if not o.pk])
    quotation.updated_by = user
    quotation.save()
    return quotation
```

- `QUOTATION_LINE_WRITE_FIELDS` is every concrete `QuotationItem` field except `id`, `company`, `quotation` and `converted_quantity`. Build it from `QuotationItem._meta.concrete_fields` rather than typing it out, so new columns aren't silently skipped.
- `_build_items` only copies keys it knows about. The round-trip test in §3.4 catches any column that a save would reset.
- Removed lines are deleted before the update. Lines with conversion records can't reach this code, because any converted quantity locks the lines. After Part IV Phase 9, lines whose conversions were all released *can* be removed; Phase 9 uses `on_delete=SET_NULL` plus a snapshot on the conversion record for that case.

### 3.3 New service helper: `SalesService.recompute_quotation_totals`
Add this next to `set_quotation_items` in `services.py`. Revision 1 of this plan rebuilt the lines from `existing_lines_as_items_data` (in `core/services/h9_amend.py`). That was wrong:
- the helper omits `expected_price`;
- it omits any other column `_build_items` doesn't copy, which would be reset to its default;
- it gave every line a new ID.

The helper now recalculates on the existing line objects and writes back only the calculated fields:

```python
@staticmethod
@transaction.atomic
def recompute_quotation_totals(quotation, user):
    quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
    items = list(quotation.items.select_related("product").order_by("id"))
    _compute_quotation_totals(quotation, items)
    QuotationItem.objects.bulk_update(items, LINE_COMPUTED_FIELDS)
    quotation.updated_by = user
    quotation.save()
    return quotation
```

- `_compute_quotation_totals` is the `get_tax_engine(...).compute_document_totals(...)` call taken out of today's `set_quotation_items` body, so both paths share it.
- `LINE_COMPUTED_FIELDS` are the per-line fields the tax engine writes. On `DocumentLineModel` the calculated columns are likely `applied_rate`, `rate_version`, `taxable_amount`, `cgst`, `sgst`, `igst`, `cess` and `line_total`.
  - `cess_amount` is **not** calculated: it is the per-unit specific-cess input, so it must be preserved.
  - Needs verification: confirm the list against `core.services.billing._apply_line_tax` and the tax engine. The round-trip test below fails if it's wrong in either direction.
- Line IDs and every non-computed column, including `expected_price`, are untouched.

### 3.4 Tests to add (`backend/tests/test_quotation_remediation.py`)
Build a "partially converted quote" fixture that creates a quote with 10 units and converts 4 to an order.

| Test | Asserts |
|---|---|
| `test_partial_quote_rejected_patch_writes_nothing` | A PATCH with `notes` and `items` returns 400. Reloading from the database shows `notes` unchanged. |
| `test_partial_quote_rejects_items_even_if_identical` | A PATCH that re-sends the exact same lines returns 400. |
| `test_partial_quote_rejects_price_change` | A PATCH with a changed `unit_price` returns 400 and the stored price is unchanged. |
| `test_partial_quote_rejects_customer_and_discount` | A PATCH with `customer` or `invoice_discount` returns 400. The error lists both fields, and `grand_total` and `customer` are unchanged. |
| `test_partial_quote_allows_whitelisted_header` | A PATCH with `valid_until`, `delivery_address`, `salesman`, `sales_channel`, `notes` and `terms_text` returns 200 and every value is saved. |
| `test_unconverted_header_change_recomputes_totals` | A PATCH with only `invoice_discount=100` changes `grand_total`, and line `expected_price` values are kept. |
| `test_unconverted_items_patch_still_replaces_lines` | Existing behaviour still works. |
| `test_non_draft_quote_cannot_be_edited` | PATCH on a CONVERTED or CANCELLED quote returns 400 with code `quotation_not_editable`. |
| `test_locked_errors_carry_codes` | The rejections above return `quotation_lines_locked` and `quotation_fields_locked`; the latter's details list the blocked fields. |
| `test_read_only_fields_ignored` | A PATCH with `status`, `number` or `grand_total` changes none of them. |
| `test_items_update_in_place_keeps_line_ids` | A PATCH that sends existing lines with their `id`s and a changed quantity keeps the same line IDs. |
| `test_items_without_ids_replace_lines` | A PATCH with lines that have no `id` (old clients, CRM) still replaces every line. |
| `test_removed_line_is_deleted` | Leaving a line out of `items` deletes it. |
| `test_foreign_line_id_rejected` | An `id` from another quote, including one in another company, returns 400 with code `quotation_unknown_line`, and nothing changes. |
| `test_recompute_round_trip_keeps_every_column` | Create a quote with every line column set to a non-default value: `expected_price`, `discount_percent`, `cess_rate`, `cess_amount`, `unit_price_inclusive`, `supply_nature`, `hsn_code`, `description`, `rate_override` and `rate_override_reason`. Run `recompute_quotation_totals`. Every `QuotationItem` column except `LINE_COMPUTED_FIELDS` is identical, including `id`. The computed fields equal a fresh calculation. |
| `test_recompute_keeps_expected_price_mix` | Lines with `expected_price` 0, a decimal value, and the model default all keep their values after recompute. |
| `test_convert_without_confirm_expired_rejected` | Converting an expired quote without `confirm_expired` returns 400 (gap listed in Part II). |

Update the existing `test_quotation_cancel_and_partially_converted_header_update`. It currently sends `items` with a partially converted quote, which is now a 400. Remove `items` from that PATCH.

**Postgres-only tests (`backend/tests/test_quotation_races.py`).** Use the `tests/test_concurrency_races.py` pattern, `pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]`:

| Test | Asserts |
|---|---|
| `test_rejected_patch_rolls_back_on_postgres` | Same as `test_partial_quote_rejected_patch_writes_nothing`, against a real Postgres transaction. |
| `test_edit_waits_for_conversion_lock` | Thread A opens a transaction and locks the quote, as a conversion does, then converts 4 units. Thread B sends a line edit at the same time. B either fails with `quotation_lines_locked` or runs after A commits and is rejected. The final `converted_quantity` is 4 in every ordering. |
| `test_crm_path_takes_the_lock` | The same race through `SalesService.set_quotation_items` called directly, as the CRM action does. |

### 3.5 Phase 2 done when
All new tests pass, including the Postgres-only ones in CI. `test_cft_cross_flow.py` and the wider sales suite (`python -m pytest tests -q -k "quotation or cft"`) are green.

---

## 4. Phase 3 — Quotation editor fixes

**Closes:** OPEN-04 (UI), OPEN-05, OPEN-06, OPEN-07, OPEN-15.  
**Files:** `web/src/pages/sales/QuotationsPage.tsx`, new `web/src/utils/quotationPayload.ts` with `quotationPayload.test.ts`, and `web/src/pages/sales/QuotationsPage.test.tsx`.

### 4.1 Move payload building into a pure function (OPEN-04, OPEN-05, OPEN-15)
Create `web/src/utils/quotationPayload.ts`:

```ts
export type QuotationFormState = {
  customerId: number;
  quotationDate: string;
  validUntil: string;
  salesman: string;
  salesChannel: string;
  deliveryAddress: string;
  invoiceType: string;
  lines: Array<{ id?: number; productId: number; qty: number; unitPrice: number; discountPercent: number; expectedPrice?: number; gstRate: number }>;
  canSeeCost: boolean;
};

export type QuotationPayloadMode = 'create' | 'edit' | 'edit-partially-converted';

export function buildQuotationPayload(form: QuotationFormState, mode: QuotationPayloadMode): Record<string, unknown>;
```

The payload depends on the mode:

| Field | `create` | `edit` | `edit-partially-converted` |
|---|---|---|---|
| `customer` | ✅ | ✅ | — |
| `quotationDate` | ✅ the **selected** date (OPEN-05) | ✅ | — |
| `invoiceType` | ✅ from `preferredInvoiceType` | — (keep the stored value, OPEN-15) | — |
| `validUntil`, `salesman`, `salesChannel`, `deliveryAddress` | ✅ | ✅ | ✅ |
| `items` | ✅ | ✅ | — |
| line `id` | — | ✅ for lines loaded from the server | — |
| line `expectedPrice` | only if `canSeeCost` | only if `canSeeCost` | — |

`createMutation` picks the mode from `editingId` and `isPartiallyConverted`, then calls `buildQuotationPayload`. Its customer and line checks apply to `create` and `edit` only.

- **Line IDs.** Keep each loaded line's server `id` in the form state and send it back, so the backend updates lines in place (Phase 2 rule 3).
- **Cost.** `canSeeCost` is `canViewFinancialReports(user)`. When false, the cost column is hidden and `expectedPrice` is never sent; the backend keeps the stored value (Part IV, Phase 8).

**Handling locked-edit errors.** When a save fails with code `quotation_lines_locked`, `quotation_fields_locked` or `quotation_not_editable`, the quote has changed since the form was opened (for example, someone converted it in another tab). Show `t('phase1.quotationChangedReload')` with a Reload button that refetches the quote and resets the form. Add the key: "This quotation changed since you opened it. Reload to see the latest version." / "आपके खोलने के बाद यह कोटेशन बदल गया है। नवीनतम संस्करण देखने के लिए फिर से लोड करें।" Needs verification: how the API client exposes the error envelope's `code` and `details` (other pages that read a backend error code show the pattern).

### 4.2 Lock the right fields when a quote is partially converted (OPEN-04)
When `isPartiallyConverted` is true:
- **Locked:** the customer autocomplete, the "Add party" row, the quotation date field, every line input, and the add-line row (already hidden).
- **Still enabled:** valid until, salesman, sales channel and delivery address.
- **Banner:** keep it, using `phase1.quotationLinesLocked`, which lists what can still change.
- **Save button:** for this mode, don't require `lines.length > 0`, because lines aren't sent.

**Accessibility of locked fields.** A `disabled` MUI input can't receive focus, so keyboard and screen-reader users can't read its value or learn why it's locked; the banner is the only explanation.
- Render locked text fields as read-only instead: `InputProps={{ readOnly: true }}` plus `aria-readonly="true"`.
- Point each one at the banner with `aria-describedby` (give the banner an `id` and `role="status"`).
- Keep `disabled` only for controls that have no value to read, such as the "Add party" button.
- The same applies to the read-only mode for non-draft quotes in Part IV (OPEN-27).

### 4.3 Quantity and number inputs (OPEN-06)
- Replace the controlled `type="number"` fields for line quantity and pending quantity with `NumericField` from `@/components/billing`, using `decimals={3}`, `min={0}` and `emptyAs={0}`. `NumericField` keeps the raw text while the user types and only snaps the value on blur. This is the same component `DraftLineTable` uses.
- Change `addLine` and `updateLine` so they no longer coerce to 0.001. Keep the value the user typed.
- Validate when saving: if any line has `qty <= 0`, the mutation throws `t('billing.qtyMustBePositive')`. This is a new key: "Quantity must be greater than 0" / "मात्रा 0 से अधिक होनी चाहिए". The offending row's quantity field also gets `error` and helper text.
- Disable the "Add" button while the pending quantity is ≤ 0.
- Optional, for consistency: move unit price, discount and expected cost to `NumericField` as well (`decimals={2}`; discount `max={100}`).

### 4.4 Cancel permission (OPEN-07)
- Import `canCancelDocuments` from `@/utils/permissions`.
- Change the per-row `canCancel` check to `q.status === 'DRAFT' && canCancelDocuments(user) && no converted quantity`.
- The row actions currently only render when `isConvertible` (which needs `canCreate`). Restructure so a user who can cancel but can't create still sees Download and Cancel.
- Replace `window.confirm` with the shared `ConfirmDialog` from `web/src/components/ConfirmDialog.tsx`, so the confirmation is styled, translated and testable.

### 4.5 Tests

**`web/src/utils/quotationPayload.test.ts` (new):**
- `create` sends the selected `quotationDate`, not today's date.
- `create` includes `invoiceType`; `edit` does not.
- `edit-partially-converted` sends only `validUntil`, `salesman`, `salesChannel` and `deliveryAddress`.
- Decimal quantities pass through unchanged (for example 2.5).

**`QuotationsPage.test.tsx`** (add a `/sales/quotations/:id` route to `mount`):
- Rename the misnamed list test, and make it check that a DRAFT row shows Number, Date, Valid Until, Customer, Status, Total and a Cancel button for an OWNER.
- With a role that has `canCreateSales` but not `canCancelDocuments`, no Cancel button is shown.
- When `getQuotation` returns a line with `convertedQuantity > 0`, the customer, quotation date and line quantity fields are disabled. Saving calls `updateQuotation` **without** `items`, `customer` or `quotationDate`.
- A line's quantity field can be cleared and retyped to `2.5`, and saving sends `quantity: 2.5`.
- Saving with a 0 quantity shows the validation message and does not call `updateQuotation`.
- An expired DRAFT row shows the "Expired" badge.
- Editing an unconverted quote sends each loaded line's `id`.
- A save rejected with code `quotation_lines_locked` shows the reload message, and Reload refetches the quote.
- Locked fields are focusable, read-only, and described by the banner (`aria-describedby`).
- For a user without `canViewFinancialReports`, the cost column is hidden and the payload has no `expectedPrice`.

**`backend/tests/test_quotation_remediation.py`:**
- `test_cancel_requires_cancel_permission`: a SALES_STAFF user with `can_create_sales=True` and `can_cancel_documents=False` gets 403 from `POST /sales/quotations/{id}/cancel/`, and the quote stays DRAFT. The same user with `can_cancel_documents=True` gets 200. The fixture's staff user lacks `can_create_sales` by default; set both flags explicitly.

### 4.6 Phase 3 done when
The web tests above pass, `npm run lint` and `npm run build` pass, and manual QA scenarios 1–6 and 9 in [section 10](#10-manual-qa-script) pass.

---

## 5. Phase 4 — List filters

**Closes:** OPEN-10.  
**Files:** `backend/sales/views.py` (`QuotationViewSet.get_queryset`), `web/src/pages/sales/QuotationsPage.tsx`, tests.

### 5.1 Backend
Follow the invoice list's validation (the B2-020 comment in `SalesInvoiceViewSet.get_queryset`):

```python
from datetime import date as _date

params = self.request.query_params
status = params.get("status")
if status:
    if status not in Quotation.Status.values:
        raise BusinessRuleError(f"Unknown status {status!r}.")
    qs = qs.filter(status=status)
if params.get("customer"):
    try:
        qs = qs.filter(customer_id=int(params["customer"]))
    except (TypeError, ValueError):
        raise BusinessRuleError("customer must be a numeric id.")
for key, lookup in (("date_from", "quotation_date__gte"), ("date_to", "quotation_date__lte")):
    raw = params.get(key)
    if raw:
        try:
            qs = qs.filter(**{lookup: _date.fromisoformat(str(raw)[:10])})
        except ValueError:
            raise BusinessRuleError(f"{key} must be an ISO date (YYYY-MM-DD).")
term = (params.get("q") or "").strip()[:100]
if term:
    qs = qs.filter(
        Q(number__icontains=term)
        | Q(customer__name__icontains=term)
        | Q(customer__phone__icontains=term)
    )
```

### 5.2 Frontend
- Add a customer picker to `HistoryFilterBar` using its `party` prop. Copy the pattern in `SalesHistoryPage.tsx` (`useCustomerSearch` plus `Autocomplete`).
- Store the selected customer ID in state. Pass it as `customer` to `listQuotationsPage`, add it to the query key, and reset `page` to 1 when it changes.
- **"Partially converted" chip (most of OPEN-29).** For a DRAFT row where any line has `convertedQuantity > 0`, show a "Partially converted" chip next to the status. This needs no backend change: the list response already includes `items` with `converted_quantity` (the viewset prefetches `items__product`). Add `phase1.partiallyConverted`: "Partially converted" / "आंशिक रूप से परिवर्तित". The remaining value is added later in Part IV, Phase 12.

### 5.3 Tests (backend)
- `test_quotation_filter_by_customer`: only that customer's quotes are returned.
- `test_quotation_search_by_number_and_phone`.
- `test_quotation_invalid_filters_return_400`, parameterised over `status=BOGUS`, `customer=abc` and `date_from=notadate`.
- `test_quotation_list_is_company_scoped`: tenant B's quotes never appear for tenant A, even when the search matches.

Frontend: choosing a customer in the picker calls `listQuotationsPage` with `customer: <id>`.

---

## 6. Phase 5 — Server-calculated totals preview

**Closes:** OPEN-09.  
**Files:** `web/src/pages/sales/QuotationsPage.tsx`, i18n, tests.

### 6.1 Approach
Reuse the existing `usePreviewTotals('sales', body)` hook (`web/src/hooks/usePreviewTotals.ts`). It calls `POST /sales/invoices/preview-totals/`, which uses the same tax engine as saving.

**Permission (resolved, checked at `9cb2acb`).** `SalesInvoiceViewSet.get_permissions` lists `preview_totals` with `CanViewSalesSurfaces`, the same permission as the quotation list. So every quote user gets totals, and no backend change is needed for them. Margin is separate:
- `_preview_bundle` sets `include_margin` only when the user has `CanViewFinancialReports` **and** the request sends a `warehouse`.
- That margin is based on warehouse stock cost, not on the quote's `expected_price`.

Revision 1 of the Part IV plan wrongly marked the permission as "Needs verification"; that note is replaced.

The request body is built from the form state. Send every field the save path uses, or the preview won't match the saved total:
- `customer`, `supplyType`, `companyGstin`
- `invoiceType`: the quote's stored type when editing, otherwise `preferredInvoiceType`
- `priceMode`, if the quote stores one
- `items`: `product`, `quantity`, `unitPrice`, `unitPriceInclusive`, `discountPercent`, `gstRate`, `cessRate`, `cessAmount`, `supplyNature`
- Header fields the quote stores (`additionalCharges`, `chargesGstRate`, `invoiceDiscount`, `invoiceDiscountMode`, `autoRoundOff`) once the editor exposes them. Until then, send the values loaded from the quote (or the model defaults on create), not hard-coded defaults.
- Don't send `warehouse`. The quote's profit figure comes from `expected_price` (see OPEN-38 in Part IV), not from stock cost.

Send the body only when a customer is selected and at least one line exists; otherwise send `null`.

### 6.2 What the panel shows
- Taxable amount (`billing.taxableAmount`).
- Either CGST and SGST, or IGST (`billing.cgst`, `billing.sgst`, `billing.igst`), based on `preview.intraState`.
- Cess, when it is greater than 0 (`billing.cess`).
- Round off, when it isn't 0 (`billing.roundOff`).
- Grand total (`billing.grandTotal`).

While `pending` is true, show the previous totals with a small spinner. If `error` is set or the preview isn't ready, show the current client-side estimate labelled `billing.estimatedTax`, with the existing `billing.previewUnavailableClientTotals` message.

### 6.3 Tests
- **Web:** mock `previewSalesTotals`.
  - When `intraState: true`, CGST and SGST are shown and IGST is hidden.
  - When the preview fails, the estimate and the "unavailable" message are shown.
- **Backend parity test:** the `grand_total` of a saved quotation equals `preview-totals` for the same lines and header. This keeps the preview honest if the two code paths drift. Parameterise it over:
  - an intra-state and an inter-state customer;
  - a tax-inclusive line (`unit_price_inclusive`);
  - a line with ad-valorem cess (`cess_rate`) and one with specific cess (`cess_amount`);
  - a header discount with each `invoice_discount_mode`;
  - additional charges with GST;
  - `auto_round_off` on and off;
  - a non-GST invoice type.
- **Permission test:** a SALES_STAFF user without `CanViewFinancialReports` gets 200 from preview-totals and no margin fields.

---

## 7. Phase 6 — Expiry decided by the server

**Closes:** the browser-versus-server date mismatch in OPEN-11.  
**Files:** `backend/sales/serializers.py`, `web/src/types/domain.ts`, `QuotationsPage.tsx`, `ConvertQuotationDialog.tsx`, the OpenAPI snapshot and the generated types.

1. Add a read-only field to `QuotationSerializer`: `is_expired = SerializerMethodField()`.
   - It returns `obj.status == Quotation.Status.DRAFT and bool(obj.valid_until and timezone.localdate() > obj.valid_until)`. The date rule is the one the convert services use.
   - Cancelled and converted quotes are never "expired", so the badge doesn't appear on closed quotes. After Part IV Phase 12, replace the status check with `obj.status in Quotation.OPEN`.
   - This computed field is the **only** source of truth for expiry. Part IV Phase 12 no longer adds a stored EXPIRED status or a nightly job.
2. Add `isExpired?: boolean` to the `Quotation` type in `web/src/types/domain.ts`.
3. Use `q.isExpired` for the list badge and in `ConvertQuotationDialog`. Fall back to the `todayIso()` comparison only when the field is missing (for example, mocks).
4. Regenerate the generated API files, because CI diffs both:
   ```powershell
   # from backend/
   python manage.py spectacular --format openapi-json --file ../docs/openapi-snapshot.json
   # from web/
   npm run gen:api-types
   ```
5. Tests:
   - **Backend:** create quotes with `valid_until` set to yesterday and to today, and check that `is_expired` is true and false respectively. A CANCELLED quote and a CONVERTED quote with `valid_until` yesterday both return false. `freezegun` is in `requirements-dev.txt` if a fixed clock is needed.
   - **Web:** the dialog shows the checkbox when `isExpired: true`, even if `validUntil` is today's date on the client.

---

## 8. Phase 7 — Product decisions

These aren't engineering tasks. Each needs an owner and a decision before the next release.

### 8.1 Chain-convert endpoint (OPEN-13)

| Option | What it involves | Recommendation |
|---|---|---|
| **A. Deprecate the endpoint** | Mark `convert_chain` as deprecated in the schema (`@extend_schema(deprecated=True)`), log each call, remove it after two releases if nobody uses it, and delete `convertQuotationChain` from `sales.ts`. | **Recommended**, unless logs show real use. |
| B. Bring the shortcut back with confirmation | Add a dialog that lists each stage (Sales Order → Delivery Challan → Invoice), states that stock will be deducted, and requires an explicit tick, as the expiry confirmation does. | Only if sales teams ask for it. |

Either way, add a release note saying the one-click "Convert → SO → DC" button was removed from the quotation list.

**Evidence before removal.** "Nothing in the web app calls it" isn't enough on its own; a mobile build or an integration might. In release N:
- log every call to `convert_chain` with the company ID, user ID, `stop_stage` and `User-Agent`;
- count the calls in the existing telemetry so usage can be charted. Needs verification: whether `insights.telemetry` has a counter; `note_once` is first-use only.

Return 410 in a later release only if there were no calls for the whole period, at least 4 weeks. This also measures the effect of removing the button: the endpoint calls should drop to zero once no web client sends them.

### 8.2 Lifecycle gaps (OPEN-14)
Now planned in [Part IV, Phase 12](QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md#iv8-phase-12-lifecycle-and-expiry).
- The "Partially converted" chip moved into Phase 4 of this plan.
- Sharing moved to Part IV, Phase 13.

### 8.3 Cost visibility (resolved)
Revision 1 asked whether `expected_price` should be gated like `expected_profit`. It should: this is now OPEN-21, fixed in Part IV, Phase 8, which ships first.

---

## 9. Test matrix

| Area | Test | Layer | Phase |
|---|---|---|---|
| Build | lint and `tsc -b` clean | CI | 1 |
| i18n | en/hi parity | Unit (web) | 1 |
| Update safety | rejected PATCH writes nothing | API | 2 |
| Update safety | items always rejected after partial conversion | API | 2 |
| Update safety | price, customer and discount changes rejected after partial conversion | API | 2 |
| Update safety | whitelisted header fields saved | API | 2 |
| Totals | header-only change recalculates totals and keeps expected cost | API | 2 |
| Totals | recompute round-trip keeps every non-computed column and line IDs | API | 2 |
| Lines | in-place update keeps IDs; no-ID payload replaces; foreign ID rejected | API | 2 |
| Errors | locked edits return machine-readable codes | API | 2 |
| Concurrency | rejected PATCH rolls back; edit vs convert race; CRM path locks | API (Postgres only) | 2 |
| Editor | reload message on locked-edit error codes | Component | 3 |
| Accessibility | locked fields focusable, read-only, described by banner | Component | 3 |
| Cost | cost column hidden and not sent without financial-report permission | Component | 3 |
| List | "Partially converted" chip | Component | 4 |
| Totals | preview permission for sales staff; no margin fields | API | 5 |
| Expiry | `is_expired` false for cancelled and converted quotes | API | 6 |
| Payload | create sends selected date and invoice type | Unit (web) | 3 |
| Payload | partial-edit payload contains only whitelisted fields | Unit (web) | 3 |
| Editor | locked fields when partially converted | Component | 3 |
| Editor | quantity can be cleared, retyped and saved as a decimal | Component | 3 |
| Editor | qty ≤ 0 blocks save | Component | 3 |
| Permissions | Cancel hidden without cancel permission | Component | 3 |
| Permissions | staff without cancel permission gets 403 from cancel API | API | 3 |
| Filters | customer, number and phone search | API | 4 |
| Filters | invalid params return 400 | API | 4 |
| Filters | company scoping | API | 4 |
| Totals | CGST/SGST vs IGST display; fallback | Component | 5 |
| Totals | preview equals saved total | API | 5 |
| Expiry | `is_expired` from server date | API | 6 |
| Expiry | dialog uses `isExpired` | Component | 6 |
| Expiry | convert without `confirm_expired` rejected | API | 2 (add with the other API tests) |

Also run the existing Playwright specs `web/e2e/sales/quotations-picker-visibility.spec.ts` and `web/e2e-golden/quotation-inline-customer.spec.ts` before release.

---

## 10. Manual QA script

Run as OWNER, then repeat steps 5 and 6 as a SALES_STAFF user without cancel permission.

1. **Create with a past date:** New quotation, pick a customer, set the quotation date to 5 days ago, add a product with qty 2.5 and save. The list shows that date and the line shows 2.5.
2. **Edit an unconverted quote:** Change the price and the quantity (clear the field and type 3), then save. The new values are kept and the total updates.
3. **Partial conversion:** Use To Order with 1 of the 3 units, then open Edit. Customer, date and lines are disabled, and the banner explains why. Change Valid Until and the delivery address, then save. Both are saved and the total is unchanged.
4. **Expired conversion:** Set Valid Until to yesterday and click Convert. The checkbox is required; tick it and convert. A draft invoice is created.
5. **Cancel:** On a fresh unconverted quote, Cancel is visible for OWNER and works. It is hidden for SALES_STAFF without cancel permission.
6. **Filters:** Search by quote number, by customer name and by phone. Filter by customer and by a date range. Try the CANCELLED status chip.
7. **Hindi locale:** Switch to Hindi and repeat steps 3 and 4. No raw key paths such as `status.expired` appear.
8. **Totals (Phase 5):** Compare totals for an intra-state and an inter-state customer, and check them against the saved PDF.
9. **Keyboard and screen reader (Phase 3):** On a partially converted quote, tab through the editor using only the keyboard. Every locked field can be reached and its value read. With a screen reader (NVDA or Narrator on Windows), a locked field announces that it is read-only, followed by the banner text explaining why.
10. **Stale tab (Phase 2 + 3):** Open the same unconverted quote in two tabs. Convert part of it in tab 1, then change a line in tab 2 and save. Tab 2 shows the "changed since you opened it" message, and Reload shows the locked state.

---

## 11. Rollout & rollback

**Release order.**
1. Phase 8 (backend part).
2. Phase 1.
3. Phases 2 + 3 as one PR.
4. Phase 4.
5. Phases 5 and 6 in a later release.

**Deploy order for the Phase 2 + 3 PR.** The new backend rejects `items` on partially converted quotes, and the current frontend always sends `items`.
- Because both are in one PR, they ship in one deploy. If the web and backend are deployed separately, deploy the **frontend first**. The Phase 3 frontend sends only whitelisted fields for partial edits, and the old backend already accepts that.
- Line `id`s sent by the new frontend are ignored by the old backend, which still deletes and recreates lines, so frontend-first is safe.
- Add a release-checklist item: "The Phase 2 backend and Phase 3 web build are in the same deploy, or the web build is already live."

**Stale browser tabs.** A tab opened before the deploy still runs the old editor and sends `items` for partially converted quotes. It gets a 400 whose message ends with "Reload the page and try again." New tabs map the error codes to the reload message.

**Other API clients.** The mobile app doesn't call the quotation endpoints. Any other integration that PATCHes partially converted quotes with `items` will start getting 400s. Mention this in the release note.

**Rollback.** Phases 1–7 are code-only, with no migrations; revert the PR. Phase 6 adds a read-only response field; reverting it means regenerating the OpenAPI snapshot and the generated types again. Reverting Phase 2 after lines have been updated in place is safe, because the old code ignores line IDs.

**Owners and dates.** Every phase needs a named owner and a target date before it starts. They are recorded in the phase table in [Part IV.2 of the review document](QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md#iv2-phase-overview).

**Tracking.** Assign the register IDs **before** the first PR, so every PR can cite one:
- Create one `qos/backlog/QOS-xxxx.yaml` entry per OPEN-ID, copying the format of the existing files.
- Record the mapping in `docs/reviews/MASTER_ISSUE_REGISTER.md`. The file is about 1.9 MB, so grep it for the last ID instead of reading it.
- The register entry should carry the same note as Part IV.1: OPEN-08 and OPEN-12 have no separate row in the finding map.
