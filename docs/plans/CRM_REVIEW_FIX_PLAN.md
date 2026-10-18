# CRM module — review findings and implementation plan

Date: 2026-10-16 · Source: screen/flow/product-impact review of CRM (Leads, CRM checklist, Opportunities, Pipeline, Campaigns, Referrals, public lead form, WhatsApp/CSV capture) · Status: **ALL WORK PACKAGES BUILT (WP-1…WP-8), uncommitted — see §8 and §9. Open: Postgres run, browser pass, CA sign-off, E1–E3 confirmation**

No CRM plan existed in `docs/plans/` or `docs/roadmap/`. This file is the first one. Shape follows [PURCHASE_REVIEW_FIX_PLAN.md](PURCHASE_REVIEW_FIX_PLAN.md).

Labels: **[O]** observed in code · **[V]** needs verification before building · **[R]** reproduced by running (none yet — see §7).

Related older items: `BUGS_LIST.md` BUG-CRM-001…006. F-01 is a side effect of the BUG-CRM-002 fix. Check the status of -001, -003 and -005 before building (they touch WP-1, WP-2, WP-4).

Scope reviewed: `backend/crm/*`, `web/src/pages/crm/*`, `web/src/pages/public/LeadFormPage.tsx`, `web/src/api/{crm,growth}.ts`, `insights/customer_360.py`, `insights/growth_metrics.py`, `ModuleGate`. **Not reviewed:** `insights/attention`, admin pages, Hindi copy, mobile layouts (screenshots exist in `docs/ux/walk/`), the assertions in existing tests. Sales invoice and credit-note internals are out of scope except where CRM calls them.

## 0. Decisions recorded (2026-10-16)

| # | Question | Decision | Drives |
|---|---|---|---|
| D1 | PERCENT referral reward basis | **Compute at mark-paid** from completed-invoice taxable value (net of completed credit notes) since the deal opened. PERCENT rewards show "amount set when paid" until then. | WP-4 |
| D2 | Referred person is already a customer | **Allow, but flag for manager.** Reward is created PENDING with a visible "existing customer" warning; the manager decides. | WP-4 |
| D3 | Revenue link deal ↔ invoice | **Store `opportunity` on the sales invoice.** One revenue definition for referral PERCENT, campaign ROI, won-vs-invoiced: completed-invoice taxable value net of completed credit notes. Needs a sales migration. | WP-5, WP-4 |
| D4 | Reopen WON/LOST | **Owner/manager only, audited.** Reverses a PENDING reward; blocked if the reward is APPROVED or PAID. | WP-2 |
| D5 | Mark-paid copy / ledger | **Not CA-confirmed: ship neutral copy** ("creates and completes a credit note for the referrer"). Confirm GL behaviour in code and flag it for CA sign-off. | WP-4 |
| D6 | Convert default | **"Mark as won" off by default.** Won requires amount > 0 or lines, plus a confirm. | WP-1 |
| D7 | Duplicate LEAD ("same as this one") | **Close the new lead as duplicate:** status LOST, reason `duplicate`, linked to the original, notes copied. No hard merge. | WP-3 |
| D8 | LOST reason | **Required** for leads and opportunities: fixed list (price, competitor, no response, not a fit, duplicate, other + free text). | WP-3, WP-2 |
| D9 | Probability | **Stage defaults, editable:** OPEN 10, QUALIFIED 30, NEGOTIATION 60, WON 100, LOST 0, applied on stage move unless the user set a custom value. | WP-6 |
| D10 | WhatsApp inbound | **Support Meta's real payload + per-company app secret;** separate verify token from URL token; keep flat format as fallback. | WP-7 |
| D11 | Public lead form | **Hide Campaign ID; show company name and a consent line;** campaign carried in a signed link parameter; add form-token rotate. | WP-7 |
| D12 | Referral code control | **Codes table + deactivate.** Employee referrers: approve only; payout stays customer-only for now. | WP-4 |
| D13 | Lead routing, no sales staff | **Round-robin across sales staff, else owner.** | WP-3/WP-8 |
| D14 | Permissions | **Reassign: owner/manager or current assignee. Issue codes / set reward value: owner/manager.** | WP-3, WP-4 |
| D15 | Campaign delete | **Block when leads or children attached;** offer COMPLETE instead. Leads can attach only to DRAFT/ACTIVE campaigns. | WP-5 |
| D16 | Board window | **Open deals always; WON/LOST last 90 days + "show older"**, server-side filters and per-column paging. | WP-6 |

Still open (do not block PR-A..C): E1 retention for `LeadIngestJob.payload` (CSV rows contain personal data); E2 whether a manager may approve their own referred deals; E3 consent wording approved by whoever owns privacy text.

## 1. Findings → work packages

| ID | Pri | Finding | WP |
|---|---|---|---|
| F-01 | P0 | PERCENT reward is snapshotted at WON, when no invoice exists, so it is ₹0 and cannot be paid. Never recomputed. [O] (side effect of the BUG-CRM-002 fix) | WP-4 |
| F-02 | P0 | Convert dialog defaults to "Mark as won", amount 0. WON is terminal, fires a FLAT reward with no sale, and the auto draft invoice then fails with no lines. [O] | WP-1 |
| F-03 | P0 | Opportunity edit dialog always sends `amount`; `validate_amount` rejects it whenever the deal has lines, so any edit of such a deal returns 400. [O] | WP-2 |
| F-04 | P1 | `resolve-dedupe` has no UI caller; a PENDING_REVIEW lead can't be cleared by a user; convert is not blocked while pending. [O] | WP-3 |
| F-05 | P1 | The dedupe answer "different" is overridden at convert: `convert_lead` re-matches by phone/email and links the existing customer. [O] | WP-3 |
| F-06 | P1 | Campaign ROI counts only quote→invoice links. Deals closed via Convert-as-won or `draft-invoice` show revenue 0. [O] | WP-5 |
| F-07 | P1 | Three revenue bases: referral PERCENT, campaign ROI, won-vs-invoiced (opportunity amount vs invoice `grand_total` incl. GST for all of the customer's invoices). [O] | WP-5 |
| F-08 | P1 | Board loads 100 rows newest-first with no paging; WON/LOST pile up and push older open deals off the board. [O] | WP-6 |
| F-09 | P1 | Mark-paid has no confirm; each reward row also offers "Draft credit note" (double-payout path); copy says "does not post a journal" [V]. | WP-4 |
| F-10 | P1 | Ingest jobs: only `BusinessRuleError`/`ValidationError` mark FAILED; any other exception leaves the job RUNNING. CSV: non-UTF-8 gives a 500; no size/row cap. [O] | WP-7 |
| F-11 | P1 | Referral codes can't be deactivated or listed; shown once after issue. [O] | WP-4 |
| F-12 | P1 | Public form exposes a numeric Campaign ID field; token can't be rotated; no company name or consent text. [O] | WP-7 |
| F-13 | P1 | WhatsApp expects flat `message_id/from/text`, not Meta's nested payload; one global `WHATSAPP_APP_SECRET`; URL token doubles as verify token. [V against Meta docs] | WP-7 |
| F-14 | P2 | `ingest_whatsapp_message` handles `IntegrityError` inside `@transaction.atomic` without a savepoint, then `lead.delete()`. Aborted transaction on Postgres. [V on Postgres] | WP-7 |
| F-15 | P2 | Lead `status`/`source` not validated on create/PATCH; no auto CONTACTED; no LOST reason; `last_touched_at` set only when null, never refreshed. [O] | WP-3 |
| F-16 | P2 | Lines can be added/removed and amount edited on WON/LOST deals; negative amounts allowed. [O] | WP-2 |
| F-17 | P2 | Probability defaults to 0, unrelated to stage; forecast is 0 until each deal is edited. [O] | WP-6 |
| F-18 | P2 | Subscription write gate applied on Leads only in the UI. **Server: `OpportunityViewSet.get_permissions` replaces the base list without `SubscriptionWritesAllowed` (only `draft_invoice` adds it), so an expired subscription can still write opportunities via API.** [O] The board confirms WON/LOST but the Opportunities edit dialog does not. | WP-2, WP-8 |
| F-19 | P2 | Checklist: "stage" step says lead but counts any opportunity move (convert-as-won never counts); "company" step says GSTIN and state but checks GSTIN only; every row shows "Next"; endpoint skips `assert_crm_enabled`. Owner counts as booker but round-robin only assigns `SALES_STAFF`. [O] | WP-3, WP-8 |
| F-20 | P2 | Pickers capped at 200 rows with raw IDs beyond; board lines show `#productId`; rewards show `#opportunityId` and raw enum; lead-edit customer Autocomplete is blank when a customer is linked. [O] | WP-8 |
| F-21 | P2 | Opportunities-page draft-invoice sends a random idempotency key (two clicks → two drafts); Convert/Assign/Save have no pending lock; board Save has no success feedback. [O] | WP-2 |
| F-22 | P2 | Opportunities list and Pipeline each edit a different half of a deal; a board user who needs a customer to win must go elsewhere. [O] | WP-6 |
| F-23 | P2 | `MvpModuleBanner` on Leads/Opportunities says "lead notebook, not a CRM pipeline" while Pipeline presents stages and a forecast. [O] | WP-8 |
| F-24 | P2 | Customer 360 `opportunity_total` sums every opportunity incl. LOST and WON; `growth_metrics.leads_with_customer` counts leads linked to a customer, not conversions. [O] | WP-5 |
| F-25 | P3 | Raw ISO timestamps; UTC month default in the won-vs-invoiced picker; unguarded clipboard writes; board cards not keyboard-focusable; no confirm on line removal; won-vs-invoiced has no error state and unformatted amounts; funnel block has no campaign name. [O] | WP-8 |
| F-26 | P3 | Campaign delete silently nulls lead attribution and re-parents children; leads can attach to DRAFT/COMPLETED campaigns. [O] | WP-5 |
| F-27 | P2 | Assign has no ownership check (any sales user reassigns any lead); any sales user can issue codes and set unbounded FLAT reward values. [O] | WP-3, WP-4 |

## 2. Order of work and dependencies

```
WP-1 (convert) ──┐
WP-2 (opportunity edit/lock/reopen) ──► WP-6 (board)
WP-5 (revenue link + definition) ──► WP-4 (rewards use it)
WP-3 (dedupe + lead lifecycle)   independent
WP-7 (capture hardening)         independent, needs a Postgres run
WP-8 (consistency sweep)         last in each PR, not one giant PR
```

PRs (each green on its own; stage only the files each PR names; the working tree is dirty with other work):

| PR | Content | Migrations | Needs |
|---|---|---|---|
| **PR-A** | WP-1 + WP-2 | crm 0016 (opportunity `lost_reason`, `reopened_at/by`) | D4, D6, D8 |
| **PR-B** | WP-5 then WP-4 | sales 0078 (invoice `opportunity`), crm 0017 (reward `needs_review`, `basis`; code `deactivated_at`) | D1–D3, D5, D12 |
| **PR-C** | WP-3 | crm 0018 (lead `lost_reason`, `duplicate_of`, `dedupe_decision`) | D7, D8, D13, D14 |
| **PR-D** | WP-6 | none | D9, D16 |
| **PR-E** | WP-7 | accounts 00xx (company WhatsApp secret) | D10, D11, E1 |
| **PR-F** | WP-8 | none | — |

Regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` in every PR that changes a serializer or route (CI drift-checks them). Never read those files whole; grep.

## WP-1 — Make convert-as-won deliberate (F-02) · PR-A

**Backend** [crm/services.py](../../backend/crm/services.py)
1. `convert_lead(..., won=True)` raises `BusinessRuleError("A won deal needs an amount or at least one line.")` when the amount ≤ 0 and the (new or existing) opportunity has no lines. Applies to both the create path and the existing-opportunity path.
2. `evaluate_referral_reward` is no longer called inside `convert_lead`; it is called from the stage-change path only (WP-2 keeps one call site).
3. `LeadViewSet.convert` ([crm/views.py](../../backend/crm/views.py)): `won` default stays False; response includes `needs_lines: true` when won was requested and no draft invoice can be made.

**Web** [LeadsPage.tsx](../../web/src/pages/crm/LeadsPage.tsx)
1. `convertWon` default `false`. When ticked, the amount field is required (> 0) and a one-line warning appears ("Closes the deal. Only an owner or manager can reopen it.").
2. After a won convert, if the draft invoice fails, navigate to the opportunity on the board with the error banner and "Add lines" focus, instead of a transient page error. Keep the dialog open until the mutation settles (today it closes immediately).
3. Disable the Convert button while pending; use `draftOpportunityInvoice` (stable key) only.

**Tests:** convert won with amount 0 and no lines → 400; convert won with amount → 200, WON, reward only after WP-4 rules; convert not-won → OPEN; double convert is idempotent (existing BB-000731 test still green).

**Done when:** a default convert never creates a terminal deal, and no reward row exists for a deal with no amount.

## WP-2 — Opportunity edit, closed-deal lock, reopen, server write gate (F-03, F-16, F-18, F-21, D4, D8) · PR-A

**Backend** [crm/serializers.py](../../backend/crm/serializers.py), [crm/views.py](../../backend/crm/views.py), [crm/growth_views.py](../../backend/crm/growth_views.py)
1. `validate_amount`: reject only when the value **differs** from the instance's amount and lines exist. Add `MinValueValidator(0)` on `Opportunity.amount` (migration crm 0016) and `probability` stays 0–100.
2. Closed-deal lock: when `instance.stage in (WON, LOST)`, `validate` rejects changes to `customer`, `lead`, `amount`, `title`; allowed: `competitor` only. `OpportunityLineViewSet` create/update/destroy returns 400 for a closed opportunity.
3. Reopen: new action `POST /crm/opportunities/{id}/reopen/` (owner/manager). Sets stage OPEN, clears `closed_at`, increments `stage_move_count`, writes `reopened_at/by`, audit entry. If a reward exists: PENDING → set REJECTED with `rejection_reason="deal_reopened"`; APPROVED/PAID → 400 "Reverse the reward first."
4. LOST requires `lost_reason` (D8): choices `PRICE, COMPETITOR, NO_RESPONSE, NOT_A_FIT, DUPLICATE, OTHER`; `OTHER` requires `lost_reason_note` (≤200). Fields on `Opportunity`; serializer rejects LOST without one. Existing LOST rows keep blank (migration leaves them).
5. `OpportunityViewSet.get_permissions`: build the list as `[*super().get_permissions(), ...]` so `SubscriptionWritesAllowed` applies to every write action (it is dropped today), keeping the special permission for `won_versus_invoices`.
6. `evaluate_referral_reward` called from one place after a WON transition (serializer `update`/`create` and nowhere else).

**Web** [OpportunitiesPage.tsx](../../web/src/pages/crm/OpportunitiesPage.tsx), [OpportunityPipelinePage.tsx](../../web/src/pages/crm/OpportunityPipelinePage.tsx)
1. Edit payload sends only changed fields; when the deal has lines, show Amount read-only ("from line items") and omit it.
2. Stage select in the edit dialog: WON/LOST go through the same `ConfirmDialog`; LOST asks for the reason; closed deals show the stage read-only plus a **Reopen** button for owner/manager.
3. Apply `useSubscriptionGate().writesBlocked` to every write control; disable lines add/remove on closed deals.
4. Opportunities-page draft-invoice uses `draftOpportunityInvoice`. Pipeline "Save" shows success feedback and a pending state.

**Tests:** edit title on a deal with lines → 200; change amount on a deal with lines → 400; PATCH a WON deal's customer → 400; add a line to a WON deal → 400; LOST without reason → 400; reopen role matrix (owner, manager OK; sales staff 403); reopen with PENDING/APPROVED reward; expired subscription → opportunity PATCH 402/403 (match the existing gate response); negative amount → 400.

**Done when:** F-03 repro test passes; a closed deal's numbers cannot change; reopen is audited.

## WP-3 — Dedupe review and lead lifecycle (F-04, F-05, F-15, F-19, F-27, D7, D8, D13, D14) · PR-C

**Backend** [crm/views.py](../../backend/crm/views.py), [crm/pipeline.py](../../backend/crm/pipeline.py), [crm/services.py](../../backend/crm/services.py), [crm/models.py](../../backend/crm/models.py)
1. Lead fields (migration crm 0018): `lost_reason`, `lost_reason_note`, `duplicate_of` (FK self, SET_NULL), `dedupe_decision` (`""|"different"|"same"`).
2. `resolve-dedupe` decisions become `different`, `same_customer`, `same_lead`:
   - `different` → clears review, sets `dedupe_decision="different"`, keeps assignment logic.
   - `same_customer` → links `customer`, clears review.
   - `same_lead` → new lead becomes LOST with `lost_reason=DUPLICATE`, `duplicate_of` = original; activities of the new lead are copied to the original with a "moved from duplicate" note; unassigned.
   Keep accepting the old `new`/`match` values for one release.
3. `convert_lead`: raise if `dedupe_review == PENDING_REVIEW`; when `dedupe_decision == "different"` skip the phone/email auto-link and create a new customer (or raise the existing "multiple customers share this phone" message only if the customer form would also reject it).
4. Validation: `LeadSerializer.validate_status` against `Lead.Status`; `validate_source` against `SOURCES`; remove the raw `setattr` loop in `create`, route `state/gstin/address/status` through the serializer; LOST requires `lost_reason`; QUALIFIED can't be set manually when no opportunity exists (it's set by convert).
5. Lifecycle: first CALL/EMAIL activity moves NEW→CONTACTED; activity create, status change, assign and convert update `last_touched_at` (fix the `save()` rule so it refreshes when `update_fields` includes `updated_at` from those paths, via an explicit `touch()` method).
6. Assign (D14): owner/manager, or the current assignee reassigning their own lead; others 403. Un-assign stays owner/manager.
7. Routing (D13): `next_assignee` falls back to the active owner when there are no `SALES_STAFF`.
8. Onboarding ([crm/onboarding.py](../../backend/crm/onboarding.py)): `assert_crm_enabled`; "company" step checks GSTIN **and** state (unregistered companies: state only); "stage" step counts a moved opportunity linked to a lead; step titles match what is checked.

**Web** [LeadsPage.tsx](../../web/src/pages/crm/LeadsPage.tsx), [CrmOnboardingPage.tsx](../../web/src/pages/crm/CrmOnboardingPage.tsx), `api/crm.ts`
1. "Review" button on PENDING_REVIEW rows → dialog listing each candidate (name, phone, email, status, last activity) with "Same customer", "Same as earlier lead", "Different person". Also use it for the 409 prompt so candidates show detail, not bare names/IDs.
2. Lead edit: LOST asks for the reason; the customer Autocomplete is controlled and shows the linked customer.
3. Add search (name/phone), status and assignee filters (the API already supports assignee). Activities dialog: formatted timestamps, author, due/overdue chips.
4. Checklist page: completed steps show a tick and no "Next"; progress count.

**Tests:** resolve each decision; convert blocked while pending; "different" then convert → new customer; invalid status/source → 400; first CALL → CONTACTED; `last_touched_at` refreshed by activity; assign role matrix; owner-only company routes to owner; checklist steps.

## WP-4 — Referral rewards you can trust (F-01, F-09, F-11, F-27, D1, D2, D5, D12, D14) · PR-B

**Backend** [crm/referrals.py](../../backend/crm/referrals.py), [crm/growth_views.py](../../backend/crm/growth_views.py), [crm/models.py](../../backend/crm/models.py)
1. Migration crm 0017: `ReferralReward.basis` (`FLAT|PERCENT`), `ReferralReward.review_note` (`""|"existing_customer"`), `ReferralCode.deactivated_at/by`.
2. `evaluate_referral_reward`: FLAT → amount at WON as today; PERCENT → create the reward with `reward_amount=0, basis=PERCENT` (status PENDING) and no calculation. Existing-customer check (D2): if the lead matched an existing customer before this deal (dedupe candidates or a customer created before `lead.created_at`), set `review_note="existing_customer"` (stays PENDING; not auto-rejected).
3. Approve for PERCENT is allowed, but **mark-paid computes the amount** inside the transaction: `reward_amount_for(PERCENT, value, base)` with `base = invoiced_taxable_for_opportunity` (WP-5 definition). If the base is 0 → `BusinessRuleError("No completed invoice yet for this deal.")`, reward stays APPROVED. The computed amount is stored on the reward before drafting the credit note.
4. `deactivate` action on `ReferralCodeViewSet` (owner/manager). `resolve_referral_code` already ignores inactive codes. Issuing codes and reward values: owner/manager only (D14); FLAT value capped by a company setting default ₹10,000 (override by owner) [V choose cap].
5. Credit-note shortcut: `mark_reward_paid` stays the only payout path. Add `credit_note` link validation so a manually drafted note with `reason_detail` "Referral reward N" is rejected as a duplicate of an existing reward note.
6. Leaderboard returns referrer names and counts; rewards endpoint returns `lead_name`, `customer_name`, `referrer_name`, `code`.
7. Code-level fact to confirm for D5: whether `SalesNotesService.complete_credit_note` posts ledger/GL entries. Record the answer in this doc and in the PR; flag for CA sign-off.

**Web** [ReferralsPage.tsx](../../web/src/pages/crm/ReferralsPage.tsx)
1. Codes table (code, referrer, type/value, uses, rewards earned, status) with Deactivate and Copy link; issue form validates value (≥ 0, ≤ 100 for PERCENT).
2. Rewards list as a table: referred lead/customer, referrer, code, amount (PERCENT: "set when paid"), status chip (translated), existing-customer warning chip.
3. Mark-paid `ConfirmDialog`: referrer, amount or "calculated now", "Creates and completes a credit note for the referrer" (neutral copy per D5). Remove the per-row "Draft credit note" link and the "does not post a journal" string; update `growth.markPaidHint` and `cog.settleNoJournal` in `en.ts` and `hi.ts` (keep `planCopy.test.ts` keys).
4. Employee referrers: no issue UI (unchanged); API rewards for them stay approve/reject only.

**Tests:** PERCENT: WON → reward 0; invoice completes; mark-paid → amount > 0, credit note COMPLETED once, status PAID; mark-paid with no invoice → 400, stays APPROVED; existing-customer flag; deactivate then use code → lead without reward; role matrix for issue/approve/pay; manual credit note duplicate rejected; double click mark-paid (idempotency key) → one credit note; `test_growth_os.py`, `test_referral_*` updated, not deleted.

## WP-5 — One revenue definition (F-06, F-07, F-24, F-26, D3, D15) · PR-B

**Backend** [sales/models.py](../../backend/sales/models.py), [crm/campaigns.py](../../backend/crm/campaigns.py), [crm/forecast.py](../../backend/crm/forecast.py), [insights/customer_360.py](../../backend/insights/customer_360.py), [insights/growth_metrics.py](../../backend/insights/growth_metrics.py)
1. Migration sales 0078: `SalesInvoice.opportunity` FK (`crm.Opportunity`, null, SET_NULL, related_name `invoices`, index on `(company, opportunity)`). Set by `draft_invoice`, by quotation→invoice conversion (copy `quotation.opportunity`), and by quote→order→invoice. Backfill command `backfill_invoice_opportunity` reads the existing `QuotationConversion` chain (reuse the logic now in `_won_revenue`), dry-run by default.
2. New helper `crm/revenue.py::opportunity_revenue(opportunity)` = sum of `taxable_total` of COMPLETED invoices with `opportunity=opportunity`, minus COMPLETED credit-note `taxable_total` against them. `_won_revenue`, `invoiced_taxable_for_opportunity` and `won_versus_invoices` all call it; the old chain-walking stays only inside the backfill.
3. `won_versus_invoices`: "won" = `opportunity.amount` (ex-GST) vs "invoiced" = helper total (ex-GST) for the **same opportunities**, not all invoices of the customers. Response labels the basis.
4. `_direct_stats`: aggregate queries instead of a per-opportunity loop; funnel payload includes `campaign_id`, `campaign_name`, `roi_basis`, and `roi_ratio` (revenue ÷ budget) labelled planned budget.
5. Customer 360: `opportunity_total` split into `open_pipeline_total` and `won_total` (keep `opportunity_total` as the sum of both for one release). `growth_metrics`: `leads_converted` = leads with an opportunity; keep `leads_with_customer`.
6. Campaign delete (D15): `perform_destroy` blocks when leads or children exist (400 with counts); leads can attach only to DRAFT/ACTIVE campaigns (serializer and `resolve_campaign`); PAUSED/COMPLETED campaigns keep reporting.

**Web:** campaign funnel shows the campaign name, basis line and per-opportunity rows with names; delete confirm explains the block; won-vs-invoiced shows formatted ex-GST amounts and an error state.

**Tests:** draft-invoice sets the link; quote→invoice conversion sets the link; backfill dry-run/apply on quote→order→invoice chains; revenue helper with a partial credit note; funnel for convert-won deals ≠ 0; delete campaign with leads → 400; aggregated stats query count stays flat (assert `django_assert_num_queries` upper bound).

## WP-6 — Pipeline board you can rely on (F-08, F-17, F-22, D9, D16) · PR-D

**Backend** `OpportunityViewSet`: filters `stage`, `stage__in`, `closed_since`, `lead`, `customer`, `q`; ordering `-updated_at`. Stage-change path sets default probability (D9) when the previous probability equals the previous stage's default or 0 (i.e. the user never customised it). New `GET /crm/opportunities/board/` returns per-stage `{count, total_amount, results[≤25], next}` with open stages unfiltered and WON/LOST limited to `closed_since` (default 90 days).

**Web** [OpportunityPipelinePage.tsx](../../web/src/pages/crm/OpportunityPipelinePage.tsx): board uses the board endpoint, each column shows count and total, "Load more", and WON/LOST "Show older". Card detail edits customer and lead inline (searchable), shows product names on lines, makes cards focusable (`role="button"`, Enter/Space opens detail), disables WON/LOST drops on touch. Forecast explains stage defaults; month picker uses local date; won-vs-invoiced error state.

**Tests:** 150 closed + 20 open → board shows all 20 open; stage move applies default probability but keeps a custom one; forecast non-zero after one stage move; per-column paging; keyboard open.

## WP-7 — Capture hardening (F-10, F-12, F-13, F-14, D10, D11) · PR-E

**Backend** [crm/tasks.py](../../backend/crm/tasks.py), [crm/views.py](../../backend/crm/views.py), [crm/pipeline.py](../../backend/crm/pipeline.py), accounts model
1. `process_lead_ingest`: catch `Exception`, mark FAILED with a short error, log with job id and company, never leave RUNNING. Add a beat task `reap_stale_lead_ingest_jobs` (RUNNING > 15 min → retry once, then FAILED).
2. CSV: file size cap (2 MB) and row cap (2,000) with clear 400s; decode utf-8-sig then cp1252; header aliasing (case/space-insensitive, `mobile`→phone); extra optional columns `state, gstin, address, source`; the job result includes up to 100 row errors and the UI offers them as a downloadable CSV. Purge `payload` after completion (E1).
3. WhatsApp: parser for Meta's `entry[].changes[].value.messages[]` (+ contact names), keep the flat format; per-company secret: `Company.whatsapp_app_secret` (encrypted field pattern used elsewhere [V]) with owner-only set/rotate; verify token stored separately from the URL token; signature check uses the company secret, falling back to the global setting only when unset. Idempotency create wrapped in `transaction.atomic()` (savepoint) around `IdempotencyRecord.objects.create`.
4. Public form: accept a signed `campaign` param (`signing.dumps`, 1 year) instead of a raw ID; ignore raw numeric campaign from the public endpoint; response never echoes Django `ValidationError` dicts (map to short messages); `rotate` option on `form-token` (owner/manager); keep honeypot and per-IP throttle; add a per-token daily cap (setting, default 500).

**Web:** [LeadFormPage.tsx](../../web/src/pages/public/LeadFormPage.tsx): company name (from a new public `GET /crm/public/lead-form/{token}/meta/`), consent line (E3 wording), no Campaign ID field, 429/400 messages in plain language. LeadsPage capture menu: guarded clipboard (fallback to a text field), "Replace form link" for owner/manager, import progress with failure and downloadable row errors.

**Tests (include Postgres run):** non-UTF-8 CSV; oversize CSV; unexpected exception → FAILED; real Meta payload fixture; duplicate `message_id` race on Postgres; wrong/missing signature; per-company secret; signed campaign param valid/tampered; form token rotate invalidates the old link.

## WP-8 — Consistency sweep (F-18, F-19, F-20, F-23, F-25) · PR-F

Runs as small commits inside each PR above where the file is already touched; PR-F collects the rest.
- Subscription gate on every CRM write control (Opportunities, Pipeline, Campaigns, Referrals).
- Replace the 200-row pickers with `CustomerField` / a new `LeadField` (search-as-you-type); never show a raw ID where a name is available.
- Banner copy: replace "lead notebook, not a CRM pipeline" with one accurate sentence per page; align Pipeline/Opportunities wording.
- Dates via the shared formatter, money via `formatMoney`, enum labels via `enumLabel`; keyboard focus on board cards; confirm before removing a line; `en.ts` and `hi.ts` updated together (parity tests).
- Campaign page: funnel placed next to the selected row, status filter, parent tree indicator.

## 3. Test matrix (cross-cutting)

1. Edit title of a deal with lines → 200 (WP-2). 2. Convert-won with no amount/lines → 400 (WP-1). 3. PERCENT code → WON → invoice completes → mark-paid → reward > 0, credit note once (WP-4/5). 4. "Different person" then convert → new customer (WP-3). 5. PENDING_REVIEW resolvable in UI; convert blocked until resolved (WP-3). 6. cp1252 / oversize CSV (WP-7). 7. Real Meta payload + duplicate-id race on Postgres (WP-7). 8. Board with 150 closed + 20 open (WP-6). 9. Convert-won → draft invoice → complete → funnel revenue ≠ 0 (WP-5). 10. Double click draft-invoice / mark-paid / convert → one document (WP-2/4). 11. Role matrix: sales staff, manager, accountant, viewer, owner on assign, issue-code, approve, mark-paid, reopen, delete. 12. Campaign delete with attached leads → 400 (WP-5). 13. Closed-deal lock + reopen reverses a PENDING reward (WP-2/4). 14. Deactivated code → no reward (WP-4). 15. Expired subscription: every CRM write endpoint refuses (WP-2). 16. Cross-tenant: ids from another company on every FK field and action.

## 4. Regression risk and suites to re-run

- **HIGH:** `convert_lead`, stage transitions, `evaluate_referral_reward`/`mark_reward_paid`, revenue helper (shared with sales, quotations, credit notes). Re-run `test_sprint_b_crm_convert.py`, `test_growth_os.py`, `test_referral_paid_status.py`, `test_referral_self_referral_guard.py`, `test_os_vision_plan.py`, `test_itc_digest_and_lead_reminders.py`, quotation tests, credit-note tests.
- **MEDIUM:** `capture_lead`/dedupe (CSV, form, WhatsApp and manual share it); the invoice FK (serializers, openapi snapshot, `openapi-types.ts`, Q-OS journey cells).
- **LOW:** campaign CRUD, checklist.
- Gates every PR must pass: backend tests (private-DB recipe in memory; concurrency/Postgres tests need the Postgres run), `ruff`, `tsc -b`, web lint (0-error, CI-gated), i18n parity tests, `qos-lint`.

## 5. Rollout

- Keep `ENABLE_REFERRALS` off for real payouts until PR-B is merged and D5 is signed off by the CA.
- Migrations are additive (nullable columns, new indexes). Run `backfill_invoice_opportunity --dry-run` on staging before `--apply`. Existing PERCENT rewards with amount 0 (status PENDING/APPROVED) are listed by a one-off report command and left for the manager to decide; nothing is auto-paid.
- Existing rows with LOST and no reason stay valid; the UI shows "—".
- Hindi review for new strings goes into `docs/CRM_HINDI_REVIEW.csv` (same format as the Money Hub/Purchase files).

## 6. Review verdict (code-only)

🟡 READY WITH FIXES. The core lead → opportunity → quote path is sound; idempotent quotation, terminal-stage protection, self-referral guard and tenant scoping are good. The money-adjacent paths (referral rewards, campaign ROI, convert-as-won) and the stuck-state paths (dedupe review, ingest jobs, board truncation, opportunity edit) are not. Overall 5/10.

## 7. Verification status and open items

- **[R] Reproduced 2026-10-16** by `backend/tests/test_crm_review_repro.py` (4 tests, all fail for the stated reason; run with a private settings module, `--reuse-db`): F-02 convert-won with amount 0 returns 200; F-03 title edit on a deal with lines returns 400 "Amount is derived from line items."; F-18 opportunity PATCH returns 200 while the lead PATCH control returns 403; F-01 mark-paid returns 400 "The reward amount must be positive…" for a PERCENT reward after the deal is invoiced. All other findings are still from reading code. Still to run: F-14 on Postgres.
- Not yet read: `insights/attention`, admin pages, Hindi strings, existing tests' assertions.
- External facts still unconfirmed: Meta's webhook shape (F-13), GL posting of credit notes (F-09/D5), the FLAT-value cap default ([V] in WP-4).
- Open questions E1–E3 in §0.

## 8. Implementation record (2026-10-16 / 10-17)

**PR-A — WP-1 + WP-2: built.** Convert-as-won needs an amount (existing deals: amount or lines); "Mark as won" is off by default; edit sends only changed fields and an unchanged derived amount no longer 400s; closed deals are locked except the competitor note and their lines are locked; LOST needs a reason (migration `crm/0016`); owner/manager `reopen` action rejects a pending reward and refuses once approved/paid; `OpportunityViewSet` keeps `SubscriptionWritesAllowed`; negative amounts refused. Deviation: `convert_lead` still creates the FLAT reward itself when a deal is won with a real amount (moving it would have broken the existing referral tests).

**WP-6 — pipeline board: built.** `GET /crm/opportunities/board/` (first 25 per stage with count, total and `older`; open stages never windowed, WON/LOST default to the last 90 days); list filters `stage`, `closed_days`, `customer`, `lead`, `q`; stage default probability (10/30/60/100/0) on create, convert, stage move and reopen, kept when the user set their own number. Web: per-column counts and totals, "Load more", "Show N older", inline customer picker on the card detail, product names on lines (`product_name`), keyboard-focusable cards, local-time month default, formatted won-vs-invoiced with an error state. Existing test `test_opportunity_competitor_is_stored_and_ignored_by_forecast` now expects the 10% default (50.00 instead of 0).

**WP-8 sweep: built, except the items that belong to other packages.** Done: subscription gate on Opportunities, Pipeline, Campaigns, Referrals; names returned by the API (`customer_name`, `campaign_name`, `lead_name`) instead of 200-row lookups; searchable `LeadField`/`CustomerField` pickers (lead `q` and `status` filters); lead edit shows the linked customer; clipboard failure shows the link; activity timestamps formatted; line-removal confirm; banner copy replaced ("leads, deals and a simple forecast"); forecast bars formatted; Campaigns: funnel opens under its own row with the campaign name, status filter (server-side), "under <parent>" label. Left for their packages: checklist logic and owner routing (WP-3), rewards table and referral formatting (WP-4), campaign delete block (WP-5), Leads-page search/status filters UI (WP-3).

Tests: `test_crm_review_repro.py` (F-01 still fails by design until PR-B), `test_crm_pipeline_board.py`, updated Opportunities/Pipeline/Leads/Campaigns web tests. OpenAPI snapshot and `openapi-types.ts` patched for the CRM changes only (other sessions' drift left alone).

## 9. Implementation record, part 2 (2026-10-17)

**WP-5 — one revenue definition: built.** `SalesInvoice.opportunity` (sales/0078) is set by `draft-invoice` and by quote, order and challan conversion; releasing a quote conversion clears it. `crm/revenue.py` is the only revenue calculation: completed-invoice taxable value minus completed credit notes, found through the link and, for older data, through the quote→order→challan chain, in a fixed number of queries. Campaign ROI (now with campaign name, basis text, per-deal titles), referral PERCENT and won-vs-invoiced (same deals, before GST) all read it. `backfill_invoice_opportunity` (dry run by default, `--apply` to write, skips ambiguous invoices). Customer 360 now has `open_pipeline_total`, `won_total` (and `opportunity_total` = open + won, lost excluded); growth metrics add `leads_converted`. A campaign with leads or sub-campaigns cannot be deleted; paused or completed campaigns take no new leads.

**WP-4 — referral rewards: built.** crm/0017. PERCENT rewards start at 0 with `basis=PERCENT` and are worked out at mark-paid from the deal's own invoices; no invoice → 400 and the reward stays APPROVED (F-01 test passes). A referred person who was already a customer gets `review_note=existing_customer` (stays PENDING for the manager). Codes: `deactivate` (owner/manager), owner/manager-only issuing, FLAT reward above ₹10,000 needs the owner. New `reverse` action takes back an APPROVED reward so the deal can be reopened. A hand-made credit note with reason "Referral reward N" is refused. Web: codes table (uses, rewards, copy link, deactivate), rewards table with names and translated status, existing-customer chip, mark-paid confirm with neutral copy, "Draft credit note" shortcut and "does not post a journal" text removed. D5 stays neutral until the CA signs off (see open items).

**WP-3 — dedupe and lead lifecycle: built.** crm/0018. `resolve-dedupe` takes `different`, `same_customer`, `same_lead` (old `new`/`match` still work); same-lead closes the new lead as LOST/duplicate and moves its notes. Convert is blocked while a review is pending and does not relink a lead answered "different". Lead status, source and GSTIN are validated; QUALIFIED needs a deal; LOST needs a reason; a first call or email moves NEW to CONTACTED; activities, status changes, assign and convert refresh `last_touched_at`. Reassigning is limited to owner, manager or the current assignee; a company with no sales staff routes to the owner. Checklist: needs CRM enabled, checks state (and GSTIN unless unregistered), counts a deal from a lead that left OPEN. Web: Review dialog with candidate details (also used in the duplicate prompt, which no longer shows bare IDs), search/status/assignee filters, lost-reason prompt, author names on activities, checklist ticks and progress count.

**WP-7 — capture hardening: built.** accounts/0063. Import jobs always end DONE or FAILED (unexpected errors logged, user sees a plain message), a reaper retries a stuck job once then fails it, and job rows are cleared on completion (E1 default). CSV: 2 MB and 2,000-row caps, UTF-8 then cp1252, header aliases, optional state/gstin/address/source columns, up to 100 row errors returned and downloadable. WhatsApp: Meta's nested payload (flat format still works), contact name used, per-company sealed app secret (owner-only, never returned; falls back to the server secret only when none is saved), separate verify token, savepoint around the idempotency insert. Public form: company name and consent line from a GET on the same URL, campaign only through a signed link value (raw numbers are ignored), form-token rotate (owner/manager), daily cap (`LEAD_FORM_DAILY_CAP`, default 500), plain 429 message. Campaigns page has "Copy form link" for the signed link.

**WP-8 leftovers: built.** Referrals formatting and statuses, checklist polish, Leads search/status/assignee filters, raw-ID fallback in the duplicate dialog removed, `docs/CRM_HINDI_REVIEW.csv` created (292 rows) for a native reviewer.

**BUGS_LIST:** BUG-CRM-001, -002, -003, -004, -005 are fixed by the above and earlier work (annotated there).

**Deviations and decisions made without asking:** (1) `convert_lead` still calls `evaluate_referral_reward` itself on a won convert; this is the same single stage-change moment as the serializer path, and the reward is now 0 for PERCENT, so the earlier concern is closed. (2) Flat reward cap fixed at ₹10,000 in code (owner may exceed), not a company setting. (3) Consent wording is a placeholder in `LEAD_FORM_CONSENT_TEXT` (E3 still needs an owner). (4) Payload purge at completion implements E1 conservatively. (5) A reopened deal whose reward was rejected does not earn a second reward.

**Tests:** new `test_crm_review_phase_b.py` (30 tests); updated `test_crm_review_repro` (F-01 now passes), `test_review_fixes`, `test_bug_open_verticals`, `test_os_vision_plan`, `test_sprint_b_crm_convert`, `test_crm_pipeline_board`, `test_llm_path_to_ten`; web: Referrals, Leads, Onboarding, Lead form tests. Backend CRM-related suites 587 passed; the only failures are not CRM (`test_bug_acc_013` reads banking view source; two `test_provision_ux_audit` tests hit an inventory unique constraint in the private test DB). Web: CRM, public and i18n suites 96 passed, `tsc -b` clean, ESLint and ruff clean. OpenAPI snapshot and `openapi-types.ts` patched for the CRM changes only.

**Still open (cannot be closed from code):** run the Postgres-only tests (F-14 savepoint, concurrency) on Postgres; a browser pass of Leads, Referrals, Pipeline and the public form; CA sign-off that completing the reward credit note posts the ledger entries (D5 copy); confirm Meta's live payload against a real test message; native Hindi review of `CRM_HINDI_REVIEW.csv`; E2 (manager approving own referred deals) and E3 (consent wording owner); `insights/attention`, admin pages and mobile layouts were never in scope of this review.
