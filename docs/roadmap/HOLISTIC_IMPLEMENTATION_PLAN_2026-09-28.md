# Holistic implementation plan

**Date:** 2026-09-28. Amended the same day after a code review of the trial plan, `_entitled`, and the grant order.
**Source of order:** the competitive audit and the seven-wave roadmap of the same day.
**This document wins** over the September 24 Growth OS plan on sequencing. That plan built the CRM objects first because the models were close. Those objects now exist. This plan turns the right ones on, in customer order, and does not rebuild them.

**Re-grep before you start.** Every “Current” and “Verify” line was checked against this working tree on 2026-09-28. The tree is mid-flight. If `main` has moved, grep the symbol again before editing. Migration numbers below match this tree’s billing head (`0011_pending_razorpay_subscription`). List `backend/billing/migrations/` again immediately before adding a file. Another branch may already have taken `0012`.

An engineer can start at H0.1. H0.4 (the ops grant command) may start as soon as H0.1’s held-set shape is settled. Do not start H4 or H5 until the exit checks for H1 and H2 are green.

## Already shipped — do not rebuild

| Capability | Where it lives | What this plan does with it |
| --- | --- | --- |
| GST Guard on invoice and credit-note complete | `sales/services.py` (~1063), `sales/notes_services.py` (~299, ~530), `reporting/gst_guard.py` | Keep the call. H0 keeps the flag in the trial grant. |
| GSTR worksheet copy | `web/src/i18n/en.ts` and `hi.ts` `gstHonesty.offlineAid`, `filePortalLink`; `GstReturnPage.tsx` | H0 checks every GSTR surface uses that copy. H1 then grants the flag. |
| e-invoice “not the IRP” sentence | `einvoice.payloadOnlyHelp` | H0 removes the hardcoded English “Submit (sandbox)” button label in `EinvoiceEwayPanel.tsx`. |
| 90-day trailing mean | `inventory/forecast.py` `METHOD = "trailing_mean"`; `osPlan.forecastHelp` in en and hi | H3 maps the raw method code to a translated label. |
| Stock method string | `StockValuationPage` in `web/src/pages/phase/InventoryPhasePages.tsx` (~606) | H3 moves that sentence into `t()`. |
| Complaint, ticket, contract, campaign, referral, project milestone, job card | `complaints`, `support`, `contracts`, `crm`, `projects`, `workshop` | H4 and H5 grant them per company. No new models in those waves. |
| Portal, Customer 360 | flags already grantable | H0 leaves both in the trial. H2 verifies the portal. |
| Offline plaintext warning | `OUTBOX_WARNING_DISMISS_KEY` in `web/src/offline/invoiceDraftCache.ts` | H2 checks flush idempotency and that sign-out behavior is still stated. |
| `grant_rollout_flag` | `core/management/commands/grant_rollout_flag.py` | E2E only (`E2E_GOLDEN_GRANT=1`). Not the production grant. H0.4 adds a separate ops command. |

## Decisions locked

1. **There is one live `trial` plan row.** `ensure_register_trial` uses `Plan.objects.get_or_create(slug="trial")` (`billing/services.py`). Every trial `Subscription.plan` points at that row. Flags are read live from `sub.plan.modules` through `plan_modules_for_company`. Updating that row changes every company already on trial, not only the next signup. H0.1 grandfathers companies that already have rows, then updates the row. It does not delete those rows.
2. **A held flag is explicit `False` in `trial_plan_modules()`, not a missing key.** `_entitled` in `accounts/packs.py` returns `True` when the company has no subscription, and `True` again when the plan dict simply lacks the key. Omitting a key does not hold it. `feature_flags.py` also treats a grantable key the plan does not mention as not a denial. Company `feature_flags` then lifts a grantable key both ways, so a `True` written by `apply_pack` beats a later hold.
3. **Company JSON overrides a grantable flag both ways** (`feature_flags.py`, the block after the plan modules). Per-company pilots use that override. They do not edit the trial plan. H0.1 does not scrape existing `True` overrides off companies that already confirmed a pack.
4. **`ENABLE_CRM`, manufacturing, and payroll are dark modules.** A subscribed plan that omits them is not entitled. CRM for one company means that company’s plan names `ENABLE_CRM: true`. Do not put it on the trial plan.
5. **New user-visible strings** go through `t()` with entries in both `web/src/i18n/en.ts` and `web/src/i18n/hi.ts`.
6. **No live IRP** unless `GSP_LIVE_ENABLED` and `GSP_CERTIFIED` are both on (`core/services/gsp_adapters.py`). This plan does not add a certification project.
7. **Complaints may call sales. Sales must not import complaints.** H4 only grants the existing flag. If H5.4 chooses the wire option, `contracts` may import `sales.RecurringInvoiceSchedule`. `sales` must not import `contracts`.
8. **`ENABLE_ARCHETYPE_PACKS` does not police `apply_pack`.** The wizard view returns 404 when that flag is off (`pack_views.py`). `apply_pack` itself never reads the flag. It calls `_entitled`. Holding the wizard flag is not the hold.

## Trial module dict after H0

`trial_plan_modules()` returns every key in `ROLLOUT_GRANTABLE_KEYS`. Granted keys are `True`. Held keys are `False`. Dark modules stay unnamed.

Already held, and they stay `False` in H0: `ENABLE_COMPLAINTS`, `ENABLE_SUPPORT_TICKETS`, `ENABLE_CONTRACTS`, `ENABLE_REFERRALS`, `ENABLE_CROSS_SELL`, `ENABLE_GSTR`, `ENABLE_TALLY`, `ENABLE_GSTN_JSON`.

| Key | After H0 | Why |
| --- | --- | --- |
| `ENABLE_WORKSHOP` | `False`, grandfather if a `JobCard` exists | Menu-only hold deletes nothing |
| `ENABLE_PROJECTS` | `False`, grandfather if a `Project` exists | Same |
| `ENABLE_INSURANCE` | `False`, grandfather if a `Policy`, `PolicyOptionSet`, or `PolicyProduct` exists | Same |
| `ENABLE_ROUTE_OPTIMIZATION` | `False` | Computed suggestion. Delivery routes stay; they are not behind this flag |
| `ENABLE_ROUTE_PROFIT` | `False` | No profit figure until cost ties to the invoice |
| `ENABLE_PURCHASE_PLANNING` | `False` | Computed. No rows to orphan |
| `ENABLE_PREDICTIVE_DUNNING` | `False` | Screen. H2.7 labels it if a company is granted it later |
| `ENABLE_ARCHETYPE_PACKS` | `False` | Hides the wizard. Does not, by itself, stop `apply_pack` |
| `ENABLE_CUSTOMER_ACTIONS` | `False` | `insights/customer_actions.py` tells the user the next order is “expected on” a date. Same honesty bar as dunning |
| `ENABLE_GSTR` | stays `False` until H1.1 | Worksheet copy first |
| `ENABLE_TALLY` | stays `False` | Per-company grant in H1.3, not the trial |
| `ENABLE_GSTN_JSON` | stays `False` | JSON export is not this plan |

Stay `True`: `ENABLE_POS`, `ENABLE_SETUP_WIZARD`, `ENABLE_TDS`, `ENABLE_GST_GUARD`, `ENABLE_CUSTOMER_PORTAL`, `ENABLE_CUSTOMER_360`, `ENABLE_REPLENISHMENT`, `ENABLE_SUPPLIER_PRICE_HISTORY`, `ENABLE_ORDER_GATES`, `ENABLE_ACTION_ASSIGNMENT`.

The last three were unnamed in the first draft. They stay on because they are not a forecast and not a filing:

- `ENABLE_SUPPLIER_PRICE_HISTORY` is past purchase price, quantity, and source (`SuppliersPage`).
- `ENABLE_ORDER_GATES` blocks confirm on credit or margin (`SalesOrderEditorPage`). H0.5 checks the error names which rule fired.
- `ENABLE_ACTION_ASSIGNMENT` assigns an existing attention row to a person.

`test_trial_modules_list_grantable_flags_and_keep_dark_off` hardcodes a smaller `held_back` and asserts `ENABLE_GSTR` is entitled. Rewrite it: every `ROLLOUT_GRANTABLE_KEYS` entry is present; held keys are `False`; the granted keys above are `True`; dark modules are absent. `test_migrated_trial_plan_row_holds_back_growth_os_flags` today asserts those keys are absent. Change that to `plan.modules[key] is False`.

---

## H0 — Honest trial and statutory labels

### H0.1 Set held trial flags to `False`, and grandfather rows

**Blast radius.** The migration updates the single `slug="trial"` row. Every company whose subscription points at it loses a flag in the same request as the deploy, unless a company override or the grandfather step keeps it. The DoD covers both a new signup and an existing trial company.

**Change `trial_plan_modules`.** Return `{key: key not in held for key in ROLLOUT_GRANTABLE_KEYS}` with the held set from the table above, including `ENABLE_CUSTOMER_ACTIONS`. Held keys are present and `False`.

**Change `_entitled`.** Keep the dark-module rejection. Then:

- No subscription (`plan_modules_for_company` returns `None`): consult `trial_plan_modules()`, not `return True`. A pack run before `ensure_register_trial` must not write a held flag onto `Company.feature_flags`, because that `True` would later beat the plan.
- Key present in the plan dict: return `bool(modules[key])`.
- Key absent from a real plan dict: leave today’s `return True`. A paid plan that never mentioned a newer key must not suddenly skip it. Do not “fix” that path in this ticket.

**Grandfather, inside the migration, before the plan update, one transaction.** For each company with a subscription to `slug="trial"`:

- Any `workshop.JobCard` → set `feature_flags["ENABLE_WORKSHOP"] = True` unless that key is already `False`.
- Any `projects.Project` → same for `ENABLE_PROJECTS`.
- Any `insurance.Policy`, `PolicyOptionSet`, or `PolicyProduct` → same for `ENABLE_INSURANCE`.

Do not delete rows. Do not clear a `True` a pack already wrote. Do not grandfather route optimization, route profit, purchase planning, dunning, customer actions, or the pack wizard: those screens are computed or they are the wizard itself. Delivery routes remain available; they are not gated by `ENABLE_ROUTE_OPTIMIZATION`.

**Migration file.** Next free number under `backend/billing/migrations/` after you list the directory. On 2026-09-28 that name is `0012_trial_plan_narrow.py`, depending on `0011_pending_razorpay_subscription`. Same `RunPython` shape as `0009_trial_plan_modules_hold_growth_os.py`, plus the grandfather loop before `Plan.objects.filter(slug="trial").update(...)`. Do not edit 0008 or 0009.

**Tests.** The existing pack tests use `tenant_a`, and `conftest.py` does not give that fixture a `Subscription`. They pass for that reason. `test_trade_pack_does_not_turn_on_crm_when_the_plan_omits_it` monkeypatches `plan_modules_for_company`. Neither is the trial path. Add:

- `ensure_register_trial(company)` then `apply_pack(..., "trade", ...)`. `ENABLE_TALLY`, `ENABLE_GSTR`, and `ENABLE_ROUTE_OPTIMIZATION` are in `skipped_flags` and are not `True` on `company.feature_flags`. `ENABLE_GST_GUARD` may still be applied; the trial grants it.
- `apply_pack` on a company with no subscription does not set those three keys `True`.
- A trial company with a `JobCard` still has `flag_enabled(..., "ENABLE_WORKSHOP")` after the migration. A trial company with no job card does not.
- A trial company with no `Project` loses `ENABLE_PROJECTS`. Its (empty) project table is still there.
- Dark modules stay absent from the trial dict.

**DoD.** New trial: workshop, projects, insurance, route optimization, route profit, purchase planning, dunning, customer actions, archetype packs, GSTR, Tally, complaints, tickets, contracts, and referrals are off. POS, GST Guard, portal, and Customer 360 are on. Existing trial: a company that already saved a job card, project, or policy still sees that module. Everyone else on the trial loses the menu and keeps the rows.

**Effort.** M. The grandfather query is the work. The dict change is small.

### H0.2 Statutory copy on the e-invoice panel

**Current.** `EinvoiceEwayPanel.tsx` hardcodes `Submit (sandbox)`, `e-Invoice submitted (sandbox)`, and `e-Way bill submitted (sandbox)`. `einvoice.payloadOnlyHelp` already says the app prepares JSON and does not submit to the IRP.

**Change.**

- Replace those three strings with `t()` keys in `en.ts` and `hi.ts`.
- The success toast says the result is a sandbox acknowledgement, not an IRN filed on the NIC portal.
- When `GSP_LIVE_ENABLED` is false, the primary button stays the sandbox label. Do not add a button that reads “File” or “Generate IRN”.
- `hasLiveIrn` / “Line edits are blocked while this IRN is live” stays. That sentence is for an IRN that was actually stored. Do not weaken it.

**Tests.** Extend `EinvoiceEwayPanel.test.tsx`: sandbox submit toast does not match `/filed|GSTN|IRP portal/i`. Hindi key exists for each new English key (a missing hi key renders the raw key; assert the key is in both catalogs, the same way other i18n tests in this repo do).

**DoD.** A reader of the panel can tell a sandbox submit from a government IRN without opening the help drawer.

**Effort.** S.

### H0.3 GSTR surfaces use the worksheet sentence before the flag is granted

**Change.** Grep `web/src/pages/reports` for GSTR, GST health, and 2B routes. Each page that can be reached with `ENABLE_GSTR` renders `t('gstHonesty.offlineAid')` or `t('gstHonesty.provisionalNo2b')` above the figures. `GstReturnPage.tsx` already links `gstHonesty.filePortalLink`. Pages that only show `gstHonesty.stubTitle` (“not implemented”) stay on that stub. Do not make a stub look like a worksheet.

**Tests.** Component test per page that was missing the sentence: the offline-aid string is in the document.

**DoD.** H1 can grant `ENABLE_GSTR` without a new copy pass.

**Effort.** S.

### H0.4 Ops grant command

Build this as soon as H0.1’s `False` shape exists. H1.3, H4, and H5.3 / H5.5 all call it. It does not wait for the H4 exit.

**Why.** `grant_rollout_flag` refuses to run unless `E2E_GOLDEN_GRANT=1`. Production grants need a different command.

**Add.** `core/management/commands/grant_company_flag.py`.

- Args: `--email`, `--flag`, `--on` or `--off`.
- Refuses `ENABLE_CRM`, `ENABLE_MANUFACTURING`, `ENABLE_PAYROLL` (dark modules; H5.1 uses the plan row).
- Flag must be in `ROLLOUT_GRANTABLE_KEYS`.
- Writes `Company.feature_flags[flag]` and saves. Does not touch the trial plan. `--on` is how a grandfathered company is joined by a second company later. `--off` clears a company override; the trial plan’s `False` then applies again.
- Prints the company id and the new value.
- Refuses to run when `E2E_GOLDEN_GRANT` is set, so it cannot be confused with the e2e command.

**Tests.** On then off. Unknown flag errors. Dark-module flag errors. Trial plan row is unchanged. After `--on` for `ENABLE_TALLY`, `flag_enabled` is true even though the trial plan says `False`.

**DoD.** An operator can enable Tally or complaints for one email without a migration.

**Effort.** S.

### H0.5 Order-gate copy

**Change.** Where `ENABLE_ORDER_GATES` blocks a sales order, the error names the rule that fired (credit limit or margin). If it already does, cite the test and stop. No hold. This flag stays `True` on the trial.

**DoD.** A blocked confirm does not read as a generic failure or a prediction.

**Effort.** S. Exit of H0 is H0.1 through H0.5. H0.2 and H0.3 may run beside H0.1. H0.4 and H0.5 wait only on the held-set shape.

---

## H1 — CA pack

Start only after H0 DoD.

### H1.1 Grant GSTR worksheets on the trial

**Change.** Set `ENABLE_GSTR` to `True` in `trial_plan_modules()`. Leave `ENABLE_GSTN_JSON` and `ENABLE_TALLY` `False`.

**Migration.** Next free billing migration after H0.1’s file. On 2026-09-28, if H0.1 took `0012`, this is `0013_trial_plan_gstr_worksheet.py`. Re-check the head first. Same `RunPython` pattern. Re-applies `trial_plan_modules()` onto `slug="trial"`. This again updates every company on that shared row: GSTR appears for all of them, which is the point of H1. Companies grandfathered in H0.1 stay grandfathered; this migration does not clear `feature_flags`.

**Tests.** Trial row has `ENABLE_GSTR is True` and `ENABLE_TALLY is False` and `ENABLE_GSTN_JSON is False`. A page test from H0.3 still shows `gstHonesty.offlineAid` when the flag is on.

**DoD.** Trial nav shows GSTR-1, 3B, and 2B. The first line on each page is the worksheet sentence, with the portal link.

**Effort.** S, plus the migration. The screens already exist behind `isGstrReportsEnabled()`.

### H1.2 GST Guard stays on, and the override is the only bypass

**Change.** None in the validator. Add one API test if it is not already there: trial company (guard flag true) cannot complete an invoice with a blocking GSTIN; the same complete with an owner reason stores the override and completes. Staff without override membership receives `gst_guard_blocked`.

**Tests.** `backend/tests/test_gst_guard.py` already forces the flag on. Point the new case at a company whose only grant is `trial_plan_modules()`, so a future held-set edit cannot drop the guard silently.

**DoD.** Completing a tax invoice on a trial company runs `validate_document`.

**Effort.** S.

### H1.3 Tally import for one company, not the trial

**Change.** Leave `ENABLE_TALLY` `False` on the trial plan. Grant it on one company with H0.4 (`grant_company_flag --flag ENABLE_TALLY --on`). The screen is `TallyMigrationPage`, gated by `isTallyEnabled()`.

**Copy.** Page subtitle, en and hi: the file is imported once; BizBoard does not keep a live connection to Tally. Put this next to the existing upload controls.

**Tests.**

- Trial modules still have `ENABLE_TALLY is False`.
- Company override `{"ENABLE_TALLY": true}` makes `flag_enabled` true (`feature_flags.py` grantable override).
- Second commit of the same batch does not double opening stock. Use the existing tally commit tests if they cover idempotency; add the case if they only cover the first commit.
- `integrations/tally_diff.py` `record_migration_diff` result is what the page shows. The page says “difference”, not “synced”.

**DoD.** One company can upload, preview, commit, and read the totals diff. A second trial company cannot see the nav item.

**Effort.** M. Most of the service is `integrations/urls.py` (`tally/upload`, `preview`, `commit`, `export`, `migrate-diff`).

### H1.4 Books proof for one company

**This is a script, not a feature.** Books stay opt-in (`company.accounting_enabled`).

**Script.** On one company with books on: complete one intra-state invoice, one receipt allocated to it, one purchase. Open trial balance, profit and loss, and the customer ledger. Trial balance nets to zero. The customer ledger matches the open invoice. Close the period and repeat the invoice; it is rejected.

**Change.** Only defects found by that script. Do not add reports.

**DoD.** The three numbers are written in the ticket. Any mismatch is a bugfix with a regression test, not a new report.

**Effort.** M, mostly the walk. Code only if the walk fails.

### H1.5 TDS certificate label

**Change.** On `TdsTcsReportsPage`, under the title, `t('tds.notACertificate')` in en and hi: “This is a worksheet of 194Q and 206C amounts. It is not Form 16A or Form 27D.”

**DoD.** The sentence is on the page. No PDF certificate work in this ticket.

**Effort.** S.

**H1 exit.** H1.1 through H1.5. A CA can open 2B and, on the migration company, a Tally diff. Nothing on those pages says filed or synced.

---

## H2 — Counter and collections

Can run beside H1 after H0. Do not start H4 until both H1 and H2 have exited.

### H2.1 Write down counter time

**Script.** Seeded company, POS on, 20-item bill, barcode then name. Record time to add a line, time to complete, time to thermal PDF. Repeat once with the network throttled. Store the numbers in the ticket.

**Change.** None until the number is bad enough that a clerk would abandon the bill. A rewrite without the number is out of scope.

**DoD.** The ticket has six numbers (barcode, name, complete, print, each on normal and throttled).

**Effort.** S.

### H2.2 Offline flush cannot post twice

**Current.** `web/src/offline/flushPosCheckout.ts` and `invoiceDraftCache.ts` already lock per company and user (`bb-outbox-flush`).

**Change.** Add a test that flushing the same idempotency key twice results in one completed invoice and one receipt. If that test already exists (`invoiceDraftCache.test.ts` “SR-51”), cite it in the DoD and do not add a second. The outbox page keeps a sentence that drafts are on this device and sign-out clears them (`freeze` C5). If the dismiss control hides that sentence for the rest of the session, leave a one-line remnant in the outbox header that dismiss does not remove.

**DoD.** Double flush is one document. The wipe sentence is visible without opening help.

**Effort.** S if the test exists. M if flush can double-post.

### H2.3 Portal on the trial

**Change.** No new model. `CustomerPortalRequestPage` / `CustomerPortalPage` already exist. Confirm `ENABLE_CUSTOMER_PORTAL` stays in the trial grant after H0.1.

**Tests.** Trial flags include the portal. The nav item renders for an owner. A magic-link response includes the open invoices and does not include another company’s invoice (existing portal tests; extend only if the list is unscoped).

**DoD.** From a trial owner, the customer can open a statement link. Pay-link behavior stays whatever the sandbox gateway already does. Do not add a new gateway.

**Effort.** S.

### H2.4 WhatsApp label matches the action

**Current.** `InvoiceDetailPage.tsx` uses `common.whatsapp`, `common.whatsappLinkHint`, and `common.whatsappOptInOffHint`. `ENABLE_WHATSAPP_CLOUD` is off in the pilot and is not a trial grant (it is an env flag, not in `ROLLOUT_GRANTABLE_KEYS`).

**Change.** Button label is `t('common.whatsappShare')` when cloud send is off, and `t('common.whatsappSend')` when the company can actually send. The click path must match the label: share opens the share sheet; send calls the cloud task. Do not enable `ENABLE_WHATSAPP_CLOUD` in this ticket.

**Tests.** Flag off: accessible name is the share string, and the handler does not call the cloud endpoint. Flag on: accessible name is the send string.

**DoD.** The button cannot say WhatsApp send while it only copies a link.

**Effort.** S.

### H2.5 Hindi on the billing path

**Scope.** Invoice editor, POS, complete-error toast, GST Guard error, outbox wipe sentence. Not the whole catalog.

**Change.** For each English string on that path, the Hindi catalog has a real sentence. A test can import both catalogs and assert the keys used by `NewInvoicePage`, `PosPage`, and `EinvoiceEwayPanel` exist in `hi.ts`.

**DoD.** Those screens do not render a raw `t` key in Hindi.

**Effort.** M.

### H2.6 First invoice time

**Script.** New user: register, setup wizard, GSTIN, series, one invoice completed. Write the elapsed time in the ticket. Code changes only for a break in that path.

**DoD.** One number, and a note if the wizard blocked the invoice.

**Effort.** S.

### H2.7 Dunning stays labeled

**Change.** On the predictive dunning page, if the flag is on, the subtitle is `t('dunning.screenOnly')`: “This list is a screen. It is not a prediction model.” en and hi. The flag stays in `held` from H0.1.

**DoD.** Turning the flag on for a test company shows that sentence. The trial does not show the nav item.

**Effort.** S.

**H2 exit.** H2.1 through H2.7. Times are written down. Portal opens. WhatsApp label matches the action.

---

## H3 — Name the stock method

After H1.4, so the method on screen is the method in the books.

### H3.1 Stock valuation copy

**Change.** Replace the hardcoded subtitle in `StockValuationPage` with `t('stockValuation.methodWavg')` or `t('stockValuation.methodFifo')` chosen from `data.method`. en and hi. Do not change costing math.

**DoD.** A FIFO company and a WAVG company each show their own sentence. The FAQ line that says FIFO is incomplete stays until a costing test says otherwise. Do not delete that caveat in this ticket.

**Effort.** S.

### H3.2 Forecast method label

**Change.** `DemandForecastPage` prints `row.method`. Map `trailing_mean` to `t('osPlan.trailingMean')`: “Average of the last 90 days.” `forecastHelp` already says this; the cell should not show the raw code.

**DoD.** The cell does not contain `trailing_mean`. No new forecast math.

**Effort.** S.

### H3.3 Routes, when granted, say what the heuristic is

**Change.** Where a pilot turns `ENABLE_ROUTE_OPTIMIZATION` on, the routes page states `t('routes.heuristic')`: “Suggested order uses pincode grouping or nearest neighbor. It does not consider vehicle capacity or time windows.” en and hi. `sales/route_optimization.py` is unchanged. `ENABLE_ROUTE_PROFIT` stays held. Do not show a profit figure.

**DoD.** The sentence is on the page whenever the optimization control is visible.

**Effort.** S.

**H3 exit.** Valuation names the method. Demand does not say it is a model. Route profit is still off.

---

## H4 — Books-linked modules, one company each

Start only after H1 and H2 exits. No new tables. Grants use H0.4. A company H0.1 grandfathered already has the flag; H4 does not turn the module on for the whole trial.

### H4.2 Complaints for one distributor

**Grant.** `grant_company_flag --flag ENABLE_COMPLAINTS --on` for that company. `ENABLE_CUSTOMER_360` stays on from the trial grant.

**Verify, do not rebuild.** Customer complaint can draft a sales return, a credit note, and a replacement order through the existing sales services. Supplier complaint can draft a purchase debit note. Status machine stays `OPEN → INSPECTING → APPROVED|REJECTED → RESOLVED`.

**Tests.** One API test on a company with the flag on and one with it off. Off: `POST /complaints/` is 404 or 403, matching the existing module gate. On: approve-and-create credit note produces one `SalesCreditNote` draft tied to the source invoice, and a second click does not create a second note.

**DoD.** That company’s nav shows complaints. A trial company does not.

**Effort.** M, almost all test and copy. Models are in `complaints/models.py`.

### H4.3 Customer 360 shows those complaints

**Current.** `Customer360Page.tsx` shows tickets and contracts only when both Customer 360 and the other flag are on. Sales, aging, and profit are already on the payload (`web/src/api/osPlan.ts`).

**Change.** Same pattern for complaints: the section renders only when `ENABLE_CUSTOMER_360` and `ENABLE_COMPLAINTS` are on. The API adds the company’s complaints for that customer (id, number, status, category). No cross-company join.

**Tests.** Flag off: response has no complaints key, or an empty list and the section is hidden. Flag on: only that customer’s rows.

**DoD.** The distributor’s customer page lists the complaint next to outstanding.

**Effort.** S.

### H4.4 Project milestones for one services firm

**Grant.** `ENABLE_PROJECTS` on that company only.

**Verify.** `projects/services.py` `invoice_milestone` already creates a `SalesInvoice` draft. Test: invoicing a milestone twice returns the same draft; completing the invoice moves the milestone to `INVOICED`; cancelling the invoice does not leave the milestone invoiced (`sync_project_milestone`).

**Copy.** Page subtitle: a milestone drafts a tax invoice. It does not track tasks or time.

**DoD.** One services company can bill a milestone. The trial nav does not show Projects.

**Effort.** S if the double-invoice test passes. M if it creates a second draft.

### H4.5 Job card for one repair shop

**Grant.** `ENABLE_WORKSHOP` on that company only.

**Verify.** A job card with a part line and a labour line produces one sales invoice, not two. Status moves to `INVOICED` only after that invoice exists.

**Copy.** Subtitle: parts and labour on one bill. This is not a serial service history.

**DoD.** One repair company can invoice a job. Everyone else cannot open `/workshop/jobs`.

**Effort.** S or M, same rule as H4.4.

**H4 exit.** Three named companies, three grants. The trial plan row is unchanged from H1.

---

## H5 — CRM only when a company asks

Do not add `ENABLE_CRM` to `trial_plan_modules`. A subscribed plan that omits a dark module is not entitled (`feature_flags.py`).

### H5.1 One-company CRM plan

**Change.** For the asking company, set that subscription’s plan modules to include `ENABLE_CRM: true`, or point the subscription at a plan that does. Do not update `slug="trial"`. `ENABLE_CRM` true on `Company.feature_flags` alone must remain insufficient when the plan omits it (existing test `test_trade_pack_does_not_turn_on_crm_when_the_plan_omits_it`). Keep that test.

**DoD.** That user sees Leads, pipeline, and campaigns. A trial user does not. Referrals stay hidden until H5.5 (`isReferralsEnabled` requires CRM and `ENABLE_REFERRALS`).

**Effort.** S.

### H5.2 Pipeline and campaigns, no sender

**Verify.** `crm/forecast.py` `pipeline_forecast` sums amount times probability for open stages. `crm/campaigns.py` ROI uses converted quotation `grand_total`, else opportunity amount.

**Copy.** Campaign page: “This records a budget and a result. It does not send email, SMS, or WhatsApp.” Pipeline page: “Forecast is amount times probability. It is not invoiced cash.”

**Tests.** Existing forecast and funnel tests stay green. Add a UI or serializer test only if those sentences are missing.

**DoD.** Both sentences are on the pages. No campaign-send endpoint is added.

**Effort.** S.

### H5.3 Tickets as an internal queue

**Grant.** `ENABLE_SUPPORT_TICKETS` via H0.4, only for this company.

**Verify.** SLA offsets stay the ones already implemented. Comments default internal. There is no inbound email endpoint in this ticket.

**Copy.** “Internal queue. Customers cannot reply from this screen.”

**DoD.** The company can assign a ticket. The trial cannot. No mailbox code.

**Effort.** S.

### H5.4 Contract value either bills or says it does not

**Choice, pick one in the ticket before coding.**

- **Label.** Contract form shows `t('contracts.valueDoesNotBill')`: “Value is for the renewal list. It does not create an invoice.” No migration. This is the default.
- **Wire.** Optional nullable FK `Contract.recurring_schedule` to `sales.RecurringInvoiceSchedule` (`sales/models.py`). `contracts` may import `sales` for that FK and for the existing recurring service. `sales` must not import `contracts`. There is no import-direction test in the tree today; add one that fails if any file under `backend/sales/` imports `contracts`. Saving a contract does not create a schedule. A button “Use this value on a recurring invoice” creates one schedule through the existing recurring service, idempotent on the contract id. Renewal status logic in `contracts/status.py` stays.

Prefer the label unless the pilot company already sells AMC and asked for the bill. Do not do both halfway.

**DoD.** A reader can tell whether the contract will raise an invoice.

**Effort.** S for the label. M for the FK and the button.

### H5.5 Referrals last

**Grant.** `ENABLE_REFERRALS` via H0.4, and only after H5.1.

**Copy.** Next to the paid action: “Paid records the decision. It does not transfer money.” `ReferralReward` already says marking PAID does not send money (`crm/models.py`).

**DoD.** The paid control uses that sentence. Self-referral reject stays (`test_referral_self_referral_guard.py`).

**Effort.** S.

### H5.6 Insurance pack only

**Change.** No code if H0.1 held `ENABLE_INSURANCE` on the trial. Document in the ops note: grant `ENABLE_INSURANCE` per company, and CRM only through the insurance pack path that already forces `ENABLE_CRM` when `pack_grant == "insurance"`. Page subtitle: “Options on a lead. This does not issue a policy.”

**DoD.** The trial plan has `ENABLE_INSURANCE is False`, except a company H0.1 grandfathered because it already had a policy row. The subtitle is on the page when the flag is on.

**Effort.** S.

### H5.7 CRM checklist booker step

**Current.** `crm/onboarding.py` sets `"booker": True` unconditionally.

**Change.** `booker` is true when the company has at least one active `CompanyUser` whose role can be assigned leads (the same roles `pick_least_loaded` already uses). False on a company with only the owner if the owner is not in that set. If the owner should count, say so in the ticket and test that case; do not leave `True` with no query.

**Tests.** Zero eligible users → step not done. One eligible user → done.

**DoD.** The step matches the company.

**Effort.** S.

**H5 exit.** One CRM company. Trial still has no CRM, no tickets, no referrals. Campaigns do not send. Paid does not pay.

---

## H6 — Hold

No tickets. A regression test in `test_onboarding.py` locks the absence:

- After H1.1, every H0 held key except `ENABLE_GSTR` is present on the trial plan and `False`. `ENABLE_GSTR` is `True`.
- Trial modules omit `ENABLE_CRM`, `ENABLE_MANUFACTURING`, and `ENABLE_PAYROLL` (still unnamed, not `False`).
- `GSP_LIVE_ENABLED` default remains false. Do not add a live NIC client.
- `ensure_register_trial` then `apply_pack` still does not write a held flag. That test from H0.1 stays in the suite.

Out of this plan: seasonal forecast, vehicle-capacity routing, live Tally sync, campaign sending, a customer helpdesk inbox, insurance issuance, the assistant, manufacturing, payroll, Form 16A, GSTN JSON upload.

## Order

```text
H0.1 → H0.2 → H0.3
H0.1 → H0.4 → H1.3
H0.1 → H0.5
H0.3 → H1.1 → H1.2 → H1.4 → H1.5
H0 → H2.1 → H2.2 → H2.3 → H2.4 → H2.5 → H2.6 → H2.7
H1.4 → H3.1 → H3.2 → H3.3
H1 exit and H2 exit → H4.2 → H4.3
                      H0.4 → H4.4
                      H0.4 → H4.5
H4 exit → H5.1 → H5.2 → H5.3 → H5.4 → H5.5
          H5.6 and H5.7 any time after H5.1
```

H0.2 and H0.3 may proceed beside H0.1. H1 and H2 may proceed in parallel after H0. H1.3 waits on H0.4, not on H4. H4.4 and H4.5 may proceed in parallel. H5 does not start for the default trial.

## What the operator tells a pilot

| After | Sentence that is true |
| --- | --- |
| H0 | “You can bill, track stock, and open a customer link. Returns and e-invoice on screen are worksheets or sandbox, not a government filing. If you already saved a job card, a project, or a policy, that screen stays. If you had not, that menu is gone and nothing was deleted.” |
| H1 | “Your CA can read the GST worksheets and still files on the portal. Tally import is a one-time file for companies we turn it on for.” |
| H2 | “WhatsApp on the invoice is a share, unless we have turned sending on for you.” |
| H3 | “Stock value says FIFO or average, and that is the method the books used.” |
| H4 | “This company can turn a complaint into a credit note.” Said only to that company. |
| H5 | “This company has a pipeline. Campaigns do not send messages. Referral paid does not move money.” Said only to that company. |
