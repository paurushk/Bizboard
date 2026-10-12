# Customers Module — Detailed Work Packages (CUS-01 … CUS-27)

**Companion to:** [CUSTOMERS_IMPLEMENTATION_PLAN.md](../CUSTOMERS_IMPLEMENTATION_PLAN.md) (audit + release map).
**Written:** 2026-10-11 against HEAD `5a8c898`. Each package below was checked against the code at that commit.
**Sizing:** S ≤ 0.5 day · M 1–2 days · L 3–5 days (one engineer, incl. tests). Owners are blank on purpose — assign at kickoff.

---

## Implementation status (2026-10-11)

All 27 packages are implemented and uncommitted in the working tree, with the decisions D-2 (verify widened to `CanCreateSales`, throttled 30/hour/company), D-3 (credit terms: OWNER and MANAGER), D-4 (reject explicit conflict, auto-fill blank state; behind `CUSTOMER_STRICT_VALIDATION`) taken at their proposed defaults. D-1 resolved by the founder on 2026-10-11: `ENABLE_CUSTOMER_360` is now on by default (backend env default and web default), as is `CUSTOMER_STRICT_VALIDATION`. Also decided: archived (`INACTIVE`) customers are refused on new invoices, quotations, orders and challans like blocked ones, and archive/delete is owner/manager only (API and UI).

Differences from the plan text: export refuses above 20,000 rows (same as receipts) instead of truncating; history keys arrive camelCased from the API renderer; the plan's example GSTIN `27AABCU9603R1ZM` has a bad check character (valid is `27AABCU9603R1ZN`); the customer list now prefetches shipping addresses (it ran one query per row before); the verify and lookup throttle is per company, not per user.

Tests: `backend/tests/test_customers_master.py` (42), `backend/tests/test_customers_concurrency_postgres.py` (2, Postgres only), `web/src/pages/sales/CustomersPage.test.tsx` (30, incl. axe, geolocation, archive role), `Customer360Page.test.tsx`, `web/src/utils/gstinStatus.test.ts`.

## 0. Baseline reconciliation — where the audit differs from HEAD

The audit plan was partly written from an older view of the code. Before starting any package, note these corrections (they change scope):

| # | Audit claim | Reality at HEAD | Effect |
|---|---|---|---|
| 1 | Search is un-debounced (`CUS-14`) | `useDebouncedValue(filters.q, 300)` already used (`CustomersPage.tsx:87`) | Drop debounce from CUS-14 |
| 2 | Clicking a row opens Customer 360° | Rows are **not** clickable. A "Customer 360" **button** exists but only renders when runtime flag `ENABLE_CUSTOMER_360` is on, and that flag defaults to `false` (`featureFlags.ts:43`) | CUS-14 becomes "add a name link"; new decision D-1 below |
| 3 | Clearing lat/lng never sends `null` (`CUS-08`) | Payload already sends `latitude: latitude \|\| null` (`CustomersPage.tsx:154-155`); the UI already rejects a half-filled pair (thrown in `mutationFn`, but the error shows behind the dialog) | CUS-08 reduces to: add a client range check + a regression test |
| 4 | Backend lacks coordinate validation (`CUS-26`) | `CustomerSerializer.validate` already enforces pairing and range (`serializers.py:83-92`) | CUS-26 reduces to phone + email only |
| 5 | Shipping addresses have `line1/city/state/pincode` (`CUS-16`) | `CustomerShippingAddress` has only `label`, `address`, `is_default` (`models.py:179-189`) | CUS-16 form uses those three fields |
| 6 | `GstinLookupResult` has `.error` (`CUS-19`) | Fields are `gstin, legal_name, status, state_code, taxpayer_type, raw`; the note/error is in `raw["error"]` / `raw["note"]` (`gstin_verify.py:15-22`) | Use `raw`; there is no `result.error` |
| 7 | `verify-gstin` bumps `customer.version` | `apply_verification` saves `update_fields` without touching `version` | Decide in CUS-09 whether verify should bump |
| 8 | Chip bug only on Customers | Same `VERIFIED`-only switch exists in `SuppliersPage.tsx:46-47`; `GstinVerificationStatus` type lists `'VERIFIED'` not `'VALID'` | Fix once in a shared util (CUS-06) |
| 9 | Customer type is complete | `CustomerStatus = 'ACTIVE' \| 'BLOCKED'` (`domain.ts:97`) — no `INACTIVE`; `Customer` has no `version` | Fix in CUS-01/12 |
| 10 | Tests go in `backend/masters/tests/` | That directory does not exist; customer tests live in `backend/tests/` (e.g. `test_business_rules.py`, `tenancy/test_endpoint_isolation.py`) | New file `backend/tests/test_customers_master.py` |
| 11 | `masters.ts:130-133` for `updateCustomer` | It is at `web/src/api/legacy/masters.ts:75-78` | Refresh all line refs |
| 12 | `apply_verification` is customer-only | It is shared with suppliers (`views.py` supplier `verify_gstin`) | Any change to it must keep the supplier path working |
| 13 | Customer 360° reads `['customer', id]` | 360° uses its own key `['customer-360', id]`; `['customer', id]` is used by invoice, POS, quotation, challan, order pages | Invalidate both (CUS-09) |

**Open decisions needed before R1 (record answers here):**
- **D-1:** Should `ENABLE_CUSTOMER_360` be turned on, or is 360° intentionally hidden? CUS-14/17 depend on this.
- **D-2 (CUS-03):** Why is `verify_gstin` owner-only? Widen to `CanCreateSales` with throttle (default), or keep owner-only and hide the button?
- **D-3 (CUS-23):** Which roles may edit `credit_limit` / `credit_days`? Default proposal: OWNER, MANAGER.
- **D-4 (CUS-07):** Reject or auto-correct a GSTIN/state mismatch? Default: reject on explicit conflict, auto-fill when state is blank.

---

## Release R1 — integrity, permissions, visible errors

### CUS-21 · Shared GSTIN helper (P1, M) — build first

**Why:** GSTIN side-effects (reset verification, state, PAN, duplicates) must not be re-implemented in `validate`, `perform_update`, verify and import.

**Design.** Pure functions in a new `backend/masters/gstin_rules.py` (no DB writes), consumed by `CustomerSerializer.validate`. Because `perform_update` applies `serializer.validated_data` with `setattr`, anything added to `attrs` inside `validate()` is persisted by both the view path and the plain `serializer.save()` path — so the reset lives in **one place** (`validate`), not in `perform_update`.

```python
# backend/masters/gstin_rules.py
from core.validators import GSTIN_RE
from masters.constants import GST_STATE_CODES   # confirm actual import location first

NO_SINGLE_STATE = {"96", "97"}                 # foreign / other territory (+ review 26/38 mapping)

def normalise(gstin: str) -> str:
    return (gstin or "").strip().upper()

def derive_state(gstin: str) -> str | None:
    return None if gstin[:2] in NO_SINGLE_STATE else GST_STATE_CODES.get(gstin[:2])

def derive_pan(gstin: str) -> str:
    return gstin[2:12] if GSTIN_RE.match(gstin) else ""

RESET_FIELDS = {
    "gstin_verification_status": "UNVERIFIED",
    "gstin_legal_name": "",
    "gstin_verified_at": None,
    "gstin_raw_payload": None,
}
```

**Steps**
1. Locate `GST_STATE_CODES` (grep `backend/`), confirm it covers 01–38, 97, and how 26/38 (Dadra & Nagar Haveli and Daman & Diu) are named so they compare equal to `state` strings stored today. Write a unit test enumerating every code.
2. Add `gstin_rules.py` with the helpers above.
3. In `CustomerSerializer.validate` (after the existing coordinate block): if `"gstin"` in `attrs`: normalise it; if it differs from `instance.gstin`, `attrs.update(RESET_FIELDS)`; if empty, also reset; fill `pan` when blank; leave `state` logic to CUS-07; duplicate check to CUS-10.
4. In `CustomerViewSet.perform_update`, after the row lock, compare `attrs["gstin"]` against `locked.gstin` (not `serializer.instance.gstin`) and apply `RESET_FIELDS` if a concurrent change slipped in. Keep this to ~4 lines.
5. Do **not** change `apply_verification` (shared with suppliers).

**Tests** (`backend/tests/test_customers_master.py`): helper unit tests; create with GSTIN leaves status `UNVERIFIED`; PATCH changing GSTIN on a customer verified `VALID` resets all four fields; PATCH of phone only does not touch them.
**Risks:** `gstin_raw_payload` is `null=True`, so reset to `None` (the audit plan said `{}`; either works, keep `None`). **Rollback:** pure additive; flag-gated by `CUSTOMER_STRICT_VALIDATION` only for the *rejecting* rules (CUS-07/10), the reset itself is always on.

---

### CUS-22 · Legacy-data audit command (P1, M)

**Files:** `backend/masters/management/commands/customers_audit.py` (the `management/` package already exists).
**Behaviour:** read-only by default; prints a table per company and exits non-zero with `--fail-on-findings` (for CI/staging gates). `--fix` applies only safe repairs.

| Check | Query | Fix with `--fix`? |
|---|---|---|
| Stale `VALID`: `gstin==""` or `gstin_verified_at is null` while status `VALID` | filter | Reset to UNVERIFIED |
| State/GSTIN mismatch | iterate `.iterator()`, compare `derive_state` | No — report only |
| Case/whitespace-duplicate GSTINs | group by `Upper(Trim(gstin))` | No |
| Walk-in anomalies: 0 or >1 walk-in; walk-in with gstin/credit_limit/non-ACTIVE | filter | No |
| Customers with `credit_days>0`/`credit_limit>0` and status `INACTIVE` | filter | No |

**Steps:** write command → unit-test on fixture rows → run against a restored copy of production-like data → attach output to the R1 release ticket. **Gate:** `CUSTOMER_STRICT_VALIDATION` is enabled in production only after mismatches are triaged.
**Size note:** keep it streaming (`.iterator(chunk_size=2000)`) — no full table load.

---

### CUS-04 · Protect the POS walk-in customer (P0, M)

**Current gaps (verified):** `is_pos_walk_in` is read-only in the serializer, but `gstin`, `credit_limit`, `status` are writable on that row via PATCH/PUT, and `destroy` has no guard (`views.py:345-357`).

**Backend**
1. `CustomerSerializer.validate`: `if instance and instance.is_pos_walk_in:` check the *effective* values (`attrs.get(k, getattr(instance,k))`): non-empty `gstin` → error on `gstin`; `credit_limit > 0` → error on `credit_limit`; `status != ACTIVE` → error on `status`. Use `serializers.ValidationError({field: msg})` so the UI can place it. (`set_pos_walk_in` already enforces the same rule on promotion, so this keeps one invariant.)
2. `CustomerViewSet.destroy`: first line after `get_object()`: `if customer.is_pos_walk_in: raise BusinessRuleError("The POS walk-in party cannot be deleted or deactivated. Choose another walk-in party first.", code="pos_walk_in_protected")`. Covers both soft delete and INACTIVE.
3. Add the same guard to any bulk/cleanup path that sets `is_deleted` on customers (grep `_soft_destroy`, `Customer.objects.filter(...).delete`).

**Frontend** (in the form dialog from CUS-17 step 1): show a "POS Walk-In" `Chip` beside the name; disable the `gstin` and `creditLimit` inputs with helper text; hide/disable **Block**, **Archive/Delete**.
**Tests:** PATCH gstin/credit_limit/status → 400 each; PUT same; DELETE → 400 and row unchanged; non-walk-in customers unaffected; `pos_walk_in` get-or-create endpoint still works. Frontend: row for walk-in has no Block button.
**Rollback:** server rule is unconditional (it's an invariant), not flagged.

---

### CUS-05 · Reset verification on GSTIN change (P1, S — mostly delivered by CUS-21)

**Remaining steps beyond CUS-21:**
1. `destroy` INACTIVE branch (`views.py:347-352`): wrap in `transaction.atomic()`, `Customer.all_objects.select_for_update().get(pk=...)`, set `status`, `version += 1`, `updated_by`, and save with `update_fields=["status","updated_by","version","updated_at"]`.
2. Verify path: after `apply_verification`, `customer.version` is unchanged. Decide: bump version (safer for optimistic locking — recommended) via `customer.save(update_fields=["version"])` inside the same transaction in the view, **not** inside the shared `apply_verification`.
**Tests:** archive bumps `version`; two sequential PATCH with stale version after archive → 409.

---

### CUS-07 · GSTIN ⇄ state consistency (P1, M)

**Backend** (inside `validate`, using `gstin_rules`):
```python
if "gstin" in attrs or "state" in attrs:                       # legacy safety: only when touched
    g = normalise(attrs.get("gstin", getattr(instance, "gstin", "")))
    if g and GSTIN_RE.match(g):
        expected = derive_state(g)
        state = attrs.get("state", getattr(instance, "state", "")) or ""
        if expected:
            if not state:
                attrs["state"] = expected
            elif state != expected and strict_enabled():
                raise ValidationError({"state": f"GSTIN {g} belongs to {expected}, not {state}."})
```
- `strict_enabled()` reads `settings.CUSTOMER_STRICT_VALIDATION` (add to settings, default `False`; staging `True` first).
- Compare normalised state names (case/whitespace-insensitive) since stored strings may differ ("Dadra and Nagar Haveli and Daman and Diu" vs historic names).
**Frontend:** in `CustomersPage` GSTIN `onChange` (line 497-505) change `matchedState && !f.state ? matchedState : f.state` to: when the **full 15-char valid** GSTIN is entered, always set `state = matchedState` and `pan = gstin.slice(2,12)`; for partial input (2+ chars) set state only if the user hasn't manually chosen one (track `stateTouched`). Show helper text when the user later picks a state that conflicts.
**Tests:** matrix of (gstin, state) → ok/auto-fill/400; special prefixes 96/97/26/38; unrelated PATCH on a mismatched legacy row succeeds; flag off → mismatch accepted.

---

### CUS-10 · Duplicate GSTIN names the conflict (P2, S)

**Note:** DRF skips conditional `UniqueConstraint`s, so the DB raises `IntegrityError` (constraint `uniq_customer_gstin_per_company`, condition `gstin != "" AND is_deleted = False`). Mirror that in `validate`:
```python
dup = Customer.objects.filter(company=company, gstin=g).exclude(pk=getattr(instance, "pk", None)).first()
if dup: raise ValidationError({"gstin": f"GSTIN {g} is already registered to customer '{dup.name}'."})
```
(`Customer.objects` is the alive-only manager, matching the constraint's `is_deleted=False`.) Company: `self.context["view"].company`; fall back to `instance.company`. Keep the DB constraint as the race-safe backstop; map `IntegrityError` on that constraint name to the same message in the existing exception handler if feasible.
**Tests:** create dup → 400 with name; PATCH to another's GSTIN → 400; self re-save allowed; soft-deleted holder doesn't block; cross-company same GSTIN allowed.

---

### CUS-26 · Phone and email validation on the server (P1, S) — coordinates already done

1. Coordinates: nothing to do (verified `serializers.py:83-92`); add one test that `latitude=null, longitude=null` succeeds on PATCH.
2. Phone: reuse `isValidIndianPhone` rules server-side — add `core.validators.validate_indian_phone` if absent; apply in `validate` only when `phone` is in `attrs` **and changed** (legacy rows may hold free text, same trick as the name check at line 98).
3. Email: model is `EmailField` (DRF validates already) — add a test only.
**Tests:** bad phone 400; unchanged legacy phone allowed on unrelated PATCH.

---

### CUS-03 · Permissions and subscription gate (P0, M)

**Backend**
1. Record decision D-2. If widening: in `get_permissions` add `"verify_gstin"` to the `CanCreateSales` branch (remove from the `IsOwner` tuple) and add a throttle: `ScopedRateThrottle` scope `gstin_verify`, e.g. `30/hour` in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`. Audit entry already written by `apply_verification` when `company` and `user` are passed (they are).
2. Leave `set_pos_walk_in` as `IsOwner`; leave `pos_walk_in` as `CanCreateSales`.

**Frontend (`CustomersPage.tsx`)**
```ts
const { writesBlocked } = useSubscriptionGate();                       // '@/hooks/useSubscriptionGate'
const canMutate = canCreateSales(user) && !writesBlocked;
const canVerify = canMutate && (decisionD2_widened || isOwner(user.role));
const canOpenLedger = canViewFinancialReports(user);
```
Replace line 120's `!isViewer(user.role)`; gate the **View Ledger** button (line 364) with `canOpenLedger`; gate **Verify** (line 336) with `canVerify`.
**Tests:** table of roles × controls: OWNER, MANAGER, SALES_STAFF (no financial reports), ACCOUNTANT (`canCreateSales=false`), AUDITOR, VIEWER, plus `writesBlocked=true`. Backend: verify as ACCOUNTANT-without-sales → 403; throttle returns 429 after limit.

---

### CUS-02 · Errors visible inside the dialog (P0, S)

1. Split state: `listError` (page-level, used by toggle/verify) and `dialogError` (save). Replace `error`/`setError`.
2. Render `<HelpErrorAlert message={dialogError} />` as the first child of `DialogContent`.
3. Clear `dialogError` in `openCreate`, `openEdit` and the dialog `onClose`.
4. Move the thrown validations out of `mutationFn` into `canSave` so they show as inline field errors (GSTIN partial length, lat/lng pair + range, email format).
5. Map field-level server errors: parse DRF `{field: [msgs]}` into `fieldErrors` and pass to the matching `TextField error/helperText`; unknown fields go to the alert. (Check `getErrorMessage` in `@/api/client` for how it flattens — extend rather than duplicate.)
**Tests:** mocked 400 with `{gstin:[...]}` shows under the GSTIN field and dialog stays open with typed values; reopen shows no stale error.

---

### CUS-06 · GSTIN status chip (P1, S)

1. New `web/src/utils/gstinStatus.ts` exporting `gstinStatusColor` and `gstinStatusLabelKey`:
   `VALID|VERIFIED → success`; `INVALID|FAILED|CANCELLED|SUSPENDED → error`; `UNVERIFIED|'' → warning`; unknown → `default`.
2. Update `GstinVerificationStatus` in `domain.ts:135` to `'UNVERIFIED' | 'VALID' | 'INVALID' | 'CANCELLED' | 'SUSPENDED' | 'VERIFIED' | 'FAILED' | string`.
3. Use it in **both** `CustomersPage.tsx:68-78` and `SuppliersPage.tsx:46-` (delete both local copies).
4. Row-scoped spinner: `verifyMutation.isPending && verifyMutation.variables === c.id`.
5. i18n: label keys `gstin.status.valid/invalid/cancelled/suspended/unverified` in `en.ts` + `hi.ts` (see CUS-13).
**Tests:** unit table for the util; component test that `VALID` renders the success class.

---

### CUS-08 · Coordinate clearing and range (P1, S — mostly already working)

1. Add a test: edit a customer with coordinates, clear both inputs, save → request body has `latitude: null, longitude: null`.
2. Add client range check to `canSave`: `-90..90`, `-180..180`, both-or-neither, with field-level helper text (replaces the thrown error at lines 146-148).
3. No backend change.

---

## Release R2 — form completeness, cache, UX

### CUS-17 (step 1) · Extract `<CustomerFormDialog />` (M) — do before CUS-01/23

**New file:** `web/src/pages/sales/CustomerFormDialog.tsx`. Props: `{ open, customer?: Customer | null, onClose, onSaved(saved: Customer) }`. It owns `form`, field errors, `dialogError`, and the save mutation; the page keeps only list state.
**Steps:** move lines 52-65 (`emptyForm`), 114-136 (validation), 138-178 (mutation), 193-218 (open handlers) and the JSX at 413-571 verbatim; add `version` to the sent payload (CUS-09); keep the existing `CustomersPage.test.tsx` green before adding features (pure refactor commit).
**Done when:** existing tests pass unchanged; `CustomersPage.tsx` shrinks by ~250 lines.

### CUS-01 · Credit, tax, shipping, notes in the form (P0, L)

**Types/API:** `Customer` (`domain.ts:261`) add `version?: number`, `taxpayerType?: TaxpayerType`; widen `CustomerStatus` to include `'INACTIVE'`. Check `mapCustomer`/axios camelCase interceptor already maps `credit_limit`→`creditLimit` (it does for existing fields; confirm `taxpayer_type`, `credit_days`, `notes`).
**Form fields (group in collapsible sections to limit load):**
- *Basics:* name, phone, email, WhatsApp opt-in (existing).
- *Tax:* GSTIN (+ verify button, CUS-16), state, PAN (auto from GSTIN, editable only when no GSTIN), `taxpayerType` select (8 options from `Customer.TaxpayerType`; default REGULAR; hint when GSTIN blank → UNREGISTERED).
- *Credit:* `creditLimit` (≥0, 2 dp), `creditDays` (integer ≥0) — read-only for roles in CUS-23.
- *Addresses:* billing, shipping (single text), pincode.
- *Other:* notes (multiline, max length per model TextField — cap 2,000 client-side), price list, dunning opt-out.
**Validation:** `creditLimit`/`creditDays` numeric and non-negative; `taxpayerType` consistent with GSTIN presence (warn, don't block).
**Table:** under *Outstanding* show `Limit ₹X` when `creditLimit>0` (CUS-18).
**Tests:** create with all fields → POST body contains them; edit shows stored values; invalid numbers disable Save.

### CUS-23 · Credit-term permissions (P1, M) — needs D-3
**Backend:** in `validate`, if `credit_limit` or `credit_days` is in `attrs` and differs from the instance (or non-zero on create) and the member role is not in `CREDIT_TERM_EDITORS` (default `{"OWNER","MANAGER"}`): `ValidationError({field: "Only an owner or manager can change credit terms."})`. Role from `get_company_user(request)` (already used in this serializer). **Audit:** write an `AuditService.log(... description="customer.credit_terms", metadata={old,new})` from `perform_update` when either changes.
**Frontend:** `canEditCreditTerms = ['OWNER','MANAGER'].includes(user.role)`; otherwise render the inputs `disabled` with helper text.
**Tests:** SALES_STAFF PATCH credit_limit → 400; MANAGER → 200 + audit row; unchanged value from SALES_STAFF (echoing the form) → 200.

### CUS-09 · Cache and concurrency (P1, M)
**Frontend**
1. New `web/src/pages/sales/customerQueries.ts`: `invalidateCustomerQueries(qc, id?)` invalidating `['customers']`, `['customers-search']`, `['customers-receipt-lookup']`, `['customers-reassign-lookup']`, `['customers-mini']`, `['customer', id]`, `['customer-360', id]`, plus `['customers-summary']` when CUS-15 lands. Use it from save, toggle, verify, archive mutations and from `invalidateInvoiceSideEffects.ts` (already invalidates three of these; extend).
2. Delete the `setQueriesData` prepend (lines 165-174) — it inserts rows into filtered/sorted pages incorrectly.
3. Send `version: editing.version` in the PATCH payload; add `version` to the `Customer` type.
4. 409 handling: detect `err.response?.status === 409`; show in-dialog notice "Someone else changed this customer" with **Reload latest** (refetch `['customer', id]`, replace `editing`, keep unsaved form values for fields the user touched).
**Backend**
5. `update()`: for PATCH, if `"version" in request.data` run the same stale check as PUT (and the re-check under lock in `perform_update`). Extract `_check_version(sent, current)` shared by both to remove the duplicated `StaleWrite` class defined inline (lines 310-315).
6. Absent `version` on PATCH keeps today's merge behaviour (documented in the docstring at line 293).
**Tests:** stale PATCH → 409 with `current` body; PATCH without `version` still merges concurrent different-field edits (reuse existing barrier test pattern in `backend/tests`).

### CUS-12 · Block/Archive lifecycle (P2, M)
1. `ConfirmDialog` (reuse existing component if present — grep `ConfirmDialog`) before Block; message includes outstanding amount when `>0`.
2. Row actions by status: `ACTIVE → Block`; `BLOCKED → Unblock`; `INACTIVE → Activate` (calls PATCH `status: ACTIVE`); never show Unblock for INACTIVE.
3. Archive/Delete action (owner/manager): calls `DELETE`; on `200` with "marked Inactive" body show a notice, on `204` show deleted; hide for walk-in (CUS-04).
4. `StatusChip` tone for INACTIVE via `customerStatusTone`.
**Tests:** Block requires confirmation; INACTIVE row shows Activate; archive of referenced customer shows the notice.

### CUS-13 · Labels and i18n (P3, S)
1. Sort field label: `t('common.sortBy')` — verify which namespace holds `'Sort'` (`en.ts:1419` sits in a different namespace from `common`; add `common.sortBy` if missing rather than reusing a `history.*` key). Provide Hindi in `hi.ts`.
2. Replace hard-coded strings at `CustomersPage.tsx` lines 291, 331, 414, 426, 439, 494, 514, 552, 556 with keys under `customers.*`; add to `en.ts` and `hi.ts`.
3. Run the i18n parity check/test if one exists (grep `hi.ts` parity test) and keep it green.

### CUS-14 · Keyboard access and responsive table (P3, S) — debounce already done
1. Make the customer **name** a `Link component={RouterLink}` to `/sales/customers/:id` — only when D-1 enables 360° (otherwise plain text). Do not make the whole `TableRow` clickable (it conflicts with action buttons and is a worse a11y pattern than a link).
2. Table already has `role="region"` and scroll container; verify 375 px: hide *Email/State/GSTIN status* columns below `md` with `sx={{ display: { xs: 'none', md: 'table-cell' } }}` and show status chip under the name on `xs`.
3. Test at 375 px via the Vitest + `matchMedia` helper used elsewhere, or a Playwright check if the repo has one.

### CUS-11 · Balance sort and duplicate aggregation (P2, M)
1. **Verify first:** read `LedgerService.bulk_customer_outstanding` and `bulk_customer_credit_exposure` (`backend/ledgers/services.py`, ~L508-535) to confirm the exposure function calls outstanding internally (the audit says three runs; confirm with a `CaptureQueriesContext` count in a test *before* changing anything).
2. Add optional `outstanding_map=` param to `bulk_customer_credit_exposure`; in `CustomerViewSet`, compute the map once per request, memoised on `self._outstanding_map`, used by `get_queryset` (sort=balance) and `get_serializer_context`.
3. Replace `Case(When(pk=…))` for sort=balance: preferred — annotate with a correlated subquery/aggregate over the ledger source table(s) that `bulk_customer_outstanding` reads; if outstanding depends on Books-ON/OFF logic that can't be expressed in SQL, order the filtered `values_list("pk")` in Python by the cached map and fetch only the requested page (override `paginate_queryset`).
4. Benchmark test: 5,000 customers, assert query count ≤ N and wall time budget (agree N with a baseline measurement; don't guess).

### CUS-19 (search/status part) · Backend filter hardening (S)
1. Extract `_filtered_queryset()` from `get_queryset` (used by list/summary/export).
2. `status` validated against `Customer.Status.values` (ACTIVE, BLOCKED, INACTIVE — confirmed) → `ValidationError({"status": ...})` (400).
3. `q = q.strip()[:100]`; add `Q(email__icontains=q)`. Note: the **supplier** viewset has an identical filter at `views.py:404` — apply email there too only if product agrees (out of scope otherwise; log it).
4. `sort`: reject unknown values with 400 or keep silent default — decide; the current silent default is existing behaviour, so keep and document.
**Tests:** email search; `status=FOO` → 400; 101-char `q` truncated, not an error.

---

## Release R3 — enhancements, audit, observability

### CUS-15 · Summary strip and CSV export (M–L)
**Permissions:** both endpoints require `canViewFinancialReports`-equivalent (find the DRF permission class used by report views, e.g. grep `CanViewFinancialReports`), not `CanCreateSales`.
**`summary/`** (`@action(detail=False, methods=["get"])`): uses `_filtered_queryset()`; returns `total_count, active_count, blocked_count, inactive_count, over_credit_limit_count, total_outstanding, total_unallocated_advance, net_credit_exposure`. Compute from the cached maps; `over_credit_limit_count` = customers with `credit_limit>0 and exposure>credit_limit`. Cache for ~30 s keyed by (company, filters) if profiling shows cost.
**`export/`:** `StreamingHttpResponse` CSV via the repo's `csv_safe` helper (grep for the receipts export, `ReceiptsViewSet.export`, and copy its pattern incl. content-disposition and filename); cap 20,000 rows; set header `X-Export-Truncated: 1` when capped; write `AuditService.log(action="EXPORT", entity_type="Customer", metadata={filters,row_count})`.
**Frontend:** `getCustomersSummary`, `exportCustomersCsv` in `masters.ts`; 4-card strip above the filter bar (reuse the receipts summary card component); **Export CSV** button gated by `canViewFinancialReports`; warning snackbar when the truncation header is set.
**Tests:** filters respected; formula-injection cell (`=1+1`) is escaped; ACCOUNTANT without reports flag → 403; company isolation; truncation header.

### CUS-16 · Lookup, custom fields, shipping addresses, geo (L)
1. **`lookup-gstin/`** (`POST`, collection action, `CanCreateSales`, same throttle scope as verify): validate checksum with `GSTIN_RE`/`validate_gstin`; call `get_gstin_provider().lookup(g)`; respond `{gstin, status, legal_name, state, pan, taxpayer_type, provider, notice}` where `state = derive_state(g)`, `pan = derive_pan(g)`, `notice` = human string from `result.raw["note"|"error"]` (e.g. "Live verification isn't configured; format is valid") — **never** `result.error`. Cache 10 min per (company, gstin). No DB write; audit `customer.gstin_lookup`.
   *Reality check:* `NullGstinProvider` returns no legal name, so in non-GSP environments autofill yields only state/PAN — the UI must say so (don't promise name autofill).
2. **Dialog:** "Verify & autofill" button beside GSTIN → fills `state`, `pan`, `taxpayerType` (when provider supplies) and offers **Use legal name** chip for `name`.
3. **Custom fields:** read `company.partyCustomFieldDefs` (as `InvoicePartyPanel.tsx` does — copy its field renderer into a shared `PartyCustomFields` component rather than duplicating); send `customFields`.
4. **Shipping addresses:** repeater of `{label, address, isDefault}` (single default enforced client-side). Backend `_replace_addresses` **deletes and recreates** all rows on every update (`serializers.py:216-227`), changing ids — check nothing references address ids (grep `CustomerShippingAddress` FKs on invoices/orders) before shipping; if something does, switch to upsert-by-id.
5. **Geo helper:** `navigator.geolocation.getCurrentPosition` button; handle denial/timeout/insecure-context; round to 6 dp (matches `DecimalField(9,6)`).
**Tests:** lookup stub-mode response; autofill applies state/PAN; custom field round-trip; address repeater default rule; geolocation mocked.

### CUS-17 (rest) · 360° edit, archive, set-walk-in (M)
1. Depends on D-1. On `Customer360Page` add **Edit** button (gated by CUS-03 `canMutate`) opening `<CustomerFormDialog>`; on save call `invalidateCustomerQueries` (both `['customer-360',id]` and `['customer',id]`).
2. Overflow menu (row + 360°): **Archive/Delete** (CUS-12), **Set as POS walk-in** (OWNER only; eligible = ACTIVE, no GSTIN, `creditLimit==0`, not already walk-in) → `POST /customers/set-pos-walk-in/ {customer}`; confirm dialog states the previous walk-in is demoted.
3. Add API helpers `deleteCustomer`, `setPosWalkInCustomer` in `masters.ts`.
**Tests:** edit from 360° refreshes header; set-walk-in OWNER-only; ineligible customers have the action disabled with reason tooltip.

### CUS-18 · Exposure transparency (S–M)
Table *Outstanding* cell: primary `formatMoney(outstanding)`; caption `Limit ₹X` (error colour if `creditExposure > creditLimit`); caption `Net of advances ₹Y` when `creditExposure < outstanding`. No new endpoint (both fields are in the list payload). `PATCH` concurrency is delivered by CUS-09, not here — remove the duplicate from this item when tracking.
**Tests:** captions appear only under their conditions; hold chip + over-limit caption consistent.

### CUS-19 (stub notice) · Verify response notice (S)
`verify_gstin` response: serializer data plus `verification_notice` derived from `result.raw` (`note`/`error`); UI shows an info toast when status stays `UNVERIFIED`. Because `apply_verification` returns the `result`, capture it: `result = apply_verification(...)`; build `{**serializer.data, "verification_notice": notice}`. Update OpenAPI via `extend_schema`.

### CUS-20 · Accessibility, mobile, OpenAPI (M)
1. Focus restoration: store the trigger element ref before opening dialogs; MUI `Dialog` restores focus by default when the trigger remains mounted — verify rather than reimplement (the `Paper` re-render after invalidate may unmount the button; if so, use `disableRestoreFocus={false}` + focus the row's action menu after close).
2. Add `vitest-axe` (check `web/package.json` first — add only if absent) to `CustomersPage.test.tsx` for table, form dialog, confirm dialog; record baseline, gate on **no new violations**.
3. 375 px layout verified (CUS-14).
4. `extend_schema` on `summary`, `export`, `lookup-gstin`; regenerate `docs/openapi-snapshot.json` (`manage.py spectacular`) and `web/src/api/openapi-types.ts`; CI diffs them — run the repo's generation script, never hand-edit (see `CLAUDE.md`: don't read these files wholesale, grep them).

### CUS-24 · Change history (M)
Read existing `AuditService` rows for `entity_type="Customer"` and `entity_id`. Add `GET /customers/{id}/history/` (permission: `canViewFinancialReports`) returning `[{at, user, action, summary}]`, paginated; render as a "History" panel on 360° showing credit-term, GSTIN, status changes with old → new (requires CUS-23 to log `old/new` metadata; older rows show description only). Check the audit model's field names and indexes (`entity_type, entity_id`) before writing the query.

### CUS-25 · Import parity (S to investigate, M to fix)
1. Grep `backend/` for customer import (`import_customers`, CSV/Excel upload, `bulk_create(Customer`). Record the result in the plan.
2. If found: route each row through `CustomerSerializer(data=row, context=…)` (not `Customer.objects.create`) so CUS-04/05/07/10/26 rules apply; return per-row errors `{row, field, message}`.
3. If not found: close the item as "not applicable" and open a separate feature request.

### CUS-27 · Observability, privacy, semantics (S–M)
1. Metrics/logs (use the repo's existing logger/metrics helper): `customer.stale_write_409`, `customer.gstin_lookup{status,provider}`, `customer.export{rows,truncated}`.
2. Document in `docs/` (one page) what `BLOCKED` vs `INACTIVE` means for: new invoice, POS, quotation, sales order, receipt, existing open documents, reports. **Verify each in code first** (grep `Customer.Status.BLOCKED` / `status == "BLOCKED"` across `sales/`, `payments/`, `pos/`) and list any inconsistencies as follow-up bugs rather than assuming.
3. Privacy note: PII fields (phone, email, GPS, bank account — already role-masked in `to_representation`) + export access rule + retention; get the founder's call on DPDP wording.

---

## Cross-cutting definition of done (every package)
- [ ] Re-checked the cited file/line against current HEAD before editing.
- [ ] Tests added in the files named above; `pytest backend/tests/test_customers_master.py` and `npx vitest run src/pages/sales/CustomersPage.test.tsx` green. Use `tsc -b` for web type-check (not `tsc -p .`); `ruff` clean.
- [ ] Postgres-only concurrency tests (CUS-09) run on Postgres, not SQLite.
- [ ] OpenAPI snapshot + TS types regenerated when an endpoint/serializer changed.
- [ ] i18n keys added to **both** `en.ts` and `hi.ts`.
- [ ] Entry added to `docs/FREEZE_SCOPE_COVERAGE.md` / QOS backlog if the repo tracks this item there.

## Suggested order of commits (each independently revertable)
1. CUS-21 helper + tests → 2. CUS-22 audit command → 3. CUS-04 → 4. CUS-05/10/26 → 5. CUS-07 (flag off) → 6. CUS-03 → 7. CUS-02/06/08 (frontend) → **R1 release; run CUS-22 on staging; flip flag**
8. CUS-17 step 1 refactor → 9. CUS-09 → 10. CUS-01 → 11. CUS-23 → 12. CUS-12 → 13. CUS-13/14 → 14. CUS-11 → 15. CUS-19a → **R2**
16. CUS-15 → 17. CUS-16 → 18. CUS-17 rest/CUS-18 → 19. CUS-19b/24/25/27 → 20. CUS-20 → **R3**
