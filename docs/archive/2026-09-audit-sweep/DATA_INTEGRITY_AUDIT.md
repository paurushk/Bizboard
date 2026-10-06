# Data Integrity Audit

**Date:** 28 September 2026  
**Scope:** State transitions, money documents, and concurrency on insurance, projects, renewals, referrals, complaints, and contract status.

RLS coverage migrations exist for the new tables (`core/migrations/0035`, `0038`, `0039`). They do not help a worker that never sets `app.company_id` (DR-001 in `ARCHITECTURE_AUDIT.md`).

---

### DR-002

| Field | Description |
| --- | --- |
| ID | DR-002 |
| Severity | P1 |
| Category | Data |
| Location | `backend/insurance/services.py` `issue_policy` lines 55–92; `choose_option` lines 45–52 |
| Problem | Issuing is idempotent only for the option that was already issued (`option.policies.exists()`). `choose_option` flips `chosen` onto another option and does not cancel or block the policy already issued from this option set. A second `issue_policy` on the newly chosen option inserts another `IN_FORCE` policy, another policy number, and another premium snapshot. |
| Root Cause | The uniqueness check is `Policy.option`, not `PolicyOptionSet` or `Lead`. Nothing in the schema says one option set yields at most one policy. |
| User Impact | One prospect is covered twice. Commission can be opened on both. Renewal diary later emits two leads. The insurer-facing number series consumes two `POL` numbers for one sale. |
| Reproduction | Create two policy products and an option set. Choose option A, issue a policy. Choose option B, issue again. Two `Policy` rows, both `IN_FORCE`, same lead. The insurance page keeps the Issue button enabled after the first success, so the second issue is a normal click after Choose on the other product. |
| Recommended Fix | Inside the existing `select_for_update` on the option, also lock the option set and reject when any option in that set already has a non-cancelled policy. Unique partial constraint on the lead or option set for `status=IN_FORCE` if the product rule is one live policy per prospect. |
| Regression Risk | A legitimate second policy for the same customer on a *different* option set (renewal, second line of business) must still be allowed. Key the guard to the option set, not the customer. |

---

### DR-003

| Field | Description |
| --- | --- |
| ID | DR-003 |
| Severity | P1 |
| Category | Data |
| Location | `backend/insurance/services.py` `renewal_diary` lines 153–168 |
| Problem | “Already created” is `Lead.objects.filter(company, campaign=policy.campaign, name=policy.customer.name, message__startswith=f"Renewal {policy.number}")`. The policy number in the prefix means two customers who merely share a name do not suppress each other. The match is still not a foreign key to `Policy`. Two overlapping requests both see `exists() == False` and insert two leads. After a customer rename, or after anyone edits that message, the next run inserts another lead. A hand-written lead whose message starts with `Renewal {number}` suppresses the real one, including when `policy.campaign` is null and the filter is `campaign=None`. |
| Root Cause | Dedup was written as a human-readable string match. `@transaction.atomic` around the loop does not stop two requests from both passing `exists()` before either inserts. There is no unique constraint. |
| User Impact | Advisors get duplicate renewal work, or a renewal disappears after a name or message change. Campaigns and referral attribution hang off those leads. |
| Reproduction | Issue a policy with `end_date` inside the diary window. POST the renewal diary twice in parallel. Expect one lead; observe two. Rename the customer and POST again. Another lead appears for the same policy number. |
| Recommended Fix | Store the source policy on the generated lead (or a small join row) with `UniqueConstraint` on `(company, policy)` for system-generated renewals. Insert under that constraint and treat `IntegrityError` as “already created”. |
| Regression Risk | Existing name-matched leads will not satisfy the new key, so the first run after deploy may create one catch-up lead per in-window policy. Do that once, on purpose. |

---

### DR-004

| Field | Description |
| --- | --- |
| ID | DR-004 |
| Severity | P1 |
| Category | Logic |
| Location | `backend/insurance/services.py` `issue_policy` line 69 |
| Problem | `end_date = start_date + timedelta(days=int(product.tenure_months) * 30)`. Twelve months becomes 360 days. A policy from 2026-01-01 ends 2026-12-27. Leap years and calendar months are ignored. `tenure_months` is the product field advisors set in the UI (the screen hard-codes 12). |
| Root Cause | Month length was approximated as 30 to avoid `dateutil`. Renewal diary and any cover check use `end_date`, so the error compounds. |
| User Impact | Cover ends about five days early on an annual policy (more on longer tenures: 24 months is 720 days, not two years). Renewal leads fire early. A claim on the missing days is opened against a policy the desk thinks is still in force only if nobody stored the short date — the stored date is the short one, so the desk thinks cover has ended while the customer was sold “12 months”. |
| Reproduction | Product `tenure_months=12`, `start_date=2026-01-01`. Issued policy `end_date` is 2026-12-27. Anniversary would be 2027-01-01 (or 2026-12-31, if the product rule is inclusive one year minus a day). Neither matches. |
| Recommended Fix | Add calendar months (`start_date`’s day clamped to the target month), or store an explicit `end_date` from the adviser. Do not multiply by 30. Backfill is a data migration: recompute only rows whose end date equals `start + 30*tenure` and that have not been endorsed. |
| Regression Risk | Recomputing existing rows moves renewal windows. Do it in a migration with a dry-run count, not silently on next read. |

---

### DR-005

| Field | Description |
| --- | --- |
| ID | DR-005 |
| Severity | P1 |
| Category | Data |
| Location | `backend/projects/services.py` `invoice_milestone` lines 61–92; `close_project` lines 94–103; `backend/projects/models.py` `ProjectMilestone.sales_invoice` lines 42–44 (`on_delete=PROTECT`) |
| Problem | The milestone is set to `INVOICED` and pointed at a **draft** `SalesInvoice`. `invoice_milestone` returns immediately whenever `sales_invoice_id` is set, including when that invoice is later `CANCELLED`. `close_project` only blocks `READY` milestones with a null FK. A draft or a cancelled draft counts as billed. `PROTECT` also means the draft cannot be deleted while the milestone points at it. |
| Root Cause | “Has an invoice row” was treated as “revenue was posted”. Completion, stock, GST, and receivables happen in `SalesService.complete`, which this path never calls. |
| User Impact | The project looks invoiced. Accounts receivable does not move. If the operator cancels the draft or leaves it, the milestone cannot be billed again. Closing the project succeeds and hides the ready-to-bill state. |
| Reproduction | Mark a milestone ready. POST `.../invoice/`. Observe milestone `INVOICED` and invoice `DRAFT` with no journal entry. Cancel that draft (or abandon it). POST invoice again. The same cancelled/draft id comes back. POST `.../close/`. Project becomes `CLOSED`. |
| Recommended Fix | Either complete the invoice inside the same transaction (and only then set `INVOICED`), or keep the milestone `READY` until the invoice transitions to `COMPLETED`, via the invoice completion signal. On cancel, clear `sales_invoice` and return the milestone to `READY` when no completed document exists. `close_project` should refuse milestones whose invoice is not `COMPLETED`. |
| Regression Risk | Auto-completing pulls GST Guard, credit limits, and period locks into the milestone action. Surfacing those 400s is required; swallowing them would leave the draft and the `INVOICED` flag half-applied. The current transaction rolls back only if `set_items` raises, not if the user never completes. |

---

### DR-007

| Field | Description |
| --- | --- |
| ID | DR-007 |
| Severity | P2 |
| Category | Data |
| Location | `backend/complaints/views.py` `_link_document` lines 71–105; `backend/complaints/services.py` `transition_status` lines 37–58 |
| Problem | Return, credit note, and replacement order are `serializer.save()` drafts. The complaint can still move `APPROVED → RESOLVED` with no check that the linked document was completed. Two complaints can link the same return; the code only adds a warning after the fact. Status transitions do not `select_for_update`, so two clerks can apply different transitions to a stale in-memory status. |
| Root Cause | Document creation was wired to the serializer create path, not the complete service. The state machine treats “a row exists” as resolution. |
| User Impact | A resolved complaint with a draft credit note leaves the customer’s balance unchanged. The report `resolved_with_document` counts that as financially closed. |
| Reproduction | Create a complaint, move it to INSPECTING, POST `create-credit-note` with items. Complaint stores the note id. Note status is DRAFT. POST transition `RESOLVED`. Customer outstanding is unchanged. |
| Recommended Fix | Resolve only when the linked return or credit note is completed, or complete the document in `_link_document` through the existing notes/return service. Lock the complaint row for transitions. |
| Regression Risk | Forcing completion at link time surfaces GST Guard and stock errors on the complaint screen. The UI must show those 400s. |

---

### DR-008

| Field | Description |
| --- | --- |
| ID | DR-008 |
| Severity | P2 |
| Category | Logic |
| Location | `backend/crm/referrals.py` `evaluate_referral_reward` lines 250–254 |
| Problem | Percent and flat rewards are quantized to `Decimal("1")` (whole rupees, half up). The rest of the ledger uses paise (`0.01`). A 2.5% reward on 1000.40 becomes 25 instead of 25.01, and any fractional rupee on a flat value is rounded away. |
| Root Cause | The quantize exponent is `1`, not `0.01`. |
| User Impact | Referrers are over- or under-paid by up to fifty paise per deal, and the reward row will not tie to a paise-accurate payout voucher later. |
| Reproduction | Code `reward_type=PERCENT`, `reward_value=2.5`, opportunity amount `1000.40`. Reward amount stored is `25`, not `25.01`. |
| Recommended Fix | Quantize to `Decimal("0.01")` with the same rounding mode the tax engine uses for rupee totals. |
| Regression Risk | Existing pending rewards keep the rounded figure unless backfilled. Do not recompute `PAID` rows. |

---

### DR-009

| Field | Description |
| --- | --- |
| ID | DR-009 |
| Severity | P2 |
| Category | Logic |
| Location | `backend/support/tickets.py` `transition_status` lines 75–93 |
| Problem | SLA pause is applied only when **leaving** `WAITING`: `sla_due_at += now - waiting_since`. While the ticket sits in `WAITING`, `sla_due_at` is still the original deadline. Anything that lists overdue tickets by `sla_due_at < now` counts customer-wait time as an agent breach. Reopening `CLOSED → IN_PROGRESS` clears `resolved_at` but does not start a new SLA clock, so a reopen is immediately overdue. |
| Root Cause | The pause is a retroactive patch on the timestamp instead of a clock that stops while `waiting_since` is set. |
| User Impact | Agents look in breach during a customer hold. Reopened tickets page as already missed. |
| Reproduction | Create a MEDIUM ticket (`sla_due_at = now+3d`). Move to WAITING. Advance the clock past `sla_due_at` without leaving WAITING. Overdue queries include it. Then move back to IN_PROGRESS and see `sla_due_at` jump forward by the wait. The in-waiting window was already counted. |
| Recommended Fix | Overdue reads should use `sla_due_at + (now - waiting_since)` when `waiting_since` is set. On reopen from RESOLVED/CLOSED, set a fresh `sla_due_at` from `SLA_OFFSETS`. |
| Regression Risk | Reports that already used the retroactive extension will shift historical breach counts if you rewrite past rows. Change the read formula; leave stored history. |

## Concurrency that is acceptable

`invoice_milestone`, `mark_ready`, `cancel_policy`, and `choose_option` lock the row with `select_for_update` inside `transaction.atomic`. Two invoice clicks on one milestone do not create two drafts. `choose_option` can deadlock if two options in one set are chosen at once (each locks its row, then updates the other). Postgres aborts one transaction. That is a 500 for one caller, not two chosen rows left true after commit. Severity stays inside DR-010 as an error-handling gap, not data corruption.
