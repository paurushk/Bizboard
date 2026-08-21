# Opening Stock / Master Data Import — Issues, Gaps &amp; Remediation

**Date:** 2026-08-21
**Scope:** Master CSV/XLSX import (Products, Customers, Suppliers, Opening Stock) — `backend/imports/`, `backend/core/services/files.py`, `web/src/pages/settings/ImportPage.tsx`. Purchase/Sales Bill LLM pipeline is separate and out of scope.
**Method:** Code review + live requests against the actual endpoints (Django test client) + config inspection. Load-test numbers below are measured, not estimated.
**Related:** full narrative writeup published as an artifact ("Opening Stock Import Audit") in this session.

Severity key: **Critical** (blocks or corrupts a normal first-time import) · **Medium** (real gap, workable today) · **Low** (polish / hardening)

---

## Critical

### IMP-001 — Commit is synchronous and row-by-row; measured to exceed every configured timeout at ordinary catalog sizes
- **Category:** Performance / Scalability
- **Evidence (measured, live requests, Django test client + in-memory SQLite):**

  | Rows | Commit time | ≈ ms/row |
  |---|---|---|
  | 1,000 | 44.3s | 44.3 |
  | 3,000 | 134.0s | 44.7 |
  | 5,000 | 220.0s | 44.0 |
  | 10,000 | 526.7s | 52.7 |

  Cost is linear per row — consistent with an uncapped per-row query pattern, not a one-off outlier.
- **Code:** `backend/imports/services.py:560–669` (`ImportService.commit` — no `bulk_create` anywhere in the write loop); `backend/inventory/services.py:35–75+` (`InventoryService.post_movement`, called once per OPENING_STOCK / opening-stock-bearing PRODUCTS row, itself issuing a warehouse lookup + row-locking balance read + existence check + insert + balance update per call).
- **Impact:** **1,000 rows is an ordinary catalog size for the target persona, not an edge case.** At 1,000 rows the commit alone (44.3s) already exceeds gunicorn's default 30s worker timeout (see IMP-002). By ~2,500–3,000 rows it exceeds the deliberately-configured 120s ceiling used by both nginx and the frontend. A typical first-time opening-stock upload has a real, high chance of failing outright.
- **Fix:** Batch the write loop in `ImportService.commit` — `bulk_create` for Customer/Supplier/Product rows, and replace the per-row `post_movement` call for OPENING_STOCK with a batched movement + balance write. Once batched, re-measure before deciding whether a timeout-flag fix (IMP-002) alone is sufficient or whether commit needs to move off the request/response cycle entirely (e.g. onto Celery, matching the async pattern the bill-import pipeline already uses).

### IMP-002 — No explicit gunicorn `--timeout`; production runs on the implicit 30s default
- **Category:** DevOps / Configuration
- **Evidence:** `backend/Dockerfile:33` — `CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]`, no `--timeout` flag. Gunicorn's sync-worker default is 30 seconds. Compare `nginx/default.conf:39,51,62` (`proxy_read_timeout 120s`) and `web/src/api/legacy/misc.ts:7` (`IMPORT_TIMEOUT_MS = 120_000`) — both clearly tuned with large imports in mind, but the gunicorn worker is SIGKILL'd well before either applies, and nginx returns a 502.
- **Impact:** The real failure ceiling in production is an unannounced, three-times-smaller number than every other layer was configured for. Compounds IMP-001 directly.
- **Fix:** Set an explicit `--timeout` value in the Dockerfile's gunicorn command, chosen deliberately (and documented) relative to nginx's/the frontend's 120s. Treat as a stopgap for small files only — it does not fix IMP-001's underlying per-row cost.

### IMP-003 — Windows-1252/ANSI CSV (Excel's default export option) is rejected, with an error message that blames the wrong thing
- **Category:** File Handling / UX
- **Evidence (reproduced with a live upload request):** A CSV encoded as Windows-1252/ANSI — what Excel calls plain **"CSV (Comma delimited)"**, the default/first entry in Excel's Save As dialog and the only CSV option in pre-2016 Excel — is rejected at the MIME-sniffing layer, before `ImportService.validate`'s own decode step ever runs. Actual server response: `400 — "File type 'text/csv' is not allowed."` For contrast, a BOM-prefixed UTF-8 CSV (Excel's *other* "CSV UTF-8" export option) containing é, ₹, and Devanagari text was confirmed to validate cleanly end-to-end (`201`, 1 valid row, 0 errors) — the underlying pipeline handles international text fine once it clears the sniffer.
- **Code:** `backend/core/services/files.py:45–68` (`_looks_like_text_csv` — rejects any byte in the sampled header that is neither ASCII nor valid UTF-8, so a high byte like `0xE9` for 'é' in cp1252 fails); `:71–111` (`_sniff_mime`); `:175–178` (the generic "file type not allowed" error raised regardless of *why* sniffing failed).
- **Impact:** The single most likely real-world Excel export for a non-technical user is rejected with a message that reads as "wrong file format," not "wrong encoding" — for a file the browser correctly labeled `text/csv`. The correct in-app hint (`en.ts:377–379`) only helps if read before hitting this wall.
- **Fix:** In `_looks_like_text_csv`/`_sniff_mime`, distinguish "not CSV-shaped" from "CSV-shaped but non-UTF-8." Either (a) decode as cp1252 with a fallback, mirroring the `utf-8-sig` fallback `ImportService.validate` already has, or (b) raise a specific, actionable `BusinessRuleError` at the sniff layer ("This CSV isn't UTF-8 — in Excel use File → Save As → CSV UTF-8 (Comma delimited)") instead of the generic rejection.

### IMP-004 — Formula/CSV injection is sanitized on one export path and not on two others that imported data can reach
- **Category:** Security
- **Evidence:** Names entered via the CUSTOMERS/SUPPLIERS/PRODUCTS import CSV are stored verbatim — no check for a leading `=`, `+`, `-`, `@`. That's acceptable on its own; the risk is where it's read back out. `reporting/views.py:597–606,629` (`_csv_safe`, used by the general `ExportView`/`EXPORTS`, including `inventory-summary`) *does* neutralize a leading formula character. Two other CSV writers in the same codebase do not:
  - `backend/integrations/tally/adapter.py:453–486`, specifically line 477 — `build_tally_export_csv` writes `inv.customer.name` straight into a cell via plain `csv.writer`.
  - `backend/accounts/tenant_backup.py:116–125` (`_csv_bytes`) — writes every field of every model verbatim for the full-tenant backup/export, including any imported `Product`/`Customer`/`Supplier` name.
- **Impact:** A name like `=HYPERLINK("http://evil","click")`, entered once via import, survives untouched and later opens live in Excel through either export path — both realistic places for a business owner or their accountant to open a CSV.
- **Fix:** Route both `build_tally_export_csv` and `_csv_bytes` through `_csv_safe` (or an equivalent shared helper), matching the protection the main `ExportView` path already has.

---

## Medium

### IMP-005 — Void is job-level only, and permanently blocked once any unit from the job has sold
- **Category:** Data Recovery / UX
- **Evidence:** `ImportService.void` (`backend/imports/services.py:673–790`) reverses an entire import job atomically, or not at all — there is no way to undo a single bad row out of an otherwise-good file. It is blocked outright the moment *any* unit from *any* row in that job has been sold or issued (`:697–719`, `"Cannot void import: stock ... has already been used"`). Since this app exists specifically to let a new business start selling immediately, that window can close within hours of the import. The UI's confirm-dialog copy (`en.ts:386–388`) is honest about this, which is good, but doesn't change the underlying gap.
- **Impact:** A single wrong row can make an entire correct-otherwise import job permanently un-voidable as soon as one sale happens anywhere in it. Note: `Stock Adjustment` (an `ADJUSTMENT` movement) is a real, working fallback for correcting *quantity* even after void closes, since the one-shot lock only checks `MovementType.OPENING_STOCK` (`imports/services.py:171–177`) — but it doesn't fix a wrong SKU/product mapping, and is surfaced only as one line of hint text (`adjustStockHint`).
- **Fix:** Add row-level void — reverse just the OPENING_STOCK movements tied to specific rows a user flags as wrong, rather than requiring the whole job to be untouched. Shorter term: make the Stock Adjustment fallback more discoverable (a direct link/CTA from a blocked-void error, not just static hint text).

### IMP-006 — Full `preview`/`errors` payload returned unpaginated in one JSON response
- **Category:** Performance / API Design
- **Evidence:** `backend/imports/serializers.py:9–14` exposes the entire `preview` and `errors` JSONFields on the create/upload response. The frontend only renders the first 50/100 rows (`PREVIEW_CAP`/`ERROR_CAP`, `ImportPage.tsx:48–49`) but the full arrays are still transferred and held in browser memory regardless of file size.
- **Impact:** Bandwidth and memory cost scale with file size with no cap — worse the larger the (already slow, see IMP-001) file gets.
- **Fix:** Paginate or cap the `preview`/`errors` arrays server-side, or move the full error report to a dedicated CSV-streaming endpoint (the error CSV download already exists client-side, `downloadErrorsCsv`, and could be backed by a real streaming export instead of the in-memory array).

### IMP-007 — Upload retries are not idempotency-key-stable, unlike commit
- **Category:** Reliability / Edge Case
- **Evidence:** `commitImport` correctly reuses one `commitKey` across retries of the same job (`ImportPage.tsx:98,113,121`), so a retried commit safely replays the stored response instead of double-committing. `uploadImport` does not: it calls `idempotencyHeaders()` with no key argument (`web/src/api/legacy/misc.ts:83–89`), which mints a **fresh** UUID on every call (`client.ts:266–268`).
- **Impact:** If a first upload attempt actually completes server-side but the client gives up (timeout, closed tab) before seeing the response, a retry carries a different Idempotency-Key and can create a second `ImportJob`/`FileAsset` for the same file. Low practical severity since nothing commits without a separate explicit user action, but inconsistent with how carefully commit is protected.
- **Fix:** Have `uploadImport` derive and reuse a stable key across retries of the same file (e.g. keyed on file hash + kind), the same pattern `commitImport` already uses.

### IMP-008 — No progress indicator during a long synchronous commit
- **Category:** UX
- **Evidence:** The commit button becomes a disabled spinner (`commitMutation.isPending`) for the entire duration of one blocking request — no row-count or percentage feedback. `ImportPage.tsx`.
- **Impact:** Fine for small files. Once row counts climb into the range measured in IMP-001, an unchanging spinner is indistinguishable, to a first-time non-technical user, from a frozen tab.
- **Fix:** Depends on IMP-001's fix. If commit moves to Celery/async, add real progress polling. If it stays synchronous for smaller files, at minimum show elapsed time or an estimated-rows-remaining indicator once row count exceeds a threshold.

---

## Low

### IMP-009 — Fuzzy header-alias matches are applied silently
- **Category:** UX / Data Integrity
- **Evidence:** `MASTER_COLUMN_ALIASES` (`backend/imports/services.py:39–57`, applied via `_map_master_row`, `:69–80`) resolves header variants like "Item Name" → `name` automatically, with no confirmation shown to the user.
- **Impact:** A wrong alias match (e.g., two similarly-named columns, one intended as SKU, the other silently picked) would only surface as odd-looking data in the preview table — never as an explicit "we mapped X → Y" step the user can catch before committing.
- **Fix:** Surface resolved alias mappings in the preview step ("We mapped your column 'Item Description' to Name — OK?").

### IMP-010 — Template sample rows never demonstrate an optional field left blank
- **Category:** UX / Onboarding
- **Evidence:** `CSV_TEMPLATES` (`ImportPage.tsx:40–46`) ships exactly one fully-populated sample row per kind. The in-app copy correctly states "Other columns are optional" (`en.ts:379`), but no example row shows what "optional" looks like in practice.
- **Impact:** Minor — a first-time user has to infer from prose alone which columns they can safely leave blank.
- **Fix:** Add a second sample row per template with one or two optional fields empty.

---

## Verified NOT issues (for traceability — do not re-flag)

These were explicitly checked against the current code and confirmed correct or already fixed. Listed so they aren't re-discovered as "new" findings in a future pass.

| Area | Status | Evidence |
|---|---|---|
| Rollback/undo after commit | **Exists.** `ImportService.void` + `POST /imports/{id}/void/` + UI button with confirm dialog. | `imports/services.py:673–790`, `imports/views.py:207–213`, `ImportPage.tsx:133–170,384–391` |
| Column mapping for non-exact headers | **Exists** (fuzzy alias matching, ~15 variants/field). | `imports/services.py:39–57,69–80` |
| Excel (.xlsx/.xlsm) upload | **Accepted**, both client and server side. | `ImportPage.tsx:225`, `imports/services.py:428–453` |
| Idempotency-Key on the initial upload/create endpoint | **Supported**, same durable-record mechanism as commit. | `imports/views.py:76–138`, `core/idempotency.py` |
| 10MB size cap disclosure | **Surfaced** before upload in copy. | `en.ts:377–379` |
| Optional vs. required columns | **Disclosed** in copy ("Other columns are optional"). | `en.ts:379` |
| Error report export | **Exists** — CSV download button. | `ImportPage.tsx:61–84,271–273` |
| Currency-symbol / suffixed price values (`"$40"`, `"40.00 INR"`) | **Correctly rejected**, not silently coerced (confirmed via live request). | `imports/services.py:107–117` |
| Duplicate SKU (in-file and against-DB) | **Correctly rejected**, never merged/overwritten. | `imports/services.py:129–194` |
| Blank file / corrupted header | **Clean error message**, not a stack trace. | `imports/services.py:480–486,493–494,508–510` |
| BOM-prefixed UTF-8 CSV with é/₹/Devanagari | **Validates correctly end-to-end** (confirmed via live request: 201, 1 valid row, 0 errors). | `imports/services.py:489` (`utf-8-sig` decode) |

---

## Suggested fix order

1. **IMP-001 + IMP-002** (commit performance + timeout) — blocks the flow from being a safe default for any customer with a normal-sized catalog.
2. **IMP-003** (encoding rejection) — blocks the single most common real-world file format for this persona.
3. **IMP-004** (formula injection on two export paths) — security gap, cheap fix (reuse existing `_csv_safe`).
4. **IMP-007** (upload idempotency) — cheap, matches an existing pattern.
5. **IMP-005, IMP-006, IMP-008** — real gaps, workable today via existing fallbacks (Stock Adjustment, client-side capping, spinner).
6. **IMP-009, IMP-010** — polish.
