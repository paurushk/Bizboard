# BizBoard — Waves E–L implementation plan (post-pilot)

**Audience:** Cursor Agent, Cursor Cloud Agent, or a human following the same tickets.  
**Companion:** [`WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md`](WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md). **Do 0–D / P0 first** unless the [PM waiver](#pm-waiver--enablement-only-books--ai-during-0d) is signed.  
**Date:** 2026-08-30 · **Revised:** 2026-08-30 (rigor review)  
**Code + tests win.** Update this file in the same PR if they disagree.

Phases 1–7 are **mostly in code**. These waves are enablement, honesty, SaaS entitlement, and charter-gated unfreeze — not a rebuild.

Create dirs if missing: `docs/roadmap/ticket-logs/` and `docs/roadmap/charters/` (README, `_TEMPLATE.md`, `demand-log.md`, `.gitkeep` belong in git).

---

## P0 (defined once)

**P0** = the P0 track in the 0–D plan: named GSP live **and** an IRN generated **in production** for a real pilot GSTIN (not `test_sprint_e_gsp_protocol.py` cassettes). GSTR-1 GSP upload is P0-adjacent (T0+16w there) but “charter after P0” in **this** file means **production IRN**.

---

## How to run

One ticket per session. Append `docs/roadmap/ticket-logs/<ID>.md` (create if missing). Do not edit progress tables in plan files.

```
Implement ticket E-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Follow the Global agent contract below and in WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Stop when DoD is met.
```

**Integrator:** `docs/roadmap/ticket-logs/INTEGRATOR.md` — not “PM until §0.5”. §0.5 has been open since 2026-08-21.

**Charters (H–L, J, K):** copy [`charters/_TEMPLATE.md`](_TEMPLATE.md) (path: `docs/roadmap/charters/_TEMPLATE.md`). Wave **L** also needs ≥3 rows in [`charters/demand-log.md`](demand-log.md) unless the charter records a PM exception.

**Bug-fix track** (`BUG-*`) does **not** wait for a charter. It applies to dark/flagged tenants already in the tree.

---

## Global agent contract (additive to 0–D)

```
You are on Waves E–L from WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.

13. Do not start E-02 (flip accounting_enabled in prod) without E-00 + E-01.
    Do not start H/I/J/K/L without a charter copied from _TEMPLATE.md.
14. Branch references CompanyGstin (FK only). Never add Branch.gstin string.
    branch_id on documents is reporting-only, never a filing dimension.
    Stock grain stays (company, warehouse, product). Do not re-key StockBalance.
15. AI never answers tax-rate / POS / GSTR liability in free text.
16. PAN/UDYAM: never stamp VALID in prod/staging from format-only or sandbox HTTP.
17. Payroll/MES/CRM flags stay off except named charter company ids.
18. BUG-* tickets may merge without a charter. Do not gate data-integrity fixes
    on enablement.
19. Every ticket in this file must leave Verify-first, Files, Tests, DoD,
    Out of scope, Rollback in the PR description if you change behaviour.
```

---

## PM waiver — enablement-only books + AI during 0–D

Without this waiver, Wave E for CAs is **~year 2** (9–15 months competitive pilot + 4–8 months E/F/G). Zoho Books already has Wave E. If displacing Tally in **one friendly CA practice** is a goal, **exercise this waiver in parallel with 0–D Wave B**, do not hide it.

| | |
|---|---|
| **Owner** | PM (name ________). Empty name = waiver **not** in force. |
| **Eng** | same as 0–D P0 Eng slot |
| **CA** | the friendly practice (name ________) |

**Criteria (all required):**

1. PD-02 (outstanding) signed in the 0–D plan.
2. E-00 plan slug exists that includes books (and AI if F-03 is in scope).
3. One named company id; **demo seed stays books-off / AI-off**.
4. E-01 golden-month harness green on a **staging clone** of that company.
5. Marketing/README still billing-first; no “Tally replacement” claim.
6. GO_NO_GO may still be unsigned; this is not a commercial books launch.
7. Waiver document: `docs/roadmap/charters/WAIVER_E_ENABLEMENT.md` (copy template, title waiver).

**Signed:** PM ________ date ________

---

## Sequencing

```
BUG-* (no charter) ── anytime; payroll/MES/CRM integrity
E-00 SaaS entitlement ── before E-02 / F-03 / J/K flags
        │
0–D + P0  OR  signed PM waiver (above)
        │
        ├─ E-01 CA pack (human + harness)
        │     ▼
        │  E-02 named-company books + prod backfill runbook
        │  E-03 period close UX (not manufacturing FY-close — that's BUG-K-FY)
        │  E-04 bank recon vs receipt matching
        │  E-05 FA/cost-center correctness (not a one-shot UAT)
        │
        ├─ F-01 copy surfaces + tax refusal
        │  F-02 usage ledger / budget=0 / i18n (enforcement exists)
        │  F-03 Owner enable
        │  F-04 digest
        │  F-05 WhatsApp pay-confirm + statement (collections)
        │  F-06 CA Practice Console ── after D-01 + B-03 + B-05 + E-02
        │
        └─ G-01 Tally export
           G-02 WABA webhook
           G-03a recurring verify (draft-only tests exist)
           G-03b notify-on-draft UAT
           G-04 FE badges + Health (BE honesty exists)
           G-05 mr/te/kn as beta unless reviewer signed

H–L: charter + template + (L) demand-log ≥3
```

---

## Effort

| Wave | Weeks | Notes |
|---|---:|---|
| BUG-* | 2–4 | Parallel with 0–D |
| E-00 | 2 | Plan.modules already AND; close books/AI holes |
| E | 6–9 | Plus CA wait; **waiver** can overlap 0–D |
| F | 4–6 | Including F-05 collections |
| G | 5–7 | G-04 shrunk |
| H–L | charter | L ≠ never: demand-log bar |

---

## Repo map

| Area | Paths |
|---|---|
| Flags + plans | `backend/core/services/feature_flags.py`, `backend/billing/` (`Plan.modules`, `plan_modules_for_company`) |
| Books | `backend/accounting/`, `web/src/pages/phase/AccountingExtraPages.tsx` |
| Insights | `backend/insights/assistant.py` (`assert_within_budget` ~L123), `insights/views.py` `AiUsageView` ~L269 |
| Identity | `backend/core/services/identity_verify.py` (never VALID from Null) |
| Recurring | `backend/sales/recurring.py` (`generate_draft_for_schedule`; no Complete) |
| Payroll | `backend/payroll/services.py` `compute_statutory` ~L147, `cancel_pay_run` ~L276 |
| PT slabs | `_STATE_PT_SLABS` in `payroll/services.py` (MH, WB, TN, AP, TG, GJ + default) |
| PAN UI | `web/src/pages/settings/GstSettingsPage.tsx` |

---

# Bug-fix track (no charter)

These are money/data bugs in **already-shipped** dark modules. Do not wait for Wave J/K.

---

## BUG-J-04 — PayRun cancel must not reopen DRAFT

| | |
|---|---|
| Effort | 1 week |
| Source | R4-009 · `cancel_pay_run` L303–307 |
| GATE | eng — **no payroll charter** |

### Verify first

`cancel_pay_run` sets `status = DRAFT` so the period can be re-run. Test `test_cancel_pay_run_reverses_journal_and_reopens_draft` **asserts that**. Re-complete of the same period can double-post PAYROLL journals / duplicate slips. Slip deletion on re-complete was already avoided (comment L304–306) — keep that.

### Files

- `backend/payroll/models.py` (`PayRun.Status`)
- `backend/payroll/services.py` `cancel_pay_run`
- `backend/tests/` the named test — **update assertions**

### Steps

1. Add `CANCELLED` (migration).
2. Cancel → `CANCELLED`, reverse GL (already). New pay run for the same period is a **new** row, not re-complete of the cancelled one.
3. Do not delete inactive-employee slips (keep current behaviour).
4. Rewrite `test_cancel_pay_run_reverses_journal_and_reopens_draft` → cancelled + new run.

### Tests

- Cancel completed run → CANCELLED; re-POST complete on **same pk** → 400.
- New PayRun for same period allowed; journals not doubled.

### DoD

- [ ] Existing test updated; PR says “changes asserted DRAFT behaviour.”
- [ ] No slip deletion.

### Out of scope

PF math (J-01). Enabling payroll flag.

### Rollback

Revert migration; old DRAFT behaviour. Worse for money — prefer forward fix.

### Agent prompt

```
Implement BUG-J-04 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
PayRun cancel → CANCELLED, not DRAFT. Update test_cancel_pay_run_reverses_journal_and_reopens_draft.
Do not wait for payroll charter. Stop when DoD is met.
```

---

## BUG-K-FY — FY/period close vs RELEASED work orders

| | |
|---|---|
| Effort | 1 week |
| Source | was split E-03 vs K-01 |
| GATE | eng — **no MES charter** |

**Owner of manufacturing FY-close is this ticket, not E-03.**

### Verify first

Grep FY close / period close vs `WorkOrder` status RELEASED / WIP 1450.

### Files

- Period/FY close services (accounting + inventory/mfg)
- `backend/manufacturing/models.py` / `services.py`

### Steps

1. If manufacturing flag **or** any RELEASED WO exists: period/FY close lists blockers and refuses until WOs are closed or CA-waived.
2. Works even when `ENABLE_MANUFACTURING` is off but stray WOs exist (data integrity).

### Tests

- RELEASED WO → close period 400 with WO ids.
- No WOs → close allowed.

### DoD

- [ ] Single owner; K-01 UAT does not re-implement this.

### Out of scope

New MES features. E-03 cashier copy (that stays E-03).

### Rollback

Flag `block_fy_close_on_open_wo` default on.

### Agent prompt

```
Implement BUG-K-FY from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Period/FY close blocks RELEASED WOs. This owns the logic, not E-03/K-01.
No MES charter. Stop when DoD is met.
```

---

## BUG-G-03 — Recurring must not Complete (only if G-03a fails)

| | |
|---|---|
| Effort | 0 if tests green; else 1 week |
| GATE | eng — no charter |

### Verify first

`backend/sales/recurring.py` has **no** `complete(` (confirmed 2026-08-30). Tests: `test_sprint_c_recurring.py`, `test_sprint_c_recurring_tds.py`. **If still true, skip this ticket** and log G-03a DONE.

If a path Completes: remove it; drafts only.

### Agent prompt

```
Run G-03a first. Only implement BUG-G-03 if recurring can Complete a sales invoice.
```

---

# Wave E-00 — SaaS entitlement (before books/AI/payroll “named companies”)

Competitor gap: seat/entitlement non-enforcing vs Zoho Billing. Flags exist; **selling** must not be a JSON hand-toggle.

---

## E-00 — Plan tier → modules enforced

| | |
|---|---|
| Effort | 2 weeks |
| Source | BB-000671 / 725–727 · `plan_modules_for_company` |

### Verify first

`Plan.modules` JSON AND-gated in `build_feature_flags` (L105–113). `ENABLE_ACCOUNTING` / `ENABLE_AI` are set from **company booleans** (L125–126), **not** from plan modules. Owner can PATCH `accounting_enabled` / `ai_features_enabled` without a paid plan.

### Files

- `backend/billing/models.py` `Plan`
- `backend/billing/services.py`
- `backend/core/services/feature_flags.py`
- `backend/accounts/serializers.py` (writable flags)
- Seed plans in migrations or `seed_demo` (demo stays free/billing-only)
- `backend/tests/test_sprint_d_saas_billing.py`

### Steps

1. Canonical module keys: `ENABLE_ACCOUNTING`, `ENABLE_AI`, `ENABLE_PAYROLL`, `ENABLE_MANUFACTURING`, `ENABLE_CRM` (plus existing).
2. `accounting_enabled` may be True only if plan.modules.ENABLE_ACCOUNTING is True (or `billing_override_active`). Same for AI.
3. Seed: `starter` (billing+stock), `books` (+accounting), `pro` (+AI). Prices in paise; Razorpay plan ids empty in dev.
4. Settings UI: “upgrade to enable books” not a naked toggle when plan forbids.
5. Ops override: existing `billing_override_active` only.

### Tests

- Starter plan + PATCH accounting_enabled True → 403 or no-op.
- Books plan + enable → flags true; TB nav visible.
- Override still works.

### DoD

- [ ] Books/AI/payroll are **sold** via Plan, not only named JSON.
- [ ] Demo seed starter / books-off.

### Out of scope

New payment gateway. Seat-limit UX beyond existing `seat_limit`.

### Rollback

`REQUIRE_PLAN_MODULES_FOR_BOOKS=0` env emergency (default on in staging/prod).

### Agent prompt

```
Implement E-00 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
AND accounting_enabled/ai_features_enabled with Plan.modules. Seed starter/books/pro.
No naked toggles. Stop when DoD is met.
```

---

# Wave E — Books on for a named CA

**Start:** PD-02 signed **and** (0–D+P0 **or** [PM waiver](#pm-waiver--enablement-only-books--ai-during-0d)) **and** E-00.

**Strategic timing:** without the waiver this is ~year 2 vs Zoho. Prefer waiver for one CA during 0–D.

---

## E-01 — CA CoA pack and golden month

| | |
|---|---|
| Effort | 1 week eng + CA calendar |
| GATE | human CA + eng harness |

### Verify first

TB/P&L/BS APIs exist. Health `AR_CONTROL_MISMATCH` tests in `test_sprint_a_accounting_p1.py` / `test_wave15d_books.py`.

### Files

- `docs/pilot/fixtures/` (create if missing)
- New `backend/tests/test_e01_golden_month.py` (skip without CSV)

### Steps

1. Pytest loads CA CSV when present; skip otherwise.
2. Assert TB vs sales/purchase register **± ₹0.01** on that fixture (same gate E-02 will use).
3. Do not tick CA signatures.

### Tests

- Skip without fixture; pass with committed golden if added.

### DoD

- [ ] Harness exists. CA signatures remain human.

### Out of scope

Enabling demo books.

### Rollback

n/a (tests only).

### Agent prompt

```
Implement E-01 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Golden-month pytest skip-without-CSV; ± paise TB vs register. No demo enable.
```

---

## E-02 — Backfill and enable books (named company)

| | |
|---|---|
| Effort | 2.5 weeks |
| Source | Phase 5 ACC-008 |

### Verify first

Idempotent backfill command (grep `backfill_accounting`). W0-01 unique posting.

### Files

- Backfill management command
- Settings enable UX
- `docs/pilot/RUNBOOKS.md` **prod cutover** section
- Tests: golden ± paise (E-01)

### Steps

1. Staging clone backfill; Health clean.
2. **Prod runbook (required):** estimate row counts; expected duration; **pause Complete** (or maintenance flag) during backfill; chunk by document date; off-peak; verify command `--dry-run`; rollback = `accounting_enabled=False` (GL rows **kept**).
3. Confirm modal copy: **“Reversible by support; posted journals are kept. Outstanding will follow GL while books are on (PD-02).”** Do **not** say irreversible.
4. Owner toggle only if E-00 plan allows.
5. Never enable `seed_demo`.

### Tests

- Backfill twice → same POSTED journal count.
- Golden tenant: P&L/TB vs register ± paise (CI).
- Flag off: books routes denied.

### DoD

- [ ] Runbook in RUNBOOKS.md.
- [ ] Modal matches Rollback (reversible; GL kept).
- [ ] ± paise CI gate.

### Out of scope

Cost centers (E-05). Manufacturing FY-close (BUG-K-FY).

### Rollback

`accounting_enabled=False`. Outstanding reverts to documents (PD-02 books-off). **Do not delete journals.**

### Agent prompt

```
Implement E-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Prod backfill runbook (pause Complete, chunking). Modal: reversible by support, GL kept.
± paise TB vs register CI. E-00 plan gate. No demo seed on.
```

---

## E-03 — Period close UX (cashiers)

| | |
|---|---|
| Effort | 1 week |

### Verify first

Period lock already 400s Completes. W0-03 holding state parks captures.

### Files

- Invoice/POS error mapping
- `web/src/i18n/en.ts` `hi.ts`
- Accounting period UI

### Steps

1. i18n: why Complete is blocked; what still works (gateway holding).
2. Reopen = Owner + reason + audit.
3. **Do not** implement manufacturing WO blockers (BUG-K-FY).

### Tests

- Vitest or API: period closed → message key not raw traceback.

### DoD

- [ ] Cashier-readable block. No WO logic here.

### Out of scope

BUG-K-FY. FY inventory valuation (W0-06).

### Rollback

Copy-only; revert strings.

### Agent prompt

```
Implement E-03 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Period-close cashier UX only. Manufacturing FY-close is BUG-K-FY. i18n.
```

---

## E-04 — Bank recon (GL) vs receipt matching

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | Phase 5.3 vs Phase 3.2 |

### Verify first

Two UIs: `payments/reconciliation` (`BankReconPage`) vs `accounting/bank-reconciliation` (`AccountingBankReconPage` / `BankReconSessionViewSet`).

### Files

- Those pages + `backend/accounting/views.py` `BankReconSessionViewSet`
- i18n help copy

### Steps

1. In-product explanation: statement↔**receipts** vs statement↔**GL bank**.
2. Unmatched GL lines API + table (account, amount, date).
3. No silent auto-clear.

### Tests

- Pytest: unmatched endpoint lists a posted unmatched bank GL line.
- Vitest: both pages render distinct help keys.

### DoD

- [ ] User can tell the two recon tools apart.
- [ ] Unmatched GL report exists.

### Out of scope

New matching algorithm. AA live feed (L-01).

### Rollback

Hide unmatched report behind flag `bank_recon_unmatched_report`.

### Agent prompt

```
Implement E-04 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Clarify payments vs accounting bank recon. Unmatched GL report + tests.
```

---

## E-05 — Cost centers and FA (books correctness)

| | |
|---|---|
| Effort | 2 weeks |
| Source | §0.4 built; GL risk |

### Verify first

`CostCenter`, `FixedAsset`, depreciation Celery task exist. Do not treat “run once” as enough.

### Files

- `backend/accounting/` FA + depreciation
- Tests new `test_e05_fixed_assets.py`

### Steps

1. Tests: mid-year acquisition proration; disposal gain/loss GL; SLM monthly; method change **blocked** or reversing entry (pick one, document).
2. Cost center on invoice line → P&L by CC for one fixture.
3. Staging UAT checklist after tests green.

### Tests

- As in steps (pytest).

### DoD

- [ ] FA edge cases in CI, not only “ran the task once.”

### Out of scope

New depreciation methods (WDV) unless already coded.

### Rollback

Keep FA flag off for the company.

### Agent prompt

```
Implement E-05 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
FA pytest: mid-year proration, disposal G/L, SLM. Cost center P&L fixture.
Not a one-shot UAT. Stop when DoD is met.
```

---

# Wave F — Insights (not an AI accountant)

**Start:** W0-07a merged. E-00 if enabling for pay.

---

## F-01 — Honesty copy and tax refusal

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | Phase 6 · `assistant.py` tax regex ~L110 |

### Verify first

Assistant already refuses some GST/tax free text. Copy may still overclaim.

### Files (copy surfaces — Owner = PM)

| Surface | Path | Signer |
|---|---|---|
| README | `README.md` | PM |
| Web onboarding | `web/src/pages/setup/`, i18n `setup.` / `ai.` | PM |
| In-app assistant empty state | insights FE | PM |
| Store listing | `mobile/` / Play copy if any | PM |
| Marketing site | **out of repo** — PM files a ticket; agent does not invent a site | PM |

Agent greps: `AI accountant`, `tax advice`, `files your GST`, `AI CA` in repo. PM signs replacements in PR or `docs/pilot/` note.

### Steps

1. Replace overclaims with “insights from your BizBoard documents.”
2. Tests: tax/GSTR/POS prompts → canned redirect (extend existing).
3. Money answers include tool citation in fixture.
4. Cross-tenant tool fail test.

### Tests

- `test_phase6_insights.py` (extend).

### DoD

- [ ] Listed in-repo surfaces cleaned.
- [ ] PM named on PR for copy.
- [ ] Tax refusal tests green.

### Out of scope

Marketing website CMS.

### Rollback

Revert copy; keep tests.

### Agent prompt

```
Implement F-01 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Grep listed surfaces only. PM signs copy. Tax refusal tests. Stop when DoD is met.
```

---

## F-02 — Usage ledger, budget=0, i18n (enforcement exists)

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | review: not unbuilt |

### Verify first

`assert_within_budget` in `insights/assistant.py` L123–131 already raises when `used >= budget`. `AiUsageView` L269–286 returns tokens vs budget. Default if `ai_monthly_token_budget is None` is settings `AI_MONTHLY_TOKEN_BUDGET_DEFAULT` (100_000) — **None is not off**.

### Files

- `insights/assistant.py`, `insights/views.py`
- `accounts/models.py` `ai_monthly_token_budget`
- FE Owner usage page (grep AiUsage)
- i18n
- Celery month boundary (ledger is per `created_at__date__gte` month start — verify timezone)

### Steps

1. **`budget=0` → assistant off** (do not use default 100k). Document None vs 0.
2. Owner UI: used/budget; i18n hard-stop (no English-only BusinessRuleError in POS).
3. Atomic increment of ledger (select_for_update or DB constraint) so two chats cannot both pass the check.
4. Confirm monthly window uses company TZ / IST consistently.

### Tests

- budget 0 → chat 400, no LLM call (mock).
- Two concurrent chats near cap → at most one succeeds.
- Usage GET matches ledger sum.

### DoD

- [ ] Verify-first comments in code point at existing assert.
- [ ] budget=0 off; i18n; atomic cap.

### Out of scope

New LLM provider.

### Rollback

Restore None→100k default if needed (worse). Prefer 0=off.

### Agent prompt

```
Implement F-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Enforcement already at assistant.py:123. Add budget=0 off, i18n, atomic counter,
Owner ledger UI. Stop when DoD is met.
```

---

## F-03 — Enable AI for Owners (plan-gated)

| | |
|---|---|
| Effort | 0.5 week |

### Verify first

`ai_features_enabled` Owner-writable (BB-000581). E-00 must land first or this ticket includes plan check.

### Files

- Settings AI page
- serializers read-only unless plan + confirm

### Steps

1. Confirm modal; &lt;30 invoices watermark (Phase 6).
2. Plan.modules ENABLE_AI.
3. Demo off.

### Tests

- Starter plan cannot enable.

### DoD

- [ ] Owner-only; plan-gated; watermark.

### Out of scope

Staff assistant.

### Rollback

Flag false.

### Agent prompt

```
Implement F-03 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Plan-gated Owner AI enable + watermark. After E-00.
```

---

## F-04 — Daily digest email / Owner WhatsApp

> Consumes the **B-05 Business Attention Center** feed (0-D) -- the digest is the top N ranked
> attention rows by money impact, not a second alert engine. If B-05 has not shipped, F-04
> falls back to the existing `insights/tasks.py` daily summary snapshot.

| | |
|---|---|
| Effort | 1 week |

### Verify first

`insights/tasks.py` daily summary; NotificationService; A-06 templates.

### Files

- `insights/tasks.py`, notifications, WhatsApp

### Steps

1. Email digest to Owner if opted in.
2. WhatsApp to Owner number only (not customers) if Cloud opt-in.
3. Default off.

### Tests

- Task no-ops when opted out; sends when on (mock).

### DoD

- [ ] Opt-in digest. No customer spam.

### Out of scope

F-05 customer statement.

### Rollback

Disable task flag.

### Agent prompt

```
Implement F-04 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Owner digest email/WA opt-in. Default off.
```

---

## F-05 — Collections: pay confirm + statement on WhatsApp

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | competitive gap vs A-06/A-07 only |

### Verify first

A-06 invoice+link; A-07 dunning; W0-03 payment_state. No customer statement send.

### Files

- `whatsapp.py` templates (add `payment_received`, `account_statement` to allowlist **after** Meta approval — until then wa.me only)
- Invoice pay-page / receipt
- Customer statement API

### Steps

1. On capture (including holding): send “payment received” if customer WhatsApp opt-in.
2. Owner action: send PDF/link of customer statement (existing ledger PDF if any).
3. Honest Cloud vs wa.me.

### Tests

- Opt-in false → no Cloud send.
- Holding capture still “payment received” not “please pay.”

### DoD

- [ ] Pay confirm + statement send exist.

### Out of scope

New dunning buckets (A-07).

### Rollback

Flags `wa_payment_received`, `wa_statement`.

### Agent prompt

```
Implement F-05 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
WhatsApp payment-received + statement send. Opt-in. Don't dunn holding captures.
```

---

## F-06 — CA Practice Console (cross-company board)

| | |
|---|---|
| Effort | 4 weeks |
| Source | one-level-up review Tier 4 * 0-D D-01 forward note |
| GATE | eng. Needs D-01 (switcher + 409) + B-03 (per-company IMS state) + B-05 (per-company attention feed) + E-02 (books tie) shipped for the client companies it aggregates. |

### Why

A CA is a distribution channel: one practice carries 20-200 client companies. The console is the
screen neither incumbent will produce -- Tally shows one company at a time and needs a VPN to reach a
client's data; ClearTax shows filing status without the books behind it. Explicitly **Phase 2 /
post-pilot**: do not start it until the single-company experience (0-D) is real.

### Verify first

Every queryset in the codebase is `company=`-scoped (correct for tenancy). The console needs a
**separate, explicitly audited aggregation path** -- not a loosened filter. Memberships + switcher
already exist (`useCompanySwitcher`, D-01).

### Files

- `backend/practice/` (new app) -- `PracticeBoardService.rows(user)` iterating the user's memberships, each row built from **already company-scoped** services (no cross-tenant query)
- `backend/practice/tests/test_isolation.py`
- FE: `/practice` route -- one row per client company; "needs me" filter; deep links
- Client-side "What my CA needs from me" view (reuses D-04 missing-doc list)

### Steps

1. One row per client company. Columns: IMS actioned (`142 / 168`), credit at risk (`Rs 84,200`),
   missing bills (`11`), GSTR-1 ready, 3B ready, books tie / not tie, next deadline (days).
2. Sort by deadline; default filter to "needs me" (any red cell).
3. Every cell is a **deep link into the fix** (that company's B-03 / D-04 / GSTR page), not a report.
   Switching company reuses D-01's `X-Company-Id` flow.
4. Roles: `PARTNER` sees all client companies; `MANAGER` / `STAFF` see assigned clients only.
   Practice-level membership, not a new tenant model.
5. Each aggregate value comes from the **same** company-scoped service the single-company screen
   uses -- the console never runs a query that spans companies.
6. Client-side mirror: "What my CA needs from me" -- missing bills (D-04), clarifications, approvals.

### Tests

- A practice with 3 client companies renders 3 rows; each number equals that company's own screen.
- `STAFF` assigned to 1 of 3 clients sees exactly 1 row; isolation test proves no cross-tenant read.
- A red "3B not ready" cell deep-links into that company's GSTR-3B page with the right context.
- Removing a membership removes the row on next load.

### DoD

- [ ] A CA runs a month-end across 10 client companies from one board without opening Tally/ClearTax.
- [ ] No query in `practice/` spans companies; isolation test green.
- [ ] Staff-scoped visibility enforced; partner sees all.
- [ ] Client sees the matching "what my CA needs" list.

### Out of scope

Bulk filing across companies; a practice-level billing/GST engine; white-label.

### Rollback

`/practice` behind `ENABLE_PRACTICE_CONSOLE` (default off). Removing it leaves D-01 untouched.

### Agent prompt

```
Implement F-06 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Cross-company CA board: one row per client company (IMS actioned, credit at risk, missing bills,
GSTR-1/3B ready, books tie, deadline), "needs me" filter, deep links. Every value from the existing
company-scoped service -- no query spans companies. Staff/partner visibility. Client-side mirror.
Behind ENABLE_PRACTICE_CONSOLE, default off. Stop when DoD is met.
```

---

# Wave G — Ecosystem leftovers

---

## G-01 — Tally export aid

| | |
|---|---|
| Effort | 2 weeks |
| Source | ECO-003 |

### Verify first

D-02 is **import**. Export may be thin or missing.

### Files

- `backend/imports/` or `integrations/` export
- FE + i18n disclaimer

### Steps

1. Date-range voucher CSV (XML if parser exists).
2. Banner: not certified sync.
3. Grep no “Tally sync.”

### Tests

- Export foots a one-invoice fixture.
- i18n/disclaimer present.

### DoD

- [ ] Export + honesty.

### Out of scope

Live sync (FZ). Busy/Zoho (L-05).

### Rollback

Hide nav flag `ENABLE_TALLY_EXPORT`.

### Agent prompt

```
Implement G-01 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Tally export CSV + not-sync disclaimer.
```

---

## G-02 — WABA delivery webhook

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | ECO-102 |

### Verify first

A-06 send path. Webhook may be missing.

### Files

- integrations WhatsApp views
- invoice send-status field

### Steps

1. Meta signature verify; map phone_number_id → company.
2. Store delivered/failed. Complete never waits on webhook.

### Tests

- Bad signature 403; good signature updates status.
- Unknown id no cross-tenant write.

### DoD

- [ ] Status stored; fail-closed signature.

### Out of scope

Chatbot.

### Rollback

Ignore webhook (send still works).

### Agent prompt

```
Implement G-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
WABA status webhook + signature. No Complete block.
```

---

## G-03a — Recurring draft-only verification

| | |
|---|---|
| Effort | 0.5 week |

### Verify first

`sales/recurring.py` module docstring draft-only; no `complete(`; tests `test_sprint_c_recurring.py`.

### Files

- Re-run those tests; grep `complete` in `sales/recurring.py` and `sales/tasks.py`

### Steps

1. CI job or ticket log: tests passed SHA.
2. If Complete found → BUG-G-03, do not mark G-03a done.

### Tests

- Existing recurring tests.

### DoD

- [ ] Logged proof draft-only **or** BUG-G-03 opened.

### Out of scope

Notify UX (G-03b).

### Rollback

n/a

### Agent prompt

```
Implement G-03a from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Verify recurring cannot Complete. Log SHA. If it can, do BUG-G-03.
```

---

## G-03b — Recurring notify-on-draft UAT

| | |
|---|---|
| Effort | 0.5 week |

### Files

- Celery after `generate_draft_for_schedule`
- NotificationService

### Steps

1. Notify Owner when drafts created.
2. UAT note in ticket-log: staging cadence produced DRAFT invoices.

### Tests

- Mock notify called once per new draft.

### DoD

- [ ] Notify exists. Still no auto-Complete.

### Out of scope

Auto-Complete.

### Rollback

Disable notify flag.

### Agent prompt

```
Implement G-03b from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Notify Owner on recurring drafts. Not Complete.
```

---

## G-04 — PAN/UDYAM FE badges + Health + prod test

| | |
|---|---|
| Effort | 0.5–1 week (BE honesty exists) |

### Verify first

`identity_verify.py`: Null never VALID; `accounts/views.py` ~L650 same. `GstSettingsPage.tsx` already says format-check until certified. This ticket is badges consistency + Health + **pytest: prod/staging settings cannot persist VALID from Null/sandbox**.

### Files

- Settings GST page, Health catalog, `identity_verify.py` tests

### Steps

1. Badge: Invalid / Unverified / Sandbox-only (never “Verified” in prod).
2. Health alert if UNVERIFIED and PAN present.
3. Test: `DJANGO_ENV=production` + Null provider → no VALID.

### Tests

- As in step 3.

### DoD

- [ ] No fake Verified in prod. Health alert. Regression test.

### Out of scope

Certified portal (FZ-09).

### Rollback

UI-only.

### Agent prompt

```
Implement G-04 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
FE badges + Health + no VALID in prod test. BE already honest in identity_verify.py.
```

---

## G-05 — mr / te / kn (beta unless reviewer)

| | |
|---|---|
| Effort | 2 weeks |
| Source | A-02b pattern |

### Verify first

A-02 locale files. Reviewers: `charters/locale-reviewers.md`.

### Files

- `web/src/i18n/mr.ts` `te.ts` `kn.ts`
- picker; CI key check
- `locale.beta` label if reviewer unsigned

### Steps

1. Money-namespace parity with `en`.
2. Picker: beta chip until locale-reviewers.md signed.
3. Native reviewer **or** stay beta — do not claim quality from CI keys.

### Tests

- CI missing keys fail.

### DoD

- [ ] Three locales; beta unless signed.

### Out of scope

Full UI (help articles).

### Rollback

Hide locales in picker.

### Agent prompt

```
Implement G-05 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
mr/te/kn money keys; mark beta unless locale-reviewers.md signed.
```

---

# Wave H — Composition (charter = `_TEMPLATE.md`)

Regular packs stay hidden (GST-009).

---

## H-01 — CMP-08 worksheet

| | |
|---|---|
| Effort | 2.5 weeks |
| GATE | charter |

### Verify first

Composition gating exists. CMP-08 may be stub `supported: false`.

### Files

- `backend/reporting/` composition builders
- FE + watermark

### Steps

1. Worksheet from composition invoices; foots sales register.
2. No Regular GSTR-1 download.
3. No portal upload unless charter + GSP (default false).

### Tests

- Composition cannot get Regular GSTR-1.
- CMP-08 foots fixture.

### DoD

- [ ] Worksheet + watermark. Charter companies only.

### Out of scope

GSTR-4 (H-02). One-click GSTN.

### Rollback

Flag off.

### Agent prompt

```
Implement H-01 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
CMP-08 worksheet. Charter required. No Regular pack leak.
```

---

## H-02 — GSTR-4 worksheet

| | |
|---|---|
| Effort | 2 weeks |
| GATE | charter |

### Files

- reporting GSTR-4 stub → worksheet

### Steps

1. Books worksheet + watermark (like GSTR-9).
2. Not a filing engine.

### Tests

- `supported: false` for upload.

### DoD

- [ ] Watermarked worksheet.

### Out of scope

Portal file.

### Rollback

Hide nav.

### Agent prompt

```
Implement H-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
GSTR-4 worksheet watermark. Charter required.
```

---

# Wave I — Branch (charter; no third GSTIN)

---

## I-01 — Branch model, CompanyGstin FK only

| | |
|---|---|
| Effort | 3 weeks |
| GATE | charter |

### Verify first

`CompanyGstin` is the filing GSTIN (W0-02). No Branch model. **Do not** add `Branch.gstin` CharField.

### Files

- new `Branch` in accounts
- documents nullable `branch_id`
- warehouses optional `branch_id`

### Steps

1. `Branch.company_gstin` FK to `CompanyGstin` (nullable only if branch is non-filing / same as company primary).
2. Reports filter `branch_id`. GSTR/IRN use stamped **CompanyGstin**, never branch.
3. Stock: warehouse only.

### Tests

- Two warehouses two branches: SALE hits invoice warehouse.
- Serializer reject extra gstin string.
- GSTR keyed by CompanyGstin.

### DoD

- [ ] FK only. Reporting-only branch_id. No stock re-key.

### Out of scope

ECO-203 StockBalance migration.

### Rollback

Nullable FKs; hide nav.

### Agent prompt

```
Implement I-01 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Branch.company_gstin FK only. No Branch.gstin. No StockBalance re-key. Charter required.
```

---

## I-02 — Branch picker

| | |
|---|---|
| Effort | 1.5 weeks |
| GATE | charter · after I-01 |

### Files

- CompanySwitcher then branch
- cashier default branch

### Steps

1. Company first (D-01), then branch.
2. CA: All branches.

### Tests

- Single-branch: no extra modal.
- Multi: filter list.

### DoD

- [ ] Picker; stock still warehouse.

### Out of scope

Filing by branch name.

### Rollback

Hide picker.

### Agent prompt

```
Implement I-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Branch picker after company. Charter required.
```

---

# Wave J — Payroll (charter after P0) except BUG-J-04

**Charter required for enablement.** Statutory math that is **wrong if half-done** stays frozen until J-01 DoD — do not enable payroll on a charter that skips EPS/EDLI.

### Verify first (all J tickets)

`compute_statutory` L147+: Basic+DA, ₹15k ceiling, employee+employer **both 12% of wage_base** (no EPS split). PT: `_STATE_PT_SLABS` includes MH, WB, TN, AP, TG, GJ — not “3 states.” Default slab if state missing can yield ₹200 or ₹0 — **must hard-gate**.

---

## J-01 — Statutory PF (or keep frozen)

| | |
|---|---|
| Effort | 4 weeks |
| Source | R4-007 · trust-killer if partial |
| GATE | charter + CA rate letter |

### Steps

1. Keep Basic+DA + ceiling.
2. Employer 12% split: EPS 8.33% of wage_base (EPS wage cap per CA letter) + EPF remainder; employee 12% EPF.
3. EDLI + admin charges from **CA-signed table** in company/payroll settings (do not invent 2026 rates in code comments only).
4. Allowances: **only Basic+DA** unless charter lists inclusions.
5. If CA will not sign → **do not ship J-01**; leave `ENABLE_PAYROLL` off.

### Files

- `payroll/services.py` `compute_statutory`
- CA fixture JSON
- Payslip breakdown UI

### Tests

- Golden slip: employee PF, employer EPF, EPS, EDLI, admin.
- basic=da=0 fallback to gross (document as legacy).

### DoD

- [ ] CA letter in charter. No silent 12%+12% without EPS if charter says statutory.

### Out of scope

ESI overhaul (already employee/employer rates). Full EPFO ECR file.

### Rollback

Flag off. Revert to current 12/12.

### Agent prompt

```
Implement J-01 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Full PF: EPS split, EDLI/admin from CA table. If no CA letter, stop BLOCKED.
Charter required. Do not half-ship.
```

---

## J-02 — LOP / proration

| | |
|---|---|
| Effort | 3 weeks |
| GATE | charter |

### Verify first

`payslip.paid_days` / `period_days` migrations exist.

### Files

- `payroll/services.py` complete_pay_run
- attendance input or paid_days on employee-period

### Steps

1. Net from paid_days/period_days.
2. Mid-month join/exit.
3. Tests vs golden.

### Tests

- 15/30 days halves basic components as specified.

### DoD

- [ ] LOP in CI.

### Out of scope

Full attendance app.

### Rollback

Ignore paid_days (document as bug).

### Agent prompt

```
Implement J-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
LOP via paid_days. Charter required.
```

---

## J-03 — PT: supported states only, never silent ₹0

| | |
|---|---|
| Effort | 1.5 weeks |
| GATE | charter |

### Verify first

`_STATE_PT_SLABS` + `Company.payroll_pt_slabs` override. `_pt_amount` may return 0 for unknown state.

### Files

- `payroll/services.py`
- enable-payroll / complete pay run

### Steps

1. Supported = keys of `_STATE_PT_SLABS` ∪ company override non-empty.
2. Unknown `pt_state`: **block pay-run complete** (and block ENABLE_PAYROLL for that company) with i18n; never compute ₹0 as if no PT.
3. Gujarat/TN/AP/TG already in table — include them in docs; do not say “3 states.”

### Tests

- `pt_state=Kerala` (or other unsupported) → 400.
- MH Feb top-up still works.

### DoD

- [ ] Unsupported state cannot silently zero PT.

### Out of scope

All 15 states’ full tables (add via override JSON + CA).

### Rollback

n/a — safer than silent 0.

### Agent prompt

```
Implement J-03 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
Unsupported PT state blocks pay run. Never silent ₹0. Charter required.
```

---

## J-04 — cancelled status

**Superseded by BUG-J-04.** If BUG-J-04 is DONE, skip. Do not re-open DRAFT behaviour.

---

# Wave K — MES/CRM enablement (charter after P0)

UAT + named flags. **Blocker fixes = BUG-K-FY / separate BUG-K-*** without waiting.

---

## K-01 — Manufacturing enablement UAT

| | |
|---|---|
| Effort | 1.5 weeks |
| GATE | charter companies |

### Verify first

MES app behind `ENABLE_MANUFACTURING`. FY-close = BUG-K-FY (must be done or this ticket depends on it).

### Files

- manufacturing services, FE

### Steps

1. Charter ids: flag on via E-00 plan + company JSON.
2. UAT BOM→WO→stock/serial. File **BUG-K-*** for defects; do not hold those on a second charter.
3. Demo off.

### Tests

- Existing mfg tests + UAT log.

### DoD

- [ ] Named companies only. Blockers filed as BUG-K-*, not “later charter.”

### Out of scope

MRP/planning. ONDC.

### Rollback

Flag off.

### Agent prompt

```
Implement K-01 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
MES UAT on charter ids. FY-close is BUG-K-FY. Fix blockers as BUG-K-* no extra charter.
```

---

## K-02 — CRM convert UAT

| | |
|---|---|
| Effort | 1 week |
| GATE | charter |

### Verify first

CRM convert amount+confirm (Q-item). Flag `ENABLE_CRM` AND plan.

### Files

- `backend/crm/`, FE

### Steps

1. Enable named ids. Convert → draft invoice confirm.
2. Blockers → BUG-CRM-* without new charter.

### Tests

- Convert confirm; demo flag off.

### DoD

- [ ] Charter ids only. Not Salesforce.

### Out of scope

Full pipeline automation.

### Rollback

Flag off.

### Agent prompt

```
Implement K-02 from docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md.
CRM convert UAT. Blockers are BUG-CRM-* not a new charter.
```

---

# Wave L — Demand-gated

**Bar:** `charters/demand-log.md` **≥3 paying written requests** for that L-id, then `_TEMPLATE.md` charter. Exception: PM one-liner in the charter. This is not “never.”

| ID | Topic | Agent notes |
|---|---|---|
| L-01 | Live AA bank feed | Fail-closed without `FIU_BASE_URL`; no prod mocks |
| L-02 | Second gateway | W0-03 holding must apply; Cashfree/PayU stay dark until charter |
| L-03 | GSTR-9 **filing** | Worksheets exist (B-02); filing needs GSP+CA |
| L-04 | iOS | A-01 says not shipping; Apple review |
| L-05 | Busy/Zoho import | Same adapter as Tally; not live sync |
| L-06 | ONDC / DigiLocker / eSign | Spike unless charter says build |

### Agent prompt

```
If demand-log < 3 and no PM exception, BLOCKED.
If charter missing, BLOCKED.
Else implement only that L-id using 0–D contract.
```

---

## Wave exits

| Wave | Exit |
|---|---|
| **E-00** | Starter cannot enable books; books plan can. |
| **E** | Named company books-on; Health + ± paise gate; runbook used once; demo off. Waiver optional for year-1 CA. |
| **F** | Tax refused; budget=0 off; pay-confirm WhatsApp; no AI CA copy in README. **F-06:** CA runs 10 client companies from one board; no query spans companies; isolation test green. |
| **G** | Export disclaimer; WABA status; PAN not VALID in prod; locales beta or signed. |
| **H–K** | Charter template filled; demo flags off. |
| **L** | Demand-log ≥3 + charter. |

---

## Progress (humans)

Agents: `ticket-logs/<ID>.md`. Integrator file: `ticket-logs/INTEGRATOR.md`.

| Date | Notes |
|---|---|
| 2026-08-30 | E–L authored |
| 2026-08-30 | Rigor revision: 0–D ticket shape, P0 def, waiver, E-00, BUG-*, templates, demand-log |
| 2026-08-30 | One-level-up review: F-06 Practice Console; F-04 consumes B-05; IMS/ITC + Attention Center live in 0-D B-03/B-05 |

---

## Cheat sheet

| User says | Ticket |
|---|---|
| Sell books / AI as a plan | E-00 |
| Friendly CA during 0–D | PM waiver then E-01/E-02 |
| TB/P&L | E-01 → E-02 |
| Period close copy | E-03 |
| Open WO vs FY close | BUG-K-FY |
| Two bank recon screens | E-04 |
| FA depreciation | E-05 |
| AI tax advice | F-01 |
| Token budget | F-02 |
| Payment received WhatsApp | F-05 |
| CA one board for all clients | F-06 (needs D-01 + B-03 + B-05) |
| Recurring completed a bill | G-03a then BUG-G-03 |
| Pay run cancel reopens | BUG-J-04 |
| PF / EPS | J-01 or keep frozen |
| PT Kerala / unknown state | J-03 |
| ONDC / iOS / GSTR-9 file | L-* + demand-log |
