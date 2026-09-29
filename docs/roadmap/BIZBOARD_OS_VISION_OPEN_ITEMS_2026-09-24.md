# Open Items — 2026-09-24

Follow-up plan for everything flagged as open or partially implemented after the deep review. The credit override, trial-plan Part A, and F1–F9 are implemented. Supplier scoring and paid-tier Part B stay out of scope.

## Decisions resolved this round

1. **Credit gate override** — add an audited override path for credit-limit breaches at Sales Order confirmation. New scope, OWNER-only permission locked in.
2. **Supplier scoring** — stays numbers-only, permanent. No further work.
3. **Pack entitlements** — wire real `Plan.modules` entries so a company's subscription actually gates which pack flags can turn on. Part A (below) is ready to execute now; Part B (real paid tiers) has no safe default and stays an open question for you — it's a pricing decision, not an engineering one.
4. **Retail/Trade flag split** — locked in as F9 below (four flags added to the existing `accounts/packs.py` split).

## Scope and locked defaults, 2026-09-24

Build only this document: the credit override, trial-plan Part A, and F1–F9. Supplier scoring and paid-tier Part B stay untouched. The 2026-09-23 implementation plan stays as history and is not edited.

Locked with the answers below, no further objection:

- Override is owner-only. All three audit fields are stamped together, never partially. A blank or whitespace-only reason still blocks.
- Margin stays warn-only. The shared helper uses a strict `< 5%` comparison, so exactly 5% does not warn.
- `credit_limit = 0` stays unlimited.
- Dark modules stay out of the trial `modules` dict. They are not in `ROLLOUT_GRANTABLE_KEYS`.
- `ENABLE_SETUP_WIZARD` and `ENABLE_GSTN_JSON` stay out of both packs.
- The round-robin row lock ships without a Postgres race test.
- A reserved key in `log_flag_event`'s `**fields` (`tenant_id`, `flag`, `flag_state`, `event`) raises instead of overwriting the real value.
- Preview gate-check stays a plain yes/no block. Nothing is committed there, so there is nothing to audit.
- F4 generates a fresh WhatsApp token. Nothing is live, so there is no backward-compat with the lead-form token.
- F9 does not backfill companies that already confirmed a pack. They pick up the four new flags only by confirming again.

## Flag split — review, not a fresh draft

`accounts/packs.py` already defines `retail` (7 flags) and `trade` (10 flags), with `distribution`/`manufacturing` correctly held back until their underlying features mature — matching the roadmap's own wave sequencing. Comparing against the full `ROLLOUT_GRANTABLE_KEYS` list (18 company-grantable flags), four are grantable but sit in neither pack. **Locked in — adding these four to `packs.py`:**

| Flag | Add to | Why |
| --- | --- | --- |
| `ENABLE_ROUTE_OPTIMIZATION` | trade | Natural companion to `ENABLE_ROUTE_PROFIT`, already in trade — same delivery-route feature area. |
| `ENABLE_TDS` | trade | TDS deduction is a B2B/trade concern; retail counter sales rarely trigger it. |
| `ENABLE_TALLY` | trade | Tally import/export matters most to B2B accounting workflows. |
| `ENABLE_GSTR` | retail and trade | GST return filing is relevant everywhere `ENABLE_GST_GUARD` already is (both packs), and it's odd to guard GST health without also enabling GST returns. |

**Left out on purpose:** `ENABLE_SETUP_WIZARD` and `ENABLE_GSTN_JSON` — the wizard flag looks like a general onboarding switch, not archetype-specific, and GSTN JSON export is a niche filing-detail flag better left to manual enablement than bundled by default.

Proceeding on the recommendation above, no objection raised — F9 below adds these four lines to `packs.py`.

## New ticket — audited credit-gate override

**Goal.** Let an authorized user confirm a Sales Order over its customer's credit limit anyway, with a mandatory reason and a durable audit trail — margin stays warn-only and untouched.

**Data model.** Three nullable fields on `SalesOrder` (additive migration, no backfill): `credit_override_reason` (`CharField`, `max_length=500`, blank), `credit_overridden_by` (FK to `accounts.CompanyUser`, null), `credit_overridden_at` (datetime, null). The same three fields, also nullable and additive, on `SalesInvoice`. A field-level audit trail on the document itself is enough — an order is confirmed once, so there is no history of multiple overrides to track.

**Invoice provenance — locked 2026-09-24.** The override covers the invoice created from that same overridden order, not a blanket pass for the customer. When an invoice is created from an order that already carries an override, copy the three fields onto the invoice at creation time. The invoice credit check skips itself only when the invoice already carries that copied override. This covers `convert_chain` in one call and a challan converted to an invoice later from the same order. An unrelated invoice for the same customer still hard-blocks.

**Permission — locked in.** Only `CompanyUser.Role.OWNER` may override.

**Service layer.** `sales/order_gates.py`'s `apply_order_gates(order, items, *, override_reason=None, acting_user=None)`: when the credit check fails, if `override_reason` is a non-blank string of at most 500 characters AND `acting_user` is an OWNER, skip the `BusinessRuleError`, stamp all three fields on `order` together, and still return margin warnings as today. No reason, a whitespace-only reason, a reason over 500 characters, or a non-owner → exactly today's hard block. The invoice credit check reads the copied fields; it does not accept a fresh reason of its own.

**API.** Extend the Sales Order confirm endpoint's request body with an optional `credit_override_reason` field, threaded through to `apply_order_gates`. `convert_chain`'s call to `confirm_sales_order` passes the same optional field through. The gate-check preview stays a plain yes/no block and does not accept a reason — nothing is committed there.

**Frontend.** On a credit-block error, show the override reason field (500 characters) only to owners; submitting re-calls confirm with the reason attached. English and Hindi.

**Tests.** Override with a valid reason and an owner succeeds and stamps all three order fields; a non-owner still blocks; blank or whitespace-only reason still blocks; a reason over 500 characters blocks; `credit_limit=0` is unaffected; an invoice created from the overridden order copies the three fields and its credit check does not re-block; an unrelated invoice for the same customer still blocks; `convert_chain` end-to-end with an override does not re-block the invoice it creates; preview does not persist a reason.

**DoD.**

- [x] Override requires both a non-blank reason of at most 500 characters and an OWNER.
- [x] All three audit fields stamped together on the order, never partially.
- [x] The invoice created from that order copies the three fields, and only that invoice skips the credit block.
- [x] Preview stays yes/no and writes nothing.
- [x] No override path affects margin's warn-only behavior.
- [x] Existing no-override tests still pass unchanged when no reason is supplied.

**Effort.** 1.5–2 weeks. Permission is answered: OWNER only.

## New ticket — wire real pack entitlements

**Finding that changes this ticket's scope.** Only one `Plan` is seeded today — `"trial"`, with `modules: {}` — and no tiered commercial plans (starter/pro/business, or similar) exist anywhere in the codebase yet. `_entitled()` isn't buggy so much as there's genuinely nothing to be entitled *against* yet. "Wire real entitlements" therefore splits into two different pieces of work:

**Part A — interim technical fix (buildable now, no business input needed).** Populate the trial plan's `modules` dict with all `ROLLOUT_GRANTABLE_KEYS` set to `True`, so `_entitled()` stops relying on the accidental "empty dict falls through to `True` anyway" behavior and instead reflects an explicit decision. Zero behavior change for existing tenants (trial already gets everything), but closes the silent-no-op gap honestly.

**Part B — deferred.** No tier names, prices, or per-tier flag lists were given. Do not invent them. Part B stays unscoped until that commercial decision exists.

**Data model (Part A only).** `modules` is already a JSONField, but `Plan.objects.get_or_create(..., defaults={"modules": {}})` only applies `defaults` on insert. Every trial row that already exists stays on `{}` unless a migration updates it. Add a data migration in `billing/migrations/` that runs `Plan.objects.filter(slug="trial").update(modules=<every ROLLOUT_GRANTABLE_KEYS entry set to True>)` (RunPython is fine). Also set that same dict in `ensure_register_trial`'s `get_or_create` defaults so a trial plan created after the migration is born explicit. Dark-module keys are not written into `modules`.

**Tests (Part A).** `_entitled(company, key)` returns `True` for every `ROLLOUT_GRANTABLE_KEYS` member on a trial-plan company, and still `False` for `DARK_MODULE_KEYS` regardless of `modules` content — locking in today's behavior as an explicit assertion instead of an implicit fallthrough.

**DoD (Part A).**

- [x] A billing data migration sets the existing `slug="trial"` plan's `modules` to every `ROLLOUT_GRANTABLE_KEYS` entry as `True`.
- [x] New trial plans created after that migration get the same explicit dict, not `{}`.
- [x] No behavior change for any existing company. Dark modules stay off.
- [x] Part B (tier names, pricing, per-tier flag lists) stays deferred and is not guessed.

**Effort.** Part A: 2–3 days. Part B: unscoped until tier design exists.

## Cleanup tickets — the remaining unfixed findings

### F1. Order-gate exposure double-counts a partially fulfilled order

**Locked 2026-09-24.** A `SalesOrder` can have multiple `DeliveryChallan`s, each becoming its own `SalesInvoice`, so an order can be partially invoiced while staying CONFIRMED. A direct SO→invoice conversion flips the order to CONVERTED, which the exposure query already excludes. The bug: `sales_order_exposure`'s "others" sum still uses the full `grand_total` for a CONFIRMED order after part of it is already inside `LedgerService.customer_exposure_for_credit_limit`. **Fix.** For each CONFIRMED order in the "others" query, subtract only the value that `customer_exposure_for_credit_limit` itself counts for invoices of that order. Read the ledger function and use its own counted figure — do not assume `grand_total`, and do not try to match the challan's value. Leave drafts and cancelled invoices out of the subtraction; the ledger has not picked that money up, so subtracting them would under-count exposure. **Tests.** An order partially invoiced via one challan, with a second challan still pending: exposure counts the pending portion once and does not count the ledger-included invoice twice. A draft or cancelled invoice from the same order is not subtracted. **Effort.** 3–5 days.

### F2. `margin_warnings` duplicates the `MARGIN_DROP_SKU` formula

**Fix.** Extract the shared `(price - cost) / price < threshold` calculation into one helper (e.g. `core/services/margin.py::margin_ratio`) and have `sales/order_gates.py`, `insights/services.py`, and `insights/alerts.py` all call it. Threshold stays `Decimal("0.05")` and the comparison stays strict `<`, so a margin of exactly 5% does not warn. **Tests.** A regression test asserting all three call sites produce the same ratio for the same inputs, including the exact-5% case. **Effort.** 2–3 days.

### F3. CRM round-robin assignment race

**Fix.** Wrap the count query and assignment decision in `next_assignee` inside `transaction.atomic()` with `select_for_update()` on the counted `CompanyUser` rows, serializing concurrent `capture_lead` calls for the same company. **Tests.** Add the row lock, and cover fairness over the 30-day window with a regular test. Do not add a Postgres race test in this pass; SQLite does not serialize `select_for_update()`, matching the CR-001/002/003 precedent noted at the bottom of this doc. **Effort.** 2–3 days.

### F4. WhatsApp webhook and public lead-form share one discoverable token

**Fix.** Add `whatsapp_webhook_token` on `Company`, separate from `lead_form_token`, generated the same way (`secrets.token_urlsafe(24)`); point `WhatsAppInboundView` at the new field. Nothing is live (the inbound flag defaults off and no tenant has registered a webhook), so the data migration backfills a fresh token and does not preserve or alias the lead-form token. **Tests.** The WhatsApp endpoint no longer resolves via the public form's token; a company's two tokens differ. **Effort.** 2–3 days including that backfill.

### F5 & F6. `inventory/planning.py` N+1s

**Fix.** Extract the per-company precomputed `WarehouseReorderLevel`/`StockBalance` maps `insights/alerts.py::_low_stock` already builds into a shared helper both call; bulk-fetch each product's last supplier in one grouped query before the loop instead of per-row. **Tests.** A query-count ceiling test (`django.test.utils.CaptureQueriesContext`) proving the planning endpoint's query count doesn't scale with the number of low-stock rows, mirroring the existing customer-portal query-count test. **Effort.** 3—4 days combined (same investigation, two call sites).

### F7. `insights/attention.py` queries `AttentionRowState` twice per request

**Fix.** Thread the `existing` dict `_apply_state` already builds through to `_attach_assignment` instead of re-querying the same table for an overlapping key set. **Tests.** A query-count test on `build_attention_rows` with `ENABLE_ACTION_ASSIGNMENT` on. **Effort.** 1–2 days.

### F8. `flag_observability.log_flag_event` has zero test coverage

**Fix.** Add `backend/tests/test_flag_observability.py` covering the normal call shape. If a caller's `**fields` includes `tenant_id`, `flag`, `flag_state`, or `event`, `log_flag_event` raises rather than letting that key overwrite the structured value. **Effort.** 1–2 days.

### F9. Add the four proposed flags to the Retail/Trade packs

**Fix.** In `accounts/packs.py`'s `PACKS` dict: add `ENABLE_ROUTE_OPTIMIZATION`, `ENABLE_TDS`, `ENABLE_TALLY` to `trade`; add `ENABLE_GSTR` to both `retail` and `trade`. Do not backfill companies that already confirmed a pack. They pick up these flags only by confirming again, which matches "packaging proposes, never overwrites." **Tests.** Extend the existing pack-application tests to assert these four flags turn on after confirming the relevant pack, that `ENABLE_GSTR` turns on for both, and that a pack already applied is not rewritten just because the definition grew. **Effort.** Under a day — a data change plus a test update, no new logic.

## Concurrency verification gap

`sales/order_gates.py`'s customer-row lock and `accounts/packs.py`'s `apply_pack` lock are both in place and correct by inspection, but this repo's local dev/CI runs SQLite, which doesn't meaningfully serialize `select_for_update()` — a race test here would either pass vacuously or flake. Matches this repo's own established convention (concurrency tests are Postgres-only, per the CR-001/002/003 precedent).

**Recommendation, not a ticket to build now:** if/when a Postgres-backed CI lane exists for this repo, add two threaded/multi-connection tests there — concurrent `confirm_sales_order` calls for the same near-limit customer, and concurrent `apply_pack` confirms for the same company — asserting the lock actually serializes them (one blocks until the other commits) rather than both succeeding. Until then, the lock's correctness rests on code review, not a green test.
