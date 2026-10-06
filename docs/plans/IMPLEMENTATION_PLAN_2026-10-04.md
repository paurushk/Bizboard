# Bizboard implementation plan (quality-first), revised

Generated from the workbook sheets *Implementation plan* and *Plan decisions* on 2026-10-04, after the 63 pre-implementation questions. The workbook is the source of truth for status; this file is the readable copy.

## Assumptions

- Start: 12 Oct 2026; agent lanes: 2; contingency buffer: 20% per item plus one release-buffer week per milestone.
- **Team assumption.** One human owner plus agents (default; confirm). Two agent lanes run in parallel only on independent items, each in its own git worktree and Postgres database. Decisions and external reviews sit outside the lanes. Change LANES in build_plan.py if the real team is different.
- **Dates.** Scheduled for the lanes above, Monday to Friday, skipping these holidays: 20 Oct 2026, 09 Nov 2026, 11 Nov 2026, 24 Nov 2026, 25 Dec 2026, 26 Jan 2027. Each estimate carries a 20% buffer, each dependency leaves one clear day for review, and each milestone adds one week before it is called. Dates are fixed text; re-run qos/evidence/build_plan.py to reschedule.
- **Waves.** Wave 1 = Build in MVP, wave 2 = Build in Pilot, wave 3 = Build in GA. Every wave 2 item depends on VER-1 and every wave 3 item on VER-2, so a later wave never starts before the earlier gate closes.
- **Freeze.** The plan does not override docs/FREEZE_SCOPE.md. Live NIC e-way, GSTR-2B API, Tally and WhatsApp Cloud stay behind their flags, default off, and are built against fakes and offline inputs. Flipping a flag is a separate freeze exception.
- **Reviewer rule.** The author never signs their own Review. Agent-built work gets an agent code-review pass, then the human signs. Human-built work gets an agent review, then the human signs after a day. Compliance items also need the CA; pharmacy items a licensed pharmacist.
- **When tests run.** Each pull request: tests for the touched apps plus lint and type checks. Full backend suite on Postgres: nightly and at each verification gate. Performance and load tests: their own scheduled job, never in the pull-request run.
- **Source of truth.** Bizboard_Product_Task_Universe_Master.xlsx is the source of truth and the file register_sync.py updates. Bizboard_Master_Task_Register_Enhanced.xlsx is a mirror written by recalc_xlsx.ps1 -Mirror. Archives are read-only.
- **Other plans.** Production bugs jump the queue, capped at 20% of capacity, and each interrupt is logged in Plan change log. This plan preempts the bug-remediation, UX, FMEA and ISO 25010 plans for new work; items there that duplicate a work item here are merged into it.
- **Slips.** An item more than 2 working days late triggers a re-plan. Every wave 1 item has a cut-line rank in column AH: rank 1 moves to wave 2 first. Before each wave starts, re-check its estimates with a one-day spike.

**Definition of done.** An item is Done when all five stages are Done or N/A. What each stage means depends on the item's Kind (column AG): see the Acceptance criteria column, which states the item's own pass condition, its rejecting case and the done rule for its kind. Features: tests for the touched apps on Postgres, lint and types clean, register_sync scores the test. Web: Vitest or Playwright, tsc -b, ESLint, accessibility check. Performance: benchmark job report. Drill: recorded timings. Decision and external: recorded decision or written sign-off. Gate: checklist.

## Milestones

| Milestone | Planned date | Exit criteria |
|---|---|---|
| M1: MVP gate ready | 12 Feb 2027 | All wave 1 items Done: audit events on every posting action, mandatory admin 2FA, field masking, encryption, ITC and e-way rules (stub actions, flags off), approval queue, credit controls, nightly trial-balance worker, restore drill. Full suite green on Postgres; drift check clean; register shows Built - tested for each. CA sign-off of the Rule 11(g) map: if missing, ship as 'pilot with documented residual'. |
| M2: Pilot gate ready | 20 Apr 2027 | All wave 2 items Done: pilot-breadth features and POS polish verified; end-to-end tests for complaints, lead de-duplication and signup; no open Red items; 0 Fail results in the register for Pilot rows. |
| M3: Later gate ready | 18 Jun 2027 | All wave 3 items Done: differentiators built and verified (Tally and GSTR-2B features still behind their flags); no unreviewed Mechanism not found on P1 compliance rows. |

## Summary by wave

| Wave | Gate | Items | Estimate days | Planned days | First start | Last due |
|---|---|---|---|---|---|---|
| 1 | MVP | 40 | 99.5 | 136 | 12 Oct 2026 | 05 Feb 2027 |
| 2 | Pilot | 23 | 62 | 87 | 09 Feb 2027 | 13 Apr 2027 |
| 3 | Later | 5 | 51 | 63 | 15 Apr 2027 | 11 Jun 2027 |

## Summary by workstream

| Workstream | Items | Estimate days |
|---|---|---|
| Platform & reliability | 5 | 13 |
| GST & compliance | 12 | 34.5 |
| Audit & integrity | 9 | 17 |
| Security | 6 | 16 |
| Payments & credit | 8 | 24 |
| Inventory & POS | 17 | 50 |
| Quality gate | 3 | 6 |
| Growth & SaaS | 8 | 52 |

## Summary by owner

| Owner | Items | Planned days |
|---|---|---|
| Agent 1 | 34 | 129 |
| Agent 2 | 31 | 153 |
| CA / external | 1 | 2 |
| Founder | 2 | 2 |

## Decisions: answers to the 63 questions

Status: Decided = settled; Confirm = default chosen, founder confirms before the item starts; External = needs a CA, pharmacist, host or other outside input; Dropped = removed from the plan.

| Q | Topic | Items | Status | Answer | What changed in the plan |
|---|---|---|---|---|---|
| 1 | Team and parallelism | All | Confirm | Plan for one human owner plus agents. Two agent lanes run in parallel only on independent items, each in its own git worktree and its own Postgres database. The human decides, reviews and signs. Start moves to Monday 12 Oct 2026, not 5 Oct. If the real team is larger, change DEVS in build_plan.py and regenerate. | Developers 3 to 2 lanes; start 12 Oct; owners Agent 1, Agent 2, Human reviewer. |
| 2 | Feature freeze | WI-027, 029-032, 060, 061 | Decided | The plan does not override the freeze. Everything touching live NIC, GSTR-2B API, Tally and WhatsApp Cloud is built behind its existing flag, default off, against a fake adapter and offline inputs. Flipping a flag is a separate freeze exception and is not part of any item. WI-027 becomes an in-app token; WI-029-031 become stub actions plus stored fields; WI-032 computes validity from entered distance only; PIN-to-PIN lookup is deferred. | Scope of WI-027, 029, 030, 031, 032, 060, 061 rewritten; flags stay off. |
| 3 | Second reviewer | All | Confirm | Rule: the author never signs their own Review. Agent-built work gets an agent code-review pass first, then the human signs. Human-built work gets an agent review, then the human signs after a day's gap. Compliance items also need the CA, pharmacy items a licensed pharmacist. If you want a named human second reviewer, add them as Owner on the Review stage. | Definition of done: reviewer rule added to Plan guide. |
| 4 | Source-of-truth workbook | All | Decided | Bizboard_Product_Task_Universe_Master.xlsx is the source of truth and the file register_sync.py updates by default. Bizboard_Master_Task_Register_Enhanced.xlsx is a mirror written by recalc_xlsx.ps1 -Mirror. Archives are read-only. The _UPDATED file is renamed over the Master once Excel releases it. | Plan guide states the rule. |
| 5 | Other open plans | All | Decided | Production bugs jump the queue, capped at 20% of capacity, and each interrupt is logged in the change log. This plan preempts the bug-remediation, UX, FMEA and ISO 25010 plans for new work, but any item in those plans that duplicates a work item here is merged into it rather than done twice. | 20% interrupt allowance noted in Plan guide. |
| 6 | Postgres host and backup keys | WI-007 | External | Recommended default: managed Postgres in an India region with built-in point-in-time recovery, RPO 5 minutes, RTO 1 hour for the pilot. Backup encryption keys live in the provider's key service, administered by the founder, with a sealed break-glass copy held separately. WI-007 cannot be designed until you pick the provider, so a new decision item DEC-HOST comes first and WI-007 depends on it. | New item DEC-HOST (owner Founder); WI-007 depends on it. |
| 7 | Chartered accountant for Rule 11(g) | WI-003, 004 | External | Build the coverage map now and sign later. A new external item CA-SIGN follows WI-003. If no CA is named by 2 Nov 2026, M1 still closes technically but is marked 'pilot with documented residual: Rule 11(g) sign-off pending'. The same CA reviews the tax rule tables in WI-016 to WI-020, so a new item DEC-CA (engage the CA) precedes them. | New items DEC-CA and CA-SIGN. |
| 8 | Item-specific pass conditions | All | Decided | Every item now has its own pass condition and rejecting case, written in the plan, and the definition of done depends on the item's kind: feature, web, performance, infrastructure drill, decision or process gate. The four pasted lines are gone. | Acceptance criteria rewritten per item; new Kind column. |
| 9 | Frontend tests and register sync | WI-043, 052-057 | Decided | Web items are done on Vitest component tests, a Playwright flow where there is a flow, tsc -b, ESLint with zero errors and an accessibility check. They do not need the backend suite. register_sync.py is extended to read Vitest and Playwright JUnit output (new item REG-WEB, first in the plan), and web test references become real file paths. | New item REG-WEB; web items depend on it; test globs replaced with files. |
| 10 | WI-002 and WI-004 | WI-002, 004 | Decided | Yes. Their remaining work is Review plus the register update. Evidence is the parent item's tests (WI-001 and WI-003). Design, Build and Tests stay N/A. | Done condition for these items: parent Done and register row updated. |
| 11 | Items with no register task | WI-033, 035, 058, 067 | Decided | Verification gates have no register row and are done when their checklist passes. WI-033 gets a new register row (next free X- number) created when the item starts, so it can be scored. | Done condition by kind; WI-033 gets a register row at start. |
| 12 | Test file for SEC-0624 | WI-010 | Decided | The existing test_mfa.py stays as the regression base. A new test_mfa_mandatory.py covers enforcement and first-login enrolment. The strict xfail test in test_register_integrity_gaps.py becomes a normal passing test. WI-005 keeps test_register_integrity_gaps.py for the invariant tests only. | Planned test files corrected. |
| 13 | When the full suite runs | All | Decided | Each pull request runs the tests for the apps it touches plus lint and type checks. The full backend suite on Postgres runs nightly and at each verification gate (WI-035, 058, 067). Performance tests run on their own schedule, never in the pull-request run. | Plan guide states the rule. |
| 14 | Wave overlap | WI-036 | Decided | Not intended. Every wave 2 item now depends on VER-1 and every wave 3 item on VER-2, so no later wave starts before the earlier gate closes. | Dependencies added; dates rescheduled. |
| 15 | Holidays | All | Confirm | Treated as non-working: 20 Oct, 9 Nov, 11 Nov, 24 Nov, 25 Dec 2026 and 26 Jan 2027. Edit the HOLIDAYS list in build_plan.py to match your calendar. | Scheduler skips the listed holidays. |
| 16 | Slack and slips | All | Decided | Item estimates carry a 20% buffer. Each milestone date also has one extra week before it is called. Any item more than 2 working days late triggers a re-plan, and every wave 1 item has a cut-line rank so the lowest-ranked can move to wave 2 instead of moving M1. | Milestone date +7 days; Cut line column added. |
| 17 | Estimates that cannot meet scope | WI-010, 028, 044, 050, 061 | Decided | Re-estimated: 2FA 1.5 to 4 days; POS latency split into a 2-day benchmark harness and a separate timeboxed 5-day optimisation; printer work narrowed to network printer plus keyboard-wedge scanner at 6 days with Bluetooth and browser camera deferred; Tally 10 to 25 days for TallyPrime masters, opening balances and one financial year of vouchers; signup 1 to 3 days. Every wave's estimates are re-checked with a one-day spike before that wave starts. | Estimates changed; WI-028 split; spike rule in Plan guide. |
| 18 | Admin 2FA | WI-010 | Decided | Gap-fill, not a rebuild. Checked 2026-10-04: MFA_ENFORCE_FOR_MONEY_ROLES defaults on in production and staging, and enrolment_required already blocks a session until TOTP is enrolled. user_has_money_role covers only OWNER and ACCOUNTANT. There is no separate Admin role: OWNER is labelled Owner/Admin, and there is no can_manage_users flag (invites are an owner action). The gap is MANAGER, whose defaults include can_post_journals and who is not enforced today. Extend enforcement to OWNER, ACCOUNTANT and any membership with can_post_journals (MANAGER by default). Do not add SALES_STAFF: they can create sales and payments, and cashiers and salespeople stay out. Recovery codes already exist. | WI-010 scope names the real roles after the repo check. |
| 19 | Audit trail gap | WI-001 | Decided | Gap-fill only. Add an audit event with actor, IP and before/after values to: sales invoice complete, cancel and amend; sales return; credit and debit notes; purchase invoice complete (books on and off); purchase return; customer receipt; supplier payment; journal post and reverse; stock adjustment, transfer and goods receipt; payroll finalise; period lock and reopen. Remove the xfails. | WI-001 scope lists the actions. |
| 20 | Encryption scope | WI-013 | Decided | New work covers bank account numbers and tax-portal secrets, with existing gateway credentials moved from Fernet to AES-256-GCM. IFSC is not secret and stays searchable. Existing plaintext rows are migrated in batches with a reversible step, storing the last four digits for display. Keys come from the host's secret store, carry a key id for rotation, and never live in the repo. | WI-013 scope rewritten. |
| 21 | Nightly seal alert | WI-034 | Decided | Checked 2026-10-04. core-seal-audit-chain is already on the Celery beat at 02:40 daily (config/settings.py). A verify failure only calls logger.error; the task comment says Sentry picks that up. There is no missed-night detector, no ops-metric for the seal, and no email. Nightly invariant failures notify the Owner in-app via NotificationService, not by email (email is the console backend unless EMAIL_HOST is set). WI-034 adds a missed-run check and alerts the same way: logger.error plus an in-app notification to the Owner. It does not add a new email path. | WI-034 channel set from the code: log plus in-app Owner notification. |
| 22 | Trial-balance worker | WI-005 | Decided | Invariants: trial balance zero; every journal balanced; AR and AP control accounts equal customer and supplier outstanding; stock ledger equals the sum of movements; allocations never exceed payments; output tax in the ledger equals invoice tax. Quarantine flags the batch, blocks period close and GST export until cleared, and does not block billing. Alert goes to Owner, Accountant and the ops mailbox. | WI-005 scope rewritten. |
| 23 | Soft delete | WI-006 | Decided | is_deleted on Customer, Supplier, Product, Warehouse and PriceList. Ledger accounts keep their existing guard. Transactions are cancelled or voided, never soft-deleted. Owner and Admin can restore. Where a foreign key cascades onto transactional rows, it becomes PROTECT; existing child rows are not touched, and the migration first prints an orphan report. | WI-006 scope rewritten. |
| 24 | Rate limiting | WI-008 | Decided | Public routes: login, OTP request and verify, register, password reset, portal links, webhooks. Limits: login 10 per minute per IP and 5 per minute per account; OTP 3 per minute and 10 per hour per target; register 5 per hour per IP; portal 60 per minute per token; authenticated API 600 per minute per tenant with burst 100; webhooks verified by signature with a separate higher limit. If Redis is down, login and OTP fail closed on a strict in-process fallback limit and the general API fails open, with an alert. | WI-008 scope rewritten. |
| 25 | Cost and margin masking | WI-009 | Decided | Visible to Owner, Admin, Accountant, Purchase Manager and Inventory Manager. Hidden from Cashier, Salesperson and Godown custodian. In API, exports and PDFs the field is omitted, not blanked or zeroed, because a zero reads as a real cost. The POS screen shows selling price and a below-cost warning computed on the server, never the cost. | WI-009 scope rewritten. |
| 26 | Session revocation | WI-011 | Decided | Both access and refresh tokens are revoked. Mechanism: a per-user session version checked on every request (Redis with a database fallback), plus the existing refresh blacklist. Whether a websocket layer exists is checked at item start; if there is none, the next API call is enough. | WI-011 scope rewritten. |
| 27 | Input sanitising | WI-012 | Decided | Both: HTML tags are stripped on save from plain-text fields (notes, descriptions, names, addresses, remarks, complaint text, imported cells), and output is escaped on render and in PDF templates. SQL injection is already handled by the ORM, so the new test is a guard that fails the build on string-built raw SQL; no new SQL sanitiser. | WI-012 scope rewritten. |
| 28 | Invoice snapshots | WI-014 | Decided | Snapshot legal name, trade name, billing and shipping address, and GSTIN at completion, for sales invoices, credit and debit notes, and purchase bills (supplier details). Backfill marks every copied row snapshot_source = backfill_from_master and flags it for review; where the audit history shows a rename, the name as of the invoice date is used instead of today's master. Old invoices are never silently rewritten. | WI-014 scope rewritten. |
| 29 | Schedule H and X register | WI-015 | External | Behind a per-tenant pharmacy flag, off by default. For Schedule H, H1 and X items a sale cannot complete without patient and prescriber name and registration number; Schedule X also keeps a prescription copy. Inspector layout: date, patient, prescriber and registration no., drug, batch, quantity, invoice no., printable as PDF and CSV. Retention default 3 years, configurable. A licensed pharmacist must review the layout and retention before any pharmacy goes live (default taken from my recollection of the Drugs Rules, so verify). | WI-015 scope rewritten; pharmacist review added. |
| 30 | Section 16(2) checklist | WI-016 | External | Mixed. The system proves invoice held (bill exists), goods received (GRN link) and the 180-day payment rule (from payments). 'Supplier paid the tax' and 'return filed' are attested by the user, because GSTR-2B is out of the freeze. A failed or unconfirmed check warns on the bill and excludes it from the claimable ITC summary; it does not block posting the bill or the ledger. CA reviews the wording. | WI-016 scope rewritten. |
| 31 | Section 16(4) time bar | WI-017 | External | 60 and 7 days are warnings before the statutory deadline (30 November following the financial year of the invoice, or the annual return date if earlier). TIME_BARRED applies after the deadline to unclaimed ITC and excludes it from the claimable summary. ITC already claimed is flagged for CA review, not reversed automatically. CA to confirm relief provisions for older years. | WI-017 scope rewritten. |
| 32 | Section 17(5) list | WI-018 | External | Implement the full blocked-credit list as a data table with effective dates (motor vehicles, food and beverages, outdoor catering, beauty and health services, club membership, employee travel benefits, works contract and construction of immovable property, personal consumption, goods lost, stolen or destroyed, gifts and free samples, and the rest). Match on HSN/SAC plus expense category; keywords only suggest. On a block, GST posts to the expense or asset account, not ITC receivable. Owner and Accountant can override with a reason, audited. CA approves the table. | WI-018 scope rewritten. |
| 33 | GSTR-2B scope in WI-019 | WI-019 | Decided | WI-019 only adds the blocked-credit classification to the reconciliation data that already exists, using uploaded 2B files. It builds no new reconciliation and calls no GSTN API, so it stays inside the freeze. | WI-019 scope narrowed. |
| 34 | Section 50 interest | WI-020 | External | Rates held in a table with effective dates: 18% a year on tax paid late, 24% on undue or excess ITC claimed. Basis: net cash liability where the return was filed late (Rule 88B), and the unpaid amount where tax was paid late after filing. Output is a worksheet plus CSV. It posts no journal. CA confirms the table and the basis. | WI-020 scope rewritten. |
| 35 | Chronic defaulter rule | WI-021 | Confirm | New rule, still to confirm: per company, any invoice more than 60 days overdue and an over-60-day total of at least Rs 5,000. The block stops credit-sale completion, sales-order confirmation and delivery challans; cash and prepaid sales still go through. Unlock is a single-use code valid 24 hours, issued by the Owner or a credit-override role, with a reason. Existing rule, checked 2026-10-04, stays and the stricter of the two wins. Always on: sales invoice complete blocks when credit_limit > 0 and exposure plus the invoice exceeds it (sales/services.py). Opt-in, default off (company.auto_credit_hold_on_severe_overdue): the same complete path also blocks when collection status is stop_credit (outstanding above the credit limit) or overdue_severe (any overdue and either a 90-plus-day bucket or average payment delay over 21 days), from payments/dunning.py customer_risk_snapshot. That opt-in does not run on sales-order confirmation or delivery challans. | WI-021 now states the existing hold instead of 'read the code first'. |
| 36 | Cheque dishonour split | WI-022, 023 | Decided | WI-022 owns reversal, bank fee and owner alert. WI-023 owns only the section 138 notice draft. The '5 days' is replaced by configurable dates taken from the bank's return memo. The notice follows the statutory sequence (written demand within 30 days of the memo, 15 days to pay) and carries the disclaimer that it is a draft for an advocate to review. Default fee is the amount from the bank memo, suggested Rs 500. Whether GST applies to the recovery is a CA decision; it is a configurable flag, default off. | WI-022 and WI-023 scopes separated. |
| 37 | Cancelled supplier GSTIN | WI-024 | Decided | Status comes from whatever feeds the existing alert plus a manual flag; no GSTN pull. New ITC is blocked for invoices dated on or after the cancellation effective date. ITC already availed is flagged for the CA, not reversed. The payment hold can be overridden by Owner or Accountant with a reason, audited. | WI-024 scope rewritten. |
| 38 | Approval queue | WI-025 | Decided | Actions: credit-limit override, stock adjustment above threshold, invoice cancel or amend after completion, discount above threshold, return or credit note above threshold, backdated posting or period reopen, supplier payment above threshold, bad-debt write-off, bulk import commit. Default approver is the Owner, configurable per action by role. A requester cannot approve their own request; an Owner with no other approver can, flagged as self-approved with a reason. Requests expire after 72 hours and count as rejected. | WI-025 scope rewritten. |
| 39 | Stock adjustment approval | WI-026 | Decided | Either test triggers it: value at cost of Rs 10,000 or more, or quantity of 10% or more of on-hand. Both are configurable per company. Dual approval needs two different users; a single-user company gets the Owner exception from WI-025. | WI-026 scope rewritten. |
| 40 | Credit override token | WI-027 | Decided | In-app one-time token for MVP; WhatsApp is added when the freeze flag is flipped. Single use, 15-minute expiry, bound to the invoice batch and requester. If the owner does not respond, the over-limit invoices stay in 'Awaiting approval', the others proceed, expiry counts as rejected, and nothing is ever auto-approved. | WI-027 scope rewritten. |
| 41 | Checkout latency | WI-028 | Decided | Target: 95th percentile 200 ms server-side for checkout complete including tax, stock and ledger, on a 2 vCPU 4 GB container with local Postgres, a 20,000-SKU catalogue and a 3-line cart. The benchmark runs outside the normal suite on its own nightly job and compares against a recorded baseline. The item splits into WI-028 (harness and baseline, 2 days) and a new WI-028b (optimise, timeboxed 5 days). | WI-028 split; WI-028b added. |
| 42 | E-way bill actions | WI-029-032 | Decided | Stub actions against the GSP adapter interface with a fake provider, plus stored fields for vehicle history, extension and multi-vehicle split, all behind GSP_LIVE_ENABLED=0. Live calls need NIC or GSP sandbox credentials from you and a freeze exception. WI-032 computes validity from the entered distance using a configurable slab table with effective dates that the CA confirms (the bands have changed over time). PIN-to-PIN distance lookup is deferred. | WI-029-032 scopes rewritten; PIN lookup deferred. |
| 43 | Concurrent customer edits | WI-033 | Decided | Both mechanisms. PATCH merges changed fields under a row lock, so concurrent edits of different fields both persist. PUT requires a version and a stale write is rejected with 409 and the current value. A register row is created when the item starts. | WI-033 scope rewritten. |
| 44 | Salt, composition, manufacturer | WI-036 | Decided | Optional fields, shown and searchable for every tenant but expected mainly by pharmacies. Billing search must stay inside the WI-028 latency budget (trigram index and a query-budget test). | WI-036 scope rewritten. |
| 45 | Bulk invoice CSV | WI-037 | Decided | Columns: invoice ref, customer, invoice date, due date, item SKU or barcode, quantity, rate, discount %, warehouse, notes; tax is computed. Mode: dry run validates everything first, then commits per invoice atomically; an invoice with any bad row is rejected whole and reported by row. Cap 2,000 rows (about 500 invoices) per file; the file hash makes re-upload idempotent. | WI-037 scope rewritten. |
| 46 | In-transit stock | WI-038 | Decided | In transit is a real location per transfer. Stock moves source to in-transit on dispatch and in-transit to destination on receipt. Partial receipt is allowed with a shortage or damage reason. No ledger entry for same-company, same-GSTIN transfers. | WI-038 scope rewritten. |
| 47 | Multi-shop dashboard | WI-039 | Decided | Warehouses within one company only; multi-company GSTIN stays out of scope. The view must stay inside the dashboard's query budget, with a test. | WI-039 scope rewritten. |
| 48 | Overdue interest and bad-debt risk | WI-040 | Confirm | Report only, no posting. Interest rate per company, default 18% a year simple. Suggested provision by age: 0 to 60 days 0%, 61 to 90 days 5%, 91 to 180 days 25%, 181 to 365 days 50%, over 365 days 100%. Confirm the buckets with your accountant. | WI-040 scope rewritten. |
| 49 | Warehouse users and contacts | WI-041 | Decided | Users map to many warehouses with one default. Contact person and phone are required; email is optional. | WI-041 scope rewritten. |
| 50 | Printer and scanner scope | WI-044, 045 | Confirm | Pilot scope: network ESC/POS printer and USB keyboard-wedge scanner. Bluetooth and the browser camera scanner are deferred; the mobile app's camera scan already works. Verification devices: a network ESC/POS printer such as an Epson TM-T82 and any keyboard-wedge scanner; you need to buy or name them. Tests: Vitest for logic plus a manual device checklist. | WI-044 and WI-045 rescoped; tests are web files. |
| 51 | Subscription invoices | WI-046 | Decided | Bizboard's own GST invoice to the tenant, with our GSTIN and place of supply from the tenant's state, generated and emailed on a captured-payment event. Freeze decision D3 names the pilot gateways: Cashfree or PayU, sandbox only, at least one configured (ENABLE_CASHFREE and ENABLE_PAYU on). The invoice generator listens to that captured-payment event and does not call a gateway SDK. Razorpay stays as it is: billing.tasks.reconcile_saas_subscriptions_task reconciles local Subscription rows and is not the source of these tax invoices. | WI-046 names Cashfree or PayU from the freeze; Razorpay recon is left alone. |
| 52 | Journey tests | WI-047-049 | Decided | They test flows that already work. If one fails, fixing it is in scope up to one day; anything larger becomes a separate item. Rejecting cases: duplicate submission, wrong-tenant access, missing permission, and a credit note created exactly once. | WI-047-049 pass and reject cases added. |
| 53 | Signup load test | WI-050 | Decided | 20 concurrent signups out of 50 total, 95th percentile provisioning at most 10 seconds, no duplicate tenants. Runs on a nightly or manual job, not in the pull-request run. Item is 3 days. | WI-050 estimate and criteria changed. |
| 54 | Cart reservation release | WI-051 | Confirm | Checked 2026-10-04: there is no cart session and no timeout. POS drafts are device-local, wiped on sign-out (freeze C5), and do not reserve stock. The only stock hold with no expiry is a confirmed sales-order reservation, released on cancel, convert or invoice complete. WI-051 adds a company-configurable expiry, default 24 hours, on that reservation and on POS holds once WI-053 creates them: release the allocation and mark the hold expired, keeping the row so it can be restored if stock is free. Confirm the 24-hour default before the item starts. | WI-051 scope states that no cart timeout exists; default TTL 24 hours, still to confirm. |
| 55 | WI-053 dependency | WI-053 | Decided | Not real. The dependency on keyboard-only POS is removed. | Dependency removed. |
| 56 | Rupee mask vs role masking | WI-057 | Decided | Yes, separate. The mask is a personal on-screen toggle for people allowed to see the figures; it is not a security control. | WI-057 scope rewritten. |
| 57 | Cash-flow simulation | WI-059 | Decided | Per debtor, bootstrap from the days-late of the last 12 settled invoices, shrunk toward the customer-segment average; 1,000 runs; show p10, p50 and p90. With fewer than 5 settled invoices, fall back to the ageing heuristic and show a 'low confidence, based on N invoices' badge. | WI-059 scope rewritten. |
| 58 | Fuzzy invoice matching | WI-060 | Decided | Score 0.95 or higher with equal GSTIN and tax within tolerance links automatically; 0.80 to 0.95 suggests a match for a person to confirm; below 0.80 shows nothing. It runs on uploaded 2B data after WI-019; nothing calls GSTN. | WI-060 scope rewritten; depends on WI-019. |
| 59 | Tally migration | WI-061 | Decided | TallyPrime only for now. Ledger masters, stock items, opening balances and one financial year of vouchers, with a mandatory mapping step for ledgers and stock items. Turning ENABLE_TALLY on is a separate freeze exception, not part of this item. Estimate 25 days; multi-year history and Tally.ERP 9 come later. | WI-061 scope and estimate changed. |
| 60 | Non-filer higher TDS/TCS | WI-062, 063 | Dropped | Dropped pending CA confirmation. To my knowledge sections 206AB and 206CCA were omitted from 1 April 2025, which would make both items obsolete. If the CA says otherwise: use an uploaded specified-person list rather than stored taxpayer credentials, valid for the financial year, applied to new documents only. | WI-062 and WI-063 removed from the plan. |
| 61 | Anomaly detector | WI-064 | Decided | Review queue only; it never blocks a bill. Unusual means a discount above 3 times the item's median discount, or a bill above both a rupee floor and 3 times the customer's median bill. Thresholds are per company and configurable. | WI-064 scope rewritten. |
| 62 | Section 128A | WI-065 | Dropped | Dropped from the plan, kept in the register as On request. The scheme window has closed, so a live tracker has no use, and a historical reconciliation is only worth building for a pilot customer who has declarations. CA to confirm. | WI-065 removed. |
| 63 | Section 171 anti-profiteering | WI-066 | Dropped | Dropped from the plan, kept in the register as On request, because enforcement has been wound down as far as I know. CA to confirm. If it comes back: count rate-cut notifications as events, with the last price before the cut as the baseline. | WI-066 removed. |

### Needs your confirmation before the affected item starts

- Q1 (Confirm): Team and parallelism, items All
- Q3 (Confirm): Second reviewer, items All
- Q6 (External): Postgres host and backup keys, items WI-007
- Q7 (External): Chartered accountant for Rule 11(g), items WI-003, 004
- Q15 (Confirm): Holidays, items All
- Q29 (External): Schedule H and X register, items WI-015
- Q30 (External): Section 16(2) checklist, items WI-016
- Q31 (External): Section 16(4) time bar, items WI-017
- Q32 (External): Section 17(5) list, items WI-018
- Q34 (External): Section 50 interest, items WI-020
- Q35 (Confirm): Chronic defaulter rule, items WI-021
- Q48 (Confirm): Overdue interest and bad-debt risk, items WI-040
- Q50 (Confirm): Printer and scanner scope, items WI-044, 045
- Q54 (Confirm): Cart reservation release, items WI-051

## Wave 1: MVP gate

| WI | Task | Work item | Workstream | Owner | Est. | Start | Due | Depends on |
|---|---|---|---|---|---|---|---|---|
| WI-068 |  | Extend register_sync.py to score Vitest and Playwright results | Platform & reliability | Agent 1 | 1 | 12 Oct 2026 | 13 Oct 2026 |  |
| WI-069 |  | Decide Postgres host, RPO/RTO and backup-key custody | Platform & reliability | Founder | 0.5 | 12 Oct 2026 | 12 Oct 2026 |  |
| WI-070 |  | Engage a chartered accountant for Rule 11(g) and the tax rule tables | GST & compliance | Founder | 0.5 | 12 Oct 2026 | 12 Oct 2026 |  |
| WI-001 | P-0115 | Maintain an audit trail | Audit & integrity | Agent 2 | 3 | 12 Oct 2026 | 15 Oct 2026 |  |
| WI-002 | X-0432 | Critical transaction → immutable audit trail exists | Audit & integrity | Agent 2 | 0 | 19 Oct 2026 | 19 Oct 2026 | WI-001 |
| WI-003 | P-0507 | Audit MCA mandated immutable audit trail (Rule 11(g) Companies Audit Rules) | Audit & integrity | Agent 1 | 2 | 19 Oct 2026 | 22 Oct 2026 | WI-001 |
| WI-004 | C-0616 | Companies (Accounts) Rules Rule 3(1) and Rule 11(g) audit trail compliance certification | Audit & integrity | Agent 1 | 0 | 26 Oct 2026 | 26 Oct 2026 | WI-003 |
| WI-005 | S-0561 | Automated background trial balance zero-sum verification worker | Audit & integrity | Agent 2 | 3 | 16 Oct 2026 | 22 Oct 2026 |  |
| WI-006 | S-0568 | Database foreign key cascade deletion defense and soft-delete enforcement | Audit & integrity | Agent 1 | 4 | 23 Oct 2026 | 29 Oct 2026 |  |
| WI-007 | S-0570 | Automated continuous WAL archiving and daily encrypted PostgreSQL pg_dump snapshot | Platform & reliability | Agent 2 | 3 | 23 Oct 2026 | 28 Oct 2026 | WI-069 |
| WI-008 | S-0572 | Distributed Redis token bucket rate limiting on public-facing API endpoints | Security | Agent 2 | 2 | 29 Oct 2026 | 02 Nov 2026 |  |
| WI-009 | SEC-0622 | Field-level role masking for sensitive commercial margins and cost prices | Security | Agent 1 | 2 | 30 Oct 2026 | 03 Nov 2026 |  |
| WI-010 | SEC-0624 | Time-based One-Time Password (TOTP) two-factor authentication (2FA) for admin roles | Security | Agent 2 | 4 | 03 Nov 2026 | 10 Nov 2026 |  |
| WI-011 | SEC-0625 | Instant user deactivation and immediate JWT session revocation | Security | Agent 1 | 3 | 04 Nov 2026 | 10 Nov 2026 |  |
| WI-012 | SEC-0626 | Cross-Site Scripting (XSS) and SQL injection sanitization on document notes and inputs | Security | Agent 1 | 2 | 12 Nov 2026 | 16 Nov 2026 |  |
| WI-013 | SEC-0628 | Cryptographic AES-256 encryption for stored bank account numbers and tax credentials | Security | Agent 2 | 3 | 12 Nov 2026 | 17 Nov 2026 |  |
| WI-014 | X-0715 | Customer changes legal name and registered address: system updates master while preserving historical invoices | Audit & integrity | Agent 1 | 2 | 17 Nov 2026 | 19 Nov 2026 |  |
| WI-015 | C-0609 | Schedule H and Schedule X restricted drug sales register and doctor prescription logging | GST & compliance | Agent 2 | 5 | 18 Nov 2026 | 26 Nov 2026 | WI-070 |
| WI-016 | C-0602 | Section 16(2) CGST Act 4-condition statutory Input Tax Credit entitlement verification | GST & compliance | Agent 1 | 4 | 20 Nov 2026 | 27 Nov 2026 | WI-070 |
| WI-017 | C-0603 | Section 16(4) time-barring automated alert and ITC exclusion engine | GST & compliance | Agent 1 | 3 | 01 Dec 2026 | 04 Dec 2026 | WI-016 |
| WI-018 | C-0604 | Section 17(5) blocked credit automated identification and accounting reclassification | GST & compliance | Agent 2 | 5 | 27 Nov 2026 | 04 Dec 2026 | WI-070 |
| WI-019 | P-0503 | Audit 2A/2B vs Books reconciliation and verify eligible vs blocked ITC | GST & compliance | Agent 1 | 3 | 08 Dec 2026 | 11 Dec 2026 | WI-018 |
| WI-020 | C-0607 | Section 50 CGST Act delayed tax payment interest calculator (18% & 24% p.a.) | GST & compliance | Agent 2 | 3 | 07 Dec 2026 | 10 Dec 2026 | WI-070 |
| WI-021 | X-0527 | Automatic debtor account freeze and delivery block on chronic overdue accounts | Payments & credit | Agent 2 | 3 | 11 Dec 2026 | 16 Dec 2026 |  |
| WI-022 | X-0530 | Handle bounced / dishonoured cheque: reverse invoice settlement, add bank fee, alert owner | Payments & credit | Agent 1 | 3 | 14 Dec 2026 | 17 Dec 2026 |  |
| WI-023 | X-0713 | Customer cheque dishonoured after 5 days: automated accounting reversal and bank fee debit | Payments & credit | Agent 1 | 2 | 21 Dec 2026 | 23 Dec 2026 | WI-022 |
| WI-024 | X-0707 | Supplier cancelled GSTIN after issuing invoice: system blocks ITC and alerts purchase team | Payments & credit | Agent 2 | 3 | 17 Dec 2026 | 22 Dec 2026 |  |
| WI-025 | P-0128 | Approve important business actions | Payments & credit | Agent 2 | 5 | 23 Dec 2026 | 31 Dec 2026 |  |
| WI-026 | P-0152 | Adjust stock with authorization | Payments & credit | Agent 1 | 2 | 04 Jan 2027 | 06 Jan 2027 | WI-025 |
| WI-027 | X-0702 | Credit limit breach during bulk invoice: owner sends temporary one-time authorization token | Payments & credit | Agent 2 | 3 | 04 Jan 2027 | 07 Jan 2027 | WI-025 |
| WI-028 | R-0636 | Sub-200ms POS billing checkout latency under continuous queue load | Inventory & POS | Agent 1 | 2 | 07 Jan 2027 | 11 Jan 2027 |  |
| WI-029 | X-0514 | Update transport vehicle number / Transporter ID on active E-Way Bill during breakdown | GST & compliance | Agent 2 | 2 | 08 Jan 2027 | 12 Jan 2027 |  |
| WI-030 | X-0515 | Extend E-Way Bill validity before expiry due to transit delay or traffic accident | GST & compliance | Agent 1 | 2 | 14 Jan 2027 | 18 Jan 2027 | WI-029 |
| WI-031 | C-0618 | E-Way Bill Part B vehicle update statutory time-limit and multi-vehicle consignment splitting | GST & compliance | Agent 2 | 2 | 14 Jan 2027 | 18 Jan 2027 | WI-029 |
| WI-032 | C-0606 | Rule 138 CGST Rules mandatory E-Way Bill distance calculation via postal PIN codes | GST & compliance | Agent 1 | 2 | 19 Jan 2027 | 21 Jan 2027 |  |
| WI-071 |  | CA sign-off of the Rule 11(g) coverage map | Audit & integrity | CA / external | 1 | 26 Oct 2026 | 30 Oct 2026 | WI-003, WI-070 |
| WI-033 |  | Concurrent customer edits: field merge plus version check | Audit & integrity | Agent 2 | 2 | 19 Jan 2027 | 21 Jan 2027 |  |
| WI-034 | S-0579 | Production check and alert for the nightly audit-chain seal | Platform & reliability | Agent 1 | 0.5 | 22 Jan 2027 | 22 Jan 2027 |  |
| WI-028b |  | Optimise POS checkout toward the 200 ms p95 target | Inventory & POS | Agent 2 | 5 | 22 Jan 2027 | 01 Feb 2027 | WI-028 |
| WI-035 |  | Wave 1 verification: full suite on Postgres, register sync, drift check, MVP gate review | Quality gate | Agent 1 | 2 | 03 Feb 2027 | 05 Feb 2027 | WI-068, WI-069, WI-070, WI-001, WI-002, WI-003, WI-004, WI-005, WI-006, WI-007, WI-008, WI-009, WI-010, WI-011, WI-012, WI-013, WI-014, WI-015, WI-016, WI-017, WI-018, WI-019, WI-020, WI-021, WI-022, WI-023, WI-024, WI-025, WI-026, WI-027, WI-028, WI-029, WI-030, WI-031, WI-032, WI-071, WI-033, WI-034, WI-028b |

### Wave 1 item detail

#### WI-068 Extend register_sync.py to score Vitest and Playwright results

- Register task: none  |  Workstream: Platform & reliability  |  Layer: Tooling  |  Kind: tooling  |  Owner: Agent 1  |  Decisions: Q9
- Estimate: 1 days (2 with buffer)  |  Planned 12 Oct 2026 to 13 Oct 2026  |  Depends on: none
- Scope: Parse Vitest and Playwright JUnit, map web test file paths to register rows, unit-test the parser against real output.
- Acceptance criteria: Pass: register_sync.py scores Vitest and Playwright results onto register rows. Rejecting case: A web test that fails marks its row Fail; an unknown path is reported as unmatched. Done means: the tool runs on real output from the suites, its parser has unit tests, and the reviewer signs.
- Planned test file: `qos/tools/tests/test_register_sync_web.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-069 Decide Postgres host, RPO/RTO and backup-key custody

- Register task: none  |  Workstream: Platform & reliability  |  Layer: Process  |  Kind: decision  |  Owner: Founder  |  Decisions: Q6
- Estimate: 0.5 days (1 with buffer)  |  Planned 12 Oct 2026 to 12 Oct 2026  |  Depends on: none
- Scope: Founder chooses the provider (default: managed Postgres in an India region with point-in-time recovery), confirms RPO 5 min and RTO 1 h, and names the key administrator.
- Acceptance criteria: Pass: Provider, RPO, RTO and key administrator recorded. Rejecting case: S-0570 does not start until this is recorded. Done means: the decision is recorded in the Plan decisions sheet with date and owner.
- Planned test file: none (process item)
- Stages:
  - [ ] Design
  - [x] Build (not applicable)
  - [x] Tests (not applicable)
  - [ ] Review
  - [x] Register sync (not applicable)
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-070 Engage a chartered accountant for Rule 11(g) and the tax rule tables

- Register task: none  |  Workstream: GST & compliance  |  Layer: Process  |  Kind: decision  |  Owner: Founder  |  Decisions: Q7
- Estimate: 0.5 days (1 with buffer)  |  Planned 12 Oct 2026 to 12 Oct 2026  |  Depends on: none
- Scope: Name the CA and agree the review scope: Rule 11(g) coverage, s.16(2), s.16(4), s.17(5), s.50 tables, e-way validity slabs, bad-debt buckets.
- Acceptance criteria: Pass: CA named and review scope agreed in writing. Rejecting case: Tax rule items do not close without CA review. Done means: the decision is recorded in the Plan decisions sheet with date and owner.
- Planned test file: none (process item)
- Stages:
  - [ ] Design
  - [x] Build (not applicable)
  - [x] Tests (not applicable)
  - [ ] Review
  - [x] Register sync (not applicable)
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-001 Maintain an audit trail

- Register task: P-0115  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q19
- Estimate: 3 days (4 with buffer)  |  Planned 12 Oct 2026 to 15 Oct 2026  |  Depends on: none
- Scope: Audit event with actor, IP and before/after values on: sales invoice complete, cancel, amend; sales return; credit and debit notes; purchase invoice complete (books on and off); purchase return; customer receipt; supplier payment; journal post and reverse; stock adjustment, transfer, goods receipt; payroll finalise; period lock and reopen. One test per action; remove the xfails.
- Acceptance criteria: Pass: Every action in the scope list writes exactly one AuditEvent with actor, IP and before/after; the chain verifies. Rejecting case: A journal post or a purchase complete with books off that writes no event fails its test (the current xfails); a tampered event fails verification. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_register_audit_coverage.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-002 Critical transaction → immutable audit trail exists

- Register task: X-0432  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q10
- Estimate: 0 days (0 with buffer)  |  Planned 19 Oct 2026 to 19 Oct 2026  |  Depends on: WI-001
- Scope: Delivered with P-0115.
- Acceptance criteria: Pass: Parent P-0115 is Done and its tests pass. Rejecting case: Same rejecting cases as P-0115. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_register_audit_coverage.py`
- Stages:
  - [x] Design (not applicable)
  - [x] Build (not applicable)
  - [x] Tests (not applicable)
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-003 Audit MCA mandated immutable audit trail (Rule 11(g) Companies Audit Rules)

- Register task: P-0507  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q7, 10
- Estimate: 2 days (3 with buffer)  |  Planned 19 Oct 2026 to 22 Oct 2026  |  Depends on: WI-001
- Scope: Rule 11(g) coverage map (action to audit event) built now; edit log on every accounting record; certification export listing the periods in which logging was on. CA sign-off is the separate CA-SIGN item.
- Acceptance criteria: Pass: Coverage map lists every accounting record with its event; certification export shows logging on for the whole year. Rejecting case: Export refuses to certify when the chain has a gap or logging was off in a period. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0507.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-004 Companies (Accounts) Rules Rule 3(1) and Rule 11(g) audit trail compliance certification

- Register task: C-0616  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1
- Estimate: 0 days (0 with buffer)  |  Planned 26 Oct 2026 to 26 Oct 2026  |  Depends on: WI-003
- Scope: Delivered with P-0507: report certifying logging was never disabled.
- Acceptance criteria: Pass: Report certifies logging was never disabled for the financial year. Rejecting case: Report flags any window in which logging was disabled. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0616.py`
- Stages:
  - [x] Design (not applicable)
  - [x] Build (not applicable)
  - [x] Tests (not applicable)
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-005 Automated background trial balance zero-sum verification worker

- Register task: S-0561  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q22
- Estimate: 3 days (4 with buffer)  |  Planned 16 Oct 2026 to 22 Oct 2026  |  Depends on: none
- Scope: Nightly worker runs these invariants: trial balance zero; every journal balanced; AR/AP control accounts equal customer/supplier outstanding; stock ledger equals movements; allocations within payments; ledger output tax equals invoice tax. A violation creates a quarantine record, blocks period close and GST export until cleared (billing continues), and alerts Owner, Accountant and the ops mailbox.
- Acceptance criteria: Pass: Nightly task runs every listed invariant; a violation creates a quarantine record, blocks period close and GST export and alerts. Rejecting case: An unbalanced journal inserted through the ORM is caught on the next run and blocks period close. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_s_0561.py; backend/tests/test_register_integrity_gaps.py (invariant tests)`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-006 Database foreign key cascade deletion defense and soft-delete enforcement

- Register task: S-0568  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q23
- Estimate: 4 days (5 with buffer)  |  Planned 23 Oct 2026 to 29 Oct 2026  |  Depends on: none
- Scope: is_deleted on Customer, Supplier, Product, Warehouse and PriceList; restore by Owner/Admin; ledger accounts keep their guard; transactions are cancelled, never soft-deleted. Cascades onto transactional rows become PROTECT; existing child rows untouched; an orphan report is produced before the migration.
- Acceptance criteria: Pass: Soft-deleted masters vanish from lists, reports and search and Owner/Admin can restore them with history intact. Rejecting case: Hard delete of a master that has transactions raises; deleting a parent no longer cascades onto transactional rows. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_s_0568.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-007 Automated continuous WAL archiving and daily encrypted PostgreSQL pg_dump snapshot

- Register task: S-0570  |  Workstream: Platform & reliability  |  Layer: Infra  |  Kind: infra drill  |  Owner: Agent 2  |  Decisions: Q6
- Estimate: 3 days (4 with buffer)  |  Planned 23 Oct 2026 to 28 Oct 2026  |  Depends on: WI-069
- Scope: Provider-specific design after DEC-HOST: WAL archiving and point-in-time recovery plus the daily encrypted dump, RPO 5 min and RTO 1 h by default, keys held in the provider key service. Restore drill into a non-production copy, timed.
- Acceptance criteria: Pass: Timed restore drill reaches a chosen target time within the RTO; the encrypted dump restores. Rejecting case: Restore with the wrong key fails; a gap in archived WAL raises an alert. Done means: the drill is executed on a non-production copy and its timings and steps are attached; the reviewer signs.
- Planned test file: `drill log in qos/evidence/ (restore or alert drill)`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-008 Distributed Redis token bucket rate limiting on public-facing API endpoints

- Register task: S-0572  |  Workstream: Security  |  Layer: Infra  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q24
- Estimate: 2 days (3 with buffer)  |  Planned 29 Oct 2026 to 02 Nov 2026  |  Depends on: none
- Scope: Redis token bucket. Login 10/min per IP and 5/min per account; OTP 3/min and 10/h per target; register 5/h per IP; portal 60/min per token; authenticated API 600/min per tenant (burst 100); webhooks signature-verified with a higher limit. Redis down: login and OTP fail closed on a strict in-process limit, the general API fails open, with an alert.
- Acceptance criteria: Pass: Each public route enforces its limit with 429 and Retry-After. Rejecting case: The 11th login attempt in a minute is refused; with Redis stopped, login still refuses over-limit attempts and the general API stays up. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_s_0572.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-009 Field-level role masking for sensitive commercial margins and cost prices

- Register task: SEC-0622  |  Workstream: Security  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q25
- Estimate: 2 days (3 with buffer)  |  Planned 30 Oct 2026 to 03 Nov 2026  |  Depends on: none
- Scope: Omit purchase_price and margin (never blank or zero) in API, exports and PDFs for Cashier, Salesperson and Godown custodian; visible to Owner, Admin, Accountant, Purchase Manager, Inventory Manager. POS shows a server-computed below-cost warning, not the cost.
- Acceptance criteria: Pass: Cashier, Salesperson and Godown custodian never receive purchase price or margin from API, exports, PDFs or POS. Rejecting case: A request from those roles for cost fields gets the field omitted, with one test per surface. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_sec_0622.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-010 Time-based One-Time Password (TOTP) two-factor authentication (2FA) for admin roles

- Register task: SEC-0624  |  Workstream: Security  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q12, 18
- Estimate: 4 days (5 with buffer)  |  Planned 03 Nov 2026 to 10 Nov 2026  |  Depends on: none
- Scope: Gap-fill, not a rebuild. Enforcement already defaults on in production and staging for OWNER and ACCOUNTANT, with first-login enrolment and recovery codes. There is no separate Admin role (OWNER is Owner/Admin) and no can_manage_users flag. Extend the same enforcement to any membership with can_post_journals (MANAGER by default). Leave SALES_STAFF, inventory staff, auditor and viewer out.
- Acceptance criteria: Pass: OWNER, ACCOUNTANT and a membership with can_post_journals cannot get a normal session without TOTP, are forced to enrol at first login, and recovery codes work once. Rejecting case: Password-only login for those memberships yields no session; SALES_STAFF can still sign in with a password. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_mfa.py; backend/tests/test_mfa_mandatory.py; backend/tests/test_register_integrity_gaps.py (xfail test)`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-011 Instant user deactivation and immediate JWT session revocation

- Register task: SEC-0625  |  Workstream: Security  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q26
- Estimate: 3 days (4 with buffer)  |  Planned 04 Nov 2026 to 10 Nov 2026  |  Depends on: none
- Scope: Per-user session version checked on each request (Redis with database fallback) plus the existing refresh blacklist, so access and refresh tokens both die on deactivation. Websocket drop only if a channel layer exists.
- Acceptance criteria: Pass: Deactivating a user invalidates access and refresh tokens at the next request. Rejecting case: A deactivated user's existing access token is answered 401. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_sec_0625.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-012 Cross-Site Scripting (XSS) and SQL injection sanitization on document notes and inputs

- Register task: SEC-0626  |  Workstream: Security  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Cut line rank: 10  |  Decisions: Q27
- Estimate: 2 days (3 with buffer)  |  Planned 12 Nov 2026 to 16 Nov 2026  |  Depends on: none
- Scope: Strip HTML tags on save from plain-text fields (notes, descriptions, names, addresses, remarks, complaint text, imported cells); escape on render and in PDF templates; a guard test fails on string-built raw SQL.
- Acceptance criteria: Pass: HTML is stripped on save from the listed fields and output is escaped in the UI and PDFs. Rejecting case: A stored script tag never executes or appears raw; string-built raw SQL fails the guard test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_sec_0626.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-013 Cryptographic AES-256 encryption for stored bank account numbers and tax credentials

- Register task: SEC-0628  |  Workstream: Security  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q20
- Estimate: 3 days (4 with buffer)  |  Planned 12 Nov 2026 to 17 Nov 2026  |  Depends on: none
- Scope: AES-256-GCM with a key id for bank account numbers and tax-portal secrets; move existing gateway credentials off Fernet. IFSC stays plain. Batch migration of plaintext rows (reversible), last four digits kept for display. Keys from the host secret store.
- Acceptance criteria: Pass: Bank account numbers and portal secrets are AES-256-GCM encrypted with a key id and migrated from plaintext. Rejecting case: Tampered ciphertext fails authentication; the wrong key is rejected; no plaintext column remains. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_sec_0628.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-014 Customer changes legal name and registered address: system updates master while preserving historical invoices

- Register task: X-0715  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q28
- Estimate: 2 days (3 with buffer)  |  Planned 17 Nov 2026 to 19 Nov 2026  |  Depends on: none
- Scope: Snapshot legal name, trade name, billing and shipping address and GSTIN at completion on sales invoices, credit and debit notes and purchase bills. Backfill flags rows as backfill_from_master and uses the audit-history name as of the invoice date where a rename exists.
- Acceptance criteria: Pass: Completed documents keep the party details as at completion. Rejecting case: Renaming the customer afterwards does not change the issued PDF or ledger view. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0715.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-015 Schedule H and Schedule X restricted drug sales register and doctor prescription logging

- Register task: C-0609  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q29
- Estimate: 5 days (6 with buffer)  |  Planned 18 Nov 2026 to 26 Nov 2026  |  Depends on: WI-070
- Scope: Per-tenant pharmacy flag, default off. Schedule H/H1/X sale cannot complete without patient and prescriber name and registration no.; Schedule X keeps a prescription copy. Inspector layout (date, patient, prescriber, drug, batch, quantity, invoice no.) as PDF and CSV; retention default 3 years, configurable. A licensed pharmacist reviews layout and retention before any pharmacy goes live.
- Acceptance criteria: Pass: A Schedule H/H1/X sale cannot complete without the required details and the register prints in inspector layout. Rejecting case: A sale without the details is rejected; a tenant without the pharmacy flag is unaffected. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0609.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-016 Section 16(2) CGST Act 4-condition statutory Input Tax Credit entitlement verification

- Register task: C-0602  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q30
- Estimate: 4 days (5 with buffer)  |  Planned 20 Nov 2026 to 27 Nov 2026  |  Depends on: WI-070
- Scope: Per-bill checklist: invoice held and goods received and 180-day payment are system-proven; supplier-paid-tax and return-filed are user-attested (GSTR-2B is outside the freeze). Unconfirmed bills warn and drop out of the claimable ITC summary; posting is not blocked. CA reviews wording.
- Acceptance criteria: Pass: The checklist shows on every purchase bill with proven and attested conditions. Rejecting case: A bill with an unconfirmed condition is excluded from the claimable ITC summary. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0602.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-017 Section 16(4) time-barring automated alert and ITC exclusion engine

- Register task: C-0603  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q31
- Estimate: 3 days (4 with buffer)  |  Planned 01 Dec 2026 to 04 Dec 2026  |  Depends on: WI-016
- Scope: Warnings 60 and 7 days before the s.16(4) deadline (30 Nov after the invoice's financial year, or annual return date if earlier); TIME_BARRED after it for unclaimed ITC, excluded from claimable. Claimed ITC is flagged for the CA, not reversed.
- Acceptance criteria: Pass: Warnings appear at 60 and 7 days before the deadline; barred ITC is marked TIME_BARRED. Rejecting case: TIME_BARRED ITC cannot be claimed; ITC already claimed is flagged, not reversed. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0603.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-018 Section 17(5) blocked credit automated identification and accounting reclassification

- Register task: C-0604  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Cut line rank: 6  |  Decisions: Q32
- Estimate: 5 days (6 with buffer)  |  Planned 27 Nov 2026 to 04 Dec 2026  |  Depends on: WI-070
- Scope: Data-driven s.17(5) rule table with effective dates covering the full blocked list; match on HSN/SAC plus expense category (keywords only suggest); blocked GST posts to expense or asset, not ITC receivable; override by Owner or Accountant with reason, audited. CA approves the table.
- Acceptance criteria: Pass: Blocked purchases post GST to expense or asset; the rule table covers the full list. Rejecting case: Claiming a blocked category without an authorised override and reason is refused. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0604.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-019 Audit 2A/2B vs Books reconciliation and verify eligible vs blocked ITC

- Register task: P-0503  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Cut line rank: 7  |  Decisions: Q33
- Estimate: 3 days (4 with buffer)  |  Planned 08 Dec 2026 to 11 Dec 2026  |  Depends on: WI-018
- Scope: Add the blocked-credit classification to the existing 2A/2B reconciliation using uploaded 2B files. No new reconciliation, no GSTN call.
- Acceptance criteria: Pass: The 2B reconciliation shows the blocked-credit classification. Rejecting case: A blocked invoice is never counted as eligible ITC. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0503.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-020 Section 50 CGST Act delayed tax payment interest calculator (18% & 24% p.a.)

- Register task: C-0607  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q34
- Estimate: 3 days (4 with buffer)  |  Planned 07 Dec 2026 to 10 Dec 2026  |  Depends on: WI-070
- Scope: Section 50 worksheet and CSV: 18% a year on late-paid tax, 24% on undue or excess ITC; net cash liability basis for late-filed returns (Rule 88B), unpaid amount otherwise. Rates in a dated table. No journal posted. CA confirms.
- Acceptance criteria: Pass: Worksheet interest matches hand-calculated cases for each rate and period. Rejecting case: A date outside the rate table is refused; no journal is posted. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0607.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-021 Automatic debtor account freeze and delivery block on chronic overdue accounts

- Register task: X-0527  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Cut line rank: 8  |  Decisions: Q35
- Estimate: 3 days (4 with buffer)  |  Planned 11 Dec 2026 to 16 Dec 2026  |  Depends on: none
- Scope: Keep the existing hold and add the chronic rule; the stricter one wins. Existing, always on: invoice complete blocks when credit_limit > 0 and exposure plus the invoice exceeds it. Existing, opt-in and default off (auto_credit_hold_on_severe_overdue): invoice complete also blocks stop_credit (outstanding above the limit) or overdue_severe (any overdue and either 90-plus days or average payment delay over 21 days). New, per company: any invoice over 60 days overdue and an over-60-day total of at least Rs 5,000 also blocks credit-sale completion, sales-order confirmation and delivery challans. Cash and prepaid still allowed. Single-use unlock code valid 24 h from the Owner or credit-override role, with reason.
- Acceptance criteria: Pass: Chronic customers are blocked from credit sale, order confirmation and challan; cash sales pass; the existing hold still works. Rejecting case: A used or expired unlock code fails; a blocked customer cannot take a credit sale. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0527.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-022 Handle bounced / dishonoured cheque: reverse invoice settlement, add bank fee, alert owner

- Register task: X-0530  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q36
- Estimate: 3 days (4 with buffer)  |  Planned 14 Dec 2026 to 17 Dec 2026  |  Depends on: none
- Scope: Bounce voids the receipt, reverses allocations, debits the bank fee (amount from the bank memo, suggested Rs 500) to the customer and alerts the owner. GST on the recovery is a configurable flag, default off.
- Acceptance criteria: Pass: A bounce voids the receipt, reopens the invoice, debits the fee and alerts the owner. Rejecting case: Bouncing the same receipt twice is rejected. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0530.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-023 Customer cheque dishonoured after 5 days: automated accounting reversal and bank fee debit

- Register task: X-0713  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Cut line rank: 4  |  Decisions: Q36
- Estimate: 2 days (3 with buffer)  |  Planned 21 Dec 2026 to 23 Dec 2026  |  Depends on: WI-022
- Scope: Section 138 notice draft only: written demand within 30 days of the bank memo, 15 days to pay, dates from the memo, disclaimer that an advocate must review. No reversal or fee logic here.
- Acceptance criteria: Pass: Notice draft carries the right dates and the disclaimer. Rejecting case: Dates outside the statutory sequence are refused. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0713.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-024 Supplier cancelled GSTIN after issuing invoice: system blocks ITC and alerts purchase team

- Register task: X-0707  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Cut line rank: 5  |  Decisions: Q37
- Estimate: 3 days (4 with buffer)  |  Planned 17 Dec 2026 to 22 Dec 2026  |  Depends on: none
- Scope: Status from the existing alert source plus a manual flag. New ITC blocked for invoices dated on or after the cancellation effective date; availed ITC flagged for the CA; payment hold overridable by Owner or Accountant with reason, audited.
- Acceptance criteria: Pass: Invoices dated on or after the cancellation date are excluded from ITC and the supplier payment is held. Rejecting case: A held payment cannot post without an authorised override. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0707.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-025 Approve important business actions

- Register task: P-0128  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q38
- Estimate: 5 days (6 with buffer)  |  Planned 23 Dec 2026 to 31 Dec 2026  |  Depends on: none
- Scope: Queue for: credit-limit override, stock adjustment above threshold, invoice cancel or amend after completion, discount above threshold, return or credit note above threshold, backdated posting or period reopen, supplier payment above threshold, write-off, bulk import commit. Default approver Owner, configurable per action; no self-approval except a flagged Owner exception; 72 h expiry counts as rejected.
- Acceptance criteria: Pass: Listed actions enter the queue; approve and reject are audited; requests expire at 72 h. Rejecting case: A requester cannot approve their own request (except the flagged Owner exception). Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0128.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-026 Adjust stock with authorization

- Register task: P-0152  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q39
- Estimate: 2 days (3 with buffer)  |  Planned 04 Jan 2027 to 06 Jan 2027  |  Depends on: WI-025
- Scope: Stock adjustment needs a second user when value at cost is Rs 10,000 or more, or quantity is 10% or more of on-hand (both configurable per company), using the approval queue.
- Acceptance criteria: Pass: An adjustment over threshold needs a second user's approval. Rejecting case: The same user approving is rejected. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0152.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-027 Credit limit breach during bulk invoice: owner sends temporary one-time authorization token

- Register task: X-0702  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q40
- Estimate: 3 days (4 with buffer)  |  Planned 04 Jan 2027 to 07 Jan 2027  |  Depends on: WI-025
- Scope: In-app single-use 15-minute token bound to the invoice batch and requester (WhatsApp only when the freeze flag is flipped). No response: over-limit invoices stay Awaiting approval, others proceed, expiry counts as rejected, never auto-approved.
- Acceptance criteria: Pass: A single-use 15-minute token releases the over-limit invoices. Rejecting case: A reused or expired token fails; no response leaves the invoice held, never approved. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0702.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-028 Sub-200ms POS billing checkout latency under continuous queue load

- Register task: R-0636  |  Workstream: Inventory & POS  |  Layer: Backend  |  Kind: perf  |  Owner: Agent 1  |  Decisions: Q41
- Estimate: 2 days (3 with buffer)  |  Planned 07 Jan 2027 to 11 Jan 2027  |  Depends on: none
- Scope: Benchmark harness and recorded baseline for POS checkout complete (tax, stock and ledger included): 2 vCPU 4 GB container, local Postgres, 20,000 SKUs, 3-line cart, p95. Runs on its own nightly job, never in the pull-request run.
- Acceptance criteria: Pass: Harness produces a repeatable p95 on the stated hardware and catalogue and records the baseline. Rejecting case: A run that regresses more than 15% against the baseline fails the nightly job (not the pull-request run). Done means: the benchmark job (outside the pull-request run) records the p95 against baseline and target and the report is attached as evidence; the reviewer signs.
- Planned test file: `backend/perf/test_r_0636_benchmark.py (nightly job)`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-029 Update transport vehicle number / Transporter ID on active E-Way Bill during breakdown

- Register task: X-0514  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q42
- Estimate: 2 days (3 with buffer)  |  Planned 08 Jan 2027 to 12 Jan 2027  |  Depends on: none
- Scope: Part B vehicle update as a stub action against the GSP adapter interface with a fake provider, plus stored vehicle history, behind GSP_LIVE_ENABLED=0. Live use needs sandbox credentials and a freeze exception.
- Acceptance criteria: Pass: Part B update stored with history; stub action works against the fake provider. Rejecting case: Update on a cancelled or expired bill is refused. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0514.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-030 Extend E-Way Bill validity before expiry due to transit delay or traffic accident

- Register task: X-0515  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Cut line rank: 2  |  Decisions: Q42
- Estimate: 2 days (3 with buffer)  |  Planned 14 Jan 2027 to 18 Jan 2027  |  Depends on: WI-029
- Scope: Validity extension as a stub action plus stored fields, same adapter and flag rule as X-0514.
- Acceptance criteria: Pass: Extension stored and allowed inside its window. Rejecting case: Extension outside the window is refused. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0515.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-031 E-Way Bill Part B vehicle update statutory time-limit and multi-vehicle consignment splitting

- Register task: C-0618  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Cut line rank: 1  |  Decisions: Q42
- Estimate: 2 days (3 with buffer)  |  Planned 14 Jan 2027 to 18 Jan 2027  |  Depends on: WI-029
- Scope: Part B time-limit alert and multi-vehicle split stored on the bill (stub action, GSP flag off).
- Acceptance criteria: Pass: Alert fires at the Part B limit; split stored. Rejecting case: Split quantities above the consignment are rejected. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0618.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-032 Rule 138 CGST Rules mandatory E-Way Bill distance calculation via postal PIN codes

- Register task: C-0606  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Cut line rank: 3  |  Decisions: Q42
- Estimate: 2 days (3 with buffer)  |  Planned 19 Jan 2027 to 21 Jan 2027  |  Depends on: none
- Scope: Validity computed from the user-entered distance using a configurable slab table with effective dates that the CA confirms. PIN-to-PIN distance lookup is deferred (needs NIC).
- Acceptance criteria: Pass: Validity from distance matches the slab table at the 100, 200 and 201 km boundaries. Rejecting case: Zero or negative distance is rejected. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_c_0606.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-071 CA sign-off of the Rule 11(g) coverage map

- Register task: none  |  Workstream: Audit & integrity  |  Layer: Process  |  Kind: external  |  Owner: CA / external  |  Decisions: Q7
- Estimate: 1 days (2 with buffer)  |  Planned 26 Oct 2026 to 30 Oct 2026  |  Depends on: WI-003, WI-070
- Scope: CA reviews the coverage map and certification export and signs. Lead time five working days.
- Acceptance criteria: Pass: Signed note from the CA attached as evidence. Rejecting case: No sign-off by M1: milestone marked 'pilot with documented residual'. Done means: written sign-off from the external reviewer is attached as evidence.
- Planned test file: none (process item)
- Stages:
  - [ ] Design
  - [x] Build (not applicable)
  - [x] Tests (not applicable)
  - [ ] Review
  - [x] Register sync (not applicable)
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-033 Concurrent customer edits: field merge plus version check

- Register task: none  |  Workstream: Audit & integrity  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q11, 43
- Estimate: 2 days (3 with buffer)  |  Planned 19 Jan 2027 to 21 Jan 2027  |  Depends on: none
- Scope: PATCH merges changed fields under a row lock so concurrent edits of different fields both persist; PUT requires a version and a stale write returns 409 with the current value. Create the register row when starting. Remove the strict xfail in test_register_race_gaps.py.
- Acceptance criteria: Pass: PATCH merges concurrent field edits and PUT with the current version succeeds. Rejecting case: A stale PUT returns 409 and changes nothing (the strict xfail test now passes). Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_register_race_gaps.py; backend/tests/test_plan_cust_lock.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-034 Production check and alert for the nightly audit-chain seal

- Register task: S-0579  |  Workstream: Platform & reliability  |  Layer: Infra  |  Kind: infra drill  |  Owner: Agent 1  |  Decisions: Q21
- Estimate: 0.5 days (1 with buffer)  |  Planned 22 Jan 2027 to 22 Jan 2027  |  Depends on: none
- Scope: The seal task is already on the Celery beat at 02:40. A verify failure only logs an error (Sentry if configured); nothing notices a night that never ran, and there is no seal email. Add a missed-run check that logs an error and sends the Owner the same in-app notification the nightly invariant task already uses.
- Acceptance criteria: Pass: A missed night logs an error and creates an in-app notification for the Owner. Rejecting case: Disabling the scheduled task in a test makes that alert fire; a successful seal does not. Done means: the drill is executed on a non-production copy and its timings and steps are attached; the reviewer signs.
- Planned test file: `drill log in qos/evidence/ (restore or alert drill)`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-028b Optimise POS checkout toward the 200 ms p95 target

- Register task: none  |  Workstream: Inventory & POS  |  Layer: Backend  |  Kind: perf  |  Owner: Agent 2  |  Cut line rank: 9  |  Decisions: Q17, 41
- Estimate: 5 days (6 with buffer)  |  Planned 22 Jan 2027 to 01 Feb 2027  |  Depends on: WI-028
- Scope: Timeboxed to 5 days after the baseline from R-0636: profile, fix the top costs, record the new p95. If the target is not met the remaining gap is reported, not hidden.
- Acceptance criteria: Pass: p95 at or below 200 ms, or the remaining gap and its causes are reported. Rejecting case: A change that worsens p95 against the new baseline is rejected by the nightly job. Done means: the benchmark job (outside the pull-request run) records the p95 against baseline and target and the report is attached as evidence; the reviewer signs.
- Planned test file: `backend/perf/test_r_0636b_benchmark.py (nightly job)`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-035 Wave 1 verification: full suite on Postgres, register sync, drift check, MVP gate review

- Register task: none  |  Workstream: Quality gate  |  Layer: Process  |  Kind: gate  |  Owner: Agent 1
- Estimate: 2 days (3 with buffer)  |  Planned 03 Feb 2027 to 05 Feb 2027  |  Depends on: WI-068, WI-069, WI-070, WI-001, WI-002, WI-003, WI-004, WI-005, WI-006, WI-007, WI-008, WI-009, WI-010, WI-011, WI-012, WI-013, WI-014, WI-015, WI-016, WI-017, WI-018, WI-019, WI-020, WI-021, WI-022, WI-023, WI-024, WI-025, WI-026, WI-027, WI-028, WI-029, WI-030, WI-031, WI-032, WI-071, WI-033, WI-034, WI-028b
- Scope: Run the full backend suite on Postgres, register_sync.py and register_drift.py, recalculate the workbook and review every wave item against its pass condition.
- Acceptance criteria: Pass: Run the full backend suite on Postgres, register_sync.py and register_drift.py, recalculate the workbook and review every wave item against its pass condition.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: full backend suite green on Postgres, register_sync.py and register_drift.py clean, workbook recalculated with 0 formula errors, every item in the wave Done and reviewed.
- Planned test file: none (process item)
- Stages:
  - [x] Design (not applicable)
  - [x] Build (not applicable)
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____


## Wave 2: Pilot gate

| WI | Task | Work item | Workstream | Owner | Est. | Start | Due | Depends on |
|---|---|---|---|---|---|---|---|---|
| WI-036 | P-0046 | Search medicines while billing | Inventory & POS | Agent 1 | 2 | 09 Feb 2027 | 11 Feb 2027 | WI-035 |
| WI-037 | P-0052 | Create bulk sales invoices | Inventory & POS | Agent 2 | 4 | 09 Feb 2027 | 15 Feb 2027 | WI-035 |
| WI-038 | P-0081 | Transfer stock between godowns | Inventory & POS | Agent 1 | 6 | 12 Feb 2027 | 23 Feb 2027 | WI-035 |
| WI-039 | P-0089 | View all shops from one dashboard | Inventory & POS | Agent 2 | 5 | 16 Feb 2027 | 23 Feb 2027 | WI-035 |
| WI-040 | P-0119 | Identify overdue payments | Payments & credit | Agent 1 | 3 | 24 Feb 2027 | 01 Mar 2027 | WI-035 |
| WI-041 | P-0180 | Configure branches/godowns | Inventory & POS | Agent 2 | 2 | 24 Feb 2027 | 26 Feb 2027 | WI-035 |
| WI-042 | X-0706 | Inter-godown transfer vehicle breakdown: goods transshipped to new tempo with E-Way Bill Part B update | GST & compliance | Agent 2 | 3 | 01 Mar 2027 | 04 Mar 2027 | WI-029, WI-038, WI-035 |
| WI-043 | UX-0596 | Clear destructive action confirmation dialog with explicit entity name typing | Inventory & POS | Agent 1 | 1 | 02 Mar 2027 | 03 Mar 2027 | WI-068, WI-035 |
| WI-044 | I-0651 | ESC/POS thermal receipt printer direct driver integration via USB, Bluetooth & Network | Inventory & POS | Agent 1 | 6 | 04 Mar 2027 | 15 Mar 2027 | WI-068, WI-035 |
| WI-045 | I-0655 | Barcode scanner HID USB wedge and 2D QR camera barcode reader | Inventory & POS | Agent 2 | 2 | 05 Mar 2027 | 09 Mar 2027 | WI-068, WI-035 |
| WI-046 | SaaS-0669 | Automated recurring subscription billing and GST tax invoice generation via Razorpay Subscriptions | Growth & SaaS | Agent 2 | 5 | 10 Mar 2027 | 17 Mar 2027 | WI-035 |
| WI-047 | GOS-0721 | End-to-end test: inbound lead de-duplication | Growth & SaaS | Agent 1 | 1 | 16 Mar 2027 | 17 Mar 2027 | WI-035 |
| WI-048 | GOS-0737 | End-to-end test: complaint to credit note, return or replacement | Growth & SaaS | Agent 1 | 1 | 18 Mar 2027 | 19 Mar 2027 | WI-035 |
| WI-049 | GOS-0739 | End-to-end test: supplier complaint to purchase debit note | Growth & SaaS | Agent 2 | 1 | 18 Mar 2027 | 19 Mar 2027 | WI-035 |
| WI-050 | SaaS-0666 | End-to-end and load test of tenant signup and provisioning | Growth & SaaS | Agent 1 | 3 | 22 Mar 2027 | 25 Mar 2027 | WI-035 |
| WI-051 | S-0562 | Release orphaned stock allocations on expired cart sessions | Inventory & POS | Agent 2 | 2 | 22 Mar 2027 | 24 Mar 2027 | WI-035 |
| WI-052 | UX-0581 | Keyboard-only POS navigation | Inventory & POS | Agent 2 | 3 | 25 Mar 2027 | 30 Mar 2027 | WI-068, WI-035 |
| WI-053 | UX-0582 | Multi-cart hold and recall at POS | Inventory & POS | Agent 1 | 3 | 26 Mar 2027 | 31 Mar 2027 | WI-051, WI-068, WI-035 |
| WI-054 | UX-0586 | Ctrl+K omnibar | Inventory & POS | Agent 2 | 2 | 31 Mar 2027 | 02 Apr 2027 | WI-068, WI-035 |
| WI-055 | UX-0588 | Warehouse rack locator badge | Inventory & POS | Agent 1 | 2 | 01 Apr 2027 | 05 Apr 2027 | WI-068, WI-035 |
| WI-056 | UX-0590 | Bulk import progress bar with time remaining | Inventory & POS | Agent 2 | 2 | 05 Apr 2027 | 07 Apr 2027 | WI-068, WI-035 |
| WI-057 | UX-0591 | Privacy mask for rupee figures | Inventory & POS | Agent 1 | 1 | 06 Apr 2027 | 07 Apr 2027 | WI-068, WI-035 |
| WI-058 |  | Wave 2 verification: full suite on Postgres, register sync, drift check, Pilot gate review | Quality gate | Agent 1 | 2 | 09 Apr 2027 | 13 Apr 2027 | WI-036, WI-037, WI-038, WI-039, WI-040, WI-041, WI-042, WI-043, WI-044, WI-045, WI-046, WI-047, WI-048, WI-049, WI-050, WI-051, WI-052, WI-053, WI-054, WI-055, WI-056, WI-057 |

### Wave 2 item detail

#### WI-036 Search medicines while billing

- Register task: P-0046  |  Workstream: Inventory & POS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q44
- Estimate: 2 days (3 with buffer)  |  Planned 09 Feb 2027 to 11 Feb 2027  |  Depends on: WI-035
- Scope: Optional salt, composition and manufacturer fields on products, searchable at billing with a trigram index inside the checkout latency budget (query-budget test).
- Acceptance criteria: Pass: Optional salt, composition and manufacturer fields on products, searchable at billing with a trigram index inside the checkout latency budget (query-budget test).. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0046.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-037 Create bulk sales invoices

- Register task: P-0052  |  Workstream: Inventory & POS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q45
- Estimate: 4 days (5 with buffer)  |  Planned 09 Feb 2027 to 15 Feb 2027  |  Depends on: WI-035
- Scope: CSV with invoice ref, customer, dates, SKU or barcode, quantity, rate, discount %, warehouse, notes; dry run, then per-invoice atomic commit; any bad row rejects that invoice and is reported by row; 2,000-row cap; file hash makes re-upload idempotent.
- Acceptance criteria: Pass: CSV with invoice ref, customer, dates, SKU or barcode, quantity, rate, discount %, warehouse, notes; dry run, then per-invoice atomic commit; any bad row rejects that invoice and is reported by row; 2,000-row cap; file hash makes re-upload idempotent.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0052.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-038 Transfer stock between godowns

- Register task: P-0081  |  Workstream: Inventory & POS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q46
- Estimate: 6 days (8 with buffer)  |  Planned 12 Feb 2027 to 23 Feb 2027  |  Depends on: WI-035
- Scope: In-transit location per transfer: dispatch moves source to in-transit, receipt moves it to destination; partial receipt with shortage or damage reason; no ledger entry for same-company, same-GSTIN transfers.
- Acceptance criteria: Pass: In-transit location per transfer: dispatch moves source to in-transit, receipt moves it to destination; partial receipt with shortage or damage reason; no ledger entry for same-company, same-GSTIN transfers.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0081.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-039 View all shops from one dashboard

- Register task: P-0089  |  Workstream: Inventory & POS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q47
- Estimate: 5 days (6 with buffer)  |  Planned 16 Feb 2027 to 23 Feb 2027  |  Depends on: WI-035
- Scope: Per-warehouse breakdown and switching inside one company on the dashboard, inside the dashboard query budget (test). Multi-company GSTIN stays out of scope.
- Acceptance criteria: Pass: Per-warehouse breakdown and switching inside one company on the dashboard, inside the dashboard query budget (test). Multi-company GSTIN stays out of scope.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0089.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-040 Identify overdue payments

- Register task: P-0119  |  Workstream: Payments & credit  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q48
- Estimate: 3 days (4 with buffer)  |  Planned 24 Feb 2027 to 01 Mar 2027  |  Depends on: WI-035
- Scope: Report only: interest exposure (default 18% a year simple, per company) and suggested provision by age (0-60 d 0%, 61-90 d 5%, 91-180 d 25%, 181-365 d 50%, over 365 d 100%). No posting.
- Acceptance criteria: Pass: Report only: interest exposure (default 18% a year simple, per company) and suggested provision by age (0-60 d 0%, 61-90 d 5%, 91-180 d 25%, 181-365 d 50%, over 365 d 100%). No posting.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0119.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-041 Configure branches/godowns

- Register task: P-0180  |  Workstream: Inventory & POS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q49
- Estimate: 2 days (3 with buffer)  |  Planned 24 Feb 2027 to 26 Feb 2027  |  Depends on: WI-035
- Scope: Users map to many warehouses with one default; contact person and phone required, email optional.
- Acceptance criteria: Pass: Users map to many warehouses with one default; contact person and phone required, email optional.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_p_0180.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-042 Inter-godown transfer vehicle breakdown: goods transshipped to new tempo with E-Way Bill Part B update

- Register task: X-0706  |  Workstream: GST & compliance  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q42
- Estimate: 3 days (4 with buffer)  |  Planned 01 Mar 2027 to 04 Mar 2027  |  Depends on: WI-029, WI-038, WI-035
- Scope: Transfer vehicle-breakdown Part B workflow on stock transfers as a stub action plus stored fields (GSP flag off).
- Acceptance criteria: Pass: Transfer Part B update stored. Rejecting case: Update on a completed transfer is refused. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_x_0706.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-043 Clear destructive action confirmation dialog with explicit entity name typing

- Register task: UX-0596  |  Workstream: Inventory & POS  |  Layer: Web  |  Kind: web  |  Owner: Agent 1  |  Decisions: Q9
- Estimate: 1 days (2 with buffer)  |  Planned 02 Mar 2027 to 03 Mar 2027  |  Depends on: WI-068, WI-035
- Scope: Typed-confirmation input on destructive dialogs.
- Acceptance criteria: Pass: The destructive button stays disabled until the exact text is typed. Rejecting case: A wrong or partial text keeps it disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/ux_0596.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-044 ESC/POS thermal receipt printer direct driver integration via USB, Bluetooth & Network

- Register task: I-0651  |  Workstream: Inventory & POS  |  Layer: Web + device  |  Kind: web  |  Owner: Agent 1  |  Decisions: Q50
- Estimate: 6 days (8 with buffer)  |  Planned 04 Mar 2027 to 15 Mar 2027  |  Depends on: WI-068, WI-035
- Scope: Network ESC/POS printer through a print bridge, with PDF fallback. Bluetooth deferred. Verified on a real network ESC/POS printer (for example Epson TM-T82) that you provide.
- Acceptance criteria: Pass: Network ESC/POS printer through a print bridge, with PDF fallback. Bluetooth deferred. Verified on a real network ESC/POS printer (for example Epson TM-T82) that you provide.. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/i_0651.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-045 Barcode scanner HID USB wedge and 2D QR camera barcode reader

- Register task: I-0655  |  Workstream: Inventory & POS  |  Layer: Web + device  |  Kind: web  |  Owner: Agent 2  |  Decisions: Q50
- Estimate: 2 days (3 with buffer)  |  Planned 05 Mar 2027 to 09 Mar 2027  |  Depends on: WI-068, WI-035
- Scope: USB keyboard-wedge timing heuristic. Browser camera scanner deferred (mobile camera scan already works).
- Acceptance criteria: Pass: USB keyboard-wedge timing heuristic. Browser camera scanner deferred (mobile camera scan already works).. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/i_0655.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-046 Automated recurring subscription billing and GST tax invoice generation via Razorpay Subscriptions

- Register task: SaaS-0669  |  Workstream: Growth & SaaS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q51
- Estimate: 5 days (6 with buffer)  |  Planned 10 Mar 2027 to 17 Mar 2027  |  Depends on: WI-035
- Scope: Bizboard's own GST invoice to the tenant (our GSTIN, place of supply from the tenant's state), generated and emailed when a Cashfree or PayU payment is captured (freeze D3: sandbox, at least one of those two). No gateway SDK inside the invoice generator. Leave the existing Razorpay subscription reconciliation task alone.
- Acceptance criteria: Pass: A captured Cashfree or PayU payment produces one GST invoice to the tenant and emails it. Rejecting case: A second delivery of the same capture does not create a second invoice; Razorpay reconciliation is unchanged. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_saas_0669.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-047 End-to-end test: inbound lead de-duplication

- Register task: GOS-0721  |  Workstream: Growth & SaaS  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q52
- Estimate: 1 days (2 with buffer)  |  Planned 16 Mar 2027 to 17 Mar 2027  |  Depends on: WI-035
- Scope: End-to-end test through the API; fixing a failing flow is in scope up to one day.
- Acceptance criteria: Pass: End-to-end test through the API; fixing a failing flow is in scope up to one day.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_gos_0721.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-048 End-to-end test: complaint to credit note, return or replacement

- Register task: GOS-0737  |  Workstream: Growth & SaaS  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q52
- Estimate: 1 days (2 with buffer)  |  Planned 18 Mar 2027 to 19 Mar 2027  |  Depends on: WI-035
- Scope: End-to-end test with stock and ledger check; credit note created exactly once.
- Acceptance criteria: Pass: End-to-end test with stock and ledger check; credit note created exactly once.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_gos_0737.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-049 End-to-end test: supplier complaint to purchase debit note

- Register task: GOS-0739  |  Workstream: Growth & SaaS  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q52
- Estimate: 1 days (2 with buffer)  |  Planned 18 Mar 2027 to 19 Mar 2027  |  Depends on: WI-035
- Scope: End-to-end test with stock and ledger check.
- Acceptance criteria: Pass: End-to-end test with stock and ledger check.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_gos_0739.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-050 End-to-end and load test of tenant signup and provisioning

- Register task: SaaS-0666  |  Workstream: Growth & SaaS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q53
- Estimate: 3 days (4 with buffer)  |  Planned 22 Mar 2027 to 25 Mar 2027  |  Depends on: WI-035
- Scope: Signup to workspace end to end; load test of 20 concurrent out of 50 signups, p95 provisioning at most 10 s, no duplicate tenants; nightly or manual, not in the pull-request run.
- Acceptance criteria: Pass: Signup to workspace end to end; load test of 20 concurrent out of 50 signups, p95 provisioning at most 10 s, no duplicate tenants; nightly or manual, not in the pull-request run.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_saas_0666.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-051 Release orphaned stock allocations on expired cart sessions

- Register task: S-0562  |  Workstream: Inventory & POS  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q54
- Estimate: 2 days (3 with buffer)  |  Planned 22 Mar 2027 to 24 Mar 2027  |  Depends on: WI-035
- Scope: No cart session or timeout exists. POS drafts are device-local and do not reserve stock. Add a company-configurable expiry (default 24 hours, confirm before starting) on confirmed sales-order reservations and on POS holds from UX-0582: release the allocation and mark the hold expired, keeping the row.
- Acceptance criteria: Pass: A reservation older than the company TTL releases its stock and is marked expired, and the row remains. Rejecting case: A reservation inside the TTL is left allocated; an expired hold does not delete the order or cart. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_s_0562.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-052 Keyboard-only POS navigation

- Register task: UX-0581  |  Workstream: Inventory & POS  |  Layer: Web  |  Kind: web  |  Owner: Agent 2  |  Decisions: Q9
- Estimate: 3 days (4 with buffer)  |  Planned 25 Mar 2027 to 30 Mar 2027  |  Depends on: WI-068, WI-035
- Scope: Complete keyboard navigation of the POS flow.
- Acceptance criteria: Pass: Complete keyboard navigation of the POS flow.. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/ux_0581.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-053 Multi-cart hold and recall at POS

- Register task: UX-0582  |  Workstream: Inventory & POS  |  Layer: Web  |  Kind: web  |  Owner: Agent 1  |  Decisions: Q55
- Estimate: 3 days (4 with buffer)  |  Planned 26 Mar 2027 to 31 Mar 2027  |  Depends on: WI-051, WI-068, WI-035
- Scope: Hold and recall several carts without losing stock reservations. Reservations use the expiry job from S-0562.
- Acceptance criteria: Pass: Hold and recall several carts without losing stock reservations. Reservations use the expiry job from S-0562.. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/ux_0582.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-054 Ctrl+K omnibar

- Register task: UX-0586  |  Workstream: Inventory & POS  |  Layer: Web  |  Kind: web  |  Owner: Agent 2
- Estimate: 2 days (3 with buffer)  |  Planned 31 Mar 2027 to 02 Apr 2027  |  Depends on: WI-068, WI-035
- Scope: Global command palette with search and actions.
- Acceptance criteria: Pass: Global command palette with search and actions.. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/ux_0586.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-055 Warehouse rack locator badge

- Register task: UX-0588  |  Workstream: Inventory & POS  |  Layer: Web  |  Kind: web  |  Owner: Agent 1
- Estimate: 2 days (3 with buffer)  |  Planned 01 Apr 2027 to 05 Apr 2027  |  Depends on: WI-068, WI-035
- Scope: Rack or bin location on stock and picking views.
- Acceptance criteria: Pass: Rack or bin location on stock and picking views.. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/ux_0588.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-056 Bulk import progress bar with time remaining

- Register task: UX-0590  |  Workstream: Inventory & POS  |  Layer: Web  |  Kind: web  |  Owner: Agent 2
- Estimate: 2 days (3 with buffer)  |  Planned 05 Apr 2027 to 07 Apr 2027  |  Depends on: WI-068, WI-035
- Scope: Progress and ETA for long imports.
- Acceptance criteria: Pass: Progress and ETA for long imports.. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/ux_0590.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-057 Privacy mask for rupee figures

- Register task: UX-0591  |  Workstream: Inventory & POS  |  Layer: Web  |  Kind: web  |  Owner: Agent 1  |  Decisions: Q56
- Estimate: 1 days (2 with buffer)  |  Planned 06 Apr 2027 to 07 Apr 2027  |  Depends on: WI-068, WI-035
- Scope: Personal on-screen toggle, separate from role masking; not a security control.
- Acceptance criteria: Pass: Personal on-screen toggle, separate from role masking; not a security control.. Rejecting case: invalid input keeps the action disabled; keyboard and screen-reader path tested. Done means: Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs.
- Planned test file: `web/src/__tests__/ux_0591.test.tsx`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-058 Wave 2 verification: full suite on Postgres, register sync, drift check, Pilot gate review

- Register task: none  |  Workstream: Quality gate  |  Layer: Process  |  Kind: gate  |  Owner: Agent 1
- Estimate: 2 days (3 with buffer)  |  Planned 09 Apr 2027 to 13 Apr 2027  |  Depends on: WI-036, WI-037, WI-038, WI-039, WI-040, WI-041, WI-042, WI-043, WI-044, WI-045, WI-046, WI-047, WI-048, WI-049, WI-050, WI-051, WI-052, WI-053, WI-054, WI-055, WI-056, WI-057
- Scope: Run the full backend suite on Postgres, register_sync.py and register_drift.py, recalculate the workbook and review every wave item against its pass condition.
- Acceptance criteria: Pass: Run the full backend suite on Postgres, register_sync.py and register_drift.py, recalculate the workbook and review every wave item against its pass condition.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: full backend suite green on Postgres, register_sync.py and register_drift.py clean, workbook recalculated with 0 formula errors, every item in the wave Done and reviewed.
- Planned test file: none (process item)
- Stages:
  - [x] Design (not applicable)
  - [x] Build (not applicable)
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____


## Wave 3: Later gate

| WI | Task | Work item | Workstream | Owner | Est. | Start | Due | Depends on |
|---|---|---|---|---|---|---|---|---|
| WI-059 | D-0684 | Predictive cash-flow simulation engine modeling actual debtor payment delay probabilities | Growth & SaaS | Agent 1 | 10 | 15 Apr 2027 | 30 Apr 2027 | WI-058 |
| WI-060 | D-0690 | Automated GSTR-2B 'Smart Reconciler' with fuzzy name and fractional rounding matching | Growth & SaaS | Agent 2 | 6 | 15 Apr 2027 | 26 Apr 2027 | WI-019, WI-058 |
| WI-061 | D-0693 | One-click complete Tally historical backup migration wizard | Growth & SaaS | Agent 2 | 25 | 27 Apr 2027 | 07 Jun 2027 | WI-058 |
| WI-064 | S-0574 | Anomaly detector for unusual discounts and bill amounts | Platform & reliability | Agent 1 | 8 | 03 May 2027 | 14 May 2027 | WI-058 |
| WI-067 |  | Wave 3 verification: full suite on Postgres, register sync, drift check, Later gate review | Quality gate | Agent 1 | 2 | 09 Jun 2027 | 11 Jun 2027 | WI-059, WI-060, WI-061, WI-064 |

### Wave 3 item detail

#### WI-059 Predictive cash-flow simulation engine modeling actual debtor payment delay probabilities

- Register task: D-0684  |  Workstream: Growth & SaaS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q57
- Estimate: 10 days (12 with buffer)  |  Planned 15 Apr 2027 to 30 Apr 2027  |  Depends on: WI-058
- Scope: Per-debtor bootstrap of days-late from the last 12 settled invoices, shrunk to the segment average, 1,000 runs, show p10/p50/p90; under 5 settled invoices fall back to the ageing heuristic with a low-confidence badge.
- Acceptance criteria: Pass: Per-debtor bootstrap of days-late from the last 12 settled invoices, shrunk to the segment average, 1,000 runs, show p10/p50/p90; under 5 settled invoices fall back to the ageing heuristic with a low-confidence badge.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_d_0684.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-060 Automated GSTR-2B 'Smart Reconciler' with fuzzy name and fractional rounding matching

- Register task: D-0690  |  Workstream: Growth & SaaS  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q58
- Estimate: 6 days (8 with buffer)  |  Planned 15 Apr 2027 to 26 Apr 2027  |  Depends on: WI-019, WI-058
- Scope: Score at least 0.95 with equal GSTIN and tax within tolerance links automatically; 0.80 to 0.95 suggests; below 0.80 shows nothing. Runs on uploaded 2B data after P-0503.
- Acceptance criteria: Pass: Score at least 0.95 with equal GSTIN and tax within tolerance links automatically; 0.80 to 0.95 suggests; below 0.80 shows nothing. Runs on uploaded 2B data after P-0503.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_d_0690.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-061 One-click complete Tally historical backup migration wizard

- Register task: D-0693  |  Workstream: Growth & SaaS  |  Layer: Full stack  |  Kind: feature  |  Owner: Agent 2  |  Decisions: Q59
- Estimate: 25 days (30 with buffer)  |  Planned 27 Apr 2027 to 07 Jun 2027  |  Depends on: WI-058
- Scope: TallyPrime only: ledger masters, stock items, opening balances and one financial year of vouchers with a mandatory ledger and stock-item mapping step. ENABLE_TALLY stays off; flipping it is a separate freeze exception.
- Acceptance criteria: Pass: TallyPrime only: ledger masters, stock items, opening balances and one financial year of vouchers with a mandatory ledger and stock-item mapping step. ENABLE_TALLY stays off; flipping it is a separate freeze exception.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_d_0693.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-064 Anomaly detector for unusual discounts and bill amounts

- Register task: S-0574  |  Workstream: Platform & reliability  |  Layer: Backend  |  Kind: feature  |  Owner: Agent 1  |  Decisions: Q61
- Estimate: 8 days (10 with buffer)  |  Planned 03 May 2027 to 14 May 2027  |  Depends on: WI-058
- Scope: Review queue only, never blocks a bill. Unusual: discount above 3 times the item's median discount, or a bill above both a rupee floor and 3 times the customer's median bill; thresholds per company.
- Acceptance criteria: Pass: Review queue only, never blocks a bill. Unusual: discount above 3 times the item's median discount, or a bill above both a rupee floor and 3 times the customer's median bill; thresholds per company.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate.
- Planned test file: `backend/tests/test_plan_s_0574.py`
- Stages:
  - [ ] Design
  - [ ] Build
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

#### WI-067 Wave 3 verification: full suite on Postgres, register sync, drift check, Later gate review

- Register task: none  |  Workstream: Quality gate  |  Layer: Process  |  Kind: gate  |  Owner: Agent 1
- Estimate: 2 days (3 with buffer)  |  Planned 09 Jun 2027 to 11 Jun 2027  |  Depends on: WI-059, WI-060, WI-061, WI-064
- Scope: Run the full backend suite on Postgres, register_sync.py and register_drift.py, recalculate the workbook and review every wave item against its pass condition.
- Acceptance criteria: Pass: Run the full backend suite on Postgres, register_sync.py and register_drift.py, recalculate the workbook and review every wave item against its pass condition.. Rejecting case: invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test. Done means: full backend suite green on Postgres, register_sync.py and register_drift.py clean, workbook recalculated with 0 formula errors, every item in the wave Done and reviewed.
- Planned test file: none (process item)
- Stages:
  - [x] Design (not applicable)
  - [x] Build (not applicable)
  - [ ] Tests
  - [ ] Review
  - [ ] Register sync
- Tracking: actual start ____  actual done ____  PR ____  evidence ____

