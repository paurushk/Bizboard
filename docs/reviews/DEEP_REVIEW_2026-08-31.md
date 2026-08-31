# Bizboard — Deep Review (2026-08-31)

Reviewer: Claude (Sonnet) · Scope: full repo at branch `main`, working tree **dirty**
(117 files, ~6,000 insertions uncommitted) · Prior audits cross-checked, not re-derived.

> **Remediation pass applied the same day (2026-08-31).** The bounded code findings
> below have been fixed in the working tree — see **§10. Remediation status**. The
> decision/infra items (§1.1, §1.2, §2.5) and the multi-week compliance features
> (§4) are unchanged and still need an owner.

---

## 0. Method & what was actually verified this pass

| Check | Command | Result (initial → after remediation) |
|---|---|---|
| Frontend typecheck | `tsc -b --noEmit --force` (web) | **FAIL — 5 errors** → **PASS (clean)** |
| Frontend unit tests | `vitest --run` | **181 / 181 pass** → still 181 / 181 |
| Frontend lint | `eslint .` | **FAIL — 6 errors, 15 warnings** → **0 errors, 8 warnings** (pre-existing, non-blocking) |
| Backend test suite | `pytest` | **NOT RUN** — local `.venv` is broken (see §1.1) |
| Backend lint / migrations | `ruff`, `makemigrations --check` | **NOT RUN** — same reason |
| Repo state | `git status`, `git diff` | Large uncommitted WIP on `main` (§1.2) |

> Correction to the first draft: the initial `tsc -b --noEmit` run was reported as
> "PASS" in error — the command's exit code was masked by a shell pipe. A forced
> re-run showed the WIP **did not typecheck** (5 errors, §3.6). Those are now fixed.

Backend correctness claims below are from **static reading + CI config + the existing
audit trail** (`DEEP_CODE_REVIEW_2026-08-29.md` + `_PROGRESS.md`, `KNOWN_LIMITATIONS_AND_TECH_DEBT.md`,
`UX_AUDIT_WAVE2_FINDINGS.md`, `E2E_UI_PLAYWRIGHT_VALIDATION_FINDINGS.md`). They should be
confirmed by running the suite once the environment is fixed.

**Overall:** this is a mature, unusually well-audited codebase. Settings hardening,
tenancy, tax engine, idempotency, and webhook handling are all defensively written with
traceable bug IDs. The dominant risks right now are **process/state** (huge uncommitted
change set, broken dev env, red lint) rather than raw code defects. The rest of this doc
is a consolidated issue list: fresh findings first, then still-open items carried from
prior audits.

Severity key: **P0** ship-blocker / data-or-money loss · **P1** correctness or
compliance gap · **P2** robustness / UX / maintainability · **P3** nice-to-have.

---

## 1. Repository & environment state

### 1.1 — P1 · Local backend virtualenv is broken
`backend/.venv/Scripts/python.exe` resolves to
`C:\Users\Dell\AppData\Local\Programs\Python\Python312\python.exe`, which no longer
exists on this machine (only Python 3.13 is installed; `py -3.12` is also a dead
launcher entry). `site-packages` holds `cp312` C-extension builds (PIL, cffi, psycopg,
yaml) that will not import under 3.13.

*Impact:* the backend test suite, `ruff`, `manage.py`, and `makemigrations --check`
cannot be run locally. Any backend claim in this review or the prior one is currently
**unverifiable on this workstation**.

*Fix:* rebuild the venv against an installed interpreter —
`py -3.12 -m venv backend/.venv` (matches CI's `python-version: "3.12"`), then
`pip install -c constraints.txt -r requirements-dev.txt`. Document the required Python
version in `backend/README` / `CONTRIBUTING`.

### 1.2 — P1 · ~6,000 lines of uncommitted work sitting on `main`
`git status` shows 117 modified files + ~40 untracked new modules/migrations/tests
(Waves 0 / A–D: `InventoryRunningCost`, `recompute_totals_for_stamped_gstin`,
`payments/holding.py`, `payments/dunning.py`, `reporting/ims*.py`, `reporting/chase.py`,
`insights/attention.py`, POS offline redesign, GSTR-2B page rewrite, …). The project
convention is to stage WIP on a `wip/phase0` branch (see recent commits); this work is
instead uncommitted on `main`.

*Impact:* single `git checkout`/`stash` mistake loses days of work; the change set is
too large to review or bisect as one blob; CI has never seen it; the migrations in it
(`accounts/0037-0040`, `inventory/0013-0014`, `masters/0010-0013`, `payments/0015-0016`,
`reporting/0009-0010`, `sales/0038-0041`, `accounting/0008`, `insights/0003-0004`) are
untested against the CI Postgres.

*Fix:* commit to a feature branch now, split into reviewable chunks by wave, run the
full suite + `makemigrations --check` before merge.

### 1.3 — P2 · Stray/committed scratch artefacts
`.tmp_invoice_preview/`, `backend/test_media/`, `docs/reviews/_wave*.py` (dozens of
one-shot generator scripts, `_stats.json` 242 KB, `_wave*_issues.py` up to 80 KB),
`docs/reviews/screenshots_*` dirs, `web/test-results/`. `MASTER_ISSUE_REGISTER.md` is
**1.9 MB** in a single file. These bloat clones and make `docs/reviews/` hard to
navigate. Move the generators to `scripts/` or an archive tag; git-ignore the output
dirs.

---

## 2. Backend findings (fresh, this pass)

### 2.1 — P2 · `except Exception` swallow sites are annotated but numerous
83 non-test `except Exception` sites. Most carry a `# noqa: BLE001 — must not break
the request` justification and are legitimate (metrics, request logging, permission
fast-paths, tenant-backup manifest). Two clusters worth a second look:
- `accounts/tenant_backup.py:136,141,227,232` — a backup/export that silently skips
  rows on any error can produce an export the Owner believes is complete. At minimum
  count + surface skipped entities in the manifest.
- `accounts/views.py:459` — bare `except Exception` with no annotation inside the OTP
  path; classify it (send failure vs. programming error) so a real bug isn't hidden as
  "SMS provider hiccup".

### 2.2 — P2 · `settings.py` env-var sprawl
~90 `os.environ.get` reads with ad-hoc parsing (`_parse_debug_flag`, `_env_value`,
inline `"1"/"true"/"yes"` sets, `!= "0"`, `in ("1","true","yes")`). Inconsistent truthy
parsing across flags (`GATEWAY_HOLDING_STATE` uses `!= "0"`; `REQUIRE_SUBSCRIPTION` uses
an explicit tri-state; most `ENABLE_*` use `== "1"` only, so `ENABLE_POS=true` is
silently **off**). Consolidate on one `env_bool()` / `env_str()` helper and a single
settings schema (e.g. `django-environ` or a typed dataclass) so operators get one
documented convention.

### 2.3 — P3 · `SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]` set twice
`settings.py:295` sets a 60-min placeholder, then `:539` overwrites from
`JWT_ACCESS_MINUTES` (default 15). Harmless but the dead placeholder invites a "why is
it 60?" bug later. Set it once.

### 2.4 — P2 · New Wave-0/A–D modules lack the surrounding review this repo usually applies
`reporting/ims.py`, `reporting/chase.py`, `reporting/ims_offline.py`,
`insights/attention.py` (578 lines), `payments/dunning.py` (381), `payments/holding.py`
introduce new state machines, new `@action` endpoints (`ims-act`, `ims-bulk-accept`,
`chase-whatsapp`, `ims-gsp-pull`, `supplier-message`, …) and new Celery beats
(`payments-ar-dunning`, `payments-gateway-holding-reconcile`). They read well, but:
- no committed tests have run against them in CI;
- `chase-whatsapp` / `supplier-message` / `dunning` send outbound messages on a beat —
  confirm the Owner opt-in gate (`masters/0011_a06_whatsapp_opt_in`,
  `masters/0012_a07_dunning_opt_out`) is enforced **server-side** on every path, not
  just the UI, and that a stub SMS/WA provider cannot silently no-op a "sent" state.

### 2.5 — Carried & still relevant from `DEEP_CODE_REVIEW_2026-08-29`
Per `_PROGRESS.md` most of that review's 95 findings are fixed or WIP. Genuinely still
open:
- **R2-022 / R2-023 (P2, perf):** `inventory.unit_cost()` replayed every `StockMovement`
  per COGS calc. The WIP adds `InventoryRunningCost` + `rebuild_running_cost` +
  `InventoryValuationSnapshot` — **verify** the running-cost row is maintained on *every*
  movement path (issue/receive/adjust/cancel/transfer/FIFO-peel) and that the "replay
  fallback" branch is only hit for FIFO tenants / empty cache, then close.
- **`test_tcs_sales_gl_206c` (P1):** pre-existing failing test. Contradiction:
  `apply_tcs_fold` recomputes TCS from the rate (→1.18) while the test asserts an
  explicit `tcs_amount=1.00` wins. Product decision needed: does an explicit amount
  override the rate, or does the rate always win? Ship the decision as a code change +
  updated test.

---

## 3. Frontend / build findings (fresh, this pass)

### 3.1 — P1 · `npm run lint` is red → CI `frontend` job fails on push/PR
`.github/workflows/ci.yml` runs `npm run lint` (`eslint . && check-fetch-all-pages.mjs`)
as a hard gate. Current tree has **6 eslint errors**:

| File | Line | Error |
|---|---|---|
| `web/src/pages/sales/NewInvoicePage.tsx` | 69 | `'Customer'` imported but never used |
| `web/src/pages/sales/NewInvoicePage.tsx` | 178 | `idempotencyKey` assigned but never read |
| `web/src/pages/purchases/NewPurchasePage.tsx` | 50 | `newIdempotencyKey` imported but never used |
| `web/src/pages/purchases/NewPurchasePage.tsx` | 223 | `idempotencyKey` assigned but never read |
| `web/src/pages/inventory/itemCustomFieldDefaults.ts` | 42, 88 | `no-useless-escape` on `\-` in a char class |

### 3.2 — P2 · Incomplete idempotency-key refactor on New Invoice / New Purchase
Root cause of two of the errors above. `PosPage.tsx` persists `idempotencyKey` into the
offline draft cache and reuses it on retry (correct). `NewInvoicePage.tsx:178/764` and
`NewPurchasePage.tsx:223/627/744` keep the same `useState`, call `setIdempotencyKey(key)`,
but **never read the state** — the actual submit uses a fresh
`userGestureIdempotencyKey()` each gesture (`NewInvoicePage.tsx:763,808`). So a user who
hits "Complete", gets a network blip, and retries can generate a *new* key and
double-create the invoice/purchase — the exact scenario the key exists to prevent. Either
wire the persisted key into the retry path (as POS does) or delete the dead state.

### 3.3 — P2 · `react-hooks/exhaustive-deps` warnings on the money-critical editors
`NewInvoicePage.tsx:488,1073`, `NewPurchasePage.tsx:484,1092`, `PosPage.tsx:734`:
effects/callbacks miss deps (`company.data?.assumeLocalStateForBlankParty`,
`company.data?.gstin`, `setError`, `saveMutation`). On these three pages a stale closure
means the GST intra/inter decision or the save handler can run against an old company
snapshot. Audit each — several look like real staleness, not noise.

### 3.4 — P3 · `react-refresh/only-export-components` in `HelpRichText.tsx:7`,
`phaseShared.tsx:18` — move shared constants/functions to a non-component file.

### 3.6 — P1 · The WIP does not typecheck (`tsc` — 5 errors) → CI `frontend` `npm run build` fails
Discovered on a forced re-run after the §0 correction. All in new/edited WIP files:
| File | Error |
|---|---|
| `pages/sales/NewInvoicePage.tsx:1132` | `UnsavedChangesGuard` used in JSX but its `import` was replaced by `usePreviewTotals` in the WIP's import-block edit |
| `pages/purchases/NewPurchasePage.tsx:1149` | same — dropped `UnsavedChangesGuard` import, kept the JSX |
| `components/CompanyRequiredDialog.tsx:22,29` | `parseMemberships` map returns `{…; role: string \| undefined}` (required) so the `m is MembershipChoice` type-predicate is invalid |
| `pages/inventory/godownConflict.ts:35` | `applyConflictChoice(conflicts, …)` — leading param unused under `noUnusedParameters` |

### 3.5 — Positive notes
- `console.*` in shipped code: **1** occurrence. `as any` / `: any`: 13. `@ts-ignore`: 0.
  Very clean for 69 kLOC.
- PWA API-cache poisoning (`BB-000738`) and offline-shell-as-fake-app (`BB-000737`) are
  addressed in `vite.config.ts` (navigate-only `NetworkFirst`, `/api` denylisted,
  `handlerDidError → offline.html`).
- AA mock-bank-data injection (`GAP-001`) is gated to dev/test in `banking/views.py:55`.

---

## 4. Compliance / accounting / GST gaps (still open — from `KNOWN_LIMITATIONS`)

These are documented "honest limitations", not regressions, but they are the real
functional gaps a pilot customer will hit:

| # | Area | Gap | Sev |
|---|---|---|---|
| 4.1 | **Live NIC / IRP GSP** | e-invoice & e-way submission is **fail-closed** until `GSP_CERTIFIED=1` + `GSP_LIVE_ENABLED=1`. The `custom` adapter's "encryption" is an HMAC-SHA256 placeholder, explicitly *not* NIC SEK/AES (`core/services/gsp_adapters.py:344-368`). No customer can actually file an IRN/e-way bill through the product yet. | P1 |
| 4.2 | **Cess** | Captured on documents only — **not** posted to GL, not in IRP/e-invoice line items, not supported for inclusive pricing or RCM. Cess liability is invisible in the books. | P1 |
| 4.3 | **Sales RCM** | GSTR excludes RCM sales, but the GL **still posts Output GST** on them → books vs. return mismatch. | P1 |
| 4.4 | **Multi-GSTIN GSTR-3B** | Filing stamp historically "resolved from an empty list". WIP `recompute_totals_for_stamped_gstin` + `series_identity()` address the invoice side — **verify** 3B aggregation now scopes to the stamped GSTIN for a multi-branch tenant. | P1 |
| 4.5 | **FIFO cancels/transfers** | Cancel of a challan / proforma / stock transfer / return peels the **wrong cost layers** (`KNOWN_LIMITATIONS` Wave 22). Silent inventory-valuation error. WIP running-cost work may or may not cover the FIFO peel paths — needs an explicit test matrix. | P1 |
| 4.6 | **GSTR-4 / 6 / 7 / 8** | "Honest stubs" — return an empty payload with `supported: false` and a disclaimer (`reporting/gstr2b.py:211-264`). Composition dealers, ISD, TDS, and e-commerce operators cannot file. | P2 |
| 4.7 | **GSTR-2B tables 4/5/6** | "not implemented" notes in the payload — import-of-services / reverse-charge / tax-paid tables absent. | P2 |
| 4.8 | **Payroll — employer PF/ESI** | Not posted to the GL. Employer statutory cost is missing from P&L. Also: no full HRMS (preview module). | P1 |
| 4.9 | **GRN (goods receipt note)** | Not implemented — purchases post stock directly on Complete, no separate receipt/inspection step. | P2 |
| 4.10 | **Postgres RLS** | `POSTGRES_RLS_ENABLED=0` and "stays off". Tenant isolation is **application-layer only** (`CompanyScopedModel` + middleware). One missing `.filter(company=…)` is a cross-tenant data leak with no DB backstop. | P1 |
| 4.11 | **Tally** | One-shot XML **export dump** only — no live/incremental sync despite the integration's presence in the nav. | P3 |
| 4.12 | **Offline outbox encryption** | Queued invoice drafts stored **plaintext** in IndexedDB/localStorage; mitigation is a logout wipe + a warning banner. | P2 |
| 4.13 | **FY close** | Zeros 4xxx/5xxx into 3100 but does **not** close 3200 (drawings/other equity). CA final-gate still required. | P2 |
| 4.14 | **Mobile** | `mobile/` is a Capacitor WebView shell (`webDir → ../web/dist`), no native source, no Play/App Store binary. Offline-billing target (8 h / 50 drafts) is a lab goal, not verified. | P2 |

---

## 5. UI / UX findings

### 5.1 — From `UX_AUDIT_WAVE2_FINDINGS.md` (2026-08-20/21, 4 Critical / 10 High) — re-verify against current tree
The WIP touches many of these areas; confirm each is closed before the pilot:
- **Conflicting Dashboard money figures** (different totals for the same metric across
  cards). `DashboardPage.tsx` is in the WIP diff — verify one source of truth.
- **Aggressive mid-flow session logout** — user loses an in-progress invoice on token
  expiry. Check refresh-on-401 + draft autosave actually rescue the form.
- **GST sales blocked / tax = ₹0 when customer state blank** — `sales/services.py`
  now raises `PLACE_OF_SUPPLY_UNRESOLVED` with a `confirm_blank_pos` escape hatch;
  confirm the FE surfaces a clear inline "confirm intra-state / set state" affordance,
  not a raw 400.
- **Negative stock shown on the home dashboard** as an alert on a fresh account.
- **PWA serves the offline shell despite a healthy API** — addressed in config (§3.5);
  re-test on a throttled connection.
- **Opening stock not available in the Add Product dialog** (must create, then adjust).
  `ItemFormDialog.tsx` has a Stock tab now — verify opening qty is capturable at create.

### 5.2 — From `E2E_UI_PLAYWRIGHT_VALIDATION_FINDINGS.md` (E2E3-001…039, marked "closed in workspace")
Marked fixed but on the **uncommitted** tree, so not yet in a shipped build. Notably:
- Login page had **no "forgot password" link**; register did **silent** empty-submit.
- Hindi toggle translated nav but **not Dashboard KPIs** (E2E3-034) — i18n coverage gap
  for number/label formatting on the dashboard.
- POS left an orphaned draft `sales invoice id 61` after a Complete-400 (GST on
  UNREGISTERED). Verify failed POS drafts are always voided/cleaned.

### 5.3 — Fresh observations
- **P2** · `PosPage.tsx` diff adds a UPI-QR path guarded by `upiComingSoon` copy
  ("UPI QR coming soon — use Cash or Collect Later", `en.ts:902`). A visible-but-dead
  payment method on the POS is a confusing dead-end; hide it behind the flag entirely
  until it works.
- **P3** · `itemCustomFieldDefaults.ts` regex bug (§3.1) is in a **validation** path —
  an unnecessary-escaped `\-` inside a character class is harmless in JS but suggests
  the intended range/exclusion wasn't what was written. Re-check the character class is
  correct, not just lint-clean.
- **P3** · 6 `disabled={u.role === 'OWNER'}` repeated inline in
  `UsersSettingsPage.tsx:206-275` — extract `const isOwner` for readability and to
  avoid one drifting.

---

## 6. Security observations

Mostly good. `settings.py` fails closed on: `*` in `ALLOWED_HOSTS` outside dev, DEBUG on
non-local hosts, placeholder `SECRET_KEY`, SQLite in prod/staging, missing
`CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS`, CORS wildcard + credentials, missing
`REDIS_URL`, `SameSite=None` refresh cookie without CSRF binding, SECRET_KEY-derived
`OTP_PEPPER` / `GSP_FERNET_KEY` when `DEBUG=False`, `OTP_DEBUG_ECHO` /
`CELERY_TASK_ALWAYS_EAGER` in prod. JWT refresh rotation + blacklist is on. Bearer auth
is disabled in prod (cookie-only). Throttle scopes are granular.

Open / to check:
- **6.1 — P1** · RLS off (§4.10) — the one structural weakness. Cross-tenant isolation
  has no defence-in-depth. Prioritise the RLS soak, or add a CI check that every
  `CompanyScopedModel` queryset in views goes through a tenant-scoped manager.
- **6.2 — P2** · `_KNOWN_PLACEHOLDER_SECRETS` is a hand-maintained denylist; a *new*
  weak-but-40-char secret still passes. Consider entropy check (unique-char ratio) in
  addition to length + denylist.
- **6.3 — P2** · `SANDBOX_WEBHOOK_SECRET` optional in production ("sandbox banned at
  view") — relies on the view check never regressing. Add a test that asserts the
  sandbox provider is rejected under `DJANGO_ENV=production` at the settings/serializer
  layer too.
- **6.4 — P3** · `pip-audit` / `npm audit` run in CI (good) but only `--audit-level=high`
  for npm and no fail-on for transitive dev deps. Acceptable; note it.
- **6.5 — P2** · New outbound-message beats (dunning / chase / supplier-message) — a
  compromised or misconfigured template + a broad customer filter = mass unsolicited
  WhatsApp/SMS from the tenant's number. Confirm per-run caps and opt-out enforcement.

---

## 7. Testing & CI observations

- **7.1 — P1** · CI `frontend` job currently fails (§3.1). Fix before the next push.
- **7.2 — P2** · Backend suite can't be run outside CI on this machine (§1.1) — slows
  iteration and means the WIP's ~15 new migrations + new modules are unproven locally.
- **7.3 — P2** · CI pins `python-version: "3.12"` but nothing in the repo declares that
  requirement for contributors (no `.python-version`, no `pyproject` `requires-python`
  near the app). Add it.
- **7.4 — P3** · `docs/reviews/_wave*_assert_gates.py` are load-bearing CI steps living
  in a `docs/` folder next to 80+ throwaway scripts. Move the asserted-in-CI ones to
  `backend/tests/` or `scripts/ci/` so they're not mistaken for scratch.
- **7.5 — P2** · No evidence the large WIP has a green `makemigrations --check` /
  `spectacular` snapshot / `helpCodes.json` diff (all CI gates). Run these before commit
  — the OpenAPI snapshot and `helpCodes.json` in particular drift silently.
- **7.6 — Positive** · CI runs the backend suite against real Postgres 17 (not SQLite)
  specifically for `SELECT … FOR UPDATE` fidelity — good call, keep it.

---

## 8. Suggested priority order

**Do before the next commit/push**
1. Move the WIP off `main` onto a branch; commit in wave-sized chunks (§1.2).
2. Fix the 6 eslint errors / red CI (§3.1); decide dead-vs-wire on the idempotency
   state (§3.2).
3. Rebuild the backend venv; run `pytest` + `ruff` + `makemigrations --check` +
   `spectacular` + `helpCodes` diff on the WIP (§1.1, §7.5).

**Before the pilot**
4. Resolve `test_tcs_sales_gl_206c` product decision (§2.5).
5. Verify the running-cost cache covers all movement paths incl. FIFO peel (§2.5, §4.5).
6. Verify multi-GSTIN 3B scoping, blank-place-of-supply UX, dashboard money consistency,
   session-expiry form rescue (§4.4, §5.1).
7. Enforce & test server-side opt-in + per-run caps on every dunning/chase/WhatsApp
   send path (§2.4, §6.5).
8. Decide the RLS timeline or add the tenant-scope CI guard (§4.10, §6.1).

**Known gaps to communicate to pilot customers (not necessarily fix now)**
9. No live IRN/e-way filing (§4.1); cess not in books (§4.2); RCM books/return mismatch
   (§4.3); no GRN (§4.9); composition/ISD/TDS/TCS returns are stubs (§4.6); Tally is
   export-only (§4.11); payroll employer PF/ESI not in GL (§4.8).

**Cleanup**
10. Env-var helper consolidation (§2.2); prune `docs/reviews/` scratch + shrink
    `MASTER_ISSUE_REGISTER.md` (§1.3); tenant-backup skip-counting (§2.1);
    exhaustive-deps sweep (§3.3).

---

## 9. Appendix — files inspected

Backend: `config/settings.py` (full), `sales/services.py` (diff), `inventory/services.py`
+ `models.py` (diff), `payments/{holding,dunning}.py`, `reporting/{ims,chase,ims_offline,
gst_rate_scan}.py`, `insights/attention.py`, `banking/{views,fiu_adapter}.py`,
`core/services/gsp_adapters.py` (grep), `reporting/gstr2b.py` (grep), `reporting/gst_periods.py`
(grep), `.github/workflows/ci.yml` + `cd.yml` (diff).
Frontend: `vite.config.ts`, `NewInvoicePage.tsx` / `NewPurchasePage.tsx` / `PosPage.tsx`
(idempotency paths), `offline/invoiceDraftCache.ts`, i18n `en.ts` (grep), eslint/tsc/vitest
full runs.
Docs: `DEEP_CODE_REVIEW_2026-08-29(_PROGRESS).md`, `KNOWN_LIMITATIONS_AND_TECH_DEBT.md`,
`UX_AUDIT_WAVE2_FINDINGS.md`, `E2E_UI_PLAYWRIGHT_VALIDATION_FINDINGS.md`.

Not covered (time/scope): `accounting/services.py` internals, `crm/`, `manufacturing/`,
`payroll/` internals, `imports/` OCR pipeline, the full 297-file web tree, mobile Gradle
config, load tests. Prior audits cover much of this; a follow-up pass should target
`accounting/services.py` and the imports pipeline.

---

## 10. Remediation status (2026-08-31)

### Fixed in the working tree this pass

| # | Finding | Fix |
|---|---|---|
| 3.1 | 6 eslint errors → red CI | `NewInvoicePage`: dropped unused `Customer` import + dead `idempotencyKey` state. `NewPurchasePage`: dropped unused `newIdempotencyKey` import + dead `idempotencyKey` state (incl. `resetForm` + gesture writes). `itemCustomFieldDefaults.ts`: `[\s_\-]` → `[\s_-]` (×2). **`eslint .` now 0 errors.** |
| 3.2 | Incomplete idempotency-key refactor | Confirmed the offline queue→flush path already reuses `draft.idempotencyKey` (`OfflineOutboxPage.tsx:69,77`), so no double-create risk — the React state was pure dead code. Removed it; added a comment on the `PD-01` gesture-key contract. POS keeps its state (genuinely used). |
| 3.3 | `exhaustive-deps` on money editors | `NewInvoicePage`/`NewPurchasePage` edit-hydration effects: cherry-picked `company.data?.x` deps → `company.data` + `setError` (both effects are one-shot, guarded by `loadedEdit`, so no extra re-runs). Keydown effects: `saveMutation.isPending/.mutate` → `saveMutation`. `PosPage` checkout `useCallback`: removed unused `idempotencyKey` + module-level `t` from deps. |
| 3.4 | `react-refresh/only-export-components` | Added a scoped `eslint-disable` with rationale to `phaseShared.tsx` and `HelpRichText.tsx` (deliberate shared-helper modules). Other pre-existing occurrences in 6 unrelated files left as-is (non-blocking warnings, not named in the finding). |
| 3.6 | **WIP did not typecheck (5 `tsc` errors)** | Restored the `UnsavedChangesGuard` import in `NewInvoicePage.tsx` + `NewPurchasePage.tsx` (JSX still used it; WIP import-block edit had dropped it). `CompanyRequiredDialog.tsx`: annotated the `parseMemberships` map callback `: MembershipChoice \| null` so the type-predicate is valid. `godownConflict.ts`: `conflicts` → `_conflicts` (unused leading param). **`tsc -b --noEmit --force` now clean.** |
| 2.1 | Tenant-backup silently skips unreadable file assets | `build_export_payload` now collects `file_asset_warnings` (per-asset `checksum_unreadable` / `bytes_unreadable`); `encrypt_export_zip` writes `file_asset_warning_count` + the list into `manifest.json`. `accounts/views.py` OTP `except Exception` now `# noqa: BLE001` + logs a warning (last-4 only, `exc_info`) instead of swallowing silently. |
| 2.2 | `settings.py` env-var truthy sprawl (`ENABLE_POS=true` silently off) | Added `_env_bool(key, default)` (one convention: `1/true/yes/on`). Converted 24 flag sites: all `ENABLE_*`, `GSP_LIVE_ENABLED`, `GSP_CERTIFIED`, `POSTGRES_RLS_ENABLED`, `GSP_HTTP_SANDBOX`, `OTP_ENABLED`, `OTP_DEBUG_ECHO`, `ADMIN_ENABLED`, `ENABLE_API_DOCS`, `USE_TLS`, `CELERY_*`, `JSON_REQUEST_LOGS`, `AUTO_PICK_COMPANY_ON_EMPTY`, `GATEWAY_HOLDING_STATE` (kept default-on), `DJANGO_FAIL_FAST_SECRETS`, `REQUIRE_SANDBOX_WEBHOOK_SECRET`. `ast.parse` clean. |
| 2.3 | `SIMPLE_JWT` access-lifetime set twice | Removed the 60-min placeholder from the dict literal; the two `SIMPLE_JWT[...] = timedelta(...)` lines below (from `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS`) are now the only assignment. |
| 5.3 | "UPI QR coming soon" dead POS control | The WIP actually **ships** POS UPI checkout (`startUpiCheckout` + `getUpiQr` + QR render). The `upiComingSoon` i18n key was orphaned — removed from `en.ts` + `hi.ts`. |
| 5.3 | `UsersSettingsPage` repeated `u.role === 'OWNER'` ×8 | Extracted `const isOwner = u.role === 'OWNER'` once per row. |

Post-fix verification (from `web/`): `tsc -b --noEmit --force` **clean**; `eslint .`
**0 errors**, 8 pre-existing non-blocking warnings; `vitest --run` — see run log
(must be run from `web/`, not repo root, or it recurses into `.claude/worktrees/`).

### NOT fixed — needs a decision or is a multi-week feature

| # | Why it's not a code-fix |
|---|---|
| 1.1 | Rebuild `backend/.venv` — the Python 3.12 the venv targets is **gone** from this machine and `py -3.12` is a dead launcher entry. Needs a 3.12 install (or a decision to move to 3.13 + `constraints.txt` bump), then `pip install -c constraints.txt -r requirements-dev.txt`. |
| 1.2 | Moving ~6,000 lines of WIP off `main` onto a branch and committing in chunks is a git operation the repo owner should drive. |
| 2.4 | Reviewing the new Wave-0/A–D modules (`ims`, `chase`, `dunning`, `holding`, `attention`) properly needs the backend suite running (§1.1) + a test-matrix pass. |
| 2.5 | `test_tcs_sales_gl_206c` — product decision: does an explicit `tcs_amount` override the rate, or does the rate always win? |
| 4.1–4.14 | Live GSP/IRN filing, cess in the GL, RCM books/return parity, FIFO layer peeling, Postgres RLS, GRN, payroll employer PF/ESI in GL, GSTR-4/6/7/8 engines — each is a feature, not a review-fix. Communicate to pilot customers. |
| 5.1–5.2 | Re-verifying the prior UX/E2E findings (dashboard money consistency, session-expiry rescue, Hindi KPI i18n, POS orphan-draft cleanup) needs the running app + a Playwright pass. |
| 6.1 | RLS soak / a CI guard that every `CompanyScopedModel` queryset is tenant-scoped — infra task. |
| 7.3 | Add `.python-version` / `requires-python` — trivial, but pairs with the §1.1 decision on which interpreter. |
