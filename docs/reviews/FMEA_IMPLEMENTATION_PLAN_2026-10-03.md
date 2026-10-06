# FMEA implementation plan

Date: 2026-10-03. Revised the same day after review.

## Source and scores

The scored register is the canvas [fmea-pilot-grant.canvas.tsx](file:///C:/Users/Dell/.cursor/projects/e-Bizboard/canvases/fmea-pilot-grant.canvas.tsx). There is no separate FMEA markdown. Class, severity (S), occurrence (O), detectability (D), and RPN below are copied from that register so a reviewer can check the ranking without opening the canvas.

RPN = S × O × D. It is a sort key. Critical and High rows were escalated when the failure is cross-tenant, a double post, a cancel that leaves a journal posted, or a demo overlay on staging.

| Id | Class | S | O | D | RPN | Function |
| --- | --- | --- | --- | --- | --- | --- |
| FMEA-016 | Critical | 10 | 2 | 8 | 160 | `integrations.shopify._shop_connection` |
| FMEA-015 | Critical | 9 | 7 | 8 | 504 | `integrations.shopify._sync_stock` |
| FMEA-001 | Critical | 9 | 4 | 8 | 288 | `payroll.services.cancel_pay_run` |
| FMEA-017 | Critical | 9 | 2 | 8 | 144 | `banking.views.AaIngestView.post` |
| FMEA-002 | Critical | 9 | 2 | 5 | 90 | `enable_full_demo.Command.handle` |
| FMEA-004 | High | 8 | 10 | 8 | 640 | `crm.campaigns._won_revenue` |
| FMEA-005 | High | 8 | 7 | 8 | 448 | `sumCustomerOpportunityValue` |
| FMEA-007 | High | 8 | 7 | 5 | 280 | `ComplaintViewSet._link_document` |
| FMEA-003 | High | 8 | 4 | 5 | 160 | `enable_full_demo.Command.handle` |
| FMEA-008 | High | 8 | 2 | 8 | 128 | `core.events.emit` |
| FMEA-006 | High | 8 | 2 | 5 | 80 | `PaymentService.share_payment_link` |
| FMEA-009 | Medium | 7 | 7 | 8 | 392 | `insights.growth_metrics.growth_metrics` |
| FMEA-010 | Medium | 7 | 10 | 5 | 350 | `billing.services.trial_plan_modules` |
| FMEA-011 | Medium | 7 | 4 | 8 | 224 | `accounting.tasks._depreciate_company_assets` |
| FMEA-013 | Medium | 5 | 7 | 5 | 175 | `contracts.tasks.refresh_contract_statuses` |
| FMEA-012 | Medium | 7 | 4 | 3 | 84 | `workshop.services.convert_to_invoice` |
| FMEA-014 | Medium | 7 | 2 | 5 | 70 | `reporting.views._maybe_gstn_json` |

## What changed in this revision

Reviewed against the code on 2026-10-03. These corrections replace the earlier wording.

1. FMEA-011 is narrower. `FixedAsset.last_depreciation_error` and `BooksHealthService._depreciation_alerts` already exist (`DEPRECIATION_FAILED` at `backend/accounting/services.py`). The outer `except` blocks already set the field. The gap is the per-month `except BusinessRuleError` at `backend/accounting/tasks.py`, which only logs, and the success path, which sets `last_depreciation_error = ""` and wipes a skipped month.
2. New tests use the prefix `fmea2_`. Names `test_tc_fmea_001` through `test_tc_fmea_013` in `backend/tests/test_fmea_mitigations.py` stay as they are and mean different things.
3. Pull requests are one finding, one app. The old bundle of contracts with accounting and reporting is split. Customer 360 and the SLA count are split.
4. FMEA-006 restricts Cloud sends only. A `wa.me` link to another number stays, because the pilot does not POST and the link is opened by a person.
5. FMEA-008 states that an audit-table failure blocks invoicing and payments. The cutover is one deploy. Cancel paths that reverse money are in the file list, including cancels that do not emit today.
6. Campaign ROI is completed-invoice taxable value, net of completed credit notes on those invoices. It is not `grand_total`.
7. A second job-card convert returns the linked draft. Status stays `IN_PROGRESS` until the invoice completes, and the response carries the invoice status.
8. Shopify still proposes an absolute on-hand. A newer level posts only inside a small band. A large delta is held, not posted. The applied timestamp is stored on the zero-delta path too. The wave 5 alert is not the control for this Critical row.
9. Client-supplied Account Aggregator rows are tagged `ingest_source=client`. `use_live_fiu` does not create a consent.
10. The dark-module change is a dry-run management command, not a migration, and it is not under Schema. Until the shop-domain column lands, two companies on one domain both get a rejected webhook. Wave 5 tells both owners.
11. Freeze Gate scope is stated below, with a coverage-map row to add.
12. Wave 5 adds read-only queries for missing audit rows and complaints that already have both a return and a credit note. Campaign ROI is computed on read, so there is no stored figure to backfill.
13. Pack grants do not enable payroll. `accounts/packs.py` skips `ENABLE_PAYROLL`. CRM and manufacturing have pack keys. The demo command must not claim otherwise.

## How to ship

Six waves. Wave 1 first. Wave 6 waits until waves 1–5 are green.

One pull request per finding. A finding that is only a command plus its test is still one pull request. Do not combine apps to save a review.

Each pull request runs `backend/tests/test_fmea_mitigations.py` and the neighbor suite named on that finding. New tests are `test_fmea2_*`. Do not add another `test_tc_fmea_*`.

Do not turn a module on. Do not build campaign sending, policy issue, or live GSTN filing.

### Rules for every change

The posting services stay the only writers of stock, tax, and journals. A bridge that already returns an existing document keeps that behavior. A second call remains a no-op or a conflict.

`PostingService.post` returns immediately when `accounting_enabled` is false. `PostingService.reverse` calls `post`. Calling reverse while books are off would mark the original journal `REVERSED` and store no reversal lines. Any repair in this plan refuses that path.

Tests use two companies whenever the finding is tenancy. Company B’s documents, movements, journals, and flags stay unchanged. Books-on cases still assert a balanced journal.

### Test name map

| New test | Finding | Do not confuse with |
| --- | --- | --- |
| `test_fmea2_001_pay_run_cancel_refuses_while_books_off` | FMEA-001 | `test_tc_fmea_001` price edit in a soft-closed period |
| `test_fmea2_002_demo_refuses_staging` | FMEA-002 | `test_tc_fmea_002` blank party assumption |
| `test_fmea2_003_demo_company_is_explicit` | FMEA-003 | none |
| `test_fmea2_004_campaign_roi_taxable_net` | FMEA-004 | `test_tc_fmea_004` referral mark-paid |
| `test_fmea2_005_opportunity_total_decimal` | FMEA-005 | `test_tc_fmea_005` complaint waits for approval |
| `test_fmea2_006_cloud_send_same_phone` | FMEA-006 | `test_tc_fmea_006` old-regime TDS rate |
| `test_fmea2_007_complaint_return_xor_credit_note` | FMEA-007 | `test_tc_fmea_007` unposted pay run |
| `test_fmea2_008_audit_failure_rolls_back` | FMEA-008 | `test_tc_fmea_008` work-order cost copy |
| `test_fmea2_008_audit_row_once` | FMEA-008 | same |
| `test_fmea2_009_waiting_ticket_sla` | FMEA-009 | `test_tc_fmea_009` RLS sweep log |
| `test_fmea2_011_skipped_month_keeps_error` | FMEA-011 | `test_tc_fmea_011` WhatsApp opt-in |
| `test_fmea2_012_convert_twice_one_invoice` | FMEA-012 | `test_tc_fmea_012` stale PDF |
| `test_fmea2_013_contract_job_skips_flag_off` | FMEA-013 | `test_tc_fmea_013` schedule start date |
| `test_fmea2_014_gstn_needs_env_and_flag` | FMEA-014 | none |
| `test_fmea2_015_shopify_holds_large_delta` | FMEA-015 | none |
| `test_fmea2_016_shopify_domain_unique` | FMEA-016 | none |
| `test_fmea2_017_aa_live_fetch_closed` | FMEA-017 | none |

## Freeze Gate

Freeze Gate Phase 2 remains the merge bar for rows in `docs/FREEZE_SCOPE.md` section A. This plan does not add a SUPPORTED feature and does not flip a frozen flag on.

| Finding | Freeze posture |
| --- | --- |
| FMEA-008 | On the SUPPORTED complete and cancel paths (sales, purchases, receipts). Must stay inside FG-2 audit evidence for a completed financial document. |
| FMEA-006 | Payment-link share is on the pilot. Cloud is off (`ENABLE_WHATSAPP_CLOUD=0`). The `wa.me` path stays. The Cloud digit check is dormant on the frozen host. |
| FMEA-014 | GSTN JSON is frozen off. The change tightens the export. It does not enable it. |
| FMEA-010 | Documentation and a lock test. The trial dict is not widened. |
| FMEA-001, FMEA-011 | Payroll and fixed assets are outside the frozen pack. Ship them, and do not treat the pull request as a freeze expansion. |
| FMEA-007, FMEA-004, FMEA-005, FMEA-009, FMEA-012, FMEA-013 | Grant lanes. Off on the frozen trial plan. |
| FMEA-002, FMEA-003 | Dev command. Staging and production stay refused. |
| FMEA-015, FMEA-016, FMEA-017 | Connection or AA flag. Off on the frozen host. |

In the FMEA-008 pull request, add a section `FMEA closures (2026-10-03)` to `docs/FREEZE_SCOPE_COVERAGE.md` with one row per finding in the table above. SUPPORTED-path rows start as partial and become gated when `test_fmea2_008_audit_row_once` is green. Grant and dark rows are marked out of freeze scope in that same table, so a later reader does not read them as new SUPPORTED surface.

## Wave index

| Wave | Name | What it locks |
| --- | --- | --- |
| 1 | Money integrity | Pay-run cancel, audit in the money transaction, one complaint document, Cloud recipient |
| 2 | Figure honesty | Taxable-net ROI, decimal opportunity total, paused SLA, second convert |
| 3 | Grants and jobs | Demo command, trial text, contract job, depreciation error, GSTN ceiling |
| 4 | Integrations | Held Shopify deltas, one shop domain, live bank fetch closed |
| 5 | Detection and existing rows | Owner notices, read-only queries for rows already wrong |
| 6 | Schema, then a separate behaviour command | Shop domain column, per-company FIU credential. Dark modules are a command, not a migration. |

## Wave 1 — Money integrity

Ship this before ROI or Shopify. These four changes do not need a migration.

### FMEA-001 — Pay-run cancel while books are off

Class: Critical. Owner: payroll. Workflow: W23.

`cancel_pay_run` in `backend/payroll/services.py` reverses the `PAY_RUN` / `PAYROLL` journal only inside `if locked.company.accounting_enabled` (around line 599), then sets `DRAFT` either way. The next complete reuses that journal because `PostingService.post` returns the existing `POSTED` row for the same source key.

Change `cancel_pay_run`:

- Load the posted journal with the same filter the reverse path already uses.
- If that journal exists and `accounting_enabled` is false, raise `BusinessRuleError` and leave status `COMPLETED`. The message tells the owner to turn books on, then cancel.
- If books are on, keep the current reverse, then set `DRAFT`.
- Do not call `PostingService.reverse` while books are off.

`BooksHealthService._unposted_pay_run_alerts` in `backend/accounting/services.py` gains a second code, `PAY_RUN_JOURNAL_OPEN`, for a pay run that is not `COMPLETED` and still has a posted `PAYROLL` journal. `test_tc_fmea_007` stays: a complete while books were off, with no journal, is still `PAY_RUN_UNPOSTED`.

Add `repair_orphan_pay_run_journals` under `backend/payroll/management/commands/`. It lists those runs. With books on and `--apply`, it calls `PostingService.reverse` and does not re-complete. With books off it prints the ids and exits. Amounts come from the journal lines.

Test `test_fmea2_001_pay_run_cancel_refuses_while_books_off` in `backend/tests/test_fmea_mitigations.py`. Owner, payroll granted, two companies. Complete with books on, turn books off, cancel: status stays `COMPLETED`, journal stays `POSTED`, company B untouched. Turn books on, cancel: journal `REVERSED`, status `DRAFT`. Re-complete: a new `POSTED` journal whose lines match the new slips, trial balance still zero.

Done when that test passes and `test_tc_fmea_007` still passes.

### FMEA-008 — Audit commits with the document

Class: High. Owner: core. Workflow: W1.

`core.events.emit` swallows handler errors. `audit_document_event` in `backend/core/handlers.py` is one of those handlers. A failed insert leaves a completed invoice and no audit row. PDF enqueue stays on the swallowing bus.

**Outage.** After this change, a failure inserting `AuditEvent` rolls back the money transaction. Invoicing, returns, credit notes, receipts, and supplier payments stop until the audit table accepts writes. That is the intended trade. Do not catch the insert. The API error is the signal. There is no second queue that completes the document later.

Add `record_document_event` in `backend/core/services/audit.py`. It calls `AuditService.log` with company, user, entity type, entity id, description (the event name), and metadata `status` and `number`. It does not catch exceptions. Call it in the same transaction as the money write, immediately before `emit`, on every path below.

Complete paths that already emit `document.completed`:

- `backend/sales/services.py` invoice complete
- `backend/sales/return_service.py` return complete
- `backend/sales/notes_services.py` credit note, debit note, challan complete
- `backend/purchases/services.py` invoice and return complete
- `backend/purchases/notes_services.py` credit note and debit note complete
- `backend/payments/services.py` receipt and supplier payment create

Cancel and void paths:

- `backend/sales/services.py` invoice cancel (`document.cancelled`)
- `backend/sales/return_service.py` return cancel
- `backend/purchases/services.py` invoice cancel and purchase-return cancel
- `backend/sales/notes_services.py` `cancel_credit_note`, `cancel_debit_note`, `cancel_challan` (these reverse money and do not emit today)
- `backend/purchases/notes_services.py` `cancel_credit_note`, `cancel_debit_note` (same)
- `backend/payments/services.py` receipt void and supplier-payment void (`document.voided`, which the current subscriber does not audit)

Edits that already emit `sales_invoice.edited` / `purchase_invoice.edited` call `record_document_event` in that same transaction.

Remove the `document.completed`, `document.cancelled`, `sales_invoice.edited`, and `purchase_invoice.edited` subscriptions from `backend/core/handlers.py` in the same pull request as the direct calls. `emit` stays best-effort for PDF and telemetry.

**One row during deploy.** Ship the direct call and the subscription removal in one pull request and one rollout. A request is handled by one worker. An old worker still uses only the subscriber. A new worker uses only the direct call. Do not deploy the call while the subscriber is still registered, and do not remove the subscriber in an earlier release. Either split leaves a window of two rows or of zero rows.

Tests:

- `test_fmea2_008_audit_failure_rolls_back`. Patch `AuditService.log` to raise. `SalesService.complete` rolls back: no completed invoice, no journal, no stock movement.
- `test_fmea2_008_audit_row_once`. Audit succeeds, PDF task raises. The invoice stays completed. Exactly one `AuditEvent` exists for that invoice id and the complete description. Cancel of that invoice writes a second event, the cancel description, and does not add another complete event.

### FMEA-007 — One complaint, one money document

Class: High. Owner: complaints. Lane: C1. Workflow: W15.

`ComplaintViewSet._link_document` in `backend/complaints/views.py` returns the existing row for the same slot and will still create the other slot. `ReturnService.complete_return` restores stock and posts the return’s own credit note. A standalone credit note does not restore stock.

Inside the existing `select_for_update`, if `attr` is `sales_credit_note` and `sales_return_id` is set, or the reverse, raise `BusinessRuleError`. A second call on the same slot still returns the existing id. Replacement orders stay a new draft. This wave only separates the return from the extra credit note.

Rows that already have both links are not unlinked here. Wave 5 lists them.

Test `test_fmea2_007_complaint_return_xor_credit_note`, beside `test_tc_fmea_005` (leave that test). Approved complaint, books on, two companies. Create the return and the credit note: the second call is 400, one draft exists. Complete the return: one `SALES_RETURN` movement, one completed credit note linked to that return, company B unchanged. Reject and resolve-with-no-document still move nothing.

### FMEA-006 — Cloud send uses the opted-in number

Class: High. Owner: payments. Workflow: W24.

`PaymentService.share_payment_link` sets `allow_cloud` from `allow_cloud_for_customer`, then `NotificationService.send` copies that into `opt_in` and posts to the `recipient` argument. The invoice share action in `backend/sales/views.py` does the same. Frozen pilot keeps `ENABLE_WHATSAPP_CLOUD=0`, so today the result is a `wa.me` link a person opens. That link is not a send. Staff may point it at the customer’s accountant. Refusing every recipient other than the customer would remove that and would not enforce consent.

When the channel is WhatsApp:

- A Cloud POST is allowed only when `customer.whatsapp_opt_in` is true and the recipient is the same number as `customer.phone`.
- Any other recipient still receives the `wa.me` link, with `allow_cloud` false. No Cloud POST.

`_normalize_phone` in `backend/core/services/whatsapp.py` keeps digits and drops `+` and spaces. `+91 98765 43210` and `919876543210` match. `9876543210` does not match `919876543210`. Compare with `accounts.otp_utils.canonicalize_user_phone` (the same helper lead convert uses) on both sides before the equality check. If canonicalization raises, set `allow_cloud` false and still return the link. Do not answer 400 for a link.

Add the same Cloud digit check in dunning’s `_send_whatsapp`, which already passes `customer.phone`. A mismatch there means skip Cloud. Dunning must not start sending a link to a different number.

Test `test_fmea2_006_cloud_send_same_phone` next to `test_tc_fmea_011` (leave that test). Customer opted in, phone stored as `919876543210`.

- Recipient `+91 98765 43210` with Cloud configured: the Cloud path may run.
- Recipient `9876543210`: treated as the same number after canonicalization, Cloud may run.
- Recipient of a different person: result mode is `link`, Cloud client is not called.

## Wave 2 — Figures that look like money

No journals are created by these reads. The API remains the place that sums money.

### FMEA-004 — Campaign ROI basis

Class: High. Owner: crm. Lane: C3. Workflow: W14.

`_won_revenue` in `backend/crm/campaigns.py` sums `Quotation.grand_total` for `CONVERTED`, and otherwise uses `opportunity.amount`. `grand_total` includes GST, so a later switch to invoice `grand_total` would still overstate campaign revenue and would ignore credit notes.

Basis, fixed in the test:

- Quotations for this company and opportunity, status `CONVERTED`, `converted_invoice_id` set.
- Invoices on those ids, same company, status `COMPLETED`.
- Revenue = sum of those invoices’ `taxable_total`, minus `taxable_total` of completed credit notes whose `sales_invoice` is one of those invoices.
- Source label `completed_invoice_taxable_net`.
- When there is no such invoice, return `Decimal("0")` and source `no_completed_invoice`. Do not substitute the opportunity amount, the quotation total, or `grand_total`.

`campaign_rollup` can keep adding child totals. Those totals will already use this basis. The funnel response should show the source label so the screen does not read the figure as cash collected.

ROI is computed on read. Nothing stored under the old basis needs a migration. The next GET is the new number. Wave 5 does not backfill campaigns.

Test `test_fmea2_004_campaign_roi_taxable_net` in `backend/tests/test_growth_os.py`. Won opportunity, converted quotation of one amount, completed invoice whose taxable total differs from both the quotation and the GST-inclusive grand total, plus a completed credit note for part of that taxable total, plus a void invoice. Funnel revenue equals taxable total minus that credit note. No `JournalEntry` for the campaign. An open opportunity with no invoice returns zero and `no_completed_invoice`.

### FMEA-005 — Customer 360 opportunity total

Class: High. Owner: web, with the sum in insights. Lane: C3. Workflow: W20. Own pull request. Do not include the SLA change.

`sumCustomerOpportunityValue` in `web/src/pages/sales/customer360Value.ts` adds `Number(row.amount)`. The page then formats that sum, and a missing total becomes 0. `formatMoney` already accepts a decimal string.

When `ENABLE_CRM` is on, `customer_360` in `backend/insights/customer_360.py` adds `opportunity_total`: `Sum(Coalesce(amount, 0))` for this company and customer, quantized to `0.01` with `ROUND_HALF_UP`, returned as a string. A null amount contributes zero. When the flag is off, omit the key. The page already renders `OffSection` for CRM off. It reads `body.opportunity_total` and stops calling the client sum. A real zero is the string `0.00`. An absent key is the off section, not a printed zero.

Test `test_fmea2_005_opportunity_total_decimal`. API: amounts `0.10`, `0.20`, and null return `0.30`. Flag off: the key is absent. Web: `Customer360Page` shows the server string and does not call `Number`. No journal.

### FMEA-009 — SLA pause in the admin count

Class: Medium. Owner: insights. Lane: C2. Workflow: W17. Own pull request, separate from FMEA-005.

`growth_metrics` counts `sla_due_at < now` for open tickets. `effective_sla_due_at` in `backend/support/tickets.py` adds the time spent in `WAITING`. Past SLA while `WAITING` is `sla_due_at + (now - waiting_since) < now`, which is `sla_due_at < waiting_since`. That is a database filter. No Python loop over tickets.

Put the predicate on `support/tickets.py` and use it in `tickets_past_sla`:

- Waiting, with `waiting_since` set: `sla_due_at < waiting_since`.
- Otherwise: `sla_due_at < now`.

Test `test_fmea2_009_waiting_ticket_sla`. A waiting ticket whose stored due is in the past, and whose paused due is still in the future, is not counted. A waiting ticket that was already breached when it entered `WAITING` (`sla_due_at < waiting_since`) is counted.

### FMEA-012 — Second convert, and serials

Class: Medium. Owner: workshop. Lane: C2. Workflow: W21.

`convert_to_invoice` copies quantity and price and sets status `INVOICED` while the sales document is still a draft. Leaving the job `IN_PROGRESS` removes that status bit, so the linked invoice has to be the guard.

On convert, under the existing row lock:

- If `sales_invoice_id` is set and that invoice is `DRAFT` or `COMPLETED`, return it. Do not create another.
- If the linked invoice is `CANCELLED`, keep today’s unlink behaviour, then continue.
- For a part with `track_serial`, pass `serial_numbers: [line.serial.serial_number]` and require quantity `1`. If `serial_id` is empty, raise before the invoice is created.
- Leave status `IN_PROGRESS` while the linked invoice is a draft.
- The convert response includes the invoice id and the invoice status, so the screen can say a draft is linked.
- `sync_job_card(..., completed=True)` remains the only writer of `INVOICED`.

`SerialNumberService` on invoice complete stays the stock gate.

Test `test_fmea2_012_convert_twice_one_invoice`. Convert twice: one `SalesInvoice`. Status is `IN_PROGRESS` until complete, then `INVOICED`. A serial-tracked part without a serial raises and leaves no invoice. A serial-tracked part with a serial completes with one `SALE` movement and the serial `SOLD`.

## Wave 3 — Grants, trial text, and jobs

Three pull requests for the three apps that used to be bundled: contracts, accounting, reporting. Demo and the trial-plan text stay their own pull requests.

### FMEA-002 and FMEA-003 — `enable_full_demo`

Class: Critical (FMEA-002) and High (FMEA-003). Owner: ops. Workflow: W26. One pull request, because it is one command.

`backend/core/management/commands/enable_full_demo.py` raises only when `DJANGO_ENV` is `production`. It writes every dark-module key and every grantable key, then takes `CompanyUser.objects.filter(user=user).first()`.

Pack grants, confirmed in `backend/accounts/packs.py` and `build_feature_flags`:

- `pack_grant=insurance` turns `ENABLE_CRM` on.
- `manufacturing_pack_grant=True` turns `ENABLE_MANUFACTURING` on.
- `ENABLE_PAYROLL` is skipped in `apply` of every pack. No pack key turns payroll on.

Stopping the command from writing dark-module JSON would remove payroll from an unsubscribed demo, and CRM and manufacturing would appear only when the matching pack key is set. The command must say that in its help text.

Change the command:

- Raise `CommandError` when the env is `production` or `staging`. Development, dev, local, and test may run.
- Require exactly one active membership, or `--company-id` that belongs to that user. Several memberships and no id is an error.
- Default run does not write `ENABLE_MANUFACTURING`, `ENABLE_PAYROLL`, `ENABLE_CRM`, `ENABLE_GSTN_JSON`, or `ENABLE_PREDICTIVE_DUNNING`.
- `--with-manufacturing-pack` sets `manufacturing_pack_grant` true. It does not set `ENABLE_MANUFACTURING` by itself.
- `--with-insurance-pack` sets `pack_grant` to `insurance`.
- `--with-dark` writes the three dark JSON keys only when the company has no subscription (`plan_modules_for_company` is `None`). On a subscribed company, print that payroll stays off because no pack grants it, and that CRM and manufacturing need the pack flags above. Do not write the dark keys in that case.
- Leave the trial `Plan.modules` row untouched.

Tests in `backend/tests/test_enable_full_demo.py`:

- `test_fmea2_002_demo_refuses_staging` and the existing production refusal.
- `test_fmea2_003_demo_company_is_explicit` for two memberships.
- A trial company in development, default command: manufacturing, payroll, and CRM stay false, trial plan row unchanged.
- Unsubscribed company with `--with-dark`: the three JSON keys are true.
- Subscribed company with `--with-dark`: payroll stays false, and the stdout says so.

### FMEA-010 — Trial plan versus the pilot env file

Class: Medium. Owner: billing. Own pull request.

`trial_plan_modules` sets `ENABLE_GSTR` and `ENABLE_GSTR_EXTENDED` true. `backend/.env.pilot.example` sets both to `0`. Grantable keys lift the env for a subscribed trial company. GSTR-6, GSTR-7, and GSTR-8 already return `supported: false` and a disclaimer. GSTN JSON stays in `TRIAL_HELD_FALSE`.

This pull request records that contract. It does not turn GSTR off and does not edit the shared trial dict to add dark modules.

- In `backend/.env.pilot.example`, under the GSTR lines, state that a trial subscription lifts those two keys and that GSTN JSON stays false.
- In `docs/FREEZE_SCOPE.md`, point the GSTR row at `trial_plan_modules` and `TRIAL_HELD_FALSE`.
- Add a test that the trial dict is true for `ENABLE_GSTR`, `ENABLE_GSTR_EXTENDED`, and `ENABLE_CUSTOMER_360`; false for every `TRIAL_HELD_FALSE` key; and that `ENABLE_CRM`, `ENABLE_MANUFACTURING`, and `ENABLE_PAYROLL` are absent.

### FMEA-013 — Contract nightly job

Class: Medium. Owner: contracts. Lane: C2. Workflow: W18. Own pull request.

`refresh_contract_statuses` in `backend/contracts/tasks.py` updates every company. After the company is loaded, skip it when `flag_enabled(company, "ENABLE_CONTRACTS")` is false. The `company_id` filter and the RLS GUC stay. Status rows already stored are left as they are when the flag is removed.

The task return value includes `skipped_flag_off`. Log that count at info, with the company ids. A skip is visible in the worker log and in the task result.

Test `test_fmea2_013_contract_job_skips_flag_off`. Company A flag on, company B flag off, both with an expiring contract. After the task, only A’s status changes, and `skipped_flag_off` is 1.

### FMEA-011 — Skipped depreciation month stays visible

Class: Medium. Owner: accounting. Workflow: W25. Own pull request.

Already built, and left as built:

- `FixedAsset.last_depreciation_error`.
- `BooksHealthService._depreciation_alerts`, code `DEPRECIATION_FAILED`, for a non-empty error (`backend/accounting/services.py` around line 1917).
- The outer `except BusinessRuleError` and `except Exception` in `backend/accounting/tasks.py` (around lines 152–157) write that field.

The gap is inside the month loop:

- `except BusinessRuleError` around lines 135–142 logs and `continue`. It does not set `last_depreciation_error`.
- A later month that posts sets `last_depreciation_error = ""` (around line 145) and erases a skipped month.

Change:

- On the per-month `BusinessRuleError`, set `last_depreciation_error` to the period key plus the exception text, save it, then `continue`. Do not add that month to `depreciated_amount`. Do not post into the closed period.
- On a successful month, clear `last_depreciation_error` only when this run has not skipped an earlier month. If any month was skipped, leave the field naming those months, including after a later open month posts.

`_depreciation_alerts` can stay. Once the field survives, the existing warning is the detective control. Wave 5 does not add a second depreciation code.

Test `test_fmea2_011_skipped_month_keeps_error`. Asset with one closed month and a later open month. The closed month has no journal. `depreciated_amount` excludes it. After the open month posts, `last_depreciation_error` still names the closed month. `DEPRECIATION_FAILED` is present.

### FMEA-014 — GSTN-shaped export

Class: Medium. Owner: reporting. Workflow: W10. Own pull request.

`_maybe_gstn_json` in `backend/reporting/views.py` reads `settings.ENABLE_GSTN_JSON` only. `ENABLE_GSTN_JSON` is in `ROLLOUT_GRANTABLE_KEYS` (`backend/core/services/feature_flags.py`). Company JSON can show the action while a process with the env at `0` still refuses the download. Removing the key from `ROLLOUT_GRANTABLE_KEYS` changes any company that already stored `ENABLE_GSTN_JSON: true`.

Before editing the flag set, run:

```sql
SELECT id, name
FROM accounts_company
WHERE feature_flags->>'ENABLE_GSTN_JSON' IN ('true', 'True', '1');
```

Put the count and the ids in the pull request.

- The view allows the export only when `settings.ENABLE_GSTN_JSON` is true and `flag_enabled(company, "ENABLE_GSTN_JSON")` is true. Keep `to_gstn_json`’s disclaimer.
- If the query returns no rows, remove `ENABLE_GSTN_JSON` from `ROLLOUT_GRANTABLE_KEYS` in the same pull request, so company JSON can only narrow the env.
- If the query returns rows, do not remove the key in this pull request. The view’s env check still refuses the file when the process flag is off. List the companies. A follow-up removes the key only after those grants are cleared by hand.

Trial plan already stores false.

Test `test_fmea2_014_gstn_needs_env_and_flag`. Env off, company JSON true: export refused. Env on, company JSON false: export refused. Env on and company JSON true: response includes the disclaimer. Company B with the flag off gets nothing.

## Wave 4 — Integrations

These run only when a connection or the AA flag is on. The frozen pilot leaves WhatsApp Cloud and Account Aggregator off. The code still changes, because a grant or a connection is enough to reach it.

### FMEA-015 — Shopify must not clobber local stock

Class: Critical. Owner: imports.

`_sync_stock` in `backend/integrations/shopify.py` posts an `ADJUSTMENT` so on-hand equals `payload["available"]` (around line 152). There is no timestamp. The view already returns duplicate for a repeated `X-Shopify-Webhook-Id` after a committed sync run. A new delivery id with an older quantity still posts. A newer delivery posts Shopify’s number over a local sale Shopify has not seen. Detection in wave 5 does not fix that.

Order import stays a draft and keeps the `shopify:{id}` marker.

Inside the transaction that locks the balance and the connection row:

- Read `updated_at`. If it is missing, return `skipped` and post nothing.
- Compare it to the last applied timestamp on the connection metadata, keyed by inventory item id.
- If the payload time is older or equal, return `skipped` and post nothing.
- If `delta == 0`, store the timestamp and post nothing. A later older webhook must still lose.
- If the level is newer and `abs(delta) <= max(Decimal("1"), Decimal("0.25") * on_hand_before)`, post the delta and store the timestamp in the same transaction.
- Otherwise hold. Do not post. Upsert one pending row in metadata for that inventory item id: available, `updated_at`, delta, on-hand before. Do not advance the applied timestamp until the pending row is posted or discarded, except that a newer `updated_at` replaces the pending payload. A repeated delivery id is still a no-op at the view.

`on_hand_before == 0` uses the floor of 1, so a one-unit first sync can post and a large first write is held. A 90 percent overwrite of a non-zero balance is held because `0.90 > 0.25`. An alert that fired on “delta greater than on-hand” is not used. It would fire on every write when on-hand is 0, and it would miss a large overwrite of a large balance.

Pending rows wait for an owner. Wave 5 lists them. This wave does not add an approve screen. Discard is deleting that metadata key. Posting a held delta is a later explicit inventory adjustment, using the pending numbers, not an automatic replay.

Do not delete old movements. Do not invent a quantity to undo stock that was overwritten before this change.

Test `test_fmea2_015_shopify_holds_large_delta`.

- Apply available 10 with a timestamp, sell 1 through `SalesService`, then a new webhook id with an older timestamp and available 10. On-hand stays at the post-sale quantity. Applied timestamp unchanged.
- A newer webhook with delta 0 stores the new timestamp and posts nothing.
- A newer webhook whose absolute delta is above a quarter of on-hand posts nothing and leaves a pending metadata row. Company B unchanged.
- The same webhook id remains a no-op.

### FMEA-016 — One shop domain, one company

Class: Critical. Owner: imports.

`_shop_connection` returns the first active Shopify connection whose metadata domain matches (`backend/integrations/shopify.py` around line 33).

If the count is not exactly one, return no connection. The webhook already answers 401 when the connection is missing. Neither company’s stock changes.

Until wave 6 adds a unique column, this reject is the control. Both companies on a shared domain stop receiving stock updates. Wave 5 `SHOPIFY_DOMAIN_CLASH` tells both owners so one connection can be deactivated. That outage of the sync is accepted. Silent writes to the wrong company are not.

Test `test_fmea2_016_shopify_domain_unique`. Two active connections, same domain. Signed webhook: 401, zero `ADJUSTMENT` rows on both companies.

### FMEA-017 — Live AA fetch, and client rows

Class: Critical. Owner: accounts.

`AaIngestView.post` can create a consent from the request body and then `fetch_live_transactions_for_consent` with the process `FIU_API_KEY`. Revoked and expired consents are already refused. Mock ingest stays limited to development and test.

`use_live_fiu`:

- Look up an `ACTIVE` consent for this company and this consent id.
- If none exists, raise `BusinessRuleError`. Do not `update_or_create`. Do not call the FIU.
- If one exists, still do not call the FIU unless this company has its own FIU credential. The global `FIU_API_KEY` is not that credential. Wave 6 adds the store. Until then, live ingest is off on every environment.

Client-supplied `transactions` on an existing active consent for this company may be stored. They are not FIU data. Set `raw["ingest_source"] = "client"` on each of those rows. Mock rows already created in development set `ingest_source` to `mock`. A future live row sets `fiu`. Readers of the AA list must be able to tell a typed row from a fetch. Do not present `client` rows as bank-verified.

A consent id this company does not already hold is not created by a live-fetch request and is not fetched.

Test `test_fmea2_017_aa_live_fetch_closed`. Owner, AA flag on, `use_live_fiu` true, a consent id that does not exist on company A. No outbound HTTP, no new `AaConsent`, no `AaTransaction`. A second case stores a client transaction on an existing consent and the saved raw contains `ingest_source=client`.

## Wave 5 — Detection, and rows that already exist

`nightly_invariants_task` and `BooksHealthService` already notify owners in app (`test_tc_fmea_010`). Add codes. Do not add a new channel.

| Code | When | Who is told |
| --- | --- | --- |
| `PAY_RUN_JOURNAL_OPEN` | Non-completed pay run, posted `PAYROLL` journal | Owner, in app, from books health. Added in wave 1. |
| `DEPRECIATION_FAILED` | Already implemented. Wave 3 makes the skipped month survive a later post. | Owner, in app |
| `SHOPIFY_DOMAIN_CLASH` | Two active connections, same domain | Owner of each company, and a log line with both company ids |
| `SHOPIFY_STOCK_HELD` | A pending Shopify delta from wave 4 | Owner, in app. This is the queue, not a second poster. |

Do not add an alert that fires when the absolute Shopify delta is greater than on-hand. Wave 4 holds the large move instead.

Read-only queries, as a management command `fmea2_existing_gaps` with no `--apply`:

- Completed sales invoices, purchase invoices, credit notes, and posted receipts that have no `AuditEvent` for that entity id. Print counts per company. Do not invent audit rows. History from before wave 1 stays listed until someone decides to backfill, which this plan does not do.
- Complaints with both `sales_return_id` and `sales_credit_note_id` set. Print them. Do not unlink. An operator completes or cancels one document through the sales screens.
- Campaign ROI: nothing to query. The figure is computed in `_won_revenue`. After wave 2 the next read uses taxable net. Say that in the command’s help text so nobody adds a fake backfill.

CI checks, as tests:

- Pay-run status and the posted `PAYROLL` journal agree, both directions (`test_fmea2_001` plus the existing `test_tc_fmea_007`).
- Campaign revenue for the fixture equals taxable net (`test_fmea2_004`).
- `tickets_past_sla` equals the waiting predicate (`test_fmea2_009`).
- `enable_full_demo` raises when `DJANGO_ENV` is staging (`test_fmea2_002`).

Stock balance versus the sum of movements stays the existing invariant. Run it in `test_fmea2_015` for the adjustment that was allowed and for the hold that was not posted.

## Wave 6 — Schema, then a behaviour command

Schema first, in two pull requests. The dark-module change is a third pull request and is not a migration.

**Shop domain column.** Add `shop_domain` on the Shopify connection, unique among `ACTIVE` rows. Backfill from metadata. Fail the migration if two active rows share a domain. An operator deactivates one, using the wave 5 clash notice, and reruns the migration. `_shop_connection` then reads the column. Until this lands, wave 4’s “count must be one” rule rejects both companies.

**Per-company FIU credential.** Store it the way WhatsApp secrets are stored, on `IntegrationConnection`, encrypted. `fetch_live_transactions_for_consent` takes that token and the company’s existing `ACTIVE` consent. The process `FIU_API_KEY` stays unused for tenant data. Only then does `use_live_fiu` run. Rows it writes set `ingest_source=fiu`.

**Dark modules, command only.** In `_build_feature_flags_uncached`, a missing plan no longer lets company JSON turn on `ENABLE_MANUFACTURING`, `ENABLE_PAYROLL`, or `ENABLE_CRM`. Those turn on from the plan, from `manufacturing_pack_grant`, or from `pack_grant=insurance`. Payroll still has no pack key. The env remains a ceiling.

Do not encode company ids in a migration. Add `grant_dark_module` with `--dry-run` and `--company-id` repeated. Dry-run prints the effective flags before and after. `--apply` writes the pack key the operator named (`insurance` or `manufacturing`). It refuses `payroll`. Companies that today rely on bare JSON keep that behaviour until an operator runs the command and a later one-line change removes the JSON fallback. Ship the command first. Remove the JSON fallback only in a follow-up pull request whose dry-run output is attached, so the behaviour change is reviewed on a real list.

## Left alone

Lead convert, referral `PAID`, contract value, and the default recurring draft already avoid posting. Portal complaints stay on the token’s customer. Bank match keeps linking a journal line and does not create a receipt. GSTR-6, GSTR-7, and GSTR-8 keep their “not a portal file” copy. Work-order serial release and cancel compensation stay as they are.

Shopify stock overwritten before wave 4 is not auto-repaired. The movement is the record. An operator reverses that adjustment through the existing inventory path.

## Pull-request order

1. Payroll: refuse pay-run cancel while the journal cannot be reversed.
2. Core: write document audit in the money transaction, including cancels and voids, and remove the subscriber in the same deploy.
3. Complaints: one return or one credit note.
4. Payments: Cloud send uses the opted-in phone. `wa.me` to another number stays.
5. CRM: campaign ROI is taxable net of completed credit notes.
6. Insights and web: decimal opportunity total. SLA is not in this pull request.
7. Insights: waiting tickets use the database SLA predicate.
8. Workshop: second convert returns the one draft. Serials are copied.
9. Ops: demo command refuses staging, picks one company, and does not pretend payroll has a pack.
10. Billing: document the trial GSTR lift and lock held flags.
11. Contracts: nightly job skips a company whose flag is off, and reports the skip count.
12. Accounting: a skipped depreciation month is stored and not cleared by a later post.
13. Reporting: GSTN export needs env and company flag, after the grant query.
14. Integrations: Shopify timestamp, zero-delta store, hold a large delta.
15. Integrations: shared shop domain rejects the webhook for both companies.
16. Banking: live fetch does not create a consent. Client rows are tagged.
17. Core: clash and held-stock notices, plus `fmea2_existing_gaps`.
18. Schema: unique `shop_domain`. Schema: per-company FIU credential.
19. Behaviour, after 18: `grant_dark_module` dry-run. The JSON fallback comes off only with that dry-run attached.
