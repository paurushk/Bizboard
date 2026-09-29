# Additional roadmap items — implementation plan

Build plans for the rows added in revision 2026-09-26b of
[BUSINESS_DNA_CONSOLIDATED.md](../BUSINESS_DNA_CONSOLIDATED.md): **INS-0**, **PRE-R1**
through **PRE-R5**, and **SAAS-6**.

INS-1 through INS-11 and SAAS-1 through SAAS-5 stay specified in that document.
They are not re-planned here. INS-4 still cannot start until INS-0 has a role
that can be granted.

**Review 2026-09-26.** The vendor-share insert must run inside `core.rls.rls_bypass()`. Every new `company` table is enrolled in RLS and named in `0020`'s `RLS_TABLES` list. `POLICY_DESK` is added by hand to `test_rbac_matrix.py`, which does not read `Role.choices`.

Grounded in the tree as of 26 Sep 2026: `accounts.models.CompanyUser.Role`,
`accounts/packs.py` (`HELD_PACKS`, `_entitled` refusing dark modules),
`core/services/feature_flags.py` (`DARK_MODULE_KEYS`), `core/viewsets.py`
(`CompanyScopedViewSet.get_queryset` filters `company=self.company`),
`sales.models.DeliveryRouteStop` (`pod_note`, `otp_code`, `delivered_at`),
`support.models.Ticket` (company-scoped, customer required),
`manufacturing/models.py` (BOM and work order, multiple ACTIVE BOMs allowed).

## What this plan will not do

- Turn on `ENABLE_CRM` or `ENABLE_MANUFACTURING` from a pack confirm.
- Add a Postgres policy that lets a vendor session `SELECT` every tenant's tickets.
- Post stock or GST from a job card or a proof-of-delivery slip. Money documents stay invoices and receipts.
- Build BOQ takeoff, retention, or RA bills.
- Choose a single ACTIVE BOM per product. That decision is already deferred in `manufacturing/models.py`.

## Order

| Phase | Tickets | Start gate |
|---|---|---|
| A. Guards | INS-0, PRE-R3, PRE-R5 | None. These lock the current rules in tests. |
| B. Documents that do not post the ledger | PRE-R2, PRE-R1 | Phase A merged. |
| C. Milestone billing, first slice | PRE-R4 | A named pilot that bills by milestone, not by repair visit. |
| D. Vendor ticket share | SAAS-6 | A named operator company that is the BizBoard vendor tenant. |

---

## Architecture decisions

### 1. New role, not a wider sales-staff grant

P12 issues policies and must not post GST. `SALES_STAFF` defaults `can_create_sales=True`, which is the wrong grant. Add `POLICY_DESK` with its own defaults. Do not reuse `ACCOUNTANT`.

### 2. Job card and POD are worksheets

`JobCard` converts into a sales invoice. `DeliveryRouteStop` gains a printable slip and an optional receipt link. Neither model calls `InventoryService` or journal posting. Stock and tax move only when the existing invoice or receipt complete path runs.

### 3. CRM and manufacturing stay dark

`packs._entitled` already returns false for `DARK_MODULE_KEYS`. PRE-R3 and PRE-R5 close when tests pin that, plus a short grant runbook. They do not add features.

### 4. Vendor support copies a redacted ticket

The copy is the one write that crosses companies. The session GUC is still the source company, and the row's `company_id` is the vendor company. That insert is legal only inside `rls_bypass()`. Decision 5 says how the new table gets a policy of its own.

`CompanyScopedViewSet` and row-level security keep a ticket inside its company. WF-28 asserts a cross-company read returns 404. SAAS-6 does not loosen that filter.

The tenant owner shares one ticket. A privileged service inserts a redacted row into the **vendor company**. Vendor staff (P10 logged into that company) read those rows with the normal company filter. They never query `support.Ticket` across companies.

Version 1 is read-only. A reply that writes back into the tenant ticket is a later ticket, not part of SAAS-6.

### 5. Every new `company` table is enrolled twice

`tests/test_rls_coverage.py::test_every_tenant_table_is_in_the_rls_migration` reads only `core/migrations/0020_rls_all_tenant_tables.py`'s `RLS_TABLES`. A later migration does not satisfy that test by itself. `0020` has already run on existing databases, so appending a name there does not create the policy on a live Postgres.

For each new model with a `company` FK (`workshop` job tables, `projects` tables, `support_vendorticketshare`):

1. Append the db table name to `RLS_TABLES` in `0020`, with the same comment the file already uses for late additions: the list entry is what the coverage test reads; the live policy comes from a new migration.
2. Add `core/migrations/0038_rls_<table>.py` (next free number) copied from `0036_rls_payment_promise.py`: `ENABLE` and `FORCE ROW LEVEL SECURITY`, policy name `bizboard_company_isolation`, `USING` and `WITH CHECK` identical to `0020` (`company_id` matches `app.company_id`, or `app.rls_bypass = '1'`). No-op unless the connection is PostgreSQL.

`test_rls_policy_present_and_forced_on_postgres` only walks `0020`'s list. After the name is on that list, the Postgres test fails until the new migration has actually created the policy. Do not add the table to `_EXCLUDED`.

---

## Phase A

### INS-0 — Policy desk role

**Goal.** `CompanyUser.Role.POLICY_DESK` exists. An owner can invite P12. That membership can be told apart from sales staff and from the bookkeeper. No policy endpoint exists yet, so the role cannot create invoices, post journals, or read financial reports.

**Model.**

- Extend `CompanyUser.Role` with `POLICY_DESK = "POLICY_DESK", "Policy desk"`.
- `capability_defaults_for_role("POLICY_DESK")` returns every existing flag false, plus `can_manage_policies=True`.
- Add `can_manage_policies = models.BooleanField(default=False)`. Owners and managers do not get it from their current defaults. Grant it on the new role only. An owner who also works the desk gets it by an explicit flag edit, not by being OWNER.
- Migration: schema for the boolean, then `AlterField` choices. Follow `accounts/migrations/0046_alter_companyuser_role.py`. No data backfill. Existing memberships stay on their current role.

**API and UI.**

- Invite and membership serializers accept `POLICY_DESK` and reject `can_manage_policies=True` on `SALES_STAFF`, `ACCOUNTANT`, `INVENTORY_STAFF`, `AUDITOR`, and `VIEWER` unless the caller is an owner setting the flag on a `POLICY_DESK` row.
- Settings → Users shows the role. No new nav item. Policy screens arrive with INS-4.

**Tests.**

`backend/tests/tenancy/test_rbac_matrix.py` is a hand-maintained list. `ROLES` and `EXPECTED` do not iterate `CompanyUser.Role.choices`. Adding `POLICY_DESK` on the model will not fail this file, and its docstring claim to cover all freeze invite roles goes stale until the new role is written in.

- Add `"POLICY_DESK"` to `ROLES`.
- Add a `"POLICY_DESK": False` entry on **every** row of `EXPECTED` (`IsOwner`, `CanManageInventory`, `CanImport`, `CanCancelDocuments`, `CanViewFinancialReports`, `CanExport`, `CanCreatePurchases`, `CanCreatePayments`, `CanPostJournals`, `CanCreateSales`, `IsOwnerManagerOrAccountant`). The role's invite defaults grant none of those classes. There is no `CanManagePolicies` class in that file until a policy endpoint exists. Do not add a permission class that nothing checks.
- A separate test invites `POLICY_DESK` and asserts `can_create_sales` is false and `can_manage_policies` is true, and that sales-invoice create, journal post, trial balance, and import return 403.
- OWNER still passes the existing capability-default test. Adding the boolean must not flip any current role's defaults.

**Done when.** An owner can invite a policy-desk user, that user has no money-posting capability, and INS-4's future view can check `can_manage_policies` instead of inventing a second role.

### PRE-R3 — CRM stays deployment-gated

**Goal.** Confirming the retail pack or the trade pack does not turn `ENABLE_CRM` on. A company JSON module map cannot sneak the dark module on either. The way a pilot actually gets CRM is a deployment grant, written down.

**Code.**

- No new CRM fields. `packs._entitled` already refuses `DARK_MODULE_KEYS`.
- Add `backend/tests/test_pack_does_not_grant_dark_modules.py` if that assertion is missing: `apply_pack(company, "trade", ...)` leaves `ENABLE_CRM`, `ENABLE_MANUFACTURING`, and `ENABLE_PAYROLL` off; same for `"retail"`.
- Add `docs/ops/DARK_MODULE_GRANT.md`: the env flag is the ceiling; a company override is not enough; who may set the deployment grant; how to turn it off.

**Done when.** The pack test is green and the grant note exists. PRE-05's product surface does not grow in this ticket.

### PRE-R5 — Manufacturing pack stays held

**Goal.** `HELD_PACKS` still contains `"manufacturing"`. `ENABLE_MANUFACTURING` stays in `DARK_MODULE_KEYS`. The BOM comment in `manufacturing/models.py` (multiple ACTIVE BOMs, no version) stays the limitation. This ticket does not pick a versioning scheme.

**Code.**

- The PRE-R3 test above covers the flag.
- Add one assertion that `propose_pack` never returns `"manufacturing"` and that `apply_pack(..., "manufacturing")` raises the existing unknown-pack error.
- Do not add manufacturing to `PACKS`.

**Done when.** A pack confirm cannot enable the module, and the hold is tested. A later plan may un-hold it only after a pilot tenant and a BOM-version decision.

---

## Phase B

### PRE-R2 — Proof of delivery on the stop

**Goal.** P7 can finish a stop with who received the goods, a photo, and a slip the office can reprint. Cash collected on the beat is an existing customer receipt, linked from the stop. The slip is not a tax invoice and does not move stock.

**What already exists.** `DeliveryRouteStop.status` (`DELIVERED`, `FAILED`, `RETURNED`), `delivered_at`, `otp_code`, `pod_note`. `DeliveryRouteService.set_stop_status` requires the route to be `IN_TRANSIT` before a stop can leave `PENDING`.

**Model.** Additive migration on `sales.DeliveryRouteStop`:

| Field | Type | Rule |
|---|---|---|
| `received_by_name` | `CharField(128)`, blank | Required when status becomes `DELIVERED` |
| `pod_photo` | FK `core.FileAsset`, null | Optional |
| `customer_receipt` | FK `payments.CustomerReceipt`, null, `SET_NULL` | Same company and same customer as the stop's sales order |

Do not add a `ProofOfDelivery` table. The stop is the record.

**Service.** Extend `set_stop_status`. On `DELIVERED`, require `received_by_name`. If `customer_receipt` is sent, reject it unless `receipt.company_id == stop.company_id` and the receipt's customer matches the sales order's customer. Do not create the receipt inside this service. P5 or P7 records the receipt on the existing receipt API, then links the id.

**API.** The existing route viewset, same company scope. New fields on the stop serializer. A `GET /api/v1/sales/delivery-routes/{id}/stops/{stop_id}/pod.pdf` returns a slip: route number, date, customer, lines from the sales order, received-by name, delivered-at, and the photo's file name. No GSTIN tax breakup on the slip. The invoice remains the tax document.

**UI.** On `/sales/delivery-routes/:id`, a delivered stop shows received-by, photo, receipt link, and "Print slip". The rider's screen is that same page. No new top-level nav item.

**Tests.**

- Delivering without `received_by_name` returns 400.
- A receipt from another company or another customer is rejected.
- Completing the stop does not create a `StockMovement` or a journal.
- Reprinting the slip after the route is `COMPLETED` still works.
- The existing in-transit rule stays: a `PLANNED` route cannot mark a stop delivered.

**Done when.** `J-ROUTE-P7-BEAT` can be demonstrated: stops end `DELIVERED` or `FAILED`, and any cash taken is a receipt whose id is on the stop.

### PRE-R1 — Job card

**Goal.** P9 opens a repair, lists spares and labour, and turns that card into one sales invoice. The card does not post stock or the ledger. `J-JOB-P9-REPAIR` is this ticket. `J-AMC-P9-VISIT` is not. A contract visit stays on `contracts` and is out of scope here.

**App.** New app `workshop`. It may import `sales` and `masters`. `sales` does not import `workshop`.

**Models.**

`JobCard(CompanyScopedModel)`

| Field | Notes |
|---|---|
| `number` | From `core.services.sequences.next_number`, scope `JOB`, prefix `JOB`. Partial unique `(company, number)` where number is not empty. Same pattern as tickets. |
| `customer` | FK `masters.Customer`, `PROTECT` |
| `technician` | FK `accounts.CompanyUser`, null |
| `status` | `DRAFT`, `IN_PROGRESS`, `INVOICED`, `CANCELLED` |
| `complaint` | text, blank |
| `sales_invoice` | FK `sales.SalesInvoice`, null. Set once, when conversion succeeds. |

`JobCardLine`

| Field | Notes |
|---|---|
| `company` | FK `accounts.Company`, same as `BomLine`, so the line is a tenant table and not a child that skips RLS |
| `kind` | `PART` or `LABOUR` |
| `product` | FK `masters.Product`. `PART` must be a stock item. `LABOUR` must be a service item. |
| `quantity`, `unit_price` | Same decimal widths as invoice lines |
| `serial` | FK `inventory` serial, null. Optional. Set only for `PART`. |

**Service `workshop.services.convert_to_invoice`.**

- Allowed from `DRAFT` or `IN_PROGRESS`, and only when `sales_invoice` is null.
- Creates a **draft** sales invoice with one line per job line, copying quantity and price. Does not call invoice complete.
- Sets `job.sales_invoice` and `status=INVOICED` in the same transaction as the draft insert.
- A second convert returns the existing draft. It does not insert another invoice.
- Cancelling a job is allowed only while `sales_invoice` is null. After conversion, cancel the invoice through the existing sales API. The job stays `INVOICED`.

**API.** `CompanyScopedViewSet` at `/api/v1/workshop/job-cards/`. Actions: `start` (`DRAFT` → `IN_PROGRESS`), `convert`, `cancel`. Permission: `can_create_sales`, which P9's sales-staff home already has. P12's `POLICY_DESK` does not.

**UI.** `/workshop/jobs` and `/workshop/jobs/:id`, under a nav item visible when `can_create_sales`. Convert button lands on the draft invoice editor. The user completes the invoice there, which is the existing stock and GST path.

**Flag.** `ENABLE_WORKSHOP`, added to `ROLLOUT_GRANTABLE_KEYS`, default off. Not a dark module. Not added to the retail or trade pack.

**RLS.** `JobCard` and `JobCardLine` both carry `company`. Enroll them as in decision 5 before the app ships. `test_every_tenant_table_is_in_the_rls_migration` fails if the names are missing from `0020`'s `RLS_TABLES`.

**Tests.**

- A `PART` line whose product does not track stock is rejected. A `LABOUR` line that tracks stock is rejected.
- Convert creates one draft and no stock movement. Complete on that invoice then decreases the spare.
- Second convert does not create a second invoice.
- `POLICY_DESK` receives 403 on create.
- Cancelling an invoiced job is rejected.

**Done when.** A mixed SAC and HSN invoice can be reached from a job card, and the card itself has no journal rows.

---

## Phase C

### PRE-R4 — Project milestones, first slice

**Start gate.** Do not start until a pilot is named whose bills are milestones (a contractor who invoices "foundation" and "handover"), not a workshop visit and not an AMC. If that pilot does not appear, this ticket stays unbuilt.

**Out of this slice.** BOQ quantity takeoff, cost-to-complete, retention, measurement books, tender comparison.

**App.** New app `projects`. It may import `sales`. `sales` does not import `projects`.

**Models.**

`Project(CompanyScopedModel)`: `number` (sequence scope `PROJECT`, prefix `PRJ`), `customer`, `name`, `status` (`OPEN`, `CLOSED`, `CANCELLED`).

`ProjectMilestone`: `company` FK (same tenant as the project), `project`, `name`, `sequence`, `amount` (money, 2 decimal places), `status` (`PLANNED`, `READY`, `INVOICED`), `sales_invoice` nullable FK.

**Service.** `mark_ready` moves `PLANNED` → `READY`. `invoice_milestone` creates one draft sales invoice for that amount, one service line, SAC taken from a required `service_product` on the milestone. Same convert rules as the job card: one invoice, no second insert, no stock movement on the milestone itself.

Closing a project is rejected while any milestone is `READY` and uninvoiced.

**Flag.** `ENABLE_PROJECTS` in `ROLLOUT_GRANTABLE_KEYS`, default off. Not in a pack.

**RLS.** `Project` is a `CompanyScopedModel`. Give `ProjectMilestone` a real `company` FK as well, the way `BomLine` does, so a milestone row cannot be written without a tenant. Enroll both tables as in decision 5.

**UI.** `/projects` and `/projects/:id`. Invoice action opens the draft invoice.

**Tests.** Two milestones produce two drafts. Invoicing the same milestone twice returns the first draft. A stock product on a milestone is rejected. Flag off returns 404 for a non-owner and for an owner, matching the dark-module 404 discipline only if we choose a dark module. This flag is a rollout flag, so flag-off is 404 from the URL include not being mounted, the same way other rollout modules hide their routes.

**Done when.** The named pilot can raise a draft invoice per milestone and the ledger moves only when that invoice is completed.

---

## Phase D

### SAAS-6 — Vendor read of a shared ticket

**Start gate.** One company row is designated the vendor tenant (BizBoard's own books). Its id is settings `VENDOR_COMPANY_ID`. Empty setting means the share action returns 404.

**Goal.** A tenant owner shares one ticket. P10, logged into the vendor company, can read the redacted copy. P10 cannot open `/api/v1/support/tickets/` for the customer's company. No role impersonation. No switch into the customer tenant.

**Model.** `support.VendorTicketShare`, **not** company-scoped to the customer.

| Field | Notes |
|---|---|
| `vendor_company` | FK `accounts.Company`. Always `settings.VENDOR_COMPANY_ID`. |
| `source_company` | FK, the customer tenant. Stored so the vendor row can name the account. |
| `source_ticket_id` | UUID or int, **not** a database FK. A FK would couple vendor queries to the tenant row and tempt a join that ignores RLS. |
| `source_number`, `subject`, `status`, `shared_at` | Copied text and the status at share time |
| `revoked_at` | Null while visible |

Do not copy description attachments, invoice ids, or amounts. Subject and status are the v1 payload. Description is included only when the owner ticks "include description" on share. Default off.

The share row's `company` field, if the base class requires one, is `vendor_company`. Vendor users then see it through `CompanyScopedViewSet` filtered to their company. Customer users do not, because their company id is different.

**RLS enrollment.** `VendorTicketShare` has a `company` FK (the vendor company). It is a tenant table. Enroll `support_vendorticketshare` as in decision 5: name it in `0020`'s `RLS_TABLES`, and add a follow-up migration in the shape of `0036_rls_payment_promise.py` that creates `bizboard_company_isolation` with `FORCE ROW LEVEL SECURITY`. Do not add it to `_EXCLUDED`. Without the policy, vendor reads of the share row are not forced through `app.company_id`.

**Write path.** `support.services.share_ticket(ticket, user, include_description: bool)`.

The request middleware has set `app.company_id` to the **source** company. The isolation policy's `WITH CHECK` is `company_id` equals that GUC, or `app.rls_bypass = '1'` (`core/migrations/0020_rls_all_tenant_tables.py`). An `INSERT` of a row whose `company_id` is `VENDOR_COMPANY_ID` fails that check. The same failure hits a later `UPDATE` of that row from the source owner's session, including revoke and "share again".

`core.rls.rls_bypass` is the escape hatch this repo already uses for a deliberate cross-tenant write (`core/tasks.py`). It sets the GUC and clears it in `finally`. It is a no-op unless Postgres RLS is enabled, so SQLite tests still run.

- Caller must be an active OWNER of `ticket.company`. Do this check **before** opening the bypass, using the ticket already loaded through the company-scoped queryset.
- Copy number, subject, status, and description (only if requested) into plain values while RLS is still the source company. Do not query `Ticket` again inside the bypass.
- Inside `with rls_bypass():`, `update_or_create` the `VendorTicketShare` row with `company_id=VENDOR_COMPANY_ID`. Nothing else runs in that block. No ticket read, no audit write, no invoice query.
- After the block exits, write an `AuditEvent` on the **source** company: action `support.ticket_shared`, ticket id, vendor company id, whether description was included. No ticket body in the audit payload. The source GUC is restored, so this insert satisfies `WITH CHECK` without bypass.
- A second share updates status and sets `revoked_at` null inside the same bypass block. It does not insert a duplicate. Unique on `(vendor_company, source_company, source_ticket_id)`.

`revoke_share` repeats the owner check outside the bypass, then sets `revoked_at` **inside** `rls_bypass()`. The source owner cannot `SELECT` the vendor row under the normal policy, because its `company_id` is the vendor. Lookup by `source_company_id` and `source_ticket_id` happens only inside the bypass, and the code checks that `source_company_id` is the caller's company before saving. The vendor list hides revoked rows. The row stays for audit.

**Read path.** `VendorTicketShareViewSet` subclasses `CompanyScopedViewSet`. `get_queryset` is the base filter plus `revoked_at__isnull=True`. There is no `?company=` parameter. There is no staff-wide unfiltered list.

**What is forbidden.**

- A queryset of `Ticket.objects.all()` or `.filter(company_id__in=...)` in vendor code.
- A database role with `USING (true)` on `support_ticket`.
- Leaving `rls_bypass()` open around anything except the share-row insert or update. Reading the source ticket inside the bypass would hide a cross-tenant ticket read.
- `switch-company` into the customer as the implementation of this console.
- Writing `TicketComment` on the source ticket from the vendor user. That is a later ticket.

**UI.** On the customer ticket, owner-only "Share with BizBoard" and "Stop sharing". On the vendor tenant, `/support/shared`, listing number, source company name, subject, status, shared time. No reply box in v1.

**Tests.**

- Company A cannot GET company B's ticket (existing isolation, keep it).
- `share_ticket` contains `rls_bypass`, on the same static check as `test_payment_webhook_uses_rls_bypass_then_sets_company`. On Postgres, with `app.company_id` set to company A, the share insert commits. That is the test that the `WITH CHECK` bypass is real, not only that SQLite accepted the row.
- `support_vendorticketshare` is in `0020`'s `RLS_TABLES`. On Postgres it has `FORCE ROW LEVEL SECURITY` and `bizboard_company_isolation`.
- Owner of A shares. A user of the vendor company can GET the share. A user of company C receives 404.
- The share payload has no amount field and no file id.
- Description is absent unless `include_description` was true.
- Revoke removes it from the vendor list and leaves the audit row on company A.
- A sales-staff user of company A receives 403 on share.
- `VENDOR_COMPANY_ID` unset: share returns 404 and writes no row.

**Done when.** `J-SAAS-P10-SUPPORT` is true for a shared ticket, and the WF-28 cross-company ticket read still returns 404.

---

## Suggested sequence inside a phase

Phase A can land as one pull request: role migration, pack tests, hold test, grant note.

Phase B is two pull requests. PRE-R2 first, because it only migrates `DeliveryRouteStop`. PRE-R1 second, because it is a new app.

Phase C and Phase D wait on their start gates. Do not schedule them in the same release as Phase A.

## Definition of done for the whole plan

- INS-0, PRE-R3, and PRE-R5 are merged and the new tests are green.
- PRE-R2 and PRE-R1 are merged behind their existing route page and `ENABLE_WORKSHOP`.
- PRE-R4 and SAAS-6 are either merged after the start gate or still listed as waiting, with the gate sentence unchanged.
- [BUSINESS_DNA_CONSOLIDATED.md](../BUSINESS_DNA_CONSOLIDATED.md) §6.0 and the SAAS-6 and INS-0 rows point at this file.
