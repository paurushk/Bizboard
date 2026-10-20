# Insights — path to 10/10

Date: 2026-10-19. Source: [INSIGHTS_SCREENS_REVIEW_2026-10-19.md](../reviews/INSIGHTS_SCREENS_REVIEW_2026-10-19.md)
(findings INS-01 … INS-27). Screens: Hub, Health, Cashflow, Alerts, Assistant.
Code: `backend/insights/`, `web/src/pages/insights/`, `web/src/components/insights/`.
Work-package IDs: **INP-00 … INP-24**. Starting score: module 5/10 (business logic 4, data/state 4, error handling 4, integration 4).

## Implementation status (2026-10-20, uncommitted)

Built: INP-01 to INP-18, INP-19 (summary `generated_at`/`stale` plus one task retry; no separate run-status model), INP-20 (Alerts links to Needs attention; no merge), INP-21 for the five screens (including the shared `AlertInboxRow`), INP-22, INP-23 (masking is client-side on narrative, factor detail, alert messages, assistant text and chart labels; the backend still writes amounts into those strings), INP-24 partly (chart text summary, focusable history points, `role="log"` transcript, chat-first on phones; no axe run).
D12 built: owner-only `POST /insights/ai-consent/` (strict true/false, audit event `company.ai_consent.enabled/disabled`), a confirmed switch button on `/settings/ai`, and a link from the consent-off screen. The company PATCH still ignores the flag. The same flag also gates bill scan, which uses a paid service, so an owner can now turn that on for themselves.
Postgres: `tests/test_insights_concurrency_postgres.py` (two simultaneous confirms send once; three simultaneous refreshes leave one live row per rule) passes on postgres:17, together with the rest of the new Insights tests. `upsert_alerts` now also locks the company row so concurrent refreshes take turns. `AlertInboxRow` is translated. Still not run: browser pass, axe, Hindi review.
Migration: `insights/migrations/0017_alert_snooze_attribution_unique_live.py` (follows the Attention migrations 0014-0016, which are also uncommitted).

## 0. Decisions (defaults apply unless the founder overrides)

| ID | Question | Default used by this plan |
|---|---|---|
| D1 | What does "absolute" cashflow mean? | **Current cash**: opening balance rolled forward by posted cash/bank movements since `opening_cash_as_of`. If no baseline, show **relative** and label it "Net change", never "Ending cash". |
| D2 | Do Insights alerts and `/attention` merge? | **Not in this plan.** Keep both; make Hub/Alerts honest and cross-link. Merge stays with DAN-08. Snooze state is shown as "also snoozed on Attention" only if cheap (INP-20). |
| D3 | Assistant permissions | Each tool requires the permission its data normally needs (reports → `can_view_financial_reports`, customer balance → customer view). Sending a reminder requires the same permission as sending reminders elsewhere. |
| D4 | Assistant threads | **Private to creator**; owner can read none (no admin read). Existing company-wide threads stay visible to their `created_by` only; rows with null creator are hidden. |
| D5 | Health grade when data is thin | **Keep computing and storing `score`/`grade`** (`BusinessHealthSnapshot.score` and `.grade` are NOT NULL, and `test_health_score_shape` / `test_health_golden_band` assert a 0-100 score and a letter on a thin tenant). The **UI and assistant withhold** the grade when `limited_data` is true (default threshold: fewer than 30 completed invoices in the last 90 days) and show "Not enough data yet" plus the factors that can be computed. API adds `grade_withheld: true`; no migration. History chart marks limited-data points. |
| D6 | Payables factor definition | Share of open AP that is **not overdue** (same shape as Collections). Replaces the payments-ratio formula. Caveat: `payables_aging` treats a bill with no due date and `payment_terms_days == 0` as due on its invoice date, so it turns overdue next day. Default: for this factor only, undated zero-terms bills get a 30-day grace, shown in the factor detail. |
| D7 | Cashflow band | Three scenarios from collection rates: low = rates ×0.6, base = current, high = rates ×1.2 (capped at 100%). Labelled "Scenario range", not "confidence". |
| D8 | "Refresh summary" side effects | Refresh **never** sends. Digest sending stays with the nightly job and a separate owner action "Send digest now". |
| D9 | Tax-question guard | Stay fail-closed but tighten patterns; refusal lists three example questions that are allowed. |
| D11 | Margin visibility | Purchase-cost signals (Health `margin` factor, `MARGIN_DROP_SKU` and `PURCHASE_PRICE_CREEP` hints, margin alerts) follow the **same access rule as the margin reports** (`canViewMarginReports`: owner or accountant with report access). Others see the factor as "restricted" and the score is computed without it for them. |
| D12 | Consent toggle | `ai_features_enabled` is a read-only chip on `/settings/ai` today (the server ignores it from the owner). Default: **add an owner-editable toggle** with an audit entry; otherwise the consent-off screen cannot honestly say "an owner turns it on". |
| D10 | Hindi | All new strings go through i18n with EN+HI; Hindi needs human review (new QOS item). |

## 1. Target per dimension

| Dimension | Now | Target | Work packages |
|---|---:|---:|---|
| Purpose clarity | 7 | 10 | 18, 22 |
| UX | 5 | 10 | 06, 08, 12, 15, 16, 17, 22 |
| Cognitive load | 5 | 10 | 08, 14, 22 |
| Flow | 5 | 10 | 12, 15, 17, 18 |
| Functionality | 5 | 10 | 05, 12, 15, 16 |
| Business logic | 4 | 10 | 03, 04, 05, 06, 13 |
| Data/state handling | 4 | 10 | 01, 02, 09, 10, 19 |
| Error handling | 4 | 10 | 07, 08, 01 |
| Cross-product integration | 4 | 10 | 11, 20, 23 |
| Consistency | 5 | 10 | 21, 22 |
| Accessibility | 5 | 10 | 14, 17, 24 |

"10" = every INS finding closed, each with a regression test, and the section 5 gate passes. Open items are in section 6.

## 2. Work packages

Order: wave 1 (trust and safety) first; waves can overlap only where files differ.

### Wave 1 — trust and safety (P0/P1)

| ID | Closes | Work | Files | Done when |
|---|---|---|---|---|
| INP-00 | — | Baseline: write failing tests for INS-01/03/05/07 first; record current golden values for health and cashflow | `backend/tests/test_phase6_insights.py`, new `test_insights_review_fixes.py` | Tests fail for the right reasons |
| INP-01 | INS-01 | Confirm: `transaction.atomic` + `select_for_update` on the message, clear `proposed_action` before send; status contract keyed off `Notification.status`: `{status: queued / sent / link_ready / failed, notification_id, share_link?, error?}`. WhatsApp: Cloud `SENT` carries a message id in `share_link` (not a URL) so show "Sent"; `LINK_READY` shows the share link; `FAILED` shows the error (today the API always returns `requires_user_share`, so Cloud sends show nothing and failures can show "Sent"). Failed send restores the proposal. `AuditLog` entries for confirm and dismiss. Web shows Queued / Sent / Open WhatsApp / Failed | `assistant.py`, `AssistantConfirmActionView`, Assistant page | Two parallel confirms send exactly one message; each of the four statuses has a test and a distinct UI |
| INP-02 | INS-04 (D3, D4, D11) | Per-tool permission map in `ToolExecutor.run` (margin rule: `get_health_score` omits the margin factor and `list_growth_hints` omits margin/purchase-price hints without margin access); catch `ValueError`/`TypeError` from bad tool arguments so one bad LLM call does not crash the turn; thread queryset filtered by `created_by`; confirm/dismiss require thread ownership + send permission; migration note for old threads | `assistant.py`, `views.py` | User without reports permission is refused AR/AP/customer tools; user B cannot read or confirm user A's thread |
| INP-03 | INS-02, 07, 08 (D1, D7) | Cashflow engine: roll baseline forward using the Cash Book's own filters (`ReportService._cleared_money_q()`, exclude `mode=CREDIT`, POSTED `CustomerReceipt` and `SupplierPayment`) with `date > opening_cash_as_of` and `<= as_of` (never roll backward if the as-of date is in the future); include bills due **today** (the AP query includes `due_date == as_of` but the day loop starts tomorrow, so they are dropped today), overdue and undated AP (day 1 / separate row); replace the per-invoice `purchase_invoice_outstanding` loop with `LedgerService.bulk_purchase_invoice_outstanding`; **fix the chart**: plot signed values with `y(v) = 50 - v/maxAbs*50` for bar and band (today `Math.abs` mirrors a negative band across the zero line); scenario band per D7; `meta.excluded` list (expenses, payroll, tax, EMIs); return `meta.disclaimer`, rates used, `as_of`, last baseline date | `services.py::forecast_cashflow`, serializers, types | Conservation test with rolled baseline (uncleared cheque excluded); negative case has `low <= high` and is drawn below the line; due-today and overdue AP appear; frontend uses `meta.disclaimer` |
| INP-04 | INS-03 | Alerts ordering: severity (critical > warning > info) then `-created_at` in the list endpoint; Hub shows the same order; Hub alerts block gets its own ErrorState | `views.py`, Hub page | Critical created last week outranks five new infos; alerts API failure never renders "No open business alerts" |
| INP-05 | INS-05, 06, 23 (D5, D6, D11) | Health: new payables factor (with the D6 grace); add `grade_withheld` driven by `limited_data` (score still stored); margin sourced from `InvoiceProfitSnapshot` (`SalesItem` stores no cost), summing revenue and COGS for the month and **excluding `ZERO_COST` and `NO_COGS` rows** so service lines do not read as 100% margin; `unavailable` when no snapshots exist or the user lacks margin access; momentum applies `is_opening_balance=False`; compliance failure returns `null` factor with "unavailable" and re-weights the rest | `services.py::compute_health_score`, `FactorBreakdown`, Health page, Dashboard health chip | Monotonic payables test (0/10/50/100% paid); empty company shows no grade in the UI while the snapshot still saves; `test_health_score_shape` and `test_health_golden_band` updated for `grade_withheld`; compliance error is visible; Dashboard chip checked |
| INP-06 | INS-09 (D8) | Refresh: owner-only button (hidden otherwise); generate-without-send; separate "Send digest now"; WhatsApp path honours the digest setting **and is disabled until a dedicated digest template exists** (today the subject falls through `NotificationService.send` to the `payment_reminder` template, so owners get the digest as a "payment reminder"); `AuditLog` entry for manual generate/send; show success/failure | `views.py`, `services.py`, Hub page | Refresh sends nothing; non-owner never sees the button; 403/500 shown |
| INP-07 | INS-12 (part), INS-03 | Alerts and Hub error states: one state at a time; hints and history errors visible | Alerts, Hub, Health pages | Test per state |

### Wave 2 — assistant quality (P1/P2)

| ID | Closes | Work | Files | Done when |
|---|---|---|---|---|
| INP-08 | INS-10 (D9), INS-20 | Rules fallback: formatted per-tool answers (no JSON, no `**`, no tool names); word-boundary routing; unmatched input returns "I can answer about …" with suggestions; response carries `mode` (`ai` / `basic`) and UI shows it; tighten tax patterns (Hindi branch bounded, `sold to`, `percent`) | `assistant.py`, serializer, Assistant page | "however" does not trigger customer lookup; "hello" does not dump the summary; a Hindi sentence containing "कर" is not refused unless tax-related |
| INP-09 | INS-11 | LLM calls outside `atomic()`; user message persisted first, assistant reply second; per-call token recording; fallback not billed; provider error recorded and shown as "AI unavailable, showing basic answer" | `assistant.py` | Tokens recorded when call 2 fails; no connection held across the network call |
| INP-10 | INS-13 | Customer resolution: exact (case-insensitive) match, else a list of candidates returned as `needs_clarification`; draft only after a single match. Candidates are returned as chips `{customer_id, customer_name, action}`; clicking one sends an unambiguous follow-up. Also pass the last N thread messages into `_run_llm_tools` and the rules path so a typed follow-up ("Sharma Traders") keeps its intent (every turn is stateless today) | `assistant.py`, Assistant page | Two "Sharma" customers produce chips, not a draft; typed and clicked follow-ups both draft for the right customer |
| INP-11 | INS-21 | Assistant UI: show recipient, channel and contact status on the proposal card; disable Confirm with a reason when no contact; optimistic user message and spinner; autoscroll; IME-safe Enter; `aria-live` transcript; auto-title threads; thread list pagination; role labels via i18n; first message auto-creates a thread | Assistant page, `views.py` | Component tests for each |
| INP-12 | INS-26, 27 | **Wire `NAVIGATE`/`SHOW_REPORT` into the Assistant page** (an "Open" button, about ten lines) and drop `CREATE_DRAFT_INVOICE` unless built. If any type is removed, update `test_confirm_requires_message_id_not_client_payload`, which confirms a `NAVIGATE` proposal. Citations link to the record and only for tools actually used | `assistant.py`, Assistant page, `test_phase6_insights.py` | Citation chip opens the record; a NAVIGATE proposal is visible and works |

### Wave 3 — surfaces and polish (P2/P3)

| ID | Closes | Work | Files | Done when |
|---|---|---|---|---|
| INP-13 | INS-16 | "MTD vs prior month": like-for-like day range, same definition both sides, % change | `services.py`, Health page | Test on 15 Oct vs 1-15 Sep |
| INP-14 | INS-22 | Health history: labelled sparkline with first/last values, keyboard-focusable points, text summary; empty state; hints empty state | Health page | axe clean; keyboard reachable |
| INP-15 | INS-12 | Alerts page: severity filter, sort, Snoozed tab with unsnooze, snooze presets (1/7/30d), per-row pending, attributed snooze (who/when), confirmation toast, "Updated <time>" and Refresh (owner). Server: treat `SNOOZED` with `snoozed_until <= now` as `OPEN` on read; stop `upsert_alerts` creating duplicate active `(company, code, subject_key)` rows under concurrency (lock or partial unique constraint, plus a one-off de-dupe in the migration); `AuditLog` entries for snooze/unsnooze/refresh | Alerts page, `views.py` (unsnooze, `snoozed_by`), `services.py::upsert_alerts`, migration | All flows covered by tests |
| INP-16 | INS-17 | Hub: **GET stays read-only** (rule R-044; `generate_daily_summary` also upserts alerts). `GET /daily-summary/` returns the latest stored row with `stale: true` when older than today; when none exists the Hub shows an EmptyState with a primary "Generate summary" button (owner) or "Ask your owner" (others), calling POST with send off; show generated time; `openAlerts` from the live list | `views.py`, Hub | New tenant gets a clear first-run state with one action; GET writes nothing (existing read-only tests stay green) |
| INP-17 | INS-18 (D12) | Gate the Assistant, Attention and **Business Health** buttons by their real permissions (Health endpoints are `CanViewFinancialReports`, Growth hints are `CanViewAiInsights`). Health page: fetch hints only when `canViewAiInsights && consentOn`, and do not block the deterministic score behind `AiConsentOffScreen`. Add the owner-editable consent toggle on `/settings/ai` (D12) and link owners to it; tell non-owners to ask an owner; rename the setting to say Insights and Assistant. A user without access lands on `LimitedAccessLanding` (route guard verified) | Hub, Health page, `AiConsentGate`, `AiSettingsPage`, company serializer | Buttons hidden without permission; owner can switch consent on from the linked page; audit entry written |
| INP-18 | INS-19 | 400 instead of 500 for bad input on `?horizon=` (accepted 7/14/30/90, UI gets 90), `DailySummaryView` `?date=` and body `date`, and snooze `days`; link to opening-cash setting from Cashflow; explain Relative vs Current cash in one line | `views.py`, Cashflow page | `?horizon=abc`, `?date=junk` and `{"days":"x"}` each return 400 |
| INP-19 | INS-24 | Record last successful nightly run per company; show "Data as of" and a warning when behind more than 1 day; retry once on task failure | `tasks.py`, model field + migration, Hub | Simulated failure shows the warning |
| INP-20 | INS-14 | Cross-link Alerts ↔ Attention; the same dedupe code shows "also on Needs attention"; shared severity vocabulary documented | Alerts page, `attention.py` read-only | No behaviour merge |
| INP-21 | INS-25 (D10) | i18n sweep of the five screens + `AlertInboxRow`; hide raw codes and `Mode/model` behind a details toggle; fix column header and Hub title | pages, i18n en/hi | No hardcoded English (lint check) |
| INP-22 | INS-02 UX | Cashflow page restructure: warning first, one-line summary ("Lowest projected cash ₹x on <date>"), detail table collapsed | Cashflow page | Review of screenshots |
| INP-23 | INS-15 | Privacy mask: backend returns structured values for narrative/factor detail; client formats and masks; assistant replies masked when mask is on | `services.py`, pages | Mask hides every amount on the five screens |
| INP-24 | INS-21/22 a11y | Accessibility pass: chart text alternative, focusable scroll regions, touch targets, dark-mode proposal card colour, mobile Assistant layout (chat first) | pages | axe + manual keyboard run |

## 3. Dependencies

- INP-03 and INP-05 both change persisted nightly outputs: take **one** snapshot-version bump and note that health history before the change is not comparable.
- INP-02 precedes INP-11 (the card needs the recipient/permission data).
- INP-15 and INP-19 each add a migration; order by merge, not by ID.
- INP-01, 06 and 15 each add `AuditLog` writes; use one shared helper.
- INP-21 last in its wave so new strings from other packages are included.

## 4. Tests added (per package, regression)

Backend: confirm race, FAILED notification, permission matrix per tool, thread ownership, severity ordering, payables monotonicity, empty-company grade, rolled baseline, negative band, overdue AP, horizon 400, refresh sends nothing, nightly-run stamp.
Web (vitest): Hub and Alerts error vs empty, non-owner Refresh, proposal card contents, IME Enter, unsnooze, filters.
e2e: owner journey Hub → alert → source → back; assistant reminder confirm once.

## 5. Verification gate

1. `ruff` clean on `backend/insights`; `tsc -b` and web lint 0 errors (see memory: web type-check uses `tsc -b`).
2. Backend suites: `test_phase6_insights.py`, new review-fix tests, `test_pj_insights_and_recommendations.py`, attention tests.
3. Postgres run of the confirm-concurrency test (SQLite does not exercise row locks).
4. OpenAPI snapshot and `openapi-types.ts` regenerated (CI drift check) — grep, do not read them.
5. Browser pass at desktop and 375px, EN and HI, dark mode, privacy mask on.
6. Rebuild `docs/PRODUCT_QUALITY_BACKLOG.md` through the qos tools; add QOS items for open sign-offs below.

## 6. Open items

People:
- Founder: D1 meaning of "current cash", D5 threshold, D7 multipliers, D11 who sees margin, D12 consent toggle.
- CA sign-off: cashflow exclusions wording, health compliance factor (new QOS item).
- Hindi review of all new strings (D10).

Still to verify (needs a browser or Postgres, not a code read):
- Audit-log entries appear in the audit screen for the new actions.
- Dark-mode and 44px touch-target points on the proposal card.
- Postgres run of the confirm-concurrency and `upsert_alerts` de-dupe tests.

Resolved by code check on 2026-10-20 and folded into packages: route guard (shows `LimitedAccessLanding`); WhatsApp digest subject (falls back to the `payment_reminder` template, INP-06); audit-log gaps (INP-01/06/15); due-today AP boundary (INP-03).

Not covered: merging Alerts with Attention (DAN-08), a configurable alert-threshold UI, any provider/model change for the Assistant.

Note: the Health endpoints now require `CanViewFinancialReports` (changed since the original review read them as `CanViewAiInsights`); INP-17 reflects the current code.
