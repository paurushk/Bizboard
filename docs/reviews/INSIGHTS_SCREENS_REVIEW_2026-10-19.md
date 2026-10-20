# Insights module — screen, flow and product-impact review

Date: 2026-10-19. Scope: Insights Hub (`/insights`), Business Health (`/insights/health`), Cashflow (`/insights/cashflow`),
Business Alerts (`/insights/alerts`), Assistant (`/insights/assistant`).

**Method and limits.** This is a static review of source: the five pages in
[web/src/pages/insights](../../web/src/pages/insights), the shared pieces in
[web/src/components/insights](../../web/src/components/insights), and the backend in
[backend/insights](../../backend/insights) (`views.py`, `services.py`, `alerts.py`, `assistant.py`, `tasks.py`, `models.py`).
I did **not** run the app, look at the screenshots in `docs/ux/walk/`, run the tests, or use a Postgres database.
Tags used throughout: **[O]** observed in code, **[I]** inferred, **[V]** needs verification, **[U]** unknown.

---

## 1. Screen purpose

| Screen | Purpose [I] | Primary action | Should NOT do |
|---|---|---|---|
| Hub | One-glance "how is the business today" plus jump-off to the other four and to Attention | Read the summary, open a top alert | Replace the Dashboard (`/`) or `/attention` |
| Health | Single 0-100 score, grade, seven weighted factors, trend | Understand *why* the score moved | Be treated as an accounting statement |
| Cashflow | 7/14/30-day projection of cash in/out | Spot a coming shortfall | Be read as a bank balance or filing basis |
| Alerts | Inbox of rule-fired business alerts | Open the source document, or snooze | Be the place where work is assigned or tracked (that is `/attention`) |
| Assistant | Natural-language questions over the same data, plus draft-and-confirm customer reminders | Ask, then confirm or dismiss one proposed reminder | Move money, give tax advice, or reach data the user cannot otherwise see |

Purpose is clear on each screen individually **[O]**. It is not clear across the module: Hub, Alerts, Growth hints,
Health's factor detail and `/attention` all describe overlapping problems (overdue AR, dead stock, thin margin, discount
pattern) in different words, thresholds and severities **[O]**. A user cannot tell which list is "the" list.

## 2. User experience

- **Strong:** every screen has a loading, error (with retry) and mostly an empty state; honest disclaimers; sign encoded by
  shape and hatch on the Cashflow bars, not colour alone (F3-058); money goes through `MoneyText` and the privacy mask.
- **Hierarchy problems.** Hub puts five text buttons above the numbers and puts **two** banners (honesty + disclaimer) above
  content. Health and Cashflow stack two or three banners before the first number. The warning on Cashflow is the most
  important message and sits third in a stack of three.
- **Terminology.** Hub title is "Insights" but the menu item is "Insights Hub". Cashflow shows `Mode: absolute · model v1`
  to the user. The Alerts table shows raw codes (`AR_OVERDUE_CRITICAL`) in a column of their own. "Document" is the column
  header for a link that is really "Open". Assistant shows the raw role strings `user` / `assistant`. Threads are all called
  "Chat".
- **Feedback.** Snooze gives no confirmation, no undo and no per-row pending state (a single disabled "…" button appears
  at the *bottom* of the page). "Refresh summary" shows nothing on success or failure. Assistant send shows no typing
  indicator.
- **Hardcoded English** in a product that ships Hindi: Cashflow ("This is a forecast…", "Ending cash / cumulative…", "Mode:"),
  Health ("Prior month:", "weight"), Assistant ("Chat #", "Copied", "Sent"), `AlertInboxRow` ("Open", "Snooze 7d").

## 3. Cognitive load

Low per screen, high across the module. The user must decide between **three alert surfaces** (Hub "Top alerts", Alerts
inbox, Attention feed) and **three advice surfaces** (Growth hints, Health factors, Assistant). Health asks the user to
interpret seven factors with percentage weights but no "what do I do" next to them. Cashflow shows seven columns where
only three decisions matter (date, net, ending cash). Cashflow "Low/High" has no explanation at all.

Reduce by: one alert surface (the DAN-08 direction already planned in
[DASHBOARD_ATTENTION_PATH_TO_TEN](../plans/DASHBOARD_ATTENTION_PATH_TO_TEN_2026-10-19.md)); a single sentence under each
health factor saying what moves it; a collapsed "details" table on Cashflow.

## 4. User flow

```text
Sidebar "Insights" (needs ENABLE_AI flag + can_view_ai_insights)
  -> /insights (Hub)  --reads--> daily-summary (last stored row), alerts (OPEN), growth-hints
       |-- Health / Cashflow / Alerts      (same permission)
       |-- Assistant                      (needs can_use_ai_assistant; button is shown to everyone on the Hub)
       '-- Attention                      (needs can_view_financial_reports; button shown to everyone)
Company AI consent off -> AiConsentOffScreen (text only; no link, no CTA)
```

- **Happy path** works for an owner with fresh data.
- **Broken or confusing:**
  1. Hub shows Assistant and Attention buttons to users who lack those permissions **[O]**; what they land on is the route
     guard's behaviour **[V]**.
  2. Consent-off screen says "An owner turns it on in Settings" with no link, and the Settings label is
     "Enable bill scan and the lateness screen" - nothing in it says Insights or Assistant **[O]**. A non-owner cannot
     find out what to ask for.
  3. A new tenant, or any day before the scheduled job runs, gets an *empty* summary (`id: null`, `kpis: {}`, narrative `""`).
     The Hub renders five "—" tiles and an empty bordered box with no explanation **[O]**. Only an owner can fix it, and
     the button is not explained.
  4. No way back from an alert to "what did I do about it": after opening the source and fixing it, the alert stays until
     the next scheduled run (see section 6).
  5. Assistant with no thread: the input is disabled until "New chat" is pressed; the first message could simply create one.

## 5. Functional review

**Hub**
- "Refresh summary" is owner-only on the server (`DailySummaryView.post`) but the button is shown to everyone; a 403 is
  swallowed because `refresh.isError` is never read **[O]**.
- That same click calls `generate_daily_summary(send_email=True)`, so a button labelled *refresh* can send the owner an email
  and a WhatsApp digest **[O]**. The email path honours `daily_summary_email_enabled`; the WhatsApp path has no flag check
  and no `email_sent_at` guard, only a subject-based de-dupe **[O]**. Whether the WhatsApp subject
  (`BizBoard daily summary — <date>`) is an approved template or is rejected at `NotificationService.send` needs checking **[V]**.
- Hub alerts query error is ignored: on failure `topAlerts` is empty and the user sees **"No open business alerts."** **[O]**.
  Same for growth hints (silently nothing).
- "Top alerts" are the first five rows of a queryset ordered `-created_at` **[O]** (`BusinessAlertEvent.Meta.ordering`).
  That is "newest five", not "most severe five". A critical alert created last week is hidden behind five new infos.
- `openAlerts` KPI is frozen at generation time; the list below is live, so the two can disagree **[O]**.

**Health**
- Score is recomputed on every GET (two heavy passes, `ReportService.dashboard` is called inside it) **[O]**.
- "MTD vs prior month" compares *month-to-date* with the *whole* prior month, shows no delta, formats the prior month as a
  raw string, and uses different definitions on each side (MTD from the dashboard, net of returns; prior month gross, not
  net of returns) **[O]**.
- History chart only appears with two or more nightly snapshots; bars have no axis, dates or values except a mouse-only
  tooltip **[O]**.
- Growth hints are on both Hub (4) and Health (all); neither has an empty state.

**Cashflow**
- Horizon dropdown offers 7/14/30; server also accepts 90 and silently turns anything else into 14; a non-numeric
  `?horizon=` raises `int()` and returns 500 **[O]**.
- No link to set the opening-cash baseline, though that setting decides whether the page shows real cash or a net
  cumulative figure (see section 7).

**Alerts**
- No severity filter, no sort, no "show snoozed", no unsnooze, only a fixed 7-day snooze (server accepts 1-90). No refresh
  button (the `alerts/refresh/` endpoint exists but nothing calls it). No "as of" stamp.
- On error the page renders `ErrorState` **and** "No open business alerts." together, because `data` is undefined and its
  length is treated as 0 **[O]**.

**Assistant**
- Message list does not auto-scroll to the newest message and is capped at 420px **[O]**.
- Enter-to-send ignores IME composition (breaks Hindi/Hinglish input methods) **[I]**.
- The draft is only cleared on success, which is correct, but the *user's own message is not shown* until the full server
  round trip completes (no optimistic render, no spinner).
- Proposal card only renders when `proposedAction.text` exists; `NAVIGATE`, `SHOW_REPORT` and `CREATE_DRAFT_INVOICE`
  proposals accepted by the backend can never be shown or confirmed in this UI (dead backend surface) **[O]**.
- The card shows the reminder text but **not the recipient, the channel, or whether the customer has any contact details**.
  Missing contact is only discovered when "Confirm & send" fails.

## 6. Data and state

| | Read | Created | Modified | Deleted |
|---|---|---|---|---|
| Hub | `DailyBusinessSummary`, open `BusinessAlertEvent`, hints (computed) | summary, alerts, owner email/WhatsApp (via Refresh) | alert rows (upsert/resolve) | none |
| Health | computed live; `BusinessHealthSnapshot` history | none from the UI | none | none |
| Cashflow | computed live | none from the UI (nightly job persists) | none | none |
| Alerts | `BusinessAlertEvent` OPEN | none | status -> SNOOZED | none |
| Assistant | company threads/messages; AR, AP, customers, sales via tools | threads, messages, `AiUsageLedger`, `Notification` | `proposed_action` cleared | none (no delete anywhere) |

State machines **[O]**:
- Alert: `OPEN -> SNOOZED -> OPEN` (only when the next `upsert_alerts` runs *after* `snoozed_until`), `OPEN/SNOOZED -> RESOLVED`
  (when the rule stops firing at the next upsert), `RESOLVED` re-fires as a **new row**.
- Proposed action: present -> cleared on confirm or dismiss; no "sent / failed" state stored.

Risks:
- **Stale by design.** Alerts, summary KPIs and health history move only when the nightly Celery job or an owner click runs.
  Nothing invalidates them when an invoice is paid. Alerts page and Hub give no "as of" time **[O]**.
- **Snoozed alerts do not reopen on time.** Expiry is evaluated inside `upsert_alerts`; between `snoozed_until` and the next
  run the alert is neither listed (filter is `status=OPEN`) nor snoozed-and-visible **[O]**.
- **Concurrent confirm.** `confirm_proposed_action` reads the message and later clears `proposed_action` with no lock or
  conditional update. Two clicks, two tabs, or two users both pass the check and **both send** **[O]**.
- **"Sent" is not a fact.** Email goes to a Celery queue; the service returns the Notification row without raising on FAILED.
  The API returns `sent: true` regardless, and the UI prints "Sent" **[O]**. NAVIGATE-type results would also print "Sent".
- **Failure loses accounting.** In `_run_assistant_turn_inner`, an exception after the first LLM call is swallowed
  (`except Exception: used_llm = False`) and the rules fallback answers; tokens already spent are never recorded **[O]**.
  The fallback then records `len//4` tokens it never used, burning the monthly budget **[O]**.
- **LLM network calls run inside `transaction.atomic()`** (two sequential calls), holding a DB connection and row locks
  for seconds **[O]**.
- Threads are company-wide (`created_by` is stored but never filtered) **[O]**.

## 7. Business logic (and what needs a decision)

**Health score** (`compute_health_score`):
- *Payables factor is non-monotonic.* If AP > 0 and nothing was paid this month the score is **80**. If AP > 0 and a
  little was paid, the score is `min(2, paid/AP) * 50`; paying 10% of AP gives **5**. Paying nothing beats paying some **[O]**.
- *Defaults flatter an empty business.* With no data the factors default to 100 / 100 / 40 / 70 / 80 / 90 / 80, which
  weights to roughly **76, grade B**. "Limited data" is a small badge; the grade is not withheld **[O]**.
- *Limited-data test* is "fewer than 30 completed invoices ever", not "in the last N days" **[O]**.
- *Margin* uses today's `product.purchase_price` against the sale price, not cost at the time of sale, over an
  **un-ordered** first 500 lines **[O]**. It disagrees with alerts' `MARGIN_DROP` and the hint of the same name.
- *Sales momentum* compares two 7-day windows **without** the `is_opening_balance=False` filter that the prior-month figure
  uses, and without returns **[O]**. Opening-balance invoices dated in the window can swing the score **[V]**.
- *Compliance* silently becomes **50** if the GST-health call throws (logged, not shown) **[O]**.
- *Collections* is "share of AR that is not overdue". An AR book of 1 invoice scores 0 or 100.
- Whether these weights and curves are what the founder and CA mean by "health" is unknown **[U]**; they are undocumented
  in the UI.

**Cashflow** (`forecast_cashflow`):
- *Opening cash is static.* `opening = company.opening_cash_balance` and `ending = opening + cumulative`. Nothing adds the
  cash movements recorded between `opening_cash_as_of` and today. A baseline set in April and never touched still anchors
  a forecast in October **[O]**. "Absolute mode" therefore looks like a real balance and is not **[V: confirm intended]**.
- *Outflows count only purchase invoices due in the window.* Not counted: payables already overdue, payables with no due
  date, expenses, payroll, GST/TDS payments, loan EMIs, owner drawings **[O]**.
- *Inflows are `expected / horizon` every day*, from fixed constants (70/50/30/15/5 %, nudged to 80/55 once ten
  allocations exist) **[O]**. The backend disclaimer was corrected (B9-029) to say "heuristic"; the **frontend still says
  "historical collection rates"** (`insights.cashflowDisclaimer`) and ignores `meta.disclaimer` **[O]**.
- *Low/High band is `ending x 0.85 / x 1.15`.* For a negative ending balance, `low` is *greater* than `high` (band inverted),
  and in relative mode (no opening) day 1 is near zero so the band is meaningless. It is not derived from any uncertainty
  in collections **[O]**.
- *Chart.* Bars and the band use `abs()` against the same mid-line, so a negative band is drawn on the wrong side. The
  bar scale is `max |ending|`, so one large day flattens the rest **[O]**.

**Alerts:** thresholds are code constants (40% concentration, 80% credit limit, 20% discount, 10% purchase creep, 1 000
minimum). Not company-configurable **[O]**. Time zone is the server's (`_company_localtime` is a seam, not a field) **[O]**.

**Assistant:**
- Routing is substring matching (`TOOL_ROUTES`): "owe" matches *however, lower, power*; "aging" matches *managing,
  packaging*; "sales" + "alert" both fire. Any unmatched message (including "hello") returns the daily summary and alerts **[O]**.
- Customer lookup in the LLM path is `name__icontains(...).first()` with no ordering: "Sharma" can return the wrong
  Sharma, and the draft reminder then carries that customer's balance **[O]**.
- Tax-question guard is both too wide and too narrow. The Hindi branch `कर` is outside `\b` and matches any text containing
  that syllable (including the verb "kar-"). `sold to \w+`, `rate for \w+`, `percent`, `inter-state` refuse ordinary
  sales questions ("what percent of my sales went to Mumbai?") **[O]**. This is the intended fail-closed direction, but
  the refusal gives no hint what *can* be asked.
- Budget: default 100 000 tokens per month **[O]**; the "contact your owner" message is shown to non-owners and the owner
  gets only an 80 % email **[O]**.

## 8. Cross-screen impact

| What changes | Where it changes | Why it matters |
|---|---|---|
| Invoice created / paid / returned | Dashboard live; Hub KPIs only after next generate; Health on next GET; Alerts on next job | Three screens give three answers for the same day |
| Opening cash set in Settings | Cashflow mode flips relative <-> absolute | Page title and chart stay the same; scale and meaning change |
| Alert snoozed | Hub "Top alerts", Alerts, assistant `list_business_alerts`, daily email list, Attention (separate state) | Snooze here does not silence the same problem on `/attention`, and vice versa |
| Customer / supplier / product renamed or deleted | Alert text is a stored string; hint and assistant citations link to list pages | Old names persist in alerts until re-upsert |
| AI consent toggled off | Menu hides, route guard, backend 403, nightly job skips | Stored summaries remain; no purge or notice |
| Role/permission changed | Hub buttons still shown; assistant tools keep reading everything | See section 12 |
| `purchase_price` edited | Health margin, MARGIN hint, MARGIN_DROP alert, dead-stock value | Four different margin results can disagree |

## 9. Cross-module impact

| Area | Impact | Notes |
|---|---|---|
| Notifications / email / WhatsApp | **HIGH** | Hub refresh and assistant confirm both create customer- or owner-visible messages |
| Reporting (`ReportService`, aging, dashboard) | **HIGH** | Insights re-implements sales/AR/AP definitions in four places (daily summary, health, assistant `get_sales_totals`, hints); status sets differ (`OPERATIONAL_SALE_STATUSES` vs `OPEN_RECEIVABLE_STATUSES`) |
| Permissions / roles | **HIGH** | Assistant exposes financial and customer data under a different flag than the screens that normally show it |
| Celery schedules | **MEDIUM** | One failed company task never retries; no UI signal that the job is behind |
| Attention feed / Dashboard | **MEDIUM** | Same signals, different state stores (`BusinessAlertEvent` vs `AttentionRowState`) |
| LLM provider / budget | **MEDIUM** | `AiUsageLedger` accuracy (see section 6); company data leaves the system when a key is set (PII keys are stripped, amounts and names are not) |
| Audit log | **MEDIUM** | Snooze, refresh, thread create, reminder send are not audit-logged here **[V]** |
| Search / analytics events | **LOW** | No search; telemetry is separate |
| Privacy mask | **MEDIUM** | Backend strings carry amounts (summary narrative, factor detail, alert messages, assistant text) and render unmasked while the tiles above them are masked **[O]** |

## 10. Edge cases

- **Data:** zero invoices (score ~76 B); one invoice; customer with no phone and no email at confirm; 40+ alerts
  (no pagination or grouping); alert message with a very long customer name; customer named like a tax term; negative
  ending cash (inverted band); all-zero series (`maxAbs` floor of 1, bars at 2 % minimum height so zero looks like a bar).
- **User:** double-click Snooze, Confirm, Send, Refresh; refresh mid-send; open assistant in two tabs and confirm in both;
  Enter during IME composition; back button from an alert's source document (queries refetch, scroll position lost).
- **System:** Celery down (summary never appears); LLM timeout (sync request, no spinner, proxy timeout); LLM key present but
  provider error (silently falls to rules, JSON dump shown); SMTP not configured in staging/prod (Notification FAILED but UI
  says Sent); budget exhausted mid-turn; concurrent `upsert_alerts` from Refresh and the nightly job (atomic but unlocked).
- **Business:** snoozed alert whose rule stops firing then re-fires (new row, snooze lost); financial year change; opening-cash
  date in the future; AP due today is excluded from "due in window" (`as_of` starts tomorrow in the loop, but the AP query
  includes today) **[V]**; opening-balance invoices; returned invoice with residual payable.

## 11. Error and recovery

| Failure | Know it failed? | Know why / how to fix? | Data or duplicate risk |
|---|---|---|---|
| Hub alerts API fails | **No** - shows "No open business alerts." | No | False reassurance |
| Alerts API fails | Yes, but contradictory empty state also shown | Message from server | none |
| Hub refresh 403 / 500 | **No** | No | none |
| Snooze fails | Yes (error block at page bottom) | Server text | none |
| Health history fails | **No** (query error ignored; chart just absent) | No | none |
| Hints fail | **No** | No | none |
| Assistant send fails | Yes (ErrorState under input) | raw server text | user message rolls back; draft kept (good) |
| Assistant confirm fails | Yes, per message | Server text | **Duplicate send possible on double click** |
| Notification FAILED after confirm | **No** - "Sent" | No | Owner believes customer was reminded |
| Budget exceeded | Yes | "Contact your owner" | none |
| Nightly job fails | **No** | No | Stale data presented as current |

## 12. Security and permissions

- **UI hiding is not the control here, and the control is weaker than the screens suggest.** All Insights endpoints require
  `can_view_ai_insights` (or OWNER) and all Assistant endpoints `can_use_ai_assistant`. Those flags are independent of
  `can_view_financial_reports`, customer or inventory permissions **[O]**. A user who is deliberately *not* allowed to see
  AR/AP or customer balances can still ask the assistant "what does X owe" and "AR aging" **[O]**.
- **Assistant sends external messages.** Confirming a reminder emails the customer through the company's mail, or builds a
  WhatsApp share link, under only `can_use_ai_assistant` - not under whatever permission governs sending reminders or
  payments communications elsewhere **[O][V]**.
- **Threads are company-visible.** Any assistant user can list all threads and read all messages, and can confirm or
  dismiss proposals in another user's thread by message id **[O]**. Chats routinely contain customer balances.
- **Snooze** is company-wide, available to every Insights viewer, not attributed, not audited **[O]**.
- `AiUsageView` is owner-only (good). `DailySummaryView.post` and `alerts/refresh/` are owner-only (good) but the UI does
  not reflect that.
- Prompt injection: tool output is wrapped in `<tool_results>` and labelled untrusted, and the reminder text is generated
  by code, not by the model (good). Customer, product and alert strings still flow into the model prompt and back into
  the visible reply **[O]**. Low risk because nothing the model writes is executed.
- Outbound links: citations go through `safeAppPath`, share links through `isAllowedShareUrl` (good).

## 13. Consistency

- Two empty-state / error idioms: Hub and Health use `PageState` early returns; Alerts renders states inline and in parallel.
- Money: tiles use `MoneyText`; text strings use hand-built `₹123.00`. Dates: raw ISO strings in Cashflow rows vs formatted
  elsewhere **[I]**.
- Cashflow and Health stack custom bars; the rest of the product has a chart pattern (Dashboard) **[V]**.
- Severity vocabulary is consistent (`critical/warning/info`) but Attention uses its own.
- Buttons: "Refresh summary" (outlined) vs "New chat" (outlined) vs nav buttons (text) all sit in the same visual tier.

## 14. Accessibility and responsiveness

- Cashflow chart: `aria-hidden` on the decoration and nothing replacing it; the table is the only accessible form, and it is
  well labelled (scrollable region). Add a one-line text summary ("lowest projected ending cash ₹x on <date>").
- Health history: mouse-hover `title` only, no keyboard or screen-reader access, no axis.
- Assistant: transcript is not an `aria-live` region; scroll container is not focusable; role labels are raw lowercase words;
  `bgcolor: 'grey.50'` is a fixed light colour (dark mode **[V]**).
- KPI tiles on Hub use `flex: 1 1 160px; maxWidth: 280` and hint cards a fixed 280px - fine at phone width, leaves
  dead space on desktop.
- Alerts table is horizontally scrollable on phones; seven-column Cashflow table likewise; neither offers a card layout.
- Assistant on a phone puts the thread list *above* the conversation, pushing chat below the fold.
- Touch targets: `size="small"` buttons in dense rows are below the 44px guideline **[I]**.

## 15. Automation opportunities

| Manual now | Automation | Benefit |
|---|---|---|
| Owner clicks Refresh to get a summary on a new tenant | Generate on first view if none exists for today | No blank Hub |
| User types the thing they want to chase | One-click "Draft reminder" from an overdue alert row | Alert becomes action |
| Snooze one alert at a time | Snooze presets (1d / 7d / 30d) plus unsnooze | Fewer repeats |
| Typing a customer name to the assistant | Disambiguation chips when more than one customer matches | Right customer |
| Setting opening cash by hand | Roll the baseline forward from posted cash movements | Cashflow stays true |
| Asking the assistant the same three questions | Suggested prompts under the empty input | Less typing |

Do not add: more hints or more scoring factors before the existing ones are trustworthy.

## 16. Regression risk

| Change | Risk | What could break |
|---|---|---|
| Reordering alerts by severity | LOW | Hub test, e2e; nothing else depends on order **[V]** |
| Changing health factor maths | **HIGH** | `test_health_golden_band`, nightly snapshots (history becomes discontinuous), assistant answers, email digest |
| Changing `forecast_cashflow` | **HIGH** | `test_cashflow_conservation`, nightly persisted runs, assistant tool, Settings baseline copy |
| Scoping assistant tools by permission | MEDIUM | Existing assistant tests and personas (`test_pj_insights_and_recommendations`) |
| Row-locking confirm | LOW | `test_confirm_requires_message_id_not_client_payload` |
| Per-user threads | MEDIUM | Existing company threads become orphaned or need a migration of `created_by` |
| Merging alerts with Attention | **HIGH** | Hub, Alerts, Attention, Dashboard, daily digest, assistant tool, `event_schema` coverage test |

## 17. High-value test scenarios

**Functional:** owner opens Hub with no summary -> sees a clear "not generated yet" state and can generate; owner snoozes
an alert -> it leaves the list, appears in a Snoozed view, returns after expiry; assistant "AR aging" returns readable,
cited text.

**Negative:** non-owner clicks Refresh (message, not silence); `?horizon=abc` returns 400; alerts API 500 shows an error and
**not** the empty state; assistant message with `कर` in an ordinary sentence.

**Data/business:** health payables factor is monotonic (pay 0 / 10 / 50 / 100 % of AP); empty company does not grade B;
negative-ending cashflow has `low <= high`; opening cash set 6 months ago is rolled forward by recorded receipts/payments;
overdue payables appear in the first forecast day; critical alerts sort first.

**Permissions:** user with `can_use_ai_assistant` but without `can_view_financial_reports` asks for customer outstanding
(expected: refused); user B cannot read or confirm user A's thread; viewer without Assistant permission does not see the
Hub button.

**Reliability:** double-click and two-tab Confirm send exactly one message; FAILED notification is surfaced as a failure;
LLM provider timeout shows a bounded wait and a retry; tokens are recorded when the first LLM call succeeds and the second
fails; fallback does not charge the budget.

**Regression:** Dashboard, Hub and Attention agree on AR overdue for the same data; privacy mask hides amounts in narrative
and factor detail; Hindi locale has no English strings on these five screens.

Gaps today: one Hub label test, one e2e (consent-off redirect), 28 backend tests - none cover confirm concurrency, severity
ordering, assistant permission scoping, payables-factor monotonicity, or frontend error states.

## 18. Problems

| ID | Pri | Problem | Impact | Recommendation |
|---|---|---|---|---|
| INS-01 | P0 | Assistant **confirm** has no lock; two clicks/tabs send twice; API returns `sent:true` even if the notification FAILED or is only queued | Customer gets duplicate reminders; owner is told it was sent when it was not | `select_for_update` + clear-then-send in one transaction; return the notification status; show Queued / Failed |
| INS-02 | P0 | Cashflow "Ending cash" is `opening_cash_balance + net`, ignoring actual cash movement since `opening_cash_as_of`; overdue and undated payables, expenses, payroll and tax are absent | A forecast that looks like a bank balance and under-reports outflows | Roll the baseline forward from posted cash/bank; include overdue AP; say what is excluded on the page |
| INS-03 | P0 | Hub "Top alerts" ordered newest-first, not by severity; Hub swallows alert API errors and shows "No open business alerts" | Critical alert hidden or a failed load reads as "all clear" | Order by severity then recency; show ErrorState for the alerts block |
| INS-04 | P1 | Assistant exposes AR/AP/customer balances and can send customer messages under `can_use_ai_assistant` alone; threads are company-wide and any user can confirm/dismiss any message | Permission bypass; private chats readable by colleagues | Gate each tool by the existing permission it mirrors; filter threads to `created_by`; require the reminder-sending permission to confirm |
| INS-05 | P1 | Health payables factor: paying nothing scores 80, paying 10 % scores 5 | Score punishes paying suppliers | Redefine on overdue AP share or days-payable; add a monotonicity test |
| INS-06 | P1 | Empty or tiny business scores ~76 "B"; "limited data" is a small chip | Unearned confidence | Withhold the grade below the data threshold; show "Not enough data yet" |
| INS-07 | P1 | Cashflow Low/High band is `ending x 0.85/1.15`: inverted for negatives, meaningless in relative mode, not tied to uncertainty; chart draws it with `abs()` | Wrong shortfall picture, exactly when it matters | Derive the band from collection-rate scenarios (low/base/high); fix the drawing |
| INS-08 | P1 | Frontend cashflow disclaimer still says "historical collection rates"; backend and code say fixed heuristic | Overclaims accuracy | Render `meta.disclaimer`; show the rates used |
| INS-09 | P1 | Hub "Refresh summary" is owner-only but shown to all, hides its 403, and emails/WhatsApps as a side effect; WhatsApp ignores the digest setting | Silent failure; surprise outbound messages | Hide for non-owners; split "refresh" from "send digest"; add the settings guard; verify the WhatsApp template |
| INS-10 | P1 | Assistant with no LLM key (the default) dumps raw tool JSON with `**` markers, cut mid-string; substring routing ("owe" in "however"); unmatched input returns the summary | Looks broken; wrong tools run | Render a short formatted answer per tool; word-boundary routing; say "I can answer about…" when nothing matches; show which mode is active |
| INS-11 | P1 | Assistant turn runs two LLM calls inside `atomic()`, swallows provider errors, loses token accounting, charges the budget for rules answers | Held connections, wrong usage and budget | Call the LLM outside the transaction; record tokens per call; do not bill fallback |
| INS-12 | P1 | Alerts page: error + empty state shown together; no sort, filter, snoozed view, unsnooze, refresh or "as of"; snooze unattributed and not confirmed | Users cannot trust or manage the inbox | One state at a time; severity sort and filter; Snoozed tab with undo; "Updated <time>" and refresh |
| INS-13 | P1 | Customer lookup `icontains.first()` unordered | Reminder drafted for the wrong customer | Exact match first; if several match, ask which |
| INS-14 | P1 | Three overlapping alert/advice surfaces (Alerts, Attention, hints) with separate snooze state and different thresholds | Duplicate work, contradictory advice | One alert source of truth (DAN-08 direction) |
| INS-15 | P2 | Privacy mask does not cover backend-authored text (narrative, factor detail, alert messages, assistant replies, chart tooltips) | Amounts visible on a shared screen | Return structured numbers and format client-side, or mask known patterns |
| INS-16 | P2 | "MTD vs prior month" compares unequal periods with different definitions; no delta | Misleading trend | Compare like-for-like day ranges, show % change |
| INS-17 | P2 | Empty summary renders blank KPIs with no explanation; KPIs have no "as of"; `openAlerts` can disagree with the list | Confusion, stale numbers | Generate on first view; show generated time; compute count from the live list |
| INS-18 | P2 | Hub buttons for Assistant and Attention shown without permission; consent-off screen has no link and Settings label never mentions Insights | Dead ends | Gate buttons; link owners to the setting; rename the setting |
| INS-19 | P2 | Cashflow `horizon` validation (500 on junk, silent fallback to 14); UI lacks 90 | Avoidable error | Validate to 400; align UI and API |
| INS-20 | P2 | Tax-refusal pattern over-matches (`कर`, `sold to`, `percent`) and gives no alternative | Legitimate questions refused | Tighten patterns; refusal offers example questions |
| INS-21 | P2 | Assistant UI: no optimistic message, spinner, auto-scroll, IME guard, aria-live; threads all titled "Chat", unbounded history, no rename/delete; recipient and channel not shown before send | Hard to use; unsafe to confirm blind | Show recipient, channel and contact status on the card; auto-title; paginate |
| INS-22 | P2 | Health history chart has no axis or keyboard access; hidden until two snapshots; hints have no empty state | Not usable without a mouse | Labelled sparkline with a text summary |
| INS-23 | P2 | Health margin factor uses current purchase price on an unordered 500-line slice; sales momentum lacks the opening-balance filter; compliance error silently becomes 50 | Quietly wrong inputs | Use cost at sale; order and bound; filter; surface "compliance unavailable" |
| INS-24 | P2 | Daily job failure, or lack of one, is invisible to users | Stale data treated as current | Store and show the last successful run |
| INS-25 | P3 | Hardcoded English (Cashflow, Health, Assistant, AlertInboxRow); raw codes and `Mode:/model` text shown to users; "Document" column header; Hub title vs menu name | Hindi users and clarity | Move to i18n; hide codes behind a details toggle |
| INS-26 | P3 | Dead backend proposal types (NAVIGATE, SHOW_REPORT, CREATE_DRAFT_INVOICE) that the UI cannot render | Unreachable code | Remove or build the UI |
| INS-27 | P3 | Citations link to list pages, not the record, and appear whether or not the reply used the tool | Weak provenance | Link the record; cite only used tools |

## 19. The three changes that matter most

1. **Make the numbers trustworthy: fix Cashflow's baseline and band (INS-02, 07, 08) and the Health payables, empty-business and
   margin logic (INS-05, 06, 23).** These screens exist to inform money decisions; today two of the headline numbers can be
   wrong in ways a user cannot see. Highest effect on product correctness and on business value (a wrong shortfall warning
   costs more than a missing feature).
2. **Close the Assistant's trust gaps: lock and truthfully report confirm, enforce permissions per tool, scope threads to their
   owner, show recipient and channel, fix routing and the default no-LLM output (INS-01, 04, 10, 11, 13, 21).** Highest effect on
   security and on customer-facing risk; also turns the weakest screen into a usable one.
3. **Make the risk surfaces honest and actionable: severity-ranked alerts with real error states, a Snoozed view, "as of"
   times and a Refresh, and one alert system instead of three (INS-03, 09, 12, 14, 17).** Highest effect on user outcome: the
   owner can believe "no alerts" means no alerts, and acts from the alert instead of just reading it.

## 20. Scores

| Dimension | Hub | Health | Cashflow | Alerts | Assistant | **Module** |
|---|---:|---:|---:|---:|---:|---:|
| Purpose clarity | 7 | 8 | 7 | 7 | 7 | **7** |
| UX | 5 | 6 | 5 | 4 | 4 | **5** |
| Cognitive load | 5 | 6 | 5 | 6 | 6 | **5** |
| Flow | 5 | 6 | 5 | 4 | 5 | **5** |
| Functionality | 5 | 6 | 4 | 4 | 5 | **5** |
| Business logic | 5 | 4 | 3 | 6 | 5 | **4** |
| Data/state handling | 4 | 5 | 3 | 4 | 3 | **4** |
| Error handling | 3 | 4 | 5 | 4 | 4 | **4** |
| Cross-product integration | 5 | 5 | 4 | 5 | 3 | **4** |
| Consistency | 5 | 6 | 5 | 5 | 5 | **5** |
| Accessibility | 6 | 5 | 5 | 6 | 4 | **5** |
| **Overall** | 5 | 5 | 4 | 5 | 4 | **5 / 10** |

## Verdict

🔴 **NOT READY** to switch on for customers as shipped; the five screens are close to **READY WITH FIXES** except where noted.

- **Hub, Health, Alerts: 🟡 READY WITH FIXES** - INS-03, 05, 06, 09, 12 are small, bounded changes.
- **Cashflow: 🔴 NOT READY** - the headline "ending cash" and the shortfall band can be wrong (INS-02, 07, 08).
- **Assistant: 🔴 NOT READY** - duplicate or false-"Sent" customer messages and the permission and privacy gaps (INS-01, 04).

Mitigation already in place: everything is behind `ENABLE_AI` plus per-company consent, which is off by default ("consent stays
off for the UX audit"), so no customer is exposed today. The fix list is mostly local to `backend/insights` and
`web/src/pages/insights`; the one decision that needs the founder is **what "absolute" cashflow should mean** (INS-02) and
whether Insights and Attention merge (INS-14).

### Open items needing verification [V]
1. What the route guard does for a user without Assistant/Attention permission who clicks the Hub button.
2. Whether `NotificationService.send` accepts the `BizBoard daily summary — <date>` WhatsApp subject, or rejects it.
3. Whether opening-balance invoices fall in the health "sales momentum" window in practice.
4. Whether snooze, refresh and thread actions are written to the audit log elsewhere.
5. Dark-mode rendering of `grey.50` on the proposal card, and the 44px touch-target point, in a browser.
6. Whether the AP-due-today boundary (query includes today, loop starts tomorrow) drops today's payables from the forecast.
