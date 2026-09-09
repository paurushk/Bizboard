# BizBoard Freeze Scope

**Status:** D1–D5 resolved 2026-09-08 (all ON; books is a hard gate). Sections G
(not-yet-scoped flows) and H (FE / mobile / async / privacy / ops / edge cases)
added 2026-09-09 — need disposition + decisions D6–D14. **Scope revision
2026-09-09b (PO call):** of D6–D14 only D9b, D12, D13, D14 are retained in the
freeze; D6, D7, D8, D9, D10, D11 demoted to KNOWN LIMITATIONS (see that section).
Pending: A/B/C/G/H review + signature.
**Created:** 2026-09-08 · **Owner:** founder · **Supersedes for scope purposes:** the
"Module status (authoritative)" table in [`../README.md`](../README.md) and every
document under [`reviews/`](reviews/).

---

## Why this document exists

BizBoard is moving from open-ended feature work to a **freeze → real-user
validation** phase. The test suite is becoming the durable specification of the
system (see the Quality Architecture / Freeze Gate plan). A spec cannot be
written against a moving target, so this document **fixes what BizBoard is** for
the freeze:

- **SUPPORTED** — must work correctly at freeze; each item is protected by a
  named Freeze Gate check (Phase 2).
- **NOT SUPPORTED** — explicitly out; a Phase 2 test asserts the feature/route is
  genuinely inaccessible in the frozen flag profile.
- **KNOWN LIMITATIONS** — works, but with a caveat a pilot user must be told.
- **DECISIONS NEEDED** — genuine product-scope calls only the founder can make;
  the freeze cannot be declared until these are resolved.

### Governing rule

> The Freeze Gate is a fixed list. When every SUPPORTED item is green and every
> NOT SUPPORTED item is proven inaccessible, BizBoard freezes. Adding scope after
> ratification requires removing scope. No new features until real-user
> validation completes.

"Freeze Gate section" references (e.g. `FG-2a/gl`, `FG-2e#3`) point at the phase
plan; they are the executable checks that protect each row.

---

## A. SUPPORTED — frozen pilot scope

Every row must be green at freeze. "Protected by" names the Freeze Gate check(s)
that guard it.

| # | Capability | Workflow granularity (what must work end to end) | Protected by |
|---|---|---|---|
| A1 | Sales invoice — GST intra-state | Draft → add lines → complete → stock ↓, CGST/SGST computed, AR ↑, GL balanced, TB = 0 | `FG-2e#1`, `FG-2a/gl`, `FG-2c` |
| A2 | Sales invoice — GST inter-state | Same as A1 but IGST (+ cess where set); place-of-supply drives the split | `FG-2e#2`, `FG-2c` |
| A3 | Sales invoice — non-GST / nil-rated | Complete with zero tax; totals and GL still consistent | `FG-2c` |
| A4 | Quotation | Create quotation → convert to invoice; no stock/GL effect until invoice completes | `FG-2e#1` (extend), `FG-2f` |
| A5 | Sales return / credit note | Against a completed invoice → stock ↑, GST reversal, AR ↓, appears in GSTR-1 CDNR aid | `FG-2e#3`, `FG-2a/gst` |
| A6 | Purchase (no GRN) | Purchase complete posts stock ↑ **and** AP ↑ atomically; ITC recorded | `FG-2e#4`, `FG-2a/gl` |
| A7 | Purchase return / debit note | Against a completed purchase → stock ↓, GST reversal, AP ↓ | `FG-2e#5` |
| A8 | Product lookup | Barcode / SKU / name search returns the right product, company-scoped | `FG-2g` (component), e2e journey |
| A9 | Inventory movements & balances | Typed, append-only movements; balance row == Σ movements for every (item, godown, lot) at all times | `FG-2a/inventory` |
| A10 | Customer receipt + allocation | Record receipt → allocate to invoice(s) → AR reflects it; over-allocation rejected | `FG-2e#1`, `FG-2a/gl` (AR recon) |
| A11 | Supplier payment + allocation | Record payment → allocate to bill(s) → AP reflects it | `FG-2e#4` |
| A12 | Customer & supplier ledgers | Derived from documents + returns + allocations (no ledger tables); balance reconciles to AR/AP control | `FG-2a/gl` (subledger recon) |
| A13 | Core reports | Trial balance, P&L, balance sheet, stock summary, customer/supplier ledger, sales/purchase registers — values stable and internally consistent | `FG-2f` (golden snapshots) |
| A14 | PDF / A4 invoice | Renders with correct totals, tax breakup, party details | `FG-2f` (PDF text snapshot) |
| A15 | Imports | Products, customers, suppliers, opening stock — re-running the same import row is idempotent (no double stock / double party) | `FG-2e` (import idempotency), `FG-2a` |
| A16 | Exports | Data exports produce well-formed files matching source data | `FG-2f` |
| A17 | RBAC | Owner/Admin can do everything in scope; Sales Staff limited per the capability flags; drift from the matrix fails CI | `FG-2d` (RBAC matrix) |
| A18 | Tenant isolation | Every list/detail/mutation endpoint is `company_id`-scoped; tenant A cannot read or mutate tenant B; IDOR on document IDs blocked | `FG-2d` (URL-conf parametrized) |
| A19 | First-run onboarding | Register → login → guided `/setup` (wizard ON) → dashboard checklist | e2e golden journey |
| A20 | Auth | Register, login, logout, session expiry boundaries | `FG-2d` (auth boundary) |
| A21 | Period close + correction | Closed period rejects back-dated posting; sanctioned H9 correction path posts a reversing + re-post pair that nets to zero | `FG-2e#7`, `FG-2a/gl` |
| A22 | Money representation | All money crosses the API as fixed-scale decimal strings; Σ line rounding == document round-off; no float on any boundary | `FG-2a/money`, existing `test_money_contract.py` |
| A23 | Counter POS *(D1 = ON)* | `/pos` checkout → retail invoice complete → stock ↓ → GST → cash/UPI receipt → GL; thermal PDF when available; shared offline draft outbox | `FG-2e#9` (POS chain), POS golden journey |
| A24 | TDS / TCS *(D2 = ON)* | 194Q / 206C on the relevant document; explicit withholding amount overrides the rate-derived amount, and both are logged; correct GL (2265 / 206C control) | `FG-2c` (named TCS/TDS checks), `FG-2a/gl` |
| A25 | Online payment collection *(D3 = ON, sandbox)* | Gateway (Cashfree **or** PayU sandbox) capture webhook → receipt → allocation → GL; replaying the same webhook is a no-op; capture for a cancelled/closed-period invoice parks then refunds | `FG-2e#8` (webhook idempotency), `FG-2a/gl` |
| A26 | OTP login *(D4 = ON)* | Request OTP → verify → session; OTP is hashed at rest; request/verify rate-limited; lockout after N failures | `FG-2d` (OTP hashing + rate-limit) |

## B. NOT SUPPORTED — out of scope for freeze

Frozen OFF in the pilot flag profile (`backend/.env.pilot.example`,
`web/.env.pilot.example`). A Phase 2 test asserts each route/feature is
inaccessible with that profile.

| Feature | Flag(s) (frozen value) | Why out for freeze |
|---|---|---|
| GSTR report screens / on-portal filing | `ENABLE_GSTR=0`, `VITE_ENABLE_GSTR=false` | Offline worksheets only; not GSTN filing (see C1) |
| GSTN JSON export | `ENABLE_GSTN_JSON=0` | Depends on GSTR screens |
| Live NIC e-invoice / e-way | `GSP_LIVE_ENABLED=0` | No live GSP integration in pilot (see C2) |
| e-invoice sandbox submit UI | `VITE_ENABLE_EINVOICE_SUBMIT=false` | Preview only; not a filing path (see C2) |
| AI insights | `ENABLE_AI` / `company.ai_features_enabled=off`, `VITE_ENABLE_AI=false` | Not a pilot differentiator; unbounded surface |
| Tally migration / sync | `ENABLE_TALLY=0`, `VITE_ENABLE_TALLY=false` | Export dump only; no live sync |
| Manufacturing | `ENABLE_MANUFACTURING=0` (dark module) | Dark in production |
| Payroll | `ENABLE_PAYROLL=0` (dark module) | Dark in production |
| CRM | `ENABLE_CRM=0` (dark module) | Dark in production |
| Fixed assets + depreciation | `ENABLE_FIXED_ASSETS=0` | KNOWN LIMITATION (D6, revision 2026-09-09b) — route 404s in the pilot profile |
| Bill of Entry / import purchase + landed cost | `ENABLE_BOE=0` | KNOWN LIMITATION (D10, revision 2026-09-09b) — route 404s in the pilot profile |
| WhatsApp Cloud API | `ENABLE_WHATSAPP_CLOUD=0` | Share-link only in pilot |
| Account Aggregator banking | `ENABLE_ACCOUNT_AGGREGATOR=0`, `ENABLE_AA_CONSENT=off` | No AA integration in pilot |
| Postgres RLS | `POSTGRES_RLS_ENABLED=0` | App-layer `company_id` scoping is the pilot isolation guarantee; RLS unproven |
| Help v2 | `VITE_HELP_V2=false`, `helpV2=off` | Help v1 is the supported surface |
| Item custom fields v2 | `item_custom_fields_v2=off` | Not in pilot scope |
| Advanced demo surfaces | `VITE_PILOT_ADVANCED=false` | Master switch for local-demo-only features |
| Native mobile / app stores | n/a | Android WebView shell for internal testing only; no store binary |
| Multi-company / multi-branch GSTIN | n/a (not built) | Single GSTIN per company in pilot |
| Full perpetual FIFO COGS | n/a | Running-cost model only (see C3) |

## C. KNOWN LIMITATIONS — supported, with caveats

| # | Area | Limitation | Pilot-user-facing note |
|---|---|---|---|
| C1 | GST returns | GSTR-1/3B are **offline worksheets / aids**, not GSTN filing. GSTR-2B ITC match is not implemented. | "Use the worksheet to file on the GST portal yourself." |
| C2 | e-invoice / e-way | Sandbox/preview only; no live IRN generation. | "e-invoice preview is not a filed IRN." |
| C3 | Inventory costing | Running weighted cost, not full perpetual FIFO COGS layers. Cost is recomputable from movements (`FG-2a/inventory`). | Internal note only. |
| C4 | Accounting books | Per-company opt-in (`company.accounting_enabled`). **D5 = at least one pilot company will use books**, so `FG-2a/gl` (balanced journals, TB=0, subledger reconciliation, closed-period) is a **hard blocking gate** for the freeze, not just a pre-opt-in check. | "Books module is opt-in per company." |
| C5 | Offline drafts | Invoice/POS drafts are **plaintext on device**; sign-out wipes them. `/api` responses are not cached. No iOS background-sync guarantee. | "Don't rely on offline drafts on a shared device." |
| C6 | OTP / SMS *(D4 = ON)* | OTP login requires `SMS_PROVIDER=msg91` or `twilio` configured on the pilot host; with `SMS_PROVIDER` unset/console, OTP is unavailable and login falls back to password. | "SMS OTP needs a live SMS provider on your deployment." |
| C8 | Payment gateway *(D3 = ON)* | Sandbox only — no live Cashfree/PayU settlement. At least one provider's sandbox credentials + `SANDBOX_WEBHOOK_SECRET` must be configured; the Phase 2 webhook chain targets whichever is configured. | "Online payments run in sandbox during the pilot." |
| C7 | Scale | Pilot is sized for small traders; no load testing yet (Phase 5). | Internal note only. |

## D. DECISIONS — resolved 2026-09-08

| # | Decision | Resolution | Freeze Gate consequence |
|---|---|---|---|
| D1 | Counter POS | **ON** — POS is in freeze scope | `FG-2e#9` POS chain + a POS golden journey added to Phase 2. Flags `ENABLE_POS` / `VITE_ENABLE_POS` / `VITE_ENABLE_ATOMIC_POS_CHECKOUT` = ON. See A23. |
| D2 | TDS / TCS | **ON** — 194Q/206C in freeze scope | Existing TCS/TDS logic + the "explicit amount overrides rate" decision promoted to named `FG-2c` checks. Flags `ENABLE_TDS` / `VITE_ENABLE_TDS` = ON. See A24. |
| D3 | Online payment collection | **ON (sandbox)** — gateway capture in freeze scope | `FG-2e#8` (webhook idempotency) is a blocking gate; needs Cashfree **or** PayU sandbox credentials + `SANDBOX_WEBHOOK_SECRET` in CI. Flags `ENABLE_CASHFREE` / `ENABLE_PAYU` = ON. See A25, C8. |
| D4 | OTP auth | **ON** — OTP login in freeze scope | OTP hashing + request/verify rate-limit + lockout join `FG-2d`. Flags `OTP_ENABLED` / `VITE_ENABLE_OTP` = ON; pilot host needs `SMS_PROVIDER=msg91\|twilio`. See A26, C6. |
| D5 | Accounting books in pilot | **Yes** — ≥1 pilot company will use books | `FG-2a/gl` (balanced journals, TB=0, subledger reconciliation, closed-period) is a **hard blocking gate** for the freeze. See C4. |

## E. Flag reconciliation (authoritative)

Every feature flag in the codebase, its frozen pilot value, and which list it
belongs to. Source: `backend/config/settings.py`,
`backend/core/services/feature_flags.py`, `web/.env.example`.

| Flag | Layer | Frozen pilot value | List |
|---|---|---|---|
| `ENABLE_SETUP_WIZARD` / `VITE_ENABLE_SETUP_WIZARD` | both | **ON** (`1` / `true`) | A19 SUPPORTED |
| `company.accounting_enabled` / `VITE_ENABLE_ACCOUNTING` | both | per-company opt-in; ≥1 pilot company ON (D5) → `FG-2a/gl` hard gate | C4 |
| `company.ai_features_enabled` / `VITE_ENABLE_AI` | both | OFF | B |
| `ENABLE_GSTR` / `VITE_ENABLE_GSTR` | both | OFF | B (worksheets = C1) |
| `ENABLE_GSTN_JSON` | backend | OFF | B |
| `ENABLE_FIXED_ASSETS` | backend | **OFF** (`0`) — default ON in code | B (D6 → KNOWN LIMITATION, revision 2026-09-09b) |
| `ENABLE_BOE` | backend | **OFF** (`0`) — default ON in code | B (D10 → KNOWN LIMITATION, revision 2026-09-09b) |
| `ENABLE_TALLY` / `VITE_ENABLE_TALLY` | both | OFF | B |
| `ENABLE_POS` / `VITE_ENABLE_POS` / `VITE_ENABLE_ATOMIC_POS_CHECKOUT` | both | **ON** (D1) | A23 SUPPORTED |
| `ENABLE_MANUFACTURING` / `VITE_ENABLE_MANUFACTURING` | both | OFF (dark) | B |
| `ENABLE_PAYROLL` / `VITE_ENABLE_PAYROLL` | both | OFF (dark) | B |
| `ENABLE_CRM` / `VITE_ENABLE_CRM` | both | OFF (dark) | B |
| `ENABLE_TDS` / `VITE_ENABLE_TDS` | both | **ON** (D2) | A24 SUPPORTED |
| `ENABLE_WHATSAPP_CLOUD` | backend | OFF | B |
| `ENABLE_ACCOUNT_AGGREGATOR` / `ENABLE_AA_CONSENT` | backend | OFF | B |
| `ENABLE_CASHFREE` / `ENABLE_PAYU` | backend | **ON, sandbox** (D3) — ≥1 provider configured | A25 SUPPORTED / C8 |
| `VITE_ENABLE_EINVOICE_SUBMIT` | frontend | OFF | B (preview = C2) |
| `GSP_LIVE_ENABLED` | backend | OFF | B |
| `POSTGRES_RLS_ENABLED` | backend | OFF (`0`) | B |
| `OTP_ENABLED` / `VITE_ENABLE_OTP` | both | **ON** (D4) — host needs `SMS_PROVIDER` | A26 SUPPORTED / C6 |
| `VITE_PILOT_ADVANCED` | frontend | OFF (`false`) | B |
| `VITE_HELP_V2` / `helpV2` | both | OFF | B |
| `item_custom_fields_v2` | both | OFF | B |
| `ENABLE_API_DOCS` | backend | OFF in prod (on under `DEBUG`) | dev tooling — n/a |
| `ADMIN_ENABLED` | backend | OFF in prod | dev tooling — n/a |
| `VITE_USE_MOCKS` | frontend | `false` (prod build refuses `true`) | dev/e2e — n/a |

**Operational toggles — not feature flags, not frozen scope** (listed so the
config-consistency guard ignores them): `AUTO_PICK_COMPANY_ON_EMPTY`,
`CELERY_ENABLE_UTC`, `CELERY_TASK_ALWAYS_EAGER`, `CLAMAV_OPTIONAL`,
`DJANGO_FAIL_FAST_SECRETS`, `GATEWAY_HOLDING_STATE`, `GSP_CERTIFIED`,
`GSP_HTTP_SANDBOX`, `JSON_REQUEST_LOGS`, `OTP_DEBUG_ECHO`,
`PAYMENTS_REFUND_EVENT_MAP_V2`, `REQUIRE_SANDBOX_WEBHOOK_SECRET`,
`SECURE_SSL_REDIRECT`, `USE_TLS`. These control
infra/runtime behaviour, not product surface. `GATEWAY_HOLDING_STATE` and
`GSP_HTTP_SANDBOX` are sub-toggles of D3 / C2 respectively and follow those
decisions.

A Phase 1 config-consistency guard (`FG-1`) asserts this table stays in sync with
the code: every product `_env_bool("X")` / `VITE_ENABLE_X` in the tree appears
here exactly once (the operational toggles above are the allow-listed
exceptions).

## F. Feature freeze declaration

On ratification:

- **No new features** merge to `main` until real-user validation (Phase 4)
  completes. Branches may exist; they do not merge.
- **In scope during freeze:** bug fixes, correctness fixes surfaced by the Freeze
  Gate, and the Freeze Gate machinery itself.
- Everything under [`reviews/`](reviews/) is **history, not scope** — see
  [`reviews/README.md`](reviews/README.md).
- The frozen flag profile is `backend/.env.pilot.example` +
  `web/.env.pilot.example`. Deviating from it in a pilot deployment is a
  documented exception, not a default.

---

## G. Not yet scoped — decide in / out before ratification

Surfaces present in the codebase that Sections A–E did not classify. Each needs a
call: **SUP** (SUPPORTED — add a Freeze Gate chain/invariant), **LIM** (KNOWN
LIMITATION — works, stated to the pilot user, not gate-tested), **OUT** (NOT
SUPPORTED — a test asserts it is inert/inaccessible), or **P3/P5** (deferred to
that phase). The "proposed" column is a recommendation, not a decision.

### G1 — Accounting core (D5 = ON makes most of these SUP)

| Flow | Proposed | If SUP → Freeze Gate artifact |
|---|---|---|
| Manual journal entry (create / post / reverse a JV) | **SUP** | WF-29; `CanPostJournals` in RBAC matrix |
| Chart of accounts management (add / edit / deactivate) | **SUP** | WF-30 + RBAC |
| Financial-year close (`fy-close/`) — retained earnings, opening carry-forward | **SUP** | WF-31; `gl.trial_balance_zero` across the FY boundary |
| Opening balance entry (TB opening + party openings) | **SUP** | WF-32; `gl.*` must hold after opening load |
| Bank reconciliation (`bank-recon-sessions`) — match statement lines to GL | **SUP** | WF-33 (extends WF-26) |
| Accounting period lifecycle (open / soft-close / reopen) | **SUP** | fold into WF-20 |
| Cost centres + allocation on postings | **LIM** | — |
| Fixed assets + depreciation + disposal (`fixed-assets`) | **D6** | founder call — recommend **OUT** for pilot |

### G2 — TDS / TCS (D2 = ON makes the core SUP)

| Flow | Proposed | If SUP → artifact |
|---|---|---|
| TCS on sales (206C) — collection, threshold, GL | **SUP** | WF-34 + `FG-2c` named checks |
| TDS on purchases (194Q) — deduction, threshold, GL | **SUP** | WF-35 |
| TDS / TCS worksheets (`tds-worksheet`, `tcs-worksheet`) reconcile to txns | **SUP** | WF-36 + report snapshot |
| GSTR-7 (TDS return) / GSTR-8 (TCS return) | **D7** | recommend **LIM** (worksheet, not portal filing — mirrors C1) |
| TDS / TCS certificates (Form 16A / 27D) | **D7** | recommend **LIM** |

### G3 — Payments (D3 = ON)

| Flow | Proposed | If SUP → artifact |
|---|---|---|
| Refunds — customer refund + gateway refund | **SUP** | WF-37 |
| MDR / settlement reconciliation (`payment-recon`) — capture vs settlement, fees | **SUP** | WF-38 |
| Advance / on-account payments + GST on advances (GSTR-1 AT / ATADJ) | **SUP** | WF-39 |
| Bad-debt write-off → GL | **SUP** | WF-40 |
| Payment links (`payment-links`, `public/pay/<token>`) — create, pay, expiry | **SUP** | fold into WF-17 |
| Bank statement import + line matching (`bank-statements`) | **SUP** | WF-41 (feeds WF-33) |
| Dunning / payment reminders (`payments/dunning.py`) — schedule + escalation | **SUP** for the schedule logic; **LIM** for actual send | WF-42 |
| Collection-risk scoring (`collection-risk`) | **LIM** | — |

### G4 — Sales / Purchase not on the checklist

| Flow | Proposed | If SUP → artifact |
|---|---|---|
| Invoice cancellation — reverse stock + GST + GL + AR; cancelled-number handling | **SUP** | WF-43 |
| Invoice amendment (H9 correction path) | **SUP** | WF-44 |
| Reverse charge (RCM) — self-invoice, RCM liability + ITC | **D8** | recommend **SUP** (freight / GTA / legal are common) |
| Composition dealer — bill of supply (no tax) + CMP-08 | **D9** | recommend **OUT** unless a pilot company is composition |
| Nil-rated / exempt / non-GST supply — GSTR treatment | **SUP** | fold into WF-27 |
| Cess — specific / per-unit (`cess_amount`, pan-masala) | **D9b** | **SUP** iff a pilot item needs it, else **LIM** |
| Discounts — line %, line amount, document-level, >100 % guard | **SUP** | settings/price matrix + a chain |
| Bill of Entry / import purchase + landed cost | **D10** | recommend **OUT** for pilot |
| ITC eligibility classification (`itc_eligibility` — blocked / ineligible) | **SUP** | part of WF-04 / WF-12 |
| Partial PO receipt / partial billing | **LIM** | — |
| Invoice share link / send (email / WhatsApp share) | **LIM** | — |

### G5 — GST returns

| Flow | Proposed |
|---|---|
| GSTR-9 (annual) / GSTR-4 (composition) / GSTR-6 (ISD) | **LIM** — worksheets, not filing (C1) |
| GST health / rate exposure / CA pack (`gst-health`, `gst-rate-exposure`, `gst-ca-pack`) | **LIM** — advisory; snapshot only |
| HSN summary correctness in GSTR-1 | **SUP** — fold into WF-27 |

### G6 — Auth / users / company / billing

| Flow | Proposed | If SUP → artifact |
|---|---|---|
| Registration (email verify + first company) | **SUP** | WF-45 |
| Password reset / change | **SUP** | WF-46 + rate-limit |
| JWT refresh / rotation / logout / session expiry enforcement | **SUP** | WF-47 |
| User invite → accept → role assignment | **SUP** | WF-48 + RBAC |
| Switch-company context (`switch-company`) | **SUP** | WF-49 + tenancy probe |
| GSTIN change effect on existing documents | **LIM** | — |
| Sandbox / trial expiry cleanup (`company_sandbox_expires_at`, `accounts/tasks.py`) | **SUP** | WF-50 (data-safety) |
| SaaS subscription lifecycle (trial / upgrade / downgrade / SaaS invoice / dunning) | **LIM** | — |
| Plan-limit enforcement (feature + count gates) | **D11** | recommend **SUP** for the feature gates that back `plan_modules_for_company` |

### G7 — Cross-cutting

| Concern | Proposed | Artifact |
|---|---|---|
| Idempotency contract (`IdempotencyRecord`) — replay any mutating call w/ same key ⇒ no double effect | **SUP** | WF-51 (dedicated) |
| Concurrency / races — oversell, double-allocation | **SUP** | adopt `tests/test_concurrency_races.py` as a Freeze Gate lane |
| Audit-trail completeness — every mutation writes `AuditEvent` | **SUP** | new invariant `audit.key_entities_logged` |
| Money-field audit (`MoneyFieldAudit`, `log_money_change`) — money changes on completed docs are logged | **SUP** | new invariant `money.changes_audited` |
| Document numbering (`DocumentSeries`) — gap-free, per-FY reset, unique under concurrency | **SUP** | new invariant `numbering.sequences_intact` + WF-52 |
| Rounding / document-figure mode (`DOCUMENTS_ALWAYS` vs derived) | **SUP** | Company settings matrix (already planned) |
| Notifications delivery (email / SMS / in-app) | **LIM** | — |
| File assets — upload/download auth + path traversal | **SUP** (security); virus scan **LIM** | tenancy sweep + a path-traversal test |
| Search behaviour (relevance) | **LIM** — tenant-scoping is covered | — |
| Rate limiting (`core/throttles.py`) on auth endpoints | **SUP** | fold into WF-18 / WF-46 |
| Export format correctness (CSV / XLSX / JSON) + non-invoice PDFs | **LIM** — snapshot the important ones later | — |
| Multi-currency | **OUT** — INR only; state it |
| Backfill / reconcile management commands — safe & idempotent | **P3** — migration rehearsal |

### Founder decisions — RESOLVED 2026-09-09 (all SUPPORTED)

> **SUPERSEDED IN PART — Scope revision 2026-09-09b (PO call):** of D6–D11, only **D9b** stays in the
> freeze. **D6, D7, D8, D9, D10, D11 are demoted to KNOWN LIMITATIONS** — see the
> [Scope revision 2026-09-09b](#scope-revision-2026-09-09b-po-call) section below. The rows here record
> the original 2026-09-09 resolution.

| # | Decision | Resolution | New Freeze Gate work |
|---|---|---|---|
| **D6** | Fixed assets + depreciation | **SUP — full chain** | WF-53: acquisition → depreciation run → disposal, each balanced GL; `gl.*` holds |
| **D7** | TDS/TCS returns + certificates | **SUP** | WF-54: GSTR-7/8 JSON assembly reconciles to the worksheets; 16A/27D generation |
| **D8** | Reverse charge (RCM) | **SUP — chain** | WF-55: RCM self-invoice → RCM liability + ITC; new RCM row in the place-of-supply matrix |
| **D9** | Composition dealer + CMP-08 | **SUP — chain** | WF-56: bill of supply (no CGST/SGST/IGST); CMP-08 quarterly assembly |
| **D9b** | Per-unit / specific cess | **SUP — always** | fold into WF-02: `cess_amount` per unit added on top of ad-valorem; GSTR treatment |
| **D10** | Bill of Entry / import purchase + landed cost | **SUP — chain** | WF-57: BOE → customs duty + IGST-on-import + landed-cost capitalised into inventory value → GL |
| **D11** | Plan-limit enforcement | **SUP — feature gates AND count limits** | WF-58: entitlement fail-closed + quota (invoice/user) enforcement + over-limit behaviour |

---

## H. Out of the invariant / chain frame

The invariants + workflow chains + matrices are deep on **backend business-state
correctness** and thin on frontend, mobile, async, privacy, ops, and edge cases.
This section assigns every one of those so nothing is merely implied. Dispositions
as in §G: **SUP** / **LIM** / **OUT** / **P3** / **P5**.

### H1 — Frontend behaviour

| Concern | Disp. | Artifact / note |
|---|---|---|
| FE↔BE validation parity (money, tax, required fields) | **SUP** | extend the API-contract layer (`FG-2g` level 2) |
| Error rendering — BE 4xx + `HelpCode` → usable message | **SUP** | one error path asserted in the golden journey |
| Auth guards / redirect-after-login / protected-route redirect | **SUP** | golden journey + a logged-out-route test |
| UI permission gating matches the RBAC matrix (role hides nav/actions) | **SUP** | new FE test: render as each role, assert hidden surfaces |
| Offline draft outbox — save / sync / **conflict** (`invoiceDraftCache.ts`) | **SUP** | adopt existing tests + add a conflict case |
| Hindi i18n (`web/src/i18n/hi.ts`) — key coverage | **LIM** | key-presence check only |
| "Fetch all pages" helper (`scripts/check-fetch-all-pages.mjs`) | **SUP** | already in `npm run lint` — keep |
| Cache invalidation / stale data; number/locale formatting | **LIM** | — |
| ~90 pages / 15 settings screens as UI flows | **LIM** | one smoke each for Company / GST / Users / Price Lists; rest LIM |

### H2 — Mobile (Capacitor)

| Concern | Disp. |
|---|---|
| Is the Android WebView shell in the pilot at all? | **D12** |
| If yes: session persistence, deep links, offline-on-mobile | **P5** (Phase-1 gate already covers `allowBackup=false` + no hardcoded URL) |
| If no | **OUT** — assert the shell is not a pilot deliverable |

### H3 — Async / Celery

| Concern | Disp. | Note |
|---|---|---|
| Task *effects* (PDF, e-invoice submit, reconcile, alerts, rebuild) | **SUP (partial)** | already run eager inside the workflow chains; final state asserted |
| Task retry / failure → user-visible state (failed PDF, stuck submit) | **SUP** | a few targeted tests |
| celery-beat periodic tasks registered + dry-runnable | **SUP** | registry assertion + per-task dry run |
| Real-broker ordering (eager mode hides it) — webhook vs period close etc. | **P5** | run key chains against a real broker |

### H4 — DPDP / data lifecycle / privacy

| Concern | Disp. | Note |
|---|---|---|
| Data-subject export = exactly one company's data | **SUP** | tenancy assertion on the export payload |
| Right-to-erasure / cascade-on-delete | **D13** | recommend **LIM** for pilot (documented manual process) |
| PII masking in request logs (`JSON_REQUEST_LOGS`) and exports | **SUP** | log/export contains no unmasked PII fields |
| Audit-log immutability | **SUP** | new invariant `audit.append_only` (no update/delete path on `AuditEvent`) |
| Backup encryption when `TENANT_EXPORT_FERNET_KEY` set | **P3** | backup/restore drill |
| Data residency | **OUT** | single region — state it |

### H5 — Observability / error paths

| Concern | Disp. | Artifact |
|---|---|---|
| Every raised `HelpCode` resolves to a help entry | **SUP** | extend `test_help_codes_live.py` — assert coverage, not just samples |
| Exception → HTTP status mapping (known errors are 4xx, never 500) | **SUP** | `tests/errors/` — trigger each error family, assert status + code |
| `HealthView` checks DB; `MetricsView` output parses | **SUP** | small smoke |
| Boot-time config validation (`DJANGO_FAIL_FAST_SECRETS`) | **SUP** | missing critical setting raises at startup |

### H6 — Business-logic edge cases  → new lane `tests/edge/`

**SUP** — parametrized: zero-qty / zero-value docs · decimal overflow at `max_digits`
· negative amounts where unexpected · backdated (before opening stock) / future-dated
· document spanning a period / FY boundary · multi-line invoice with mixed rates /
HSN / cess · rounding at 0.005 · UoM conversion · same party as customer + supplier
· service (non-stock) vs stock item · deleting a `PROTECT`-referenced master ·
duplicate-customer merge.

### H7 — Report reconciliation

**SUP** — new invariant `reports.cross_reconcile`: P&L net == TB (income − expense);
balance sheet ties to TB; stock-summary value == inventory GL account balance;
dashboard KPI == its drill-down list. Plus snapshots of the key reports **under
date / party / godown / cost-centre filters** (current snapshots are unfiltered).

### H8 — Pagination / bulk / scale

| Concern | Disp. |
|---|---|
| Pagination correctness — page-size cap, stable ordering, total count (`core/pagination.py`) | **SUP** (light) |
| Bulk endpoints — size limits, partial-failure semantics | **LIM** |
| Large-company behaviour (100k invoices → reports / exports / lists) | **P5** (perf) |

### H9 — Environment / deployment

| Concern | Disp. | Note |
|---|---|---|
| SQLite (local default) vs Postgres (prod) parity | **SUP — covered** | CI `backend` / `invariant-sweep` / `e2e-golden` run on Postgres; keep it that way |
| Security headers / CORS / CSRF / CSP present | **SUP** | header-presence test |
| Docker image actually runs + `/health` responds | **P3** | Phase-1 only builds it |
| Secret rotation, DB connection limits, static/media serving | **P5 / ops** | — |

### H10 — Integrations

| Concern | Disp. | Note |
|---|---|---|
| Webhook signature verification for **every** inbound webhook | **SUP** | enumerate them; apply the WF-17 pattern to each |
| Email / SMS sending (adapters exist, `test_next_batch_smtp_gsp`) | **LIM** | delivery is external |
| File-storage backend (`FileAsset`) — upload / download auth / path traversal | **SUP** | folded into H4 + the tenancy sweep |
| LLM bill extraction — failure / timeout / cost handling + prompt-injection on uploaded bills | **D14** | recommend **SUP** for failure handling + an injection guard |

### H11 — Test-infra & governance (process, not product scope)

| Item | Owner / phase |
|---|---|
| Suite speed (~7 min small runs) — split the fast lane | **Phase 2 blocker — now** |
| `INVARIANTS_STRICT=1` full-suite triage | **Phase 2** |
| Run the mutation audit (`scripts/mutation_audit.sh`), act on survivors | **Phase 2h** |
| Capture a coverage baseline; make diff-cover blocking | **finish Phase 1** |
| Get `determinism-probe` (frozen clock / no socket) green | **finish Phase 1** |
| Enforce "red-then-green evidence" for regression tests with a check | **finish Phase 1** |
| Wire CA sign-off to the blessed GST / accounting golden fixtures | **Phase 3** |
| Check branch-protection required checks against GitHub (not just `ci.yml`) | **Phase 3** (needs `gh` API) |
| Feature-flag kill-switch / rollback test; validate `docs/pilot/RUNBOOKS.md` | **Phase 3** |
| External security pen-test | **Phase 5** |

### Founder decisions — RESOLVED 2026-09-09

> **Confirmed by Scope revision 2026-09-09b (PO call):** D12, D13, D14 all stay in the freeze as resolved here.

| # | Decision | Resolution | New Freeze Gate work |
|---|---|---|---|
| **D12** | Capacitor Android shell in the pilot | **SUP — ships to pilot users** | §H2 items pulled forward: mobile session persistence, deep links, offline-on-mobile → a mobile test lane |
| **D13** | Right-to-erasure | **SUP — automated now** | WF-59: cascade erasure across all tenant data, retain only what law requires, nothing orphaned (new invariant `tenancy.no_orphans_after_erasure`) |
| **D14** | LLM bill-extraction hardening | **SUP — failure handling + prompt-injection guard** | `tests/errors/` + a guard: provider timeout/error → draft-with-warning, never crash/silent-wrong-data; injected instructions in uploaded bill text are inert |

---

## Scope revision 2026-09-09b (PO call)

The D6–D14 tranche resolved 2026-09-09 roughly doubled the Phase 2 chain count. This PO revision trims it
back to what the first pilot (ARCH-03 semi-wholesaler, desktop-first) actually needs, plus the two
cross-cutting delivery/compliance items the founder wants shipped.

**Retained in the freeze / Phase 2 build:**

| # | Decision | Freeze Gate artifact |
|---|---|---|
| **D9b** | Per-unit / specific cess | fold into WF-02 — specific cess → line tax → GSTR-1 cess column → GL cess account → e-invoice `cess_nonadvol_amt` |
| **D12** | Capacitor Android shell ships to pilot | mobile test lane — session persistence across app restart, deep links, offline-on-mobile; built APK + device smoke; push-notifications surface decided (recommend OUT for pilot) |
| **D13** | Automated right-to-erasure | WF-59 + invariant `tenancy.no_orphans_after_erasure` — owner-initiated cascade over every `company`-scoped model; statutory-retention carve-out; wipe-set completeness fails CI on drift. Builds on the existing `wipe_logical_tenant_rows()` |
| **D14** | LLM bill-extraction hardening | `tests/errors/` (provider timeout / 5xx / 429 / malformed JSON → job FAILED, never crash / silent partial) + injection-guard test + cost-ceiling assert + draft-with-warning surfaced in preview |

**Demoted to KNOWN LIMITATIONS** — capability not built for the pilot; stated to the pilot user with a
manual workaround; where a UI/route surface exists, a Phase 2 test asserts it is inert/inaccessible:

| # | Decision | Pilot-user-facing note / workaround |
|---|---|---|
| D6 | Fixed assets + depreciation | Track assets and depreciation in existing books; post the monthly depreciation journal manually. |
| D7 | TDS/TCS returns + certificates | Bizboard gives the TDS/TCS worksheet; the CA produces GSTR-7/8 and Form 16A/27D from it. |
| D8 | Reverse charge (RCM) | Merchants with material RCM exposure (GTA/legal/security) are screened out of the pilot, or record the RCM self-invoice + ITC manually. |
| D9 | Composition dealer + CMP-08 | Composition dealers are out of the pilot. Bill of supply + the CMP-08 worksheet exist in code but are not a freeze-gated flow. |
| D10 | Bill of Entry / import purchase + landed cost | Enter import purchases as a domestic purchase bill with duty / landed cost as a charge line; no BoE document or automatic cost-layer capitalization in the pilot. |
| D11 | Plan-limit enforcement | Plan feature-gates and count quotas are not enforced in the pilot; billing / limits handled out of band. |

Consequences for [`BUSINESS_ARCHETYPES_AND_PERSONAS.md`](BUSINESS_ARCHETYPES_AND_PERSONAS.md): Invariant 3
keeps landed cost / BoE **out of scope**; ARCH-07's RCM exposure is a **pilot limitation**; ARCH-02
(composition) stays commercially deprioritized. D12 and D13 change no archetype disposition.

**Execution tracker:** [`roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md`](roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md)
— work packages SR-01..SR-91, phased, with per-item acceptance criteria and a status board. Branch
`feat/scope-revision-2026-09-09b`.

**Phase 2 chain-list effect:** WF-53, WF-54, WF-55, WF-56, WF-57, WF-58 (the D6/D7/D8/D9/D10/D11
chains) are **struck** — not built for the pilot. **WF-59** (D13 erasure) is retained. D9b folds into
**WF-02**; D14 lands in `backend/tests/errors/`; D12 becomes a mobile test lane. The demoted surfaces
instead get inert-in-pilot-profile assertions (plan item SR-03).

---

## Ratification checklist

- [x] D1 (POS) — **ON**, written into the pilot flag profile (2026-09-08)
- [x] D2 (TDS) — **ON**
- [x] D3 (online payment collection) — **ON (sandbox)**
- [x] D4 (OTP) — **ON**
- [x] D5 (per-company accounting books in pilot) — **Yes; `FG-2a/gl` is a hard gate**
- [x] `backend/.env.pilot.example` and `web/.env.pilot.example` match the resolved decisions (2026-09-08)
- [x] README "Freeze status" section points here
- [ ] Section A reviewed — every SUPPORTED workflow (A1–A26) is one the founder will stand behind
- [ ] Section B reviewed — nothing critical is hiding in NOT SUPPORTED
- [ ] Section C limitations (C1–C8) are acceptable to state to a pilot user
- [ ] D3: at least one of Cashfree / PayU sandbox credentials + `SANDBOX_WEBHOOK_SECRET` obtained for CI
- [ ] D4: `SMS_PROVIDER` (msg91 or twilio) account obtained for the pilot host
- [x] D6–D11 resolved 2026-09-09; **revised 2026-09-09b (PO)** — only **D9b** retained; D6/D7/D8/D9/D10/D11 → KNOWN LIMITATIONS (see "Scope revision 2026-09-09b")
- [x] D12–D14 resolved 2026-09-09; **confirmed 2026-09-09b (PO)** — D12 mobile shell **SUP (ships)**, D13 erasure **SUP (automated)**, D14 LLM **SUP (failure + injection guard)**
- [ ] Section G reviewed — remaining G1–G7 flows not covered by the retained D9b/D12/D13/D14 given a SUP / LIM / OUT disposition
- [ ] Section H reviewed — FE / async / privacy / ops / edge-case dispositions confirmed
- [x] Scope-size acknowledgement: resolved by Scope revision 2026-09-09b — retained set is **D9b** (fold into WF-02) + **D12** mobile lane + **D13** WF-59/erasure + **D14** `tests/errors/`; WF-53–58 and the count-quota work are deferred (LIM)
- [ ] Signed: ________________  Date: __________
