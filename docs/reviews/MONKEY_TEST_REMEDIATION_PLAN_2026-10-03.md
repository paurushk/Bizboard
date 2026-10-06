# Monkey-test remediation plan

Session: 2026-10-03, main stack `http://127.0.0.1`, Owner `uxplan-owner@bizboard.local`, company Demo Traders.

Revised after review against the code. Numbering precedence is not changed. The service-worker change is a separate release and is not done until the generated worker is inspected.

## Pull requests

| PR | Items | Why it is separate |
|---|---|---|
| 1 | MT-001 | P0. Users on the broken worker cannot use refresh. Ship alone, with the `sw.js` gate. |
| 2 | MT-002, MT-004 | Validation and copy. No numbering, no worker. |
| 3 | MT-003 | Invoice and purchase editors only. Other editors are listed as deferred. |
| 4 | MT-005 | Numbering and GST health. Starts only after the Demo Traders data check is written into this file. |

## Not changed

- No database constraint on `pincode`. Existing bad values must not fail migrate.
- `resolve_series_gstin` precedence stays: document stamp, then active primary `CompanyGstin`, then any active `CompanyGstin`, then `company.gstin` (`backend/core/services/document_numbers.py`).
- No rewrite of `DocumentSeries` rows, no serializer that renumbers, no change to already issued invoice numbers.
- `networkTimeoutSeconds` stays 10.
- `EmptyState` default title stays “Nothing here yet”.
- Customer CSV import does not write `pincode` today (`backend/imports/services.py` `_commit_customers`). No import change in this work.
- `coordinates_for_pincode` stays a reader. A bad stored PIN still returns no centroid. It is not a write path.
- Deferred dirty-check editors, listed under MT-003.

---

## MT-001 — Full loads show the offline page while online

PR 1.

### Cause

`web/vite.config.ts` sets Workbox `navigateFallback` to `/offline.html`. That registers a navigation route which serves the fallback for any navigation that is not an exact precached URL, without asking the network. Nginx already returns `index.html` (HTTP 200, title `Bizboard`) for `/login`, `/sales/new`, and unknown paths. With the worker in control, the browser shows `offline.html` immediately. `/` still works because it is precached. In-app React Router clicks never issue a document navigation, so they keep working.

The comment at `vite.config.ts` lines 46–50 says “keep SPA navigateFallback for deep links” and then sets the fallback to `offline.html`. Those two sentences disagree. Rewrite the comment in the same change so the next edit does not put `offline.html` back.

`handlerDidError` on the `NetworkFirst` navigate rule is the right place for `offline.html`. That is what BB-000737 asked for: a failed navigation must not look like a live app.

Do not set `navigateFallback` to `index.html`. `index.html` is precached. A `NavigationRoute` aimed at it serves the cached shell and never runs the `NetworkFirst` rule or the 10-second timeout.

`registerType: 'prompt'` still needs a precache. Removing the fallback means the navigate runtime route is what handles document loads. Set `navigateFallback` to `null` (or omit it, if the plugin treats omit as null) so vite-plugin-pwa does not emit a `NavigationRoute`.

### Contract

- Online full load of `/`, `/login`, `/sales/new`, and an unknown path renders the SPA shell.
- `/api` is not NetworkFirst-cached. `bizboard-pages` stores the HTML shell only. No authenticated API body is in that cache. A timeout that falls back to cache can show the shell to the next person on a shared browser; it must not show another user’s data. Confirm this by reading the generated cache rules, not by assumption.
- When the navigation request fails, the response is `offline.html`.
- `networkTimeoutSeconds` stays 10. UXW2-004 set that value so a slow link is not treated as offline. This PR does not retune it. A slow-but-alive connection can still hit the offline page at 10 seconds; that remains a known limit, called out in the PR, not silently “out of scope”.

### Generated-worker gate (required)

After `npm run build` in `web/`:

1. Open the emitted worker (`web/dist/sw.js` or the workbox file it imports).
2. Confirm there is no `NavigationRoute` whose handler is `offline.html`.
3. Confirm there is no `NavigationRoute` that serves precached `index.html` ahead of the network.
4. Confirm the navigate `NetworkFirst` route is registered, `networkTimeoutSeconds` is 10, and its error plugin matches `offline.html`.
5. Confirm no route caches `/api`.

If any of those fail, do not merge. The config comment is not the proof. The generated worker is.

### People already stuck

The broken worker answers navigations from cache, so a new `sw.js` is not fetched until something gets past it.

Recovery that already exists in `web/public/offline.html`:

- “Reload without cache” runs `unregisterAndReload`: unregister every registration, then replace to `/login?nocache=…`. That script is in the page they are already looking at. It needs JavaScript.
- “Try again” while `navigator.onLine` replaces to `/`. `/` is precached as the shell, which is how the session got back into the app. From the shell, the update prompt can run.

No-JS recovery is not available. A plain link is still a navigation, and the worker will serve `offline.html` again. Do not claim a no-JS kill switch.

Before release, read the **deployed** `offline.html` (not only the repo file) and confirm `unregisterAndReload` is present and not stripped by the cache. The PR note tells stuck users to use “Reload without cache” on the page already on screen. Do not rely on them loading a new worker first.

`registerType` stays `prompt`. Do not switch to silent auto-reload (F1-003 dropped unsaved bills).

### Tests

Rewrite:

- `backend/tests/test_wave22_f4_pwa_flags.py` `test_bb_000737_758_navigate_fallback_is_offline_html`
- `backend/tests/test_sprint6_platform.py` `test_bb_000580_pwa_has_offline_fallback`

They currently require `navigateFallback: '/offline.html'`. Change them to require `handlerDidError` → `offline.html`, `navigateFallback` null or absent, and the existing BB-000738 “no NetworkFirst on `/api`” checks.

Browser proof does not belong on the current `e2e` job. That job runs `npm run dev -- --mode e2e` (`web/playwright.config.ts`), which does not build the worker. Golden e2e is also the Vite server on port 5173.

Add a separate CI job, or a script invoked only by this PR’s check: `npm run build` then `vite preview`, Playwright against that preview, worker registered, `page.goto('/sales/new')` expects the invoice UI (or login), not `#offline-title`. One offline case if the harness can disable the network: goto expects `#offline-title`. Do not add this spec to `npm run test:e2e`.

### Files

- `web/vite.config.ts` (config and the comment)
- `web/public/offline.html` (confirm the unregister script; change it only if the deployed copy lacks it)
- `backend/tests/test_wave22_f4_pwa_flags.py`
- `backend/tests/test_sprint6_platform.py`
- New preview-based Playwright spec and the CI job that builds first

### Done when

The `sw.js` gate passes, and a refresh of `/sales/new` on a preview that serves that worker shows Create Sales Invoice.

---

## MT-002 — Customer pincode `-1` is stored

PR 2, with MT-004.

### Cause

`Customer.pincode` is a `CharField(max_length=10, blank=True)`. `CustomerSerializer.validate` checks coordinates and party name. It does not check the PIN. e-invoice code requires six digits later (`backend/sales/einvoice_payload.py`).

Company and `CompanyGstin` pincode fields are the same shape and are accepted by `backend/accounts/serializers.py` without a PIN check. One helper covers all three.

### Rule

Indian PINs are six digits and the first digit is 1–9. Source: India Post PIN allocation (the first digit is the region, 1–9; `0` is not used). Regex after trim: `[1-9][0-9]{5}`.

- Blank saves.
- `" 560001 "` trims to `560001` and saves.
- `-1`, `abc`, `5600`, `000000`, `100000` wait: `100000` matches the regex and is accepted. `000000` does not, because it starts with 0.
- `1234567` is rejected.

Message, via i18n: key such as `validation.pincode` = “Enter a 6-digit PIN code.” Add the same key to `web/src/i18n/hi.ts`. The API can return the English sentence; the form shows `t(...)`.

### When validation runs

Only when `"pincode" in attrs` and the trimmed value differs from the stored value. An edit that does not send `pincode`, or sends the same bad value unchanged, must succeed. The next change to that field fails until the PIN is blank or valid. The 400 body names `pincode`, so the form can mark that field.

Do not reject the whole update of an unrelated field because an old bad PIN is still on the row.

### Other writers

- Customer CSV import does not set `pincode` (`imports/services.py` `_commit_customers`). No change. If a PIN column is added later, it must call this helper before `bulk_create`. `bulk_create` skips serializers.
- Seed commands that set `pincode` must keep using values that match the regex (`560001` already does).
- `pin_centroids.py` only reads. Leave it tolerant of legacy bad PINs.

### Existing data

Before deleting anything, on the demo database:

```sql
SELECT COUNT(*) FROM masters_customer
WHERE pincode <> '' AND pincode !~ '^[1-9][0-9]{5}$';
```

Run the same pattern for company and company-GSTIN pincode columns. Record the counts in the PR. Customer 192 may not be the only row.

Cleanup of customer 192, demo tenant only: `DELETE /api/v1/customers/192/` as the Owner session, or `Customer.objects.filter(pk=192, company_id=1).delete()` in a Django shell pointed at that database. Do not run that delete against any other environment. If the count query finds more rows, list them in the PR and correct them by hand. Do not bulk-blank every bad PIN in this change.

### UI

On the customer pincode field, trim, then show the helper when the value is non-empty and fails the regex. The API remains the gate.

### Tests

- Create `-1` → 400, field `pincode`, no row.
- Create `560001` and `" 560001 "` → stored `560001`.
- Create `""` → 201.
- Update phone on a row whose pincode is already `-1`, without sending `pincode` → 200, pincode unchanged.
- Update that row’s pincode to `-1` again when it is already `-1` → 200 if the value is unchanged; update to `560001` → 200.
- Company update and company-GSTIN create reject a newly sent `-1`.

### Files

- Shared PIN helper (next to existing party/GST validators)
- `backend/masters/serializers.py`
- `backend/accounts/serializers.py`
- `web/src/pages/sales/CustomersPage.tsx`
- `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`
- Masters API tests

---

## MT-004 — Filtered search says the list is empty

PR 2, with MT-002.

### Cause

`EmptyState` defaults its title to `t('common.empty')` (“Nothing here yet”). True-empty lists depend on that. Do not change the default.

`CustomersPage` and `SuppliersPage` pass `description={t('common.noResults')}` (“No results found”) on the filtered-empty branch, so the heading and the body disagree.

`grep` for `common.noResults`: the only `EmptyState` callers are those two pages. Sales history, purchase history, and the invoice product search use an `Alert` or `noOptionsText`. Leave those.

### Contract

- Filtered customers or suppliers, zero rows: title “No results found”, no second line, no “Nothing here yet”.
- No customers and no filter: “Nothing here yet” and the add action, unchanged.
- Hindi already has `common.noResults`. No new key.

### Files

- `web/src/pages/sales/CustomersPage.tsx`
- `web/src/pages/purchases/SuppliersPage.tsx`
- Their tests

---

## MT-003 — New Invoice drops typed values with no prompt

PR 3.

### Cause

`NewInvoicePage` arms the guard only when there is a line or a selected customer:

```tsx
<UnsavedChangesGuard when={!skipLeaveGuard && (lines.length > 0 || Boolean(customerId))} />
```

The session had neither. `additionalCharges` is page state (`useState(0)` near line 237) and was ignored. The walk-in name is `manualName` inside `InvoicePartyPanel` and dies on unmount. Save draft stays disabled until there is a line and a customer, so there was no save path and no warning.

The same narrow predicate is copied in:

| File | Predicate | This PR |
|---|---|---|
| `NewInvoicePage.tsx` | lines or `customerId` | Fix |
| `NewPurchasePage.tsx` | lines or `supplierId` | Fix |
| `SalesOrderEditorPage.tsx` | lines or `customerId` | Deferred |
| `PurchaseOrderEditorPage.tsx` | lines or `supplierId` | Deferred |
| `PurchaseNoteEditorPage.tsx` | `effectiveLines` or `supplierId` | Deferred |
| `SalesInvoiceNoteEditor.tsx` | `invoice` or `activeSourceLines` | Deferred |
| `PosPage.tsx` | `cart.length > 0` | Deferred. Cart is the bill. A separate pass if POS has fields outside the cart. |

A list of fields will miss the next control added to the page. Match `InventoryPhasePages`, which compares `JSON.stringify(edit)` to a baseline taken when the form became clean.

### Contract

- After mount, and after a device draft is applied, snapshot the editor. That snapshot is clean. Opening a restored draft must not prompt on the next navigation if the user has not changed it.
- Prompt when the current snapshot differs. That covers charges, discount, amount received, notes, HSN, walk-in text, lines, and customer, including fields added later if they are inside the snapshot.
- Stay keeps the values, including the walk-in text. Leave discards.
- A blank editor does not prompt.
- `skipLeaveGuard` still suppresses the prompt after a successful save.
- Save draft stays disabled until the bill is saveable. This PR does not allow a charge-only save.
- Device draft restore today reads `lines` and `customerId` only (`readDraft` around line 300). Confirm a restore finishes, then the baseline is taken. If restore is async, the baseline is taken in the effect that applies it, not on the first render.

### Implementation

1. Lift `manualName` into `NewInvoicePage` (and the purchase page). Do not report dirtiness from a `useEffect` in the child. A callback that flips a boolean one render later can miss a fast click on Complaints.
2. Build one object of the fields that constitute the draft, including `manualName`, `additionalCharges`, `chargesHsn`, `chargesGstRate`, `invoiceDiscount`, `amountReceived`, `notes`, `lines`, and `customerId`. Confirm those names against the `useState` calls while wiring it. Stringify and compare to the baseline.
3. Set the baseline after draft restore and after a successful save.
4. Pass `when={!skipLeaveGuard && snapshot !== baseline}` to the existing guard. Copy stays `billing.unsavedTitle` / `billing.unsavedBody`.
5. Do the same on `NewPurchasePage` for its equivalent state.

### Tests

- Blank snapshot equals baseline.
- Changing `additionalCharges` to `1`, or `manualName` to `"A"`, makes them differ.
- Applying a restored `{ lines, customerId }` and then snapshotting does not differ until the user edits.
- Purchase: charges alone differ from baseline.

### Files

- `web/src/pages/sales/NewInvoicePage.tsx`
- `web/src/pages/sales/invoice/InvoicePartyPanel.tsx`
- `web/src/pages/purchases/NewPurchasePage.tsx` and its party panel
- New unit test for the snapshot compare

---

## MT-005 — “No GSTIN” and the invoice series disagree

PR 4. Do not start the code until the data check below is filled in here.

### Data check first

On Demo Traders (company id 1), record:

- `company.gstin`
- `company.registration_type`
- every `CompanyGstin` row: `gstin`, `is_primary`, `is_active`
- `DocumentNumberService.peek` for `SALES_INVOICE` (prefix, `gstin_key`, `next_number`)

`CompanyGstin.save` mirrors a primary stamp onto `company.gstin`. A blank `company.gstin` with a primary stamp means that mirror did not run or the company field was cleared later. A blank `company.gstin` with only non-primary stamps is allowed by the model.

Write the rows into this section before any patch. If peek’s `gstin_key` is empty and the prefix still ends in `F1ZW`, stop. That would be a series-selection bug, and the design below does not cover it.

Recorded 2026-10-03 from the running API container (`Company` id 1):

| Field | Value |
|---|---|
| `company.name` | Demo Traders |
| `company.gstin` | `""` |
| `company.registration_type` | `REGULAR` |
| `company.is_gst_registered` | `True` |
| `CompanyGstin` id 1 | `29ABCDE1234F1ZW`, `is_primary=True`, `is_active=True` |
| peek `SALES_INVOICE` | prefix `INV-2627-F1ZW`, `gstin_key` `29ABCDE1234F1ZW`, `next_number` 14, `fy_label` `2026-27` |

`gstin_key` is the primary stamp, not empty. The `F1ZW` suffix is the last four characters of that stamp. This is not the stop condition. Health still reads the blank head-office column, which is the bug this PR fixes. Do not change `resolve_series_gstin` order. Do not renumber; next number stays 14 on prefix `INV-2627-F1ZW`.

Invalid non-blank PINs on the same database (India Post `[1-9][0-9]{5}`), counted before any delete:

| Table | Rows |
|---|---|
| `masters_customer` | id 192, company 1, pincode `-1` (MONKEY Probe, `monkey-probe@example.com`) |
| `company` | none |
| company GSTIN | none |

No other bad PINs. Delete only customer 192 on this demo tenant after the validator lands. Do not blank other rows.

### What is actually wrong

`resolve_series_gstin` (`document_numbers.py` lines 104–123) already resolves: stamp, else active primary `CompanyGstin`, else any active `CompanyGstin`, else `company.gstin`. The docstring omits the “any active” step. The code has it.

If that function returns empty, peek already uses an empty `gstin_key`. The prefix is then FY-only (`INV-2627`) or the legacy unscoped prefix. It does not keep allocating on an old `…-F1ZW` series. Do not “fix” that. Add a test that locks it.

`Company.is_gst_registered` is true when `company.gstin` is set, or when any active `CompanyGstin` exists. It does not require `is_primary`. That matches the “any active row” fallback in `resolve_series_gstin`.

Health and the editor ignore `CompanyGstin`:

- `build_gst_health` (`gst_health.py` 186–210) treats a blank `company.gstin` as `GSTIN_MISSING_COMPANY`. The `elif` / `else` format check, and the 90-day `GSTIN_UNVERIFIED` check, read `company.gstin`, `company.gstin_verification_status`, and `company.gstin_verified_at`.
- `companyStepIncompleteNeedsGst` is `registrationType === 'REGULAR' && !company.gstin`.
- `/api/v1/auth/me/` returned `gstin: ""`, which is only the head-office column.

`CompanyGstin` has no `gstin_verified_at`. Pointing the 90-day check at a branch GSTIN would warn forever.

### Precedence (do not invert)

Do not add an `effective_gstin()` that prefers `company.gstin` over `CompanyGstin` and then feed it into `resolve_series_gstin`. A company with both set to different values would get a new `gstin_key` and the sequence would restart at 1.

One function, the existing order. Health and UI call `resolve_series_gstin(company)` (no stamp). They do not reimplement it. `resolve_series_gstin` itself is not reordered.

### Health behavior

Let `resolved = resolve_series_gstin(company)`.

| Situation | Alert |
|---|---|
| `registration_type` is `UNREGISTERED` | No company-GSTIN alerts (unchanged). |
| `resolved` is empty, and the company is not unregistered | `GSTIN_MISSING_COMPANY`. |
| `resolved` is non-empty and fails `GSTIN_RE` | `GSTIN_INVALID_FORMAT` on `resolved`. |
| `resolved` equals stripped `company.gstin` | Keep today’s verification / 90-day branch on `company.gstin_verified_at`. |
| `resolved` comes only from `CompanyGstin` (`company.gstin` blank or different) | No `GSTIN_UNVERIFIED`. The stamp has no verification timestamp. Do not add those fields in this PR. |

`test_period_close_blocked_when_regular_company_has_no_gstin` (`test_holistic_remaining.py`) uses a company with no GSTIN and expects `GSTIN_MISSING_COMPANY` plus a blocked period close. That fixture must still have no `CompanyGstin` row, and the test stays red if the alert disappears. Keep it green.

### UI

- Expose the resolved value on the company payload as `seriesGstin` (name can match serializer style). Leave `gstin` as the head-office column so settings can still show it blank.
- `companyStepIncompleteNeedsGst` is true only when `registrationType === 'REGULAR'` and `seriesGstin` is empty. Fallback to `gstin` if an old payload has no `seriesGstin`.
- New Invoice and New Purchase: when `seriesGstin` is set, show that full GSTIN under the prefix. The “save a GSTIN” banner stays only when `seriesGstin` is empty.
- Update `taxHints.test.ts`.

### Acceptance: next number before and after

For each row, record peek `prefix`, `gstin_key`, and `next_number` before the patch and after. They must be equal. No sequence restarts.

| Company shape | Expected `gstin_key` | Health |
|---|---|---|
| Only `CompanyGstin` (primary or, if no primary, one active row) | That stamp | No `GSTIN_MISSING_COMPANY`. No `GSTIN_UNVERIFIED` from the stamp. |
| Only `company.gstin` | `company.gstin` | Missing alert off. Format and 90-day checks use `company.gstin`. |
| Both set, different values | The `CompanyGstin` winner (primary, else any active), not `company.gstin` | Missing alert off. 90-day check does not run against the stamp. |
| Neither | `""` | `GSTIN_MISSING_COMPANY`. Prefix has no GSTIN suffix. |

Add one API test for “both set and different” that asserts `gstin_key` is the stamp and `next_number` is unchanged from the pre-existing series row.

### Files

- `backend/reporting/gst_health.py`
- Company serializer used by auth/me
- `web/src/onboarding/taxHints.ts` and `taxHints.test.ts`
- `web/src/pages/sales/NewInvoicePage.tsx`
- `web/src/pages/purchases/NewPurchasePage.tsx`
- Company type for `seriesGstin`
- `backend/tests/test_holistic_remaining.py` (keep the no-GSTIN close test green)
- New test for both-GSTIN-values-differ

`document_numbers.py` changes only if a test shows peek and health disagree. Do not reorder `resolve_series_gstin` as part of the feature.

---

## Verification pass

On the demo tenant only, after the PR that owns the step:

1. PR 1. Paste `/sales/new` and `/sales/customers` with the new worker. Both show the app. From a copy of the old offline page, “Reload without cache” reaches login.
2. PR 2. Count bad pincodes first. `-1` on create is rejected and the message is the i18n string. `560001` saves; delete that new row in the same pass (`DELETE` as Owner, demo company only). Customer 192 is removed or its pincode corrected the same way. A phone-only edit of a legacy bad PIN succeeds.
3. PR 3. On a blank invoice, type additional charges and a walk-in name, open Complaints. The unsaved dialog appears. Stay shows both values. Open a restored device draft and leave without editing: no dialog.
4. PR 2. Customer search with no matches is titled “No results found”.
5. PR 4, only after the data check is filled in. The four-shape table above matches peek before and after. Demo Traders’ next invoice number is the same prefix and the same next integer as before the deploy.
