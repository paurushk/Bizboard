# LLM implementation plan — path to 10, code only

**Date:** 2026-09-29. Amended the same day after a line check against the tree.
**Why these twelve.** Each one is a gap that can be closed and proved inside this repo. A score of 8 is parity: the usual case and the usual exceptions finish, errors are recoverable, and the numbers tie. A score of 10 also needs an advantage recorded on a session or a file. This plan does not claim either score. It only builds the proof a later session can cite. Live IRN, GSTN filing, WhatsApp Cloud, a bank feed, and a counter timed against Vyapar or Tally are outside that proof, so they are not tickets here.
**Register.** Each ticket is a QOS item in `qos/backlog/`. Do not hand-edit `docs/PRODUCT_QUALITY_BACKLOG.md` or `docs/reviews/MASTER_ISSUE_REGISTER.md`. Those files are generated. The yaml is the seam.

## What this plan does not do

| Item | Why it is not a ticket |
| --- | --- |
| Live IRN / e-way | Needs `GSP_LIVE_ENABLED` and `GSP_CERTIFIED`, and a real IRN. Do not turn the submit flag on. |
| GSTN filing of GSTR-1, 3B, or 2B | A worksheet cannot pass 6 against Zoho or ClearTax. The portal link and the worksheet sentence already exist. |
| WhatsApp Cloud delivery | Needs a provider that accepts a message. The share-versus-send label is already done. Leave `ENABLE_WHATSAPP_CLOUD` off. |
| Bank feed / Account Aggregator | Needs a consent provider. |
| Counter timing versus Vyapar or Tally | Needs a person at a counter. The existing test only fails if a step hangs past 20 seconds. |
| Form 16A or Form 27D | A PDF that looks like the statutory certificate would contradict `reports.tdsSubtitle`. |
| Pharma scheme classes | Marg’s commercial schemes are not specified here. Expired-stock blocking already has tests (`test_pj_batch_expiry.py`, `test_phase4_inventory.py`). |
| Seasonal forecast, full VRP, campaign sending, the assistant | Held. |
| Manufacturing, payroll, insurance issuance | Outside the trader score. |
| Support email inbox | Needs a mailbox. |
| New GST Guard NIC codes | `reporting/gst_guard.py` checks GSTIN, HSN master, and rate consistency. Do not add NIC codes from memory. |

## Already in the tree — cite, do not rebuild

| Capability | Where | Ticket rule |
| --- | --- | --- |
| Durable idempotency | `core/idempotency.py` `wrap_idempotent`, `IdempotencyRecord`, `MONEY_IDEMPOTENCY_SCOPES` | Decision 6. Do not write a second get-or-create. |
| Lead-time reorder quantity | `inventory/services.py`, `test_configured_uses_velocity_lead_time_and_safety` | Do not flip `ENABLE_PURCHASE_PLANNING` on the trial. |
| GRN converts to one bill | `purchases/grn_service.py`, `test_wf_grn_receive_complete_convert` | L3. On-hand is asserted after GRN complete (`8.000`) and is not asserted again after the bill completes. |
| Expired batch block | `company.block_expired_stock` | No new policy. |
| Lead convert reuses the party | `crm/services.py` `convert_lead` | L6 creates the invoice through the existing sales create. |
| Complaint credit note, second click | `test_complaint_credit_note_replacement_isolation_and_flag` | L8 is the portal case only. |
| Books equation | `test_plan_closeout.py` | L2 shows those numbers. It does not add a report. |
| Portal throttles | `CustomerPortalRequestAnonThrottle` scope `customer_portal_request` at `5/min` in `config/settings.py` | L8 adds its own scope. It does not reuse the read bucket. |
| Mark paid role check | `ReferralRewardViewSet.mark_paid` already requires OWNER or MANAGER | L9 keeps that check. |
| Route suggest permission | `DeliveryRouteViewSet.suggest_sequence` uses `CanCreateSales` | L11 keeps that permission. |
| Period close permission | `accounting/views.py` close action uses `IsOwner` | L2 calls that action. It does not add a close endpoint. |
| Contract label | `growth.valueDoesNotBill` on `ContractsPage.tsx` | L12 removes it in the same change as the button. |

## Decisions

1. Trial flags stay as `trial_plan_modules()` left them. These tickets do not grant Tally, complaints, referrals, contracts, route optimization, or purchase planning to every trial company.
2. Every new user-visible string goes through `t()` in both `web/src/i18n/en.ts` and `web/src/i18n/hi.ts`. A ticket whose DoD names a screen is not done until both catalogs have the new keys. This applies to L2, L4, L7, L8, L9, L10, L11, and L12, not only the tickets that repeat the sentence.
3. `sales` must not import `contracts` or `complaints`. `contracts` may import `sales` for L12.
4. A failing new test is fixed in the existing service. Do not add a parallel code path.
5. Re-grep the symbol and list the app’s `migrations/` directory before adding a file. This tree is mid-flight. On 2026-09-29 the heads seen were `crm/0014_leadactivity_due_at` and `contracts/0003_contract_products`. Another branch may already have taken the next number.
6. **Idempotency.** New creates and money actions call `wrap_idempotent` in `core/idempotency.py`. The scope string in the view must be exactly the string registered. `B6-014` was two scope names that matched nothing and silently protected money creates. A money-creating or money-posting scope is added to `MONEY_IDEMPOTENCY_SCOPES` in the same change as the view. A non-money create still uses `wrap_idempotent` and is not added to that set. L6 uses the existing scope `sales_invoice_create`. L9 adds `referral_reward_credit_note`. L12 adds `contract_recurring_schedule`. L8 uses `portal_complaint_create` and does not add it to the money set.
7. **The durable link is a nullable foreign key, not the idempotency row.** `IdempotencyRecord` replays a request. It is not the lookup for “which note does this reward already have?” L9 adds `ReferralReward.credit_note` (nullable, `SET_NULL`) in the next `crm` migration. L12 adds `Contract.recurring_schedule` (nullable, `SET_NULL`) in the next `contracts` migration. No other ticket adds a column or a table. L10 stays a query.
8. **Tenant isolation.** Querysets go through `CompanyScopedViewSet` or an explicit `company_id` filter. A cross-tenant test uses the second tenant and expects 404. `crm_referralreward` and `contracts_contract` are already enrolled (`core/migrations/0035_rls_growth_os.py` and `0020_rls_all_tenant_tables.py`). A new column on those tables does not need a new RLS migration. A new table does: copy `core/migrations/0041_rls_policy_renewal_lead.py` into the next `core` migration after listing `backend/core/migrations/`.
9. **Concurrency.** L6, L9, and L12 each have two tests. The sequential test posts the same `Idempotency-Key` twice and is the SQLite DoD. The race test follows `backend/tests/test_concurrency_races.py`: two threads, one key, skip unless the database is PostgreSQL. One row must exist after both threads finish.
10. **Roles** are the classes already in `core/permissions.py`. Each ticket names them. Do not invent a new permission class.

## Order

```text
L1 Tally second commit          QOS-0083
L2 Books close screen           QOS-0084
L3 GRN on-hand after the bill   QOS-0085
L4 Collections open balance     QOS-0086
L5 Credit note after a receipt  QOS-0087
L6 Won lead to one draft invoice QOS-0088
L7 Job serial history           QOS-0089
L8 Portal complaint             QOS-0090
L9 Referral credit note         QOS-0091
L10 Won amount next to invoices QOS-0092
L11 Route capacity warning      QOS-0093
L12 Contract schedule           QOS-0094
```

L1 through L5 are trader jobs. L6 through L12 run only for a company that already has the module flag. L5 lands before L9 because L9 completes a credit note through the same notes path.

---

### L1. Second Tally commit does not add stock — QOS-0083

**Current.** `commit_tally_preview` raises `BusinessRuleError("Already committed.")` when the run status is `COMMITTED` (`integrations/tally/adapter.py`). No test commits the same run twice and checks opening quantity.

**Permission.** The existing upload, preview, and commit views. `CanImport` on upload, preview, and commit. No new endpoint.

**Change.** No production change unless the test fails. Grant `ENABLE_TALLY` for one company. Upload a CSV with `opening_qty`, preview, commit, record on-hand, commit again. The second response is an error and on-hand is unchanged. The other trial company still receives 404.

**DoD.** One product, one opening quantity, one failed second commit.

### L2. Books close on one screen — QOS-0084

**Current.** The API walk in `test_plan_closeout.py` ties and a closed period rejects the next invoice. Closing a period is already `IsOwner` (`accounting/views.py`). Reading the reports is already `CanViewFinancialReports`.

**Permission.** The screen reads with `CanViewFinancialReports`. The close control calls the existing close action and does not grow a new one. A user who is not owner can read the numbers and cannot close.

**Change.** One section shows trial-balance debit, trial-balance credit, whether they match, profit-and-loss income, and one customer’s outstanding from `LedgerService.customer_outstanding`. The row-level invoice balance is not this screen. Copy is `t()` in English and Hindi.

**Tests.** The section renders debit, credit, and the match flag. The backend walk in `test_plan_closeout.py` stays the equation proof.

**DoD.** A reader with report access sees the equation and the lock result. Both catalogs contain the new keys.

### L3. On-hand after the bill, not only after the GRN — QOS-0085

**Current.** `test_wf_grn_receive_complete_convert` asserts `available_quantity == Decimal("8.000")` immediately after GRN complete. It then converts and completes the bill and does not read on-hand again. That second read is the double-post check. An assertion that only exists before the bill is not this ticket.

**Permission.** None new. The test uses the owner client already in that file.

**Change.** In that test, after the converted bill is completed, assert `available_quantity` is still `Decimal("8.000")`. If it is not, fix the purchase complete path that posts a GRN-sourced bill. Do not add a GRN service.

**DoD.** On-hand after GRN complete equals on-hand after bill complete.

### L4. Collections row uses the invoice outstanding — QOS-0086

**Current.** `LedgerService.customer_outstanding` is the party total. `LedgerService.sales_invoice_outstanding` is the open amount of one invoice. The collections page already says the list is not a prediction model.

**Permission.** Whoever can already open the collections page. No new role.

**Change.** Each open-invoice row shows days overdue, amount received, and balance. The balance is `sales_invoice_outstanding` only. If a customer total is also shown, that total is `customer_outstanding` and the label says it is the customer total. Do not feed the row from the customer total. Do not add a risk score and do not turn on `ENABLE_PREDICTIVE_DUNNING`. New strings are in both catalogs.

**Tests.** One partial receipt. The row balance equals `sales_invoice_outstanding`. A second company’s invoice is absent.

**DoD.** The number on the invoice row is `sales_invoice_outstanding`.

### L5. Credit note after a receipt — QOS-0087

**Current.** Receipt allocation and credit notes both exist. This case is not the books walk.

**Permission.** `CanCreateSales` to complete the note, `CanCreatePayments` for the receipt. Both already exist. The owner client satisfies them.

**Change.** Write the test first: intra-state invoice, partial receipt allocated, credit note for the remainder, complete the note. Assert one receipt, one allocation, one credit note, and `sales_invoice_outstanding` equals the remaining balance. Fix `sales/notes_services.py` only if that fails.

**DoD.** The three documents exist once, and the invoice outstanding matches.

### L6. Won lead, one customer, one draft invoice — QOS-0088

**Current.** `convert_lead` is idempotent and reuses a customer matched by phone or email. It does not create a sales invoice. Invoice create already uses `wrap_idempotent` with scope `sales_invoice_create`, which is already in `MONEY_IDEMPOTENCY_SCOPES`.

**Permission.** `CanCreateSales` and `SubscriptionWritesAllowed`, the same classes as `SalesInvoiceViewSet.create`. `ENABLE_CRM` must already be on for that company. Do not grant it on the trial.

**Change.** From the won opportunity, create one draft sales invoice for that customer through the existing sales create, with an `Idempotency-Key`. Do not add a scope string. Do not create another customer.

**Tests.** Sequential: convert once, invoice once, convert again, same invoice key again. Customer count is 1 and invoice count is 1. A lost lead still refuses convert. Race: two threads, same key, PostgreSQL only, one invoice. A second company cannot read the invoice.

**DoD.** The invoice customer id is the converted customer id. No new scope and no new column.

### L7. Job card history for one serial — QOS-0089

**Current.** `JobCardLine.serial` exists. Retrieve does not list earlier jobs for that serial.

**Permission.** The existing job retrieve permission. Do not widen it. `ENABLE_WORKSHOP` off remains 404.

**Change.** On retrieve, include at most 20 earlier job cards in the same company that use that serial, newest `id` first. Fields: id, number, status, date. Empty when the line has no serial. The payload says when the list stopped at 20. New strings are in both catalogs.

**Tests.** Two jobs, one serial. The second lists the first. A 21st older job is outside the 20. Another company’s job is absent.

**DoD.** The second job shows the first, and the list is capped at 20.

### L8. Customer files a complaint on the portal — QOS-0090

**Current.** Staff create is idempotent for the credit-note action. The portal has no complaint write. Description on the model is an unbounded `TextField`. Portal reads are throttled separately from portal link requests.

**Permission.** No company role. The caller is the magic-link customer. The view checks `ENABLE_COMPLAINTS` on that token’s company and 404s when it is off. The complaint customer is the token’s customer.

**Change.** `wrap_idempotent` with scope `portal_complaint_create`. Do not add that scope to `MONEY_IDEMPOTENCY_SCOPES`. Description is required and at most 2000 characters. Category is one of the existing complaint categories. A new throttle scope `customer_portal_complaint` is `10/hour` in `DEFAULT_THROTTLE_RATES`, on the same anon-throttle pattern as `customer_portal_request`. New strings are in both catalogs.

**Tests.** Flag off is 404. Flag on creates one row. The same `Idempotency-Key` returns that row. A 2001-character description is 400. A second token cannot read the complaint. The throttle scope is the new one, not `customer_portal_read`.

**DoD.** The trial portal has no complaint form. A granted company’s customer can submit one, and a long description is refused.

### L9. Referral paid drafts one credit note — QOS-0091

**Current.** `mark_reward_paid` sets `PAID` and does not create a document (`crm/referrals.py`). `mark_paid` already returns 403 unless the membership is OWNER or MANAGER. There is no link from the reward to a credit note.

**Permission.** Keep OWNER or MANAGER. `CanCreateSales` is already on the viewset. `ENABLE_REFERRALS` off stays 404.

**Change.** Add nullable `ReferralReward.credit_note` in the next crm migration after listing that folder. `mark_paid` calls `wrap_idempotent` with scope `referral_reward_credit_note`, and that exact string is added to `MONEY_IDEMPOTENCY_SCOPES`. The first call creates one draft credit note through the existing notes service and stores it on the reward. A later call returns `reward.credit_note` and does not create another. Completing the note uses the existing complete path (`sales_credit_note_complete` is already registered). Replace `growth.markPaidHint` in both catalogs with a sentence that paid drafts a credit note, and completing the note adjusts the customer balance. It does not send cash. Update the model comment that says marking paid does not send money so it matches that sentence.

**Tests.** Sequential second click returns the same note id and the reward’s foreign key is that note. Race: two threads, one note, PostgreSQL only. Self-referral still rejects. A sales-staff membership still receives 403. Flag off is 404.

**DoD.** The customer balance changes only after the note is completed. The reward points at one note.

### L10. Won amount next to invoices — QOS-0092

**Current.** `crm/forecast.py` multiplies open amount by probability. Nothing stores a forecast snapshot, so an accuracy percentage would be invented.

**Permission.** `CanCreateSales` is not enough for a money comparison. Use `CanViewFinancialReports`, and require `ENABLE_CRM` already on. No new permission class.

**Change.** For a chosen month, show two sums: opportunities moved to won in that month, and completed sales invoices for those opportunities’ customers in that month. Label both as those sums. Do not say “predicted”. No new table and no new column. Both catalogs get the labels.

**Tests.** One won opportunity and one completed invoice for that customer in the month are in the sums. An open opportunity is not. Another company is not.

**DoD.** The page shows the two sums and does not call them a model.

### L11. Route capacity warning — QOS-0093

**Current.** `suggest_sequence` is `CanCreateSales` and `ENABLE_ROUTE_OPTIMIZATION`. `NearestNeighborTwoOptStrategy` returns one ordered list and has no cap (`sales/route_optimization.py`).

**Permission.** Keep `CanCreateSales` on `suggest_sequence`. Flag off stays 404.

**Change.** Optional positive integer `stop_cap`. Run the existing sequencer unchanged. Keep the first `stop_cap` stops in that returned order. Every later stop is `unassigned`, in that same relative order, with reason `over_stop_cap`. A cap greater than or equal to the stop count assigns every stop. An omitted cap keeps today’s response. No new optimizer and no time windows. The heuristic sentence stays. New strings are in both catalogs.

**Tests.** Five stops, cap 2: the first two of the uncapped sequence are sequenced, and the last three are unassigned in that same order. Cap omitted matches today’s order. Flag off is 404.

**DoD.** Given one uncapped order, the cap keeps a prefix of it. The sequencing function is still the current one.

### L12. Contract value creates one recurring schedule — QOS-0094

**Current.** The contract page says value does not create an invoice. `Contract` has no schedule link. `RecurringInvoiceSchedule` already has `company_id` and is already in RLS (`0012_sprint_c_rls_recurring.py`).

**Permission.** `IsOwner` to create the schedule. `ENABLE_CONTRACTS` off is 404. Saving a contract does not create a schedule.

**Change.** Add nullable `Contract.recurring_schedule` in the next contracts migration after listing that folder. The button calls `wrap_idempotent` with scope `contract_recurring_schedule`, registered in `MONEY_IDEMPOTENCY_SCOPES`. The first call creates one schedule through the existing recurring service and stores it on the contract. A later call returns that schedule. `contracts` may import `sales`. An ast walk of `backend/sales/` still finds no `contracts` import. Remove `growth.valueDoesNotBill` from the page in the same change. The button’s sentence, in both catalogs, says the value is copied onto one recurring invoice.

**Tests.** Sequential second click returns the same schedule id and the contract’s foreign key is that schedule. Race: two threads, one schedule, PostgreSQL only. Flag off is 404. A non-owner receives 403.

**DoD.** One schedule exists, the page no longer says the value does not bill, and `sales/` does not import `contracts`.

## Exit

L1 through L5 are green on a trial company without new trial flags. L6 through L12 are green only after `grant_company_flag` for that module, and a second company without the grant is refused. The QOS yaml for a finished ticket moves to the lifecycle the generator already uses for done work. No ticket enables live IRN, GSTN upload, WhatsApp Cloud, a bank feed, or a dark module.
