# Dashboard + Needs attention — path to 10/10

Date: 2026-10-19. Source: the screen review of `/` ([DashboardPage.tsx](../../web/src/pages/DashboardPage.tsx)) and
`/attention` ([AttentionPage.tsx](../../web/src/pages/AttentionPage.tsx)), backed by
[attention.py](../../backend/insights/attention.py), `insights/views.py`, `ReportService.dashboard`.
Starting scores: overall 6/10 (error handling 4, data/state 5, cognitive load 5).
Work-package IDs: **DAN-00 … DAN-19**.

## 0. Decisions (defaults apply unless the founder overrides)

| ID | Question | Default used by this plan |
|---|---|---|
| D1 | Dismiss/snooze: shared per company, or per user? | **Shared per company, but attributed** (who, when, why shown on the row) and reversible. Per-user hiding would let one person's blind spot differ from another's on money risks. |
| D2 | Should cashier/sales roles get a limited feed? | **No.** The feed endpoint stays financial-reports only. Because every caller already has `can_view_financial_reports`, `_can_see` is effectively a no-op today (each branch has an `or can_view_financial_reports`). **Do not delete the sales/inventory/payments branches**: `_can_see` is reused as the *assignee* check (DAN-04), where an operational team member without financial reports is a legitimate assignee. Instead: (a) document `_can_see` as "does this person own/handle this code", (b) fix the `TICKET_SLA_BREACH` / `CONTRACT_RENEWAL` / `MILESTONE_OVERDUE` / `JOB_READY_TO_INVOICE` branch so it also admits financial-reports users, (c) decide whether GST/stock codes should additionally be gated by `can_view_tax_worksheets` / `can_manage_inventory` for accountants (default: no, financial-reports is enough). |
| D3 | Which rows may be dismissed without a reason? | **`info`/`warning` rows: reason optional. All `critical` rows: reason required (≥3 chars).** Rows in the explicit `NON_DISMISSIBLE` set (below) cannot be dismissed, but **remain snoozable and assignable** (an owner must be able to assign a GST fix to the accountant). Enforced server-side. |
| D6 | Dismissed/snoozed rows whose condition has gone away | The Snoozed/Dismissed tabs must still render them, so a **snapshot** is persisted on `AttentionRowState` at dismiss/snooze time (DAN-09). |
| D7 | "New since last visit" storage | **Per-user server-side** `last_attention_seen_at` on `CompanyUser` (survives logout and devices); `localStorage` is not used. |
| D4 | Is the `Money` column a loss figure? | **No.** Rename to "Amount involved" and show a per-row basis label (overdue, invoice total, tax delta, credit at risk). Ranking stays severity, then amount, but the basis is visible. |
| D5 | Language of row text | Backend returns code + params; client translates (EN/HI). Needs Hindi review (new QOS item). |

## 0f. Closure pass (2026-10-20): every item left open above is now closed or decided

Where 0a to 0e say "not done", read this section; it supersedes them.

| Was open | Now |
|---|---|
| DAN-04 unknown keys accepted; classification not enforced | Keys for codes outside `KNOWN_CODES` are refused. A test fails if a detector emits a code that is not in `KNOWN_CODES`, the dedupe-key document, or the Hindi/English catalogue. |
| DAN-05 all-or-nothing pause; no truncated signal | `DETECTOR_CODES` maps each detector to the codes it owns; only those codes keep their state when it fails or is capped (an unknown detector name pauses everything). The feed envelope carries `truncated_codes` and the page shows a banner. |
| DAN-07 return-trip feedback; run-time links | Fix remembers the row; on return the page says "Resolved: …" only when it can see the whole list. A test builds a real feed and checks every link against the route table. |
| DAN-08 `AR_OVERDUE_CUSTOMER`, Collections card | **Decision:** `AR_OVERDUE_CRITICAL` / `AR_OVERDUE_WARN` / `AR_OVERDUE_CUSTOMER` are company-wide aging summaries, not per-customer, so they stay separate rows. The Collections card stays: it is the collections worklist with its record-payment action, which the feed does not offer. |
| DAN-09 custom snooze | "Another length…" accepts 1 to 90 days, validated. |
| DAN-10 diagnostics, getting started, timezone, footing | Counter diagnostics moved to an owner-only settings screen (`/settings/counter-diagnostics`). The invite prompt waits until the checklist is complete. A note says today and this month follow IST. A test shows receivables equal the sum of the aging buckets, with uncleared cheques shown beside them. |
| DAN-11 translations | Every detector text now has `params` and an English and Hindi template, except `GST_GUARDRAIL` (and the three reserved e-invoice/GSTR-2B codes), whose text is the GST health module's own message and is shown as written. The shared actions are one component (`AttentionRowActions`). A test checks the catalogue against the code list. |
| DAN-13 focus, keyboard, contrast | Vitest checks keyboard use and focus return; Playwright runs axe with colour contrast on, in English and Hindi, in real Chrome. The product has a light theme only, so there is no dark-mode check. |
| DAN-14 telemetry | One `attention_action` event per action (migration `0016`). |
| DAN-15 stress, per-customer cost | Test with 5,000 invoices and 500 customers. `customer_risk_snapshot` now uses one bulk outstanding query per customer (1,505 to 455 queries for the capped 30 customers). |
| DAN-16 Postgres, roles, attribution | `test_dan_concurrency_postgres.py` passed on PostgreSQL 17 after it found a real defect (a dismissed row still carrying a snooze); each action now takes the row lock. Role matrix covers every role; a second person sees who set a row aside and can reopen it. |
| DAN-17 offline | The page now says "You are offline" and keeps the list (it used to say nothing). Playwright covers offline and back. |
| DAN-19 follow-ups | `manage.py attention_cleanup_old_keys` (dry run by default, `--apply` deletes) is ready for one release after shipping. The deployed beat service runs `celery -A config beat`, which reads the sweep entry from settings; a test pins both. |

Verification (2026-10-20): backend suite 5,248 passed (non-Postgres), 3 Postgres race tests passed on PostgreSQL 17, web suite 2,874 passed, 5 live-backend Playwright tests passed in real Chrome, 76 mock-mode Playwright tests (axe, mobile layout, dashboard budget) passed, tsc, eslint (0 errors), ruff and `qos-lint` clean. Two GSTR snapshot tests (`test_gstr1_json`, `test_gstr3b_json`) fail, and fail identically on a clean checkout of HEAD, so they are not from this work.

Still not done, because they need a person: **QOS-0137** (Hindi review: `docs/ATTENTION_HINDI_REVIEW.csv`, about 200 lines), **QOS-0138** (accountant sign-off on the amount labels and receivable footing), **QOS-0139** (one physical phone).

## 0a. Phase A status (built 2026-10-19, uncommitted)

DAN-01…06 are built and tested. Differences from the plan as written:
- **DAN-04:** unknown or free-form keys are not rejected (existing tests deliberately use keys such as `NOT_A_SOURCE:4`). Rules are applied by code parsed from the key: `NON_DISMISSIBLE`, reason for critical rows (severity read from the cached live feed) and `DUPLICATE_PAYMENT`, `_can_see` for the actor and the assignee. The persisted snapshot idea moves to DAN-09.
- **DAN-05:** instead of mapping each key to an owning detector, any failed detector pauses the dismissal lapse and the resolved-outcome sweep for that round; a capped detector pauses it only for its own codes (`status.truncated`). Failures show as a non-dismissible `FEED_DEGRADED` row; a degraded result is cached for 5 s, a healthy one for 60 s, with the status stored alongside the rows.
- **DAN-06:** `GET` is read-only; `sweep_attention_state` runs every 5 minutes for every company (`insights-attention-sweep`), and `first_seen` for unstored rows is the 5-minute bucket start so it does not advance on refresh.
- New row fields so far: `dismissible`, `snoozable`, `assignable`, `requires_reason` (section 2a lists the rest, still to come in DAN-09/11/12).
- Tests: `backend/tests/test_dan_phase_a_attention.py` (16), plus new web tests in `AttentionPage.test.tsx` and `DashboardPage.test.tsx`.

## 0b. Phase B status (built 2026-10-19, uncommitted)

DAN-07…10 are built. Differences from the plan as written:
- **No `ENABLE_ATTENTION_V2` flag.** A new flag means five registries (settings, two backend lists, web flags, packs) and their parity tests. The risky part, the key change in DAN-08, is made rollback-safe in data instead: migration `0015` COPIES state to `AR_CUSTOMER:<id>` and leaves the old rows. DAN-19 therefore ships Phase B ungated.
- **DAN-07:** every static link in the detectors is checked against `App.tsx` routes by `tests/test_dan_phase_b_links.py`; rows without a link fall back to a page for their kind, never `/`. Cache invalidation is by model signals (`insights/signals.py`), not a `?from=attention` parameter; the page refetches on mount.
- **DAN-08:** the dashboard's separate "top 3 business alerts" list is removed (they are in the feed). `CollectionAttentionCard` is kept for now: it shows the collections worklist, which the feed does not.
- **DAN-09:** snapshot, fingerprint, `state_at` on `AttentionRowState`; `last_attention_seen_at` on `CompanyUser`; `reopen`/`seen` endpoints; `status`, `severity`, `category`, `assigned`, `limit`, `offset` query parameters; row fields `amount_basis`, `age_days`, `is_new`, `state`, `state_by`, `state_at`, `state_reason`.
- **DAN-10:** health chip for every dashboard user (health endpoints now need financial reports, not AI); the insights strip, the duplicated sales sentence and the "Alerts" heading are gone (low stock is headed "Low stock"); an "updated at" line and Refresh button added. **Not done:** moving "Counter diagnostics" off the home screen (it stays collapsed at the bottom) because no destination page exists yet.
- Tests: `test_dan_phase_b_attention.py`, `test_dan_phase_b_links.py`, and new web tests.

## 0c. Phase C status (built 2026-10-19, uncommitted)

DAN-11…13 are built. Differences from the plan as written:
- **DAN-11:** rows carry `params` and keep their server text. The client (`components/attention/rowText.ts`) uses the catalogue (EN + HI) for the codes that have values (merged customer row, degraded feed, ITC at risk, IRN failed, GST rate exposure, paid-pending-books) and for the known action labels, and falls back to the server text for everything else or when a template would show an unfilled `{value}`. The health band (`healthy`/`watch`/`action`) now comes from the server (`health_band`), not from 70/45 in the UI. `Draft #`, `ms` and telemetry failure reasons are translated. Not translated yet: the many detector titles/reasons without structured values; they need params added detector by detector.
- **DAN-12:** health chip wording is "Worth watching" (no longer "Needs attention"); "Money" became "Amount involved" with a basis label; the Needs attention help page explains snooze/dismiss/reopen, the amount, non-dismissible rows and the degraded banner.
- **DAN-13:** phone layout is a card list; action buttons are described by their row (`aria-describedby`, so the button name stays "Dismiss"); 44 px touch targets on phones; dashboard header buttons wrap; the empty table header and heading order were fixed (section titles are h2, KPI values and empty-state titles are no longer headings). axe passes on both pages in jsdom (colour contrast is left to the browser pass).
- Tests: `test_dan_phase_c_attention.py`, plus web tests for translation, fallback, descriptions, phone cards and axe.

## 0d. Phase D status (built 2026-10-20, uncommitted)

DAN-14 and DAN-15 are built. Differences from the plan as written:
- **DAN-14:** dismiss, snooze, assign and reopen run in one transaction with an `AuditEvent` (`attention.dismissed` etc.) holding the full key, reason, and state before and after. A separate telemetry event was not added: the audit trail is the single source. The key contract is `docs/ATTENTION_DEDUPE_KEYS.md`, and `tests/test_dan_phase_d_attention.py` fails if a detector adds a key shape or code that the document does not list.
- **DAN-15:** the dashboard payload carries the first five low-stock rows, so the page no longer calls the stock-alert endpoint on load (the attention feed's own low-stock check runs inside its 60-second cache). `_overdue_customer_rows` now finds the customers who really owe with two bulk queries and builds the expensive risk snapshot only for them; this also fixes a correctness bug where 30 customers with paid-up overdue invoices could crowd out one who still owed. `_residual_return_rows` uses the bulk outstanding query (constant query count, tested). Not done: a stress test with 5,000 invoices / 500 customers and a p95 budget; `customer_risk_snapshot` itself is still per customer (capped at 30).

## 0e. Phase E status (done 2026-10-20, uncommitted)

- **DAN-16:** role matrix, company isolation and paging-clamp tests (`test_dan_phase_e_attention.py`); a live-backend Playwright spec (`web/e2e-golden/attention-golden.spec.ts`, run with `playwright.golden.localchrome.config.ts`): overdue invoice to row, snooze, Snoozed tab, reopen, dismiss, Undo, Hindi, phone cards. Both tests pass.
- **DAN-17 (browser pass, found real defects, all fixed):** (1) the Needs attention page did not re-render when the language was switched (it lacked `useLocale()`, a bug that predates this work); (2) the dashboard scrolled sideways by 581 px on a phone because the visually-hidden table header I added in DAN-13 escaped its scroll container; (3) the row button read "Snooze 7d" though the dialog offers 1, 7 and 30 days; (4) "1 items". Checked by eye on desktop and 375 px screenshots. Colour contrast on a real device is left to QOS-0139.
- **DAN-18:** QOS-0137 (Hindi review), QOS-0138 (accountant sign-off on the amount labels and receivable footing), QOS-0139 (device/contrast check), QOS-0140 (Postgres concurrency); `docs/PRODUCT_QUALITY_BACKLOG.md` regenerated, `qos-lint` passes; `FREEZE_SCOPE_COVERAGE.md` rows added.
- **Still open:** the Postgres two-writer test (QOS-0140; SQLite does not exercise row locks), the 5,000-invoice stress budget, "Counter diagnostics" still on the dashboard, many detector texts without structured values for Hindi, and the CA sign-offs.
- Dev database: migrations `accounts.0066`, `insights.0014`, `insights.0015` were applied to the local `db.sqlite3` by the e2e run.

## 1. Target state per dimension

| Dimension | Now | Target | What gets it there |
|---|---:|---:|---|
| Purpose clarity | 8 | 10 | DAN-08, DAN-10 (one alert surface, clear naming) |
| UX | 6 | 10 | DAN-03, 07, 08, 09, 13 |
| Cognitive load | 5 | 10 | DAN-08 (merge overdue signals), DAN-10 (reorder/collapse), DAN-09 |
| Flow | 6 | 10 | DAN-07 (deep links, post-fix refresh), DAN-09 |
| Functionality | 7 | 10 | DAN-09, DAN-12 (snooze presets, undo, filters, show snoozed) |
| Business logic | 6 | 10 | DAN-04, 05, 06 |
| Data/state handling | 5 | 10 | DAN-02, 04, 05, 06 |
| Error handling | 4 | 10 | DAN-01, 03, 11 |
| Cross-product integration | 7 | 10 | DAN-07, 08, 14 (events, cache invalidation) |
| Consistency | 6 | 10 | DAN-11, 12 (i18n, shared components) |
| Accessibility | 6 | 10 | DAN-13 |

"10" here means: every finding in the review closed, each closed finding has a regression test, and the
verification gate in section 5 passes. It is not a claim of zero unknowns; open items are listed in section 6.

## 2. Work packages

Order: Phase A (correctness, ship first) → B (state model) → C (flow and UX) → D (consistency, a11y, polish) → E (verification).

### Phase A — correctness and trust (P0/P1)

**DAN-01 — Error and empty states (P0).**
- [AttentionPage.tsx:96](../../web/src/pages/AttentionPage.tsx:96): render EmptyState only when `query.isSuccess && rows.length === 0`.
- Never show ErrorState and EmptyState together. Add a "last updated" stamp and a stale banner when a refetch fails but old data exists (keep rows visible, say they may be out of date).
- Dashboard preview: same rule; add per-section ErrorState so one failed card does not hide others.
- Tests (vitest): API 500 → error only, no "all clear"; refetch failure keeps rows plus stale banner; success + 0 rows → empty.

**DAN-02 — Dashboard resilience.**
- Stop gating the whole page on `getDashboard`. If it fails, show an inline ErrorState in the KPI area with retry; the Attention preview, Collections card and onboarding still render.
- Gate `getDashboard`, `listLowStock` and `listAttentionRows` with `enabled: canViewFinancialReports(user)` (all three 403 otherwise), so a non-financial user who somehow renders the page gets one redirect/forbidden state, not several inline 403 errors. `HomePage` already redirects them; this is the defence for direct renders and permission changes mid-session.
- Guard `localStorage` in try/catch; key the invite-CTA flag by `userId:companyId`.
- Tests: dashboard 500 with attention OK renders attention; storage throwing does not crash.

**DAN-03 — Mutation feedback.**
- Dismiss, snooze, assign: pending state on the button (disabled, spinner), success toast ("Dismissed. Undo"), error shown **inside** the dialog (or as a row-level alert for plain dismiss), never at page bottom.
- Do not close the duplicate-payment dialog until success: today [AttentionPage.tsx:231](../../web/src/pages/AttentionPage.tsx:231) calls `setDismissing(null)` synchronously right after `dismiss.mutate(...)` (unlike snooze/assign, which close in `onSuccess`). Move it into `onSuccess`; keep the typed reason on failure.
- Call `dismiss.reset()` / `snooze.reset()` / `assign.reset()` when a dialog opens or closes so a stale error from one row never shows on another.
- Prevent double submit via `isPending` on all three.
- Tests: 400 on dismiss shows message and keeps reason; double-click sends one request; error visible while dialog open.

**DAN-04 — Server-enforced dismiss/snooze/assign rules (backend).**
- Validate the key **without re-running the 10+ live detectors on every POST**. Order: (1) existing `AttentionRowState` for `(company, dedupe_key)` (which carries the persisted snapshot, DAN-09) → use its `code`; (2) otherwise parse the code from the key (`code_for_key`) and check it against the code registry; (3) only if neither resolves, fall back to one cached-feed lookup. Reject (`400`, code `row_not_actionable`) unknown keys and codes the actor cannot handle (`_can_see`). Already-snoozed/dismissed rows (acted on from the tabs) are valid targets.
- Replace the UI regex `/gstin/i` with an explicit set in `attention.py`, per action:
  - `NON_DISMISSIBLE = {GST_GUARDRAIL, GST_RATE_EXPOSURE, ITC_AT_RISK, GSTR2B_UNMATCHED, GST_HEALTH_CRITICAL_OPEN, EINVOICE_FAILED, EINVOICE_PENDING, IRN_FAILED, PAID_PENDING_BOOKS, FEED_DEGRADED}` (final list confirmed against every code emitted by `alerts.py`, `services.build_growth_hints`, `customer_actions`, `predictive_dunning` during implementation; a test fails if a new code is added without being classified).
  - These stay **snoozable and assignable**. `FEED_DEGRADED` is neither snoozable nor assignable.
- Critical rows require a reason on dismiss (D3); replace the `DUPLICATE_PAYMENT:`-only prefix check.
- Assignee must pass `_can_see(assignee, code)` (see D2: those branches are kept for exactly this), else `BusinessRuleError`.
- Row contract v2 (see section 2a) adds `dismissible`, `snoozable`, `assignable`, `requires_reason`; the UI reads them instead of regex/code checks. Regenerate OpenAPI snapshot and `openapi-types.ts`.
- Tests: direct API dismiss of GST row → rejected; critical dismiss without reason → rejected; unknown key → rejected; assign to user who cannot see the code → rejected.

**DAN-05 — Don't lose decisions when detectors fail (backend).**
- `_build_raw_rows` returns `(rows, status)` where `status` maps `detector → ok | failed | truncated`; wrap each detector in a runner that records it.
- Failure must be visible at the source: [`_run_alert_builder`](../../backend/insights/alerts.py:71) currently logs and returns `[]`, so `build_business_alerts` cannot tell a failed sub-builder from an empty one. Change it to record failures into a status collector (returned alongside the alerts). Same for the detectors that run **outside** the cached call in `build_attention_rows` (`predicted_rows`, `build_customer_action_rows`, `_residual_return_rows`): they report status too.
- **Cache the status with the rows.** `_build_raw_rows_cached` stores `(rows, status)` together so a cache hit still knows about failures/truncation (otherwise a hit would let `_apply_state` un-dismiss rows from a detector that failed on the miss). A **degraded result is not cached** (or cached for ≤5 s) so a transient DB error is not served to every user for 60 s.
- `_apply_state` un-dismisses a key **only if** its owning detector ran successfully and was not truncated. Keys from a failed/capped detector keep their state.
- Replace the silent `except Exception: return rows` blocks (`_itc_and_gst_rows`, `_expiry_rows`) with logged failure + the detector status; surface "some checks could not run" as a visible banner row (code `FEED_DEGRADED`, non-dismissible) so a failed detector can never look like "all clear".
- Remove hard caps from the correctness path: either raise caps to "all" with pagination, or return a `truncated: true` flag and a "+N more" row linking to the full list.
- Tests: detector raises → dismissed row stays dismissed, banner appears; cap hit → no un-dismiss churn; condition truly gone → un-dismiss.

**DAN-06 — Make the feed read-only (backend).**
- Move state writes out of GET: `bulk_create` of first-seen rows, snooze expiry reset, un-dismiss sweep and `observe_resolved_outcomes` go to a periodic task. GET issues **strictly zero writes** (no "lazy touch").
- **The task must not use `_iter_ai_company_ids()`** (the existing tasks in `insights/tasks.py` do; they only cover `ai_features_enabled` companies). The attention feed is not AI-gated, so the sweep iterates all active companies (or those with activity in the last N days), in batches.
- `first_seen` stability: until the sweep persists a row, GET computes `first_seen` in memory, which would advance on every refresh. To avoid that, the in-memory value is `min(raw detector timestamp where available, otherwise the start of the current sweep interval)`, and the sweep interval is short (5 min). Acting on a row (`assign`, `snooze`, `dismiss`) already creates its state row with `first_seen=now` via `get_or_create`; make those pass the in-memory `first_seen` they were shown so outcome windows are not reset.
- `observe_resolved_outcomes` only counts assigned rows that left the feed; with the sweep it runs against the same persisted `first_seen`, so a fast fix (< one interval) after an assign is still recorded because assign persists the state.
- Tests: GET issues zero writes (assert on write queries); the sweep covers a non-AI company; sweep produces the same outcomes as before; first_seen does not advance across consecutive GETs; existing `test_b05_attention` and `test_attention_outcomes` still pass.
- Risk: outcome timing shifts by up to one task interval; check the 7-day window tests and `learning_report`.

### Phase B — state model and attribution

**DAN-07 — Actionable rows and post-fix refresh.**
- Require a specific `action_href` for every code: add a test that iterates all detector codes and asserts `href != "/"` and resolves to a real route. `AR_COLLECTION_RISK` links to the customer snapshot route `/sales/customers/:id` (verified in `App.tsx`; `customer_actions.py` already uses it), not the `/sales/customers` list. Where the next step is collection, link to `/reports/customer-ledger?customer={id}` (as `CollectionAttentionCard` does). The all-codes link test resolves each href against the router table so a wrong route fails the test.
- Fix links carry `?from=attention&row=<dedupe_key>`; when the destination flow completes, call `invalidate_attention_cache` (server) and `invalidateQueries(['attention-rows'])` (client), and show "Resolved" feedback on return.
- Reduce the 60-second raw cache window for rows that change by user action (receipts, returns, invoice completion): signal-based invalidation from those services.
- Tests: all-codes link test; receipt posted → row gone on next load without waiting 60 s.

**DAN-08 — One receivables signal per customer; one alert surface.**
- Backend: collapse the **customer-scoped** receivables signals into one row per customer (`AR_CUSTOMER:{customer_id}`) with the strongest severity and a combined reason. Scope, verified against the code:
  - Merge: `AR_COLLECTION_RISK` (`…:customer:{id}`), `PREDICTED_LATE_PAYMENT` (key per **invoice**, `predictive_dunning.py`), `PROMISE_TO_PAY_DUE` (key per **promise**) and `CREDIT_LIMIT_NEAR` (`…:customer:{id}`). `AR_OVERDUE_CRITICAL` / `AR_OVERDUE_WARN` are company-wide aging alerts (payload is the company aging), so they are not merged either; they stay as one company-level row each.
  - Do **not** merge `AR_OVERDUE_CUSTOMER`: its hint key is company-scoped (`AR_OVERDUE_CUSTOMER:hint:{company}`), so it is not a per-customer signal; and `AR_RESIDUAL_AFTER_RETURN` stays per-invoice (different action: fix a return).
  - Sub-signals stay listed in the merged row's detail (list of `{code, invoice/promise ref, amount}`), so the user sees why.
- **Migration is a copy, not a rename** (also needed for the flag rollout, DAN-19). Group old `AttentionRowState` / `AttentionOutcome` rows by `(company, customer)` and write one new-key row per group: `first_seen = MIN`, `dismissed = AND` (a group counts as dismissed only if all its sub-rows were), `snooze_until = MIN` among non-expired, `assigned_to`/`due_date` from the most recent. This avoids the `(company, dedupe_key)` unique-constraint violations a plain key rename would hit when a customer has several invoice/promise rows. Old rows stay in place.
- **Escalation resets suppression.** A merged key must not let an old dismissal/snooze hide a *new* problem (e.g. dismissed overdue on Monday, a promise-to-pay comes due Tuesday). Store a `signal_fingerprint` (sorted set of active sub-signal codes + max severity) in the state snapshot at dismiss/snooze time; if the current fingerprint adds a code or raises severity, clear `dismissed`/`snooze_until` and show the row with an "updated" marker.
- Tests: one customer with all signals → one row; customer with 3 invoices of old state → migration succeeds without `IntegrityError`; dismissed then new promise due → row reappears; dismissed and nothing new → stays hidden.
- Dashboard: remove the separate top-3 business-alert list from the insights strip (these already flow into the feed); rename the low-stock section "Low stock" (not "Alerts"); keep `CollectionAttentionCard` only if it shows something the feed does not (a promise-to-pay calendar), otherwise fold it into the feed and remove it.

**DAN-09 — Attention page features.**
- Default sort severity then amount; add filters (severity, category: money / GST / stock / customers, assigned: all/mine/unassigned, status: open/snoozed/dismissed) and a count per filter.
- "Snoozed" and "Dismissed" tabs showing who/when/why with **Reopen** (undo). Backend: list endpoint accepts `status`, returns `state_by`, `state_at`, `state_reason`; add `reopen` endpoint (audit-logged).
  - **Snapshot for the tabs.** `AttentionRowState` gains `snapshot` (JSON: `code`, `severity`, `params`, title/reason/action_label, `money_impact_paise`, `amount_basis`, `action_href`, `entity_ref`, `signal_fingerprint`), written at dismiss/snooze/assign time from the row the user saw. The Snoozed/Dismissed tabs read `AttentionRowState` directly (no detector run) and still render rows whose condition has since disappeared; if the condition is gone they are marked "Resolved since" and offered "Clear".
  - **Reopen vs outcomes.** `AttentionOutcome` is unique on `(company, dedupe_key)` and `observe_resolved_outcomes` skips any key already present, so a dismissed-then-reopened row could never later count as resolved, and it would inflate `dismissed_in_window`. `reopen` therefore deletes the `DISMISSED` outcome for that key (the audit-log entry from DAN-14 is the immutable record) and a regression test asserts a reopened row that is later fixed counts as `resolved`. Undo from the toast uses the same path.
  - **`state_by` identity.** `updated_by` is a `User` FK while `assigned_to` is a `CompanyUser` FK. The API returns `state_by` as `{user_id, name}` (display name resolved server-side) and `assigned_to` keeps `CompanyUser.id`; the UI never matches one id space against the other.
  - **"New" marker.** Per D7, store `last_attention_seen_at` on `CompanyUser`, set by a `POST /insights/attention/seen/` call when the user leaves/unmounts the Attention page (and not by GET). `is_new = first_seen > last_attention_seen_at`.
- Snooze presets 1 / 7 / 30 days plus custom (backend already supports 1–90).
- Pagination (default 25, "load more") so the page scales past the current caps.
- Show age ("open 9 days") from `first_seen`, and a "New" marker for rows first seen since the user's last visit.
- Dashboard preview: show "+N more" count; header shows total and critical counts.
- Tests: filters, tabs, reopen, presets, pagination, age, count correctness.

**DAN-10 — Dashboard information architecture.**
- New order: header → critical attention (preview) → KPI tiles → receivables/payables aging → recent invoices → low stock. Onboarding and invite CTA collapse into one dismissible "Getting started" card that disappears once complete.
- Move "Counter diagnostics" (owner telemetry) out of the home screen into the ops/insights area (project rule: staff tooling does not go on the customer SPA home). Keep a link for owners.
- Move the negative-stock policy note to GST/inventory settings; show it on the dashboard only as a normal attention row when policy is not BLOCK.
- Drop the duplicate "Sales today" sentence; keep tiles. Show the health chip for all dashboard users (not AI-gated). `compute_health_score` is deterministic (no LLM), but `HealthScoreView` / `HealthHistoryView` currently require `CanViewAiInsights`, so a non-AI user would get 403 and the chip links to an AI-gated page. Backend: change both views to `CanViewFinancialReports`; frontend: relax the `/insights/health` route guard to match and fetch `getBusinessHealth` with `enabled: canViewFinancialReports(user)`; the AI-only parts of the Insights hub stay gated. Test: non-AI owner sees the chip, 200 from both endpoints, and the destination page renders.
- Add "as of <time>" and a refresh button; define "today/month" in company timezone and say so in a tooltip.
- Reconcile numbers: a footing test that `receivables == sum(aging buckets)` (+ uncleared cheques disclosed) and that the tile links open the matching drill-down with identical totals (QOS item for CA sign-off if TDS affects it).

### Phase C — consistency, accessibility, localisation

**DAN-11 — i18n and shared components.**
- Backend rows **keep** `title`, `reason`, `action_label` populated (English, or translated via `Accept-Language`) so other consumers (exports, summaries, API clients) don't break, and **also** return `code` + structured `params`. The client renders from catalog keys (EN + HI) when it has one for the code and falls back to the server text otherwise. Remove the `'Open rate back-scan'` string match.
- Replace hardcoded strings (`Draft #`, `ms`, telemetry reason keys, policy enum) with i18n keys.
- Extract a shared `AttentionRowActions` and `SeverityChip`/money formatter used by both preview and table so they cannot drift.
- Health thresholds (70/45) come from the backend response.
- Tests: key-coverage check (every code has EN and HI); Hindi snapshot of a long row; a lint that no string literals remain in these two files.

**DAN-12 — Terminology.**
- "Needs attention" is the section and nav name only. The health band becomes "Watch" / "Action needed" / "Healthy". Column "Money" → "Amount involved" plus basis label (D4). Glossary entry in help content.

**DAN-13 — Accessibility and responsive.**
- Row actions get accessible names ("Snooze: <title>"); each row is a list item/table row with a described severity; focus returns to the trigger after a dialog closes; live region announces dismiss/snooze/undo results.
- Phone layout: Attention page becomes a card list below `sm`; row actions in a menu; dashboard header buttons wrap or collapse into a menu.
- Touch targets ≥ 44 px; contrast check on warning/critical chips in light and dark.
- Tests: axe on both pages (light/dark, EN/HI), keyboard-only walkthrough e2e, 375 px screenshot with no horizontal page scroll.

### Phase D — integration and observability

**DAN-14 — Events and audit.**
- Every dismiss/snooze/assign/reopen writes an audit entry (actor, key, reason, before/after) and a telemetry event; the learning report reads from the same source.
- Document the dedupe-key format as a contract (`docs/`), add a test that fails when a detector changes its key format without a migration entry. This closes the regression risk of orphaned state.

**DAN-15 — Performance budget.**
- Keep `test_qos0016_dashboard_budget`; add budgets for the feed endpoint (query count and p95 with 5k invoices / 500 customers). Replace the per-customer loop in `_overdue_customer_rows` with one aggregate query. Use `select_related`/bulk for `_residual_return_rows` (currently per-invoice ledger call).
- The dashboard stops issuing unused queries (insights summary only when its panel renders).
- **Low stock is computed three times per dashboard load**: `ReportService.dashboard` (`low_stock_alert_payload`), `listLowStock`, and the attention feed (`alerts.py` low-stock builder). Compute once per request/short TTL (memoise `low_stock_alert_payload` per company for ~60 s with the same invalidation hook as the feed), and return the top-5 low-stock rows in the dashboard payload so the page no longer calls `listLowStock` on mount (the full list stays on `/inventory/low-stock`). Test: dashboard + feed load triggers one low-stock computation.

### Phase E — verification

**DAN-16 — Test completion.** Close every gap listed in the review:
- Web: dashboard attention preview, errors, permissions redirect; attention snooze, assign, mine, filters, tabs, reopen, empty+error, stale banner.
- Backend: all DAN-04/05/06/07 cases above; tenant isolation for new endpoints; role matrix (owner, accountant with/without flag, sales, cashier, viewer).
- e2e (Playwright, `web/e2e`): dashboard → Fix → complete → returns and row gone; dismiss critical needs reason; shared dismissal visible to a second user with attribution.
- Postgres run for the new concurrency cases (two users dismiss/snooze the same key at once).

**DAN-17 — Browser pass.** Manual/automated walkthrough on desktop and 375 px, light/dark, EN/HI, slow network and offline; capture screenshots.

**DAN-18 — Docs and QOS.** Update `docs/FREEZE_SCOPE_COVERAGE.md`, add QOS backlog items for: Hindi review of new strings, CA sign-off on receivable figures, device check. Note decisions D1–D5.

**DAN-19 — Rollout.** Ship Phase A behind no flag (pure fixes). Ship DAN-08/09/10 behind `ENABLE_ATTENTION_V2` (default on in dev, off in prod for one release). The DAN-08 migration **copies** state to the new keys and leaves the v1 keys untouched, so the v1 path keeps working while the flag is off and turning it off again is a clean rollback. Old keys are removed by a separate cleanup migration one release after the flag is deleted.

## 2a. Row contract v2 (the frozen `AttentionRow` shape changes in one place)

`ATTENTION_ROW_KEYS` / `_contract()` in `attention.py` currently strip anything outside the frozen 13 keys, and several tests assert the exact shape (`test_b05_attention`, `test_growth_os`, `test_holistic_*`, persona tests). The new fields are introduced **once**, here, behind a version bump; every WP above refers to this table.

| Field | Type | Added by | Notes |
|---|---|---|---|
| `params` | object | DAN-11 | structured values for client i18n |
| `amount_basis` | enum (`overdue`, `invoice_total`, `tax_delta`, `credit_at_risk`, `none`) | DAN-12 | labels the amount (D4) |
| `dismissible`, `snoozable`, `assignable` | bool | DAN-04 | server decides (D3) |
| `requires_reason` | bool | DAN-04 | critical rows |
| `signal_fingerprint` | string | DAN-08 | escalation detection |
| `state` | enum (`open`, `snoozed`, `dismissed`) | DAN-09 | |
| `state_by` | `{user_id, name}` or null | DAN-09 | |
| `state_at`, `state_reason` | datetime / string or null | DAN-09 | |
| `is_new` | bool | DAN-09 | from `last_attention_seen_at` |
| `age_days` | int | DAN-09 | from `first_seen` |

Feed envelope (today `{rows, count}`): adds `total_count`, `critical_count`, `counts_by_filter`, `next_cursor`, `truncated`, `degraded` (list of failed detectors), `as_of`.

Work: update `ATTENTION_ROW_KEYS`, `_contract`, serializers, OpenAPI snapshot and `openapi-types.ts`; update every test asserting exact keys; keep old keys unchanged so v1 clients keep working.

## 3. Sequencing and dependencies

```
DAN-01 ─┬─ DAN-03 ── DAN-09
DAN-02 ─┘
DAN-04 ─┬─ DAN-09 (uses dismissible flags)
DAN-05 ─┤
DAN-06 ─┘── DAN-14 ── DAN-15
DAN-07 ── DAN-08 ── DAN-10
DAN-11 ── DAN-12 ── DAN-13
all ── DAN-16 ── DAN-17 ── DAN-18 ── DAN-19
```

Parallelisable once DAN-04's contract (new row fields) is agreed: backend (04, 05, 06, 14, 15) and web (01, 02, 03, 11, 13) touch different files.

## 4. Migrations and operator steps

- New row-contract fields: regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` (CI diff-checks both).
- DAN-06: new periodic task; confirm the scheduler entry in deploy config.
- DAN-08: one-time **copy** migration of `AttentionRowState` / `AttentionOutcome` into merged `AR_CUSTOMER:{id}` keys (merge rules in DAN-08; must not violate the `(company, dedupe_key)` unique constraints).
- DAN-09: `AttentionRowState` gains `state_at`, `snapshot` (JSON), `signal_fingerprint`; `CompanyUser` gains `last_attention_seen_at`. Backfill `state_at` from `updated_at`; `state_by` is derived from the existing `updated_by` (a `User` FK).
- DAN-06: scheduler entry for the sweep covering all active companies (not only AI-enabled).
- DAN-10: `HealthScoreView` / `HealthHistoryView` permission change (no migration).

## 5. Verification gate ("done" means all true)

1. Every review finding P0–P3 has a closed WP and a test that fails before the fix.
2. `tsc -b`, eslint (0 errors), vitest, ruff, backend suites for `insights`, `reporting`, `payments` green; OpenAPI drift check green.
3. Postgres concurrency run passes for the new dismiss/snooze race tests.
4. Browser pass (DAN-17) recorded: no console errors, no horizontal scroll at 375 px, axe clean.
5. Dashboard budget tests pass; feed p95 within the new budget.
6. Re-score with the same 20-section review: no dimension below 9, overall ≥ 9.5.

## 6. Residual risks / what 10 does not claim

- Receivable totals and TDS treatment need CA sign-off (QOS item).
- Hindi copy needs human review (QOS item).
- The "amount involved" ranking is still a heuristic; D4 makes it honest, not predictive.
- The merged-row migration (DAN-08) is the riskiest change: it is why it ships behind a flag.
- Estimate (rough): Phase A 3–4 days, B 5–6, C 3–4, D 2–3, E 3 — about 3 weeks for one developer, less with the backend/web split.
