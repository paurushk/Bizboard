# Customers + Customer 360° — deep review of the implemented scope (2026-10-12)

> **Status (2026-10-12, later):** all four fix batches below are implemented and tested. Decisions taken: lifting a block or archive is owner/manager only; archiving a customer with a balance or an unallocated advance is refused outright. Still open (need a person, not code): audit/export retention policy and a native-speaker review of the Hindi strings.

Reviewed: backend (`masters/`, `ledgers/services.py`, `imports/services.py`, sales validators), web (`CustomersPage`, `CustomerFormDialog`, `Customer360Page`), tests, docs, and every caller I could find that reads or writes customers.
**Confirmed** = reproduced by a throwaway test this session. **Code-read** = seen in the code, not run.

## A. Bugs

| # | Sev | Finding | Evidence |
|---|---|---|---|
| B1 | High | **Editing the Customer 360° dialog loses your typing.** The dialog renders only while `!editable.isFetching`; React Query refetches on window focus, so alt-tabbing unmounts the open dialog and discards unsaved edits. | Code-read, `Customer360Page.tsx` (`editOpen && editable.data && !editable.isFetching`) |
| B2 | High | **A draft invoice cannot be saved once its customer is archived or blocked.** `SalesInvoiceSerializer.validate_customer` rejects any non-ACTIVE customer even when the customer did not change (the quotation serializer exempts an unchanged customer). Every archived customer has documents, so this now hits real drafts. | Confirmed: PATCH with `customer` → 400 "inactive customer"; without it → 200 |
| B3 | High | **Delete can hide a customer that is still in use.** `Customer.is_referenced()` omits complaints, contracts, support tickets, projects, workshop job cards, insurance policies, POS refunds, challan returns, advance refunds, credit unlocks, recurring schedules, payment promises and journal lines. Soft delete bypasses the `PROTECT` foreign keys, so these customers vanish from the alive manager. | Confirmed: customer with a contract → `DELETE` 204, `is_deleted=True` |
| B4 | Med | **Valid mobile numbers starting with 91 are rejected** (e.g. 9123456789). The rule strips a leading `91`/`0` before counting digits, so a 10-digit number beginning 91 becomes 8 digits. The same bug already existed in the web `isValidIndianPhone`, so the form blocks it too. | Confirmed on the API |
| B5 | Med | **Archive allowed with money owed.** The API archives a customer with an outstanding balance; they then disappear from the receipt picker (unless "show inactive") and can't be billed. | Confirmed: archive a customer with a completed invoice → 200 |
| B6 | Med | **Wrong "not configured" message when the GSP is configured but down.** `HttpGstinProvider` falls back silently to the null provider on any network or JSON error, so `_verification_notice` says "Live verification is not configured". | Code-read, `gstin_verify.py:99-100` |
| B7 | Med | **Verify GSTIN is unreachable on a phone.** The GSTIN-status column (with the Verify button) is hidden below `md`; only a chip stays under the name. | Code-read |
| B8 | Low | **CSV export ignores the chosen sort.** The UI sends `sort`, the API always orders by name. | Code-read |
| B9 | Low | Grammar: "a inactive customer" (message built from `billing_block_word`). | Confirmed |
| B10 | Low | Field errors for keys not on the form fall back to the generic alert only when no field matched; if one field matched, an unmatched server error is dropped. | Code-read, `CustomerFormDialog` onError |
| B11 | Low | A PUT or PATCH that changes nothing still writes an empty `UPDATE` audit event. | Code-read |
| B12 | Low | Two shapes for a 409: the pre-check returns a bare `{detail, current}`, the locked re-check goes through the error envelope. | Code-read |
| M1 | High | **Role bypass through `PATCH`/`PUT`.** `CanArchiveCustomer` is attached only to `destroy`. A sales user can `PATCH {status: "INACTIVE"}` (archive) or `{status: "ACTIVE"}` on a BLOCKED customer (unblock, i.e. lift a credit hold). Found by a second reviewer. | Confirmed: sales staff PATCH → 200 for both |
| M2 | Med | **Stale PAN (and state) when the GSTIN changes through the API.** PAN is derived only when the customer has none, so a new GSTIN keeps the old GSTIN's PAN (the web form masks this because it always sends `pan`). State is only re-derived when blank. Found by a second reviewer. | Confirmed: changed GSTIN → `pan` still `ABCDE1234F`, new one is `AABCU9603R` |
| M3 | Med | **Every credit-term edit shows twice in History.** `perform_update` writes the general `UPDATE` event (with `changes`) and a second `customer.credit_terms` event; `history` lists both. My earlier test counted by description, so it missed this. Found by a second reviewer. | Confirmed: 2 rows with changes for one edit |
| M4 | Low | **Two simultaneous requests setting the same GSTIN** can both pass the serializer check; the loser hits the database constraint. It does **not** return a 500: `core/exceptions.py` turns `IntegrityError` into a generic conflict message, so the only loss is that the message doesn't name the holder. Downgraded from the second reviewer's "Low–Med / 500". | Code-read |

## B. Gaps

**Rules that other write paths bypass**
- **CRM lead conversion** (`crm/services.py:132`) creates customers with no GSTIN checksum, no upper-casing, no state or PAN derivation and no duplicate message. A duplicate GSTIN ends in a raw database error.
- **Sales-bill import** (`imports/services.py` `_resolve_customer`) creates customers by name or GSTIN with no GSTIN/state rules.
- **Tenant backup restore** (`accounts/tenant_backup.py:1368`) is outside the rules (acceptable for a restore, but undocumented).
- **PAN** has no validation anywhere on the customer (model or serializer), so any 10 characters are accepted.

**Archive and lifecycle**
- **Recurring invoice schedules keep generating drafts** for archived or blocked customers (`sales/recurring.py` creates DRAFT invoices with no customer-status check). Those drafts then can't be completed.
- **Pickers still offer unusable customers.** The invoice customer search and the shared party-search hook send no `status` filter, so archived and blocked customers can be chosen and then fail at save.
- **Dunning and reminders** do not look at the customer status.
- **No "reopen" help.** An archived customer with a balance is only discoverable through the Inactive filter.

**Throttle and abuse**
- Verify and lookup share one 30/hour budget per company, so one user (or "verify all rows") can exhaust it for everyone. No per-user limit.
- The 10-minute lookup cache is per company and GSTIN; a stale CANCELLED/VALID can be shown for 10 minutes.

**Data protection**
- Audit `metadata.changes` stores old and new **phone, email and PAN**. That copy outlives an erasure request, and the History panel shows it to anyone with financial-reports permission.
- No retention rule for customer audit events or exports.

**Testing**
- No tests for: the 429 throttle, `customers_audit --fix`, export under row-level security, the 409 on Block/Activate, History for non-credit changes, CRM and import paths, the shipping-address round trip, or the Hindi strings.
- The balance-sort path with books on (GL basis) is not covered.
- Everything UI-side was verified in jsdom or mock mode only; no run against a real backend.

**Docs**
- The plan file still contains superseded claims (old line numbers, "row click opens 360°").
- `FREEZE_SCOPE_COVERAGE.md` and the QOS backlog were not updated.
- The OpenAPI snapshot was generated with the test settings, not CI's.

## C. Improvement suggestions (refined after the second review)
1. **B1:** show the dialog as soon as `editable.data` exists and set `refetchOnWindowFocus: false` for that query. Gating on `isFetching` is the wrong condition for any modal, because any background refetch would unmount it.
2. **M1 (security):** enforce in `CustomerSerializer.validate`:
   - any change **to** `INACTIVE` needs OWNER or MANAGER (the founder's archive rule);
   - **BLOCKED → ACTIVE** (lifting a credit hold) needs OWNER or MANAGER too. Blocking itself can stay with sales staff. *Decision needed:* confirm unblock is owner/manager only.
3. **B2:** let a draft be saved when its customer is unchanged, but keep the check in the complete/issue step (`SalesService.complete`) so a blocked or inactive customer still cannot have a draft turned into a completed invoice. Cancelling a draft stays allowed. Only the invoice and quotation serializers validate status today; orders and challans check it in their services.
4. **B3:** build the reference check from `Customer._meta.related_objects` (all `PROTECT` relations) instead of a hand-kept list, with these cautions: skip child tables the customer owns (`CustomerShippingAddress`, which cascades), use the base manager so soft-deleted rows still count, add journal lines and recurring schedules, and test one row per relation. Do the same for `Supplier.is_referenced` as a follow-up (not in scope here).
5. **B4:** accept exactly `^[6-9]\d{9}$`, `^0[6-9]\d{9}$` (11 digits), `^91[6-9]\d{9}$` or `^\+91[6-9]\d{9}$`. Never strip `91` from a 10-digit number. Apply to the API and to the web `isValidIndianPhone`.
6. **M2:** when the GSTIN changes and `pan` was not sent, replace the stored PAN **only if it equals the PAN derived from the old GSTIN** (a hand-entered PAN, which an unregistered customer can legitimately have, is kept). Clearing the GSTIN keeps the PAN. When the GSTIN changes and `state` was not sent, re-derive the state from the new GSTIN.
7. **M3:** drop the second `customer.credit_terms` event, or keep it for searching but have `history` skip it. Prefer skipping it in `history` so existing audit searches keep working.
8. **B5:** make `DELETE` refuse with a clear 400 when the customer has an outstanding balance **or** unallocated advances (a liability back to the customer), and tell the user to settle first. Pause the customer's recurring schedules on archive or block. *Decision needed:* hard block (recommended) versus allow with a typed confirmation.
9. **B8:** honour `sort` in the export (`recent`, `balance`), reusing the same ordering as the list.
10. **B9:** put the article in the message, or reword it ("... because the customer is inactive").
11. **B11/B12:** skip the version bump and the audit row when nothing changed; make the pre-check and the locked re-check raise the same `StaleWrite` carrying `current`, so the web handler reads one shape.
12. **Pickers:** pass `status: 'ACTIVE'` in the invoice, order, quotation and POS customer searches; keep "show inactive" only on receipts.
13. **One creation service** (`create_customer`) built on `gstin_rules`, used by CRM lead conversion and sales-bill import; add PAN format validation (`^[A-Z]{5}[0-9]{4}[A-Z]$`).
14. **Provider honesty (B6):** distinct "provider unavailable" status instead of falling back to null; **per-user** verify throttle plus a company one; Verify reachable on mobile (B7).
15. **PII in audit metadata:** mask or hash phone, email and PAN in `changes`; decide retention.
16. **Operational:** schedule `customers_audit` monthly; native-speaker review of the Hindi strings.

**Second-review comments not taken as written:** its file paths (`apps/...`) don't match this repository, and its status names (`ISSUED`) don't exist here (invoices go DRAFT to COMPLETED); the substance was applied. Its M4 was downgraded because `IntegrityError` is already mapped to a 4xx.

## D. Cross-module impact (what the changes touch)

| Module | Impact now | Risk / action |
|---|---|---|
| Sales invoices | Archived customers refused; draft edit blocked (B2); customer picker still lists them | High — fix B2 and the picker |
| Quotations / orders / challans / conversions | Archived customers refused on create and convert; unchanged-customer edits allowed only on quotations | Medium — align the other serializers |
| POS | Walk-in protected (cannot be archived or given a GSTIN); offline checkout creates customers with name only; archived customers fail at checkout | Low–Medium |
| Receipts / Money in | Archived hidden from the picker unless "show inactive"; receipts still accepted | Medium (B5) |
| Credit notes / returns | Still allowed for archived customers (intended) | Low |
| Collections, dunning, aging, ledger | Unchanged; dunning ignores archive; summary adds advance and exposure figures | Medium (gap) |
| GST returns / e-invoice | Taxpayer type, state and PAN now derive from GSTIN; changed GSTIN clears legal name (e-invoice falls back to the customer name) | Positive; check e-invoice buyer name after a GSTIN edit |
| CRM | Lead conversion bypasses the rules; duplicate GSTIN → raw error | High-ish |
| Imports | Customer import now uses the rules (strict on by default, so mismatch rows are **skipped**); bill import bypasses | Medium |
| Recurring / contracts | Schedules keep generating for archived customers; contract customers can be soft-deleted | High (B3) |
| Complaints, tickets, workshop, projects, insurance | Customers can be soft-deleted while referenced | High (B3) |
| Customer 360° / insights | Flag on by default; new Edit and History; cache invalidation helper used by the customer screens only | Medium — invoice party panel and import do not use it |
| Reports / exports | Customer list CSV is a new PII export; existing reports unchanged | Medium — retention |
| Billing / subscription | `SubscriptionWritesAllowed` still enforced server-side; UI gate only fetches the subscription for owners | Low |
| Feature flags / packs | `ENABLE_CUSTOMER_360` default flipped; `FREEZE_SCOPE.md` updated; two tests changed | Low |
| Mobile app | No customer API use found | None |
| API clients / integrations | New 400s for duplicate GSTIN, mismatch, bad phone; `version` now honoured on PATCH; credit fields refused for non-managers; DELETE refused for sales staff | Medium — announce |

## E. Suggested fix order
1. **Batch 1, security and integrity:** M1, B1, B2 (draft save only, completion stays blocked), B3, B4, M2. Each with a test.
2. **Batch 2, lifecycle:** B5 (refuse archive with balance or advances, pause recurring schedules), picker status filters.
3. **Batch 3, creation paths and audit:** one customer-creation service for CRM and import, PAN validation, M3, B11, B12, PII masking.
4. **Batch 4, UX and resilience:** B6 provider state, B7 mobile Verify, B8 export sort, B9 wording, per-user throttle.

**Decisions needed before Batch 1/2:** (a) unblock (BLOCKED to ACTIVE) owner/manager only? (b) archive with a balance: hard block or typed confirmation?


## F. Fix status (what was done)

| Item | Status | How |
|---|---|---|
| B1 | Fixed | 360° dialog renders once data exists; the query no longer refetches on window focus. Test added. |
| B2 | Fixed | A draft keeps saving for its own non-active customer; `complete` still refuses. Test added. |
| B3 | Fixed | `is_referenced` is built from every PROTECT relation (skips owned child tables, uses the base manager). Test with a contract. |
| B4 | Fixed | `core.validators.is_valid_indian_mobile` and the web `isValidIndianPhone` share one rule. |
| B5 | Fixed | `DELETE` returns 400 `customer_has_balance` for a balance or an unallocated advance; archive pauses recurring schedules; the recurring job skips non-active customers. |
| B6 | Fixed | The HTTP provider reports `provider_unavailable`; the notice says the service could not be reached. |
| B7 | Fixed | Verify GSTIN is in the row menu on small screens. |
| B8 | Fixed | Export honours `sort` (name, recent, balance). |
| B9 | Fixed | Messages use "a blocked customer" / "an inactive customer". |
| B10 | Fixed | A server error for a field the form lacks is shown in the dialog alert. |
| B11 | Fixed | An unchanged save writes no version bump and no audit row. |
| B12 | Fixed | Both 409 paths raise one `stale_write` error. It no longer embeds the row; the client reloads. |
| M1 | Fixed | `status` changes to INACTIVE, or from BLOCKED/INACTIVE to ACTIVE, need OWNER or MANAGER in the serializer; blocking stays open. UI hides Unblock/Activate for others. |
| M2 | Fixed | A new GSTIN brings its PAN (unless the stored PAN was typed by hand) and its state. |
| M3 | Fixed | History skips the `customer.credit_terms` marker event. |
| M4 | Fixed | A GSTIN clash caught by the database constraint (PostgreSQL names the constraint, SQLite names the columns) now returns the same error that names the holder, on create and update. |
| Gap: CRM and bill import bypass | Fixed | Both use `masters.services.create_customer`. |
| Gap: PAN not validated | Fixed | `validate_pan` on the serializer. |
| Gap: pickers offer archived customers | Fixed | `activeOnly` on the document pickers, the invoice picker and recurring-invoice page. |
| Gap: PII in audit changes | Fixed | phone, email and PAN are masked in `changes`. |
| Gap: one shared throttle | Fixed | Added a per-user `gstin_verify_user` budget (15/hour) beside the company one. |
| Gap: dunning ignores status | Fixed | Archived (INACTIVE) customers get no reminders; blocked customers still do, because a credit hold means they still owe. |
| Gap: retention for audit/export | Open | Needs a founder decision. |
| Gap: Hindi review | Open | Needs a native speaker. |
| Gap: Supplier.is_referenced | Fixed | Customer and Supplier now share `has_protected_references`, built from the PROTECT relations. |

### Second pass (items left after section F)
| Item | Status | How |
|---|---|---|
| Invoice party panel and CRM paths skip the cache helper | Fixed | Panel, invoice custom-field save and lead conversion use `invalidateCustomerQueries` / the creation rules |
| Other pickers list archived customers | Fixed | Leads picker and the support/contract/complaint customer field use `activeOnly`. Ledger, banking and receipt pickers keep archived customers on purpose (money in, statements) |
| Lookup cache can hide a status change for 10 minutes | Fixed | TTL is 60 seconds |
| Tenant restore bypasses the rules | Documented | Deliberate; see the semantics doc |
| No bulk verify | Fixed | `POST /customers/verify-gstin-bulk/` (10 at a time, 3 calls/hour per user) and a "Verify selected" button |
| Archived customers hard to find | Fixed | "N archived" link under the Active customers card |
| Metrics are logs only | Fixed | `/metrics` counters via `bump_event` |
| No scheduled audit | Fixed | Monthly `customers_audit_task` + owner notification (`masters/audit.py` is shared with the command) |
| Test gaps | Fixed | 429 on verify, history for name/status/GSTIN, lead conversion and merge, shipping-address round trip, ledger-basis balance sort, bulk verify, UI 409 on Block |
| Docs housekeeping | Fixed | Plan file has a "where this is out of date" note; coverage doc lists the gating tests |
| Q-OS backlog entries | Not added | Generated and rubric-linted; add through `qos/tools` |
| CRM lead merge could set a GSTIN another customer holds | Fixed (found in this pass) | Lead merge now checks format and ownership, and fills PAN and state |

### Third pass
| Item | Status | How |
|---|---|---|
| 3 backend Hindi-voucher tests failing | Fixed | Cause was a missing local dependency (`uharfbuzz` is in requirements but was not installed in this venv). Installed; the three tests pass. Not a code change. |
| Postgres run | Done | 97 passed: customer tests, real-concurrency tests, export/list isolation under row-level security, dunning, pipeline |
| Q-OS entries | Done | QOS-0124 (fixed), QOS-0125 (open: retention decision, Hindi review); `qos/tools/lint.py` clean |
| Hindi review | Prepared | `docs/CUSTOMERS_HINDI_REVIEW.csv` (90 rows) for a native speaker to fill in; the review itself still needs a person |
| Retention policy | Written | Recommended policy in the semantics doc; the founder still confirms it (QOS-0125) |
| Owners cannot see the audit counts | Fixed | `GET /customers/health/` (owner/manager) and a banner on the Customers page |
| Lookup cache hides a status change | Fixed | The Verify & autofill button always asks the provider (`refresh`) |
| Restore bypasses the rules silently | Fixed | A restore logs the health-check counts |
| Real-browser run | Done | `web/e2e/customers.spec.ts` (8 runs on Chrome desktop and Pixel 5) passes. It found a real bug: the Customers page scrolled sideways on a phone (1040px in 375px) because the screen-reader-only header text was absolutely positioned outside the scroll area. Fixed. |
| Strict rules against real data | Partly | `customers_audit` on the local dev database: 245 companies, 0 findings. Not run against the Docker dev or any production database |

### Help and FAQs (2026-10-12)
- **Customers help page** rewritten for the current rules; new **Customer Snapshot** help page on `/sales/customers/:id` (`web/src/contextHelp/catalog/sales.ts`, `routes.ts`). English and Hindi.
- **FAQs** (category Customers): 4 existing answers updated (blocked customer, credit limit, duplicate GSTIN, walk-in) and 18 new ones (verify GSTIN, why Unverified, GSTIN edit resets verification, state/GSTIN mismatch, who can block/unblock/archive, block vs archive vs delete, why archive is refused, archived customers and reactivation, Customer Snapshot, History, export, "changed by someone else", phone format, POS walk-in, addresses and extra fields, taxpayer type, health banner, summary cards).
- Tests: `web/src/pages/help/customersHelp.test.tsx`; the existing catalog, route-coverage, FAQ-token and Hindi checks pass.
- Not done: new backend help codes for the customer error messages (archive refused, conflict, walk-in protected). Those need `help_codes.py`, the generated `helpCodes.json` and the CI guard together.
