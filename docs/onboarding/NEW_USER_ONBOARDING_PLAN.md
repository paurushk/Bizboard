# BizBoard — New User Onboarding Path

**Status:** Implemented (2026-08-21) — Waves A-D; wizard behind ENABLE_SETUP_WIZARD (default off)  
**Canonical path:** [`docs/onboarding/NEW_USER_ONBOARDING_PLAN.md`](./NEW_USER_ONBOARDING_PLAN.md)  
**Root pointer:** [`ONBOARDING_IMPLEMENTATION_PLAN.md`](../../ONBOARDING_IMPLEMENTATION_PLAN.md)  
**Related:** [`docs/pilot/ONBOARDING.md`](../pilot/ONBOARDING.md) · MVP E6.4 · BB-000251 / BB-000389 / BB-000007 / BB-000418

**Stack touchpoints:**  
`backend/accounts/` · `backend/core/services/registration_gates.py` · `backend/core/services/feature_flags.py` · `web/src/pages/RegisterPage.tsx` · `web/src/components/OnboardingChecklist.tsx` · `web/src/pages/AcceptInvitePage.tsx` · settings pages · `web/src/App.tsx` · `web/src/i18n/{en,hi}.ts`

---

## 0. Goal

Get a **self-serve Owner** from signup to a **Completed first bill** in **< 30 minutes**, with GST registration type set correctly so tax Complete does not fail later.

**First bill definition (explicit):**  
- Default path: guided **sales invoice** Complete.  
- If `ENABLE_POS` (or equivalent) is on **and** Owner prefers counter billing: Step 5 may offer **POS quick-sale** as an alternate activation path (see §5 / D-6). Goal text and Step 5 must stay aligned — do not claim POS in §0 without implementing the branch.

**Committed scope:** Waves **A + B** only.  
**Provisional backlog:** Waves **C + D** — prioritize / cut using Wave A–B funnel data (§0 metrics), not upfront commitment.

**Non-goals:** live GSTN filing, CoA/accounting enablement, AI/Tally/Manufacturing/Payroll/CRM first-run, multi-company wizard, marketing site redesign, flipping `registration_type` model default without create-site audit (see D-5).

### Success metrics (instrument from Wave A)

| Metric | Target (pilot) |
|--------|----------------|
| Signup → first successful login | ≥ 85% within 24h |
| Login → tax profile saved (or derived complete) | ≥ 90% of Owners within first session |
| Login → ≥1 product | ≥ 70% within 24h |
| Login → first **Completed** sales/POS doc | ≥ 50% within 7 days; stretch 30% within 24h |
| Support tickets: GST invoice / GSTIN confusion | Down vs pre-ship baseline |
| Wizard step drop-off | Top abandonment step fixed within 2 iterations |

### Metrics destination (required — not stubs alone)

| Piece | Decision for pilot |
|-------|-------------------|
| **Where events land** | Client emits structured events to existing logging/telemetry path (or `console` + backend `AuditService` / analytics table if none). Prefer one sink: e.g. PostHog / Plausible / CloudWatch custom metrics — **pick before A7 ships**; document in `web/.env.example`. |
| **Minimum events** | `register_success_view`, `login_after_register`, `setup_step_view`, `setup_step_complete`, `setup_skip`, `setup_first_bill_complete`, `onboarding_checklist_cta` |
| **Who reviews** | Pilot owner / PM — **weekly 15-min funnel review** during Wave B pilot; drop-off action items go into next iteration |
| **Without a sink** | A7 may land DEV-only stubs, but Wave B hard-redirect must not ship to real pilots until a viewable funnel exists (even a CSV export from logs) |

### Honesty / security gates (do not violate)

| Gate | Rule |
|------|------|
| Anti-enumeration | No register email oracle; no JWT/cookies on register (`BB-000251`, `BB-000389`). Success UX → login, not auto-login. |
| Scope honesty | No live NIC / GST portal / flagged modules as core. |
| Registration gates | COMPOSITION / UNREGISTERED must not be guided into GST tax Complete (`registration_gates.py`). |
| Least privilege | Invitees never enter Owner `/setup`. |
| Pilot flags | POS / GSTR / AI / Tally / accounting CTAs only when flags allow. |
| **Wizard kill-switch** | `ENABLE_SETUP_WIZARD` (BE + `VITE_ENABLE_SETUP_WIZARD` or feature-flags API). When off: no hard redirect; fall back to soft checklist (Wave A behavior). Required before Wave B pilot. |

---

## 1. Current-state snapshot

| Capability | Today | Gap |
|------------|-------|-----|
| Register (FE) | Company, email, password, phone, **state** | No registration type / GSTIN |
| Register (BE) | Owner + company + warehouse; `_register_payload()` **without** session | Success feels like failure |
| Company default | Model default `REGULAR`; RegisterView passes **UNREGISTERED** | Other create paths inherit model default — do not silently flip (D-5) |
| First-run UX | Dashboard checklist (4 tiles) | Soft; GSTIN copy/link wrong |
| GST setup | `/settings/gst` | Not in checklist completion |
| Invite | Raw token in dialog; `/invite` **already** reads `?token=` | Gap is link generation (D1), not query-param read |
| Progress | Derived in checklist from fields | Fine for most steps; only Skip needs persistence |

---

## 2. Product design

### 2.1 Entry paths

| Path | Who | Landing |
|------|-----|---------|
| **A — Self-serve Owner** | New register | After login → `/setup` if wizard enabled + incomplete |
| **B — Invitee** | Staff / Accountant / Viewer | Role welcome → first allowed action |
| **C — Seeded / ops / existing tenants** | Fixtures + backfilled companies | Treated as complete — never forced into `/setup` |

### 2.2 Owner setup spine

```text
Register → Login → /setup (if ENABLE_SETUP_WIZARD)
  1. Tax profile
  2. Shop identity
  3. Payments (optional)
  4. Catalog (quick add OR CSV)
  5. First bill (sales invoice OR POS if enabled — D-6)
→ Dashboard + residual checklist + optional invite CTA
```

**Branching (registration type)**

| Type | Tax step | First-bill guidance |
|------|----------|---------------------|
| UNREGISTERED | No GSTIN; BoS / non-GST | `tax_enabled=false` path |
| REGULAR | Valid GSTIN required | GST tax invoice; HSN/rate on products |
| COMPOSITION | GSTIN optional; warn no regular tax invoices | BoS only |

### 2.3 UX principles

1. One job per step; EN+HI.  
2. Skip only non-blocking steps; tax + ≥1 product + first bill are core.  
3. Whole-wizard Skip → set `onboarding_dismissed_at`; residual checklist remains until first Completed bill.  
4. **Derive progress from real data**; persist Skip (and optional timestamps) only — see §3.  
5. Shared helper for registration-type → checklist/setup copy & CTAs (`getOnboardingTaxHints(company)`) — used by Wave A checklist and Wave B steps so A3/A5 logic is not rewritten then discarded.

---

## 3. Data model & API (revised: derive-first)

### 3.1 Prefer derivation over four synced fields

Most wizard progress is already knowable (same idea as today's checklist):

| Derived signal | Source |
|----------------|--------|
| Tax profile done | UNREGISTERED/COMPOSITION: type explicitly set post-register **or** REGULAR with valid GSTIN (and type ≠ accidental default — see note) |
| Shop done | `address` (+ `state` from register) |
| Payments done (optional) | `bank_account` or `upi_id` |
| Catalog done | ≥1 product |
| Activation done | ≥1 Completed sales invoice **or** Completed POS sale |

**Persist minimally on `Company`:**

| Field | Type | Why |
|-------|------|-----|
| `onboarding_dismissed_at` | DateTime null | Only state that cannot be derived ("Owner chose Skip") |
| `onboarding_started_at` | DateTime null | Optional: first `/setup` visit (analytics) |

**Do not** persist a separately updated `onboarding_status` / `onboarding_step` that can drift from PATCH races. Compute:

```text
if activation_done → COMPLETED
else if onboarding_dismissed_at → DISMISSED
else if any setup signal → IN_PROGRESS (step = first incomplete)
else → NOT_STARTED
```

**API:** expose a read-only computed `onboarding` object on company payload (`status`, `step`, `dismissed`, derived flags). PATCH only `dismiss` / clear-dismiss. No `complete-step` write API required.

**Tax-profile derivation caveat:** Register creates `UNREGISTERED` today. "Tax step incomplete until Owner confirms" — use `onboarding_started_at` or a tiny `tax_profile_confirmed_at` if we must distinguish "still default UNREGISTERED" from "Owner confirmed Unregistered." Prefer **`tax_profile_confirmed_at`** (nullable) over a free-form status enum if confirmation is required.

### 3.2 Migration & backfill (mandatory — prevents trapping existing Owners)

B1 migration **must** include a data migration:

| Rule | Result |
|------|--------|
| Company has ≥1 Completed sales (or POS) document | Treat as complete: set `onboarding_dismissed_at` **or** `tax_profile_confirmed_at` + leave dismiss null — derived status → COMPLETED via activation |
| Else company has non-blank `address` **or** ≥1 product **or** non-blank `gstin` | Set `tax_profile_confirmed_at=now()` (and optionally `onboarding_dismissed_at=now()`) so hard redirect does **not** fire — existing pilots stay on dashboard |
| Else (genuinely empty new shell) | Leave nulls → `NOT_STARTED` |

**Seeds:** `seed_demo` / `seed_pilot_fixtures` ensure activation or confirmed+dismissed so wizard never traps demos.

**Test:** migration against fixture with "old Owner + historical invoices" → next login is **not** `/setup`.

### 3.3 API / routes

| Endpoint / route | Change |
|------------------|--------|
| Register | Unchanged anti-enum body; short form; GST deferred to setup |
| Company GET | Computed `onboarding` + dismiss fields |
| Company PATCH | `dismiss_onboarding=true` / confirm tax profile timestamp |
| Feature flags | `ENABLE_SETUP_WIZARD` |
| `/setup` | Owner only; gated by flag + derived incomplete |
| `/invite?token=` | Already prefilled today; D1 adds shareable URL from invite API |

**Routing guard (when flag on):** Owner + derived `NOT_STARTED`/`IN_PROGRESS` + not dismissed → redirect `/` & dashboard → `/setup`. Flag off → Wave A checklist only.

---

## 4. Delivery waves

| Wave | Name | Duration | Commitment |
|------|------|----------|------------|
| **A** | Unblock & align | ~3–5 days | **Committed** |
| **B** | Guided `/setup` MVP | ~1.5–2.5 weeks | **Committed** (behind kill-switch) |
| **C** | Time-to-value polish | ~1–1.5 weeks | **Provisional** — gate on A/B funnel |
| **D** | Staff invite + activation | ~1 week | **Provisional** — gate on A/B funnel |

Solo estimate for **committed** work: **~2–3.5 weeks**. C+D only if metrics justify.

---

### Wave A — Unblock & align (P0)

| ID | Work item | Done when |
|----|-----------|-----------|
| A1 | Register success UX → login (not error Alert on happy path) | Clear next step; e2e |
| A2 | Login `?registered=1` banner EN/HI | Visible after redirect |
| A3 | Checklist Step 1: address+state; REGULAR needs GSTIN; CTA → `/settings/gst` when incomplete | Via **shared helper** |
| A4 | Hide POS when POS flag off | No dead CTA |
| A5 | Unregistered/Composition first-bill copy → BoS (shared helper) | Branches on type |
| A6 | Pilot ONBOARDING.md note + link this plan | No contradiction |
| A7 | Emit funnel events to **chosen sink** (or DEV stub + sink ticket blocking B pilot) | Viewable or explicitly deferred with owner ack |

**Exit:** register → login → honest checklist; Regular GST path clear.

---

### Wave B — Guided `/setup` MVP (P0)

| ID | Work item | Done when |
|----|-----------|-----------|
| B0 | `ENABLE_SETUP_WIZARD` kill-switch (default **off** until UAT; on for staged pilot) | Flag off restores checklist-only |
| B1 | Minimal migration (`dismissed` / `tax_profile_confirmed_at` / optional `started_at`) + **backfill rules §3.2** + seeds | Existing companies not trapped; tests prove it |
| B2 | Derive onboarding on API; Owner guard + `/setup` shell; Skip sets dismiss | Incomplete new Owners only |
| B3–B5 | Tax / shop / payments steps | Shared tax helper; PATCH company fields |
| B6 | Catalog quick-add or Import `return=` | ≥1 product |
| B7 | First bill: sales invoice path; **POS alternate if D-6 = yes and flag on** | Activation Complete; derived COMPLETED |
| B8 | Residual checklist for dismissed / optional leftovers | No double nag when activated |
| B9 | i18n `setup.*` EN/HI | Complete |
| B10 | Tests: backfill; dismiss; Unregistered e2e; **Composition GST tax Complete blocked (automated e2e/API)**; Regular needs GSTIN | CI green — Composition gate is compliance-critical |

**Exit:** New Unregistered Owner finishes setup → Completed bill. Kill-switch off = safe fallback. Old tenants unaffected.

---

### Wave C — Polish (P1, provisional)

Prioritize only after funnel shows which step drops. Candidate items: sample products (C1), walk-in party (C2), empty-state continue (C3), GSTIN verify (C4), mobile sticky CTA (C5), weekly metrics hygiene (C6).

**Gate:** Skip or reorder if A/B data shows e.g. tax step abandonment ≫ mobile issues.

---

### Wave D — Staff invite (P1, provisional)

| ID | Work item | Notes |
|----|-----------|-------|
| D1 | Invite API returns absolute `{WEB_ORIGIN}/invite?token=…`; copy-link UI | **Primary gap** |
| D2 | Polish AcceptInvite (token already from query); EN/HI; login redirect | Not "add query read" — improve framing / paste fallback |
| D3 | Role welcome after accept | Staff never `/setup` |
| D4 | Post-activation "Invite staff" soft CTA | Optional |
| D5 | Docs / support runbook | After D ships |

**Gate:** Defer if Owner activation funnel is still weak — invites help scale, not first-bill.

---

## 5. Step specifications (Wave B)

### Steps 1–4

Unchanged intent: tax → shop → optional payments → catalog (quick add or import return). Progress **derived** after each successful PATCH/create; do not write a parallel step cursor.

### Step 5 — First bill (aligned with §0)

1. Resolve walk-in / default customer.  
2. **Branch (D-6):**  
   - **Invoice (default):** draft sales doc compatible with registration type → one line → Complete.  
   - **POS (if enabled + chosen):** guided POS quick-sale Complete.  
3. On success, activation derived COMPLETED (no status field write required).  
4. Celebrate; PDF/print if ready.

**Failure:** show BusinessRuleError; do not dismiss wizard.

---

## 6. Interaction with existing systems

| System | Interaction |
|--------|-------------|
| `registration_gates.py` | Doc type / tax_enabled match type; Composition covered by **automated** test |
| Feature flags | POS + **ENABLE_SETUP_WIZARD** |
| Billing middleware | Surface write-block in setup |
| Checklist | Soft path when wizard off; residual when dismissed |
| `Company.objects.create` | See D-5 — do not change model default without audit |

---

## 7. Test plan

### Automated (required)

| Case | Layer |
|------|-------|
| Backfill: company with historical Completed sale → not redirected to `/setup` | BE migration / integration |
| Backfill: empty new company → NOT_STARTED | BE |
| Dismiss → no hard redirect; checklist may show | FE/BE |
| Unregistered setup → Complete bill | e2e |
| Regular without GSTIN cannot finish tax step | e2e/FE |
| **Composition cannot Complete GST/TAX invoice** (gate regression) | **API + e2e** — not manual-only |
| Kill-switch off → no `/setup` redirect | e2e |
| Staff invitee never forced to `/setup` | e2e |

### Manual UAT

Unregistered / Regular happy paths; Skip path; mobile smoke; invite link copy (when D ships).

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Existing Owners trapped in `/setup` | **Backfill §3.2** + kill-switch |
| Hard redirect + broken PATCH | `ENABLE_SETUP_WIZARD` off instantly |
| Status/step drift | Derive-first; minimal persisted fields |
| Silent `registration_type` default flip | D-5 audit; default **defer** |
| Composition illegal GST invoice | Automated gate tests in B10 |
| Metrics without viewers | Sink + weekly review before B pilot |
| Overbuilding C/D | Provisional; funnel-gated |

---

## 9. Out of scope

Email verify / magic signup · auto-login · full product tour · mandatory opening stock/purchase · CoA/GSTR/e-invoice in first-run · WhatsApp nudges · multi-company · marketing redesign · changing model `registration_type` default without create-site audit

---

## 10. Documentation updates

| Doc | When |
|-----|------|
| This plan | Living |
| `docs/pilot/ONBOARDING.md` | A6; again if D ships |
| `README.md` | After B + flag docs |
| `web/.env.example` | Wizard flag + analytics sink |
| Support runbook | If/when D ships |

---

## 11. Implementation order

```text
[ ] Wave A1–A7 (+ shared tax helper, metrics sink decision)
[ ] Wave B0  — ENABLE_SETUP_WIZARD
[ ] Wave B1  — minimal fields + backfill + tests
[ ] Wave B2–B7 — setup + first bill (POS per D-6)
[ ] Wave B8–B10 — residual + i18n + Composition automated gate
[ ] Review funnel → decide Wave C / D scope
[ ] Provisional C / D as justified
```

---

## 12. Decisions

| # | Topic | Resolution |
|---|-------|------------|
| D-1 | GST at register vs setup | **Short register + `/setup` tax step** |
| D-2 | Hard vs soft redirect | **Hard redirect when wizard flag on**, with Skip + kill-switch |
| D-3 | When COMPLETED | **Derived** from any Completed sales/POS doc |
| D-4 | Composition GSTIN | **Optional but recommended** |
| D-5 | Model default → UNREGISTERED | **Defer.** RegisterView already passes UNREGISTERED. Audit every `Company.objects.create` (admin, seeds, `tenant_backup` sandbox, `conftest`, etc.) before any default change. Flipping default changes GST gate behavior for implicit creates. Prefer explicit `registration_type=` at each create site. |
| D-6 | POS in Step 5 | **Decide before B7:** (a) Invoice-only in V1, POS CTA only outside wizard; or (b) Step 5 chooser when POS flag on. Default recommendation: **(a) invoice-only in Wave B**; add POS branch only if pilot is POS-heavy (Wave C). Update §0 wording to match chosen option. |
| D-7 | Persisted fields | **Derive status/step; persist `onboarding_dismissed_at` + `tax_profile_confirmed_at` (+ optional `started_at`)** — not a four-field status machine |
| D-8 | Waves C/D | **Provisional**, gated on A/B funnel |
| D-9 | Metrics | **Named sink + weekly pilot review** before hard-redirect pilot |

---

## 13. Traceability

| Requirement | Source |
|-------------|--------|
| First invoice < 30 min | MVP E6.4 |
| Pilot ops | `docs/pilot/ONBOARDING.md` |
| GST Complete gates | `registration_gates.py` / BB-000007 |
| Non-enumerating register | BB-000251 / BB-000389 |
| Invite accept | BB-000418 (`AcceptInvitePage` already reads `?token=`) |
| Checklist | `OnboardingChecklist.tsx` |

### Review incorporation log (2026-08-21)

| Review point | Plan change |
|--------------|-------------|
| Migration backfill for existing companies | §3.2 + B1 tests |
| D-5 model default risk | Deferred; audit create sites |
| Goal vs Step 5 POS mismatch | D-6 + §0/§5 alignment |
| Composition gate manual-only | B10 automated e2e/API |
| No wizard kill-switch | B0 `ENABLE_SETUP_WIZARD` |
| Metrics with no destination | §0 metrics destination + D-9 |
| Invite `?token=` overstated | D2 narrowed; D1 is real gap |
| Duplicate A3/A5 then B tax copy | Shared helper |
| Four persisted fields vs derive | §3.1 derive-first |
| C/D 4–6 weeks committed | A+B committed; C/D provisional |

---

**Bottom line:** Commit to **Wave A + Wave B** behind a kill-switch, with **backfill + derive-first progress** so existing tenants are safe. Treat **C/D as backlog** until funnel data says what matters. Do **not** flip `registration_type` model default in B1.