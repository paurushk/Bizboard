# BizBoard — Waves 0 / A / B / C / D implementation plan

**Audience:** Cursor Agent, Cursor Cloud Agent, or a human following the same tickets.  
**Branch:** implement on `main` (or a feature branch cut from it).  
**Date:** 2026-08-29 · **Revised:** 2026-08-31 (B-05 AttentionRow contract; merge target `main`)  
**Source of truth for intent:** this file. Freeze list in `docs/roadmap/FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.3 still applies except where this file **explicitly unfreezes** live GSP / GSTR-1·3B GSP upload as the P0 track.  
**Source of truth for code:** the repo. If this plan and the code disagree, **code + tests win**; update this file in the same PR.

This plan is the executable breakdown of the high-level feature plan. It is **not** a from-zero rebuild of Phases 1–7. Each ticket is a **delta**.

**Revision (2026-08-30):** execution machinery kept; competitive gaps closed. Live e-invoice + GSTR-1/3B GSP filing is a named **P0 track** (not “Wave B, GATE: human”). WhatsApp send, AR dunning, telemetry, performance SLOs, offline duration, distributor schemes, next languages, invoice audit UI, and DPDP posture are tickets. Deferred product calls (idempotency, outstanding, invoice-number gaps) are **locked below** — agents must not invent a fourth option. Wave A shop-floor tickets run **in parallel** with Wave 0. Calendar rebaselined to **9–15 months** solo including a 30–50% integration/QA tail.

---

## How to run this with Cursor or Cloud

### One ticket per agent session

Do **not** paste this whole file into one agent. Paste **one ticket ID** plus:

1. The **Agent prompt** block for that ticket (copy from §Ticket catalog).
2. The **Global agent contract** below.
3. “Stop when DoD is met. Do not start the next ticket.”

Tickets that say **BLOCKED on PD-*** must not start until that row in [Locked product decisions](#locked-product-decisions-resolve-before-the-ticket-starts) is signed (name + date). The decisions themselves are already written; the signature is the human gate, not a new design.

### Cursor (local)

```
Implement ticket W0-01 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Follow the Global agent contract in that file. Stop when the ticket DoD is met.
```

### Cursor Cloud

Same prompt. Set the workspace to this repo, branch from `main`, and attach this markdown file. Cloud agents cannot sign `GO_NO_GO.md`, sign a GSP contract, or publish to Play Store — those are **GATE: human**. They **can** land fail-closed GSP plumbing (B-01) and WhatsApp/reminder code behind flags.

### After each ticket

- Run the **Tests** listed on the ticket.
- Append one line to `docs/roadmap/ticket-logs/<TICKET-ID>.md` (create the file if missing). **Do not edit the Progress log table in this file** — parallel Cloud agents will conflict. Format:

  ```
  YYYY-MM-DD | DONE|PARTIAL|BLOCKED | <short-sha> | <one sentence>
  ```

- Do not commit unless the user asked. Do not push unless the user asked.

### Integrator (merge owner)

Parallel one-ticket branches need a single merger. **Do not wait for FUTURE_ROADMAP §0.5** (open since 2026-08-21). Use `docs/roadmap/ticket-logs/INTEGRATOR.md` (on-duty / backup). Cloud agents never merge to `main` without the integrator.


---

## Global agent contract

Copy this into every session.

```
You are implementing one numbered ticket from
docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.

Rules:
1. Read the ticket fully, then grep/read the listed files BEFORE editing. Several
   Wave 0 items are partially shipped — extend, do not rewrite.
2. Do not unfreeze: payroll (PF Basic+DA, LOP, PT slabs), manufacturing/MES,
   full CRM, ONDC, DigiLocker, eSign, Busy/Zoho adapters, live Tally sync,
   second live payment gateway (Cashfree/PayU stay dark), GSTR-4/6/7/8/9 as
   filing engines, certified PAN/UDYAM portal. Live GSP is allowed only on
   P0-01 / B-01 / B-02 as written, fail-closed without named-provider secrets.
3. Do not invent Chart of Accounts codes. Use existing 1200/2100/2210-2230/
   1310-1330/1370/1390/2261-2266/2240-2280/2300/1250. If a ticket needs a new
   code, stop and mark BLOCKED for CA.
4. Tenant isolation: every queryset stays company-scoped. No cross-tenant leaks.
5. Money: Decimal, quantized to paise. No float. Complete/post paths stay atomic.
6. GST: compute_document_totals in backend/core/services/billing.py is the tax
   engine. Do not add a third calculator. Frontend tax.ts is POS optimistic UI only.
7. i18n: user-visible strings go through t() and must exist in en.ts and every
   locale file the ticket names (minimum en + hi).
8. Feature flags: manufacturing/payroll/crm stay behind feature_flags() AND
   SaaS entitlement. Do not default them on. Money-math tickets must ship a
   documented rollback (flag or revert path) as written on the ticket.
9. Tests: add or extend pytest/vitest named on the ticket. Re-use tenant_a
   fixtures. Do not delete failing tests to go green.
10. Scope: only files needed for THIS ticket. No drive-by refactors, no new
    markdown unless the ticket is a docs/ops ticket.
11. Locked product decisions (PD-01..PD-03) are binding. Do not pick a
    different outstanding formula, idempotency 4xx policy, or number-gap policy.
12. Stop when DoD is met. Do not start the next ticket.
13. Append status to docs/roadmap/ticket-logs/<TICKET-ID>.md — never the
    Progress log table in this plan.
```

### Suggested models (if the user asks)

- Wave 0 money/GST/concurrency: strongest available reasoning model.
- Wave A i18n / POS copy: any capable FE model.
- Wave B / P0 GSP protocol: strongest available + keep fail-closed.
- Cloud: same tickets; human-gated tickets stay with a human.

---

## What “beat competitors” means here

ICP: Regular-GST Indian shop / wholesaler — invoices, stock, e-invoice, GSTR month-end, collections on WhatsApp. Not a Tally/Zoho ERP replacement (see [Concessions](#concessions-acceptable-gaps-for-this-icp)).

Win-blockers from `docs/reviews/18_COMPETITOR_ANALYSIS.md`: **compliance completeness** (2B, live e-invoice, composition honesty), **collections reliability**, **voucher speed / offline**. This plan now has tickets for those. Sandbox CI IRN is **not** a competitive DoD.

---

## The one-level-up thesis

Recording what happened is table stakes -- Tally, Vyapar and Marg all do it. What puts BizBoard a
level above a billing/accounting product is a single loop:

> **Detect** what needs attention -> **quantify** the money involved -> **explain** why ->
> **help finish** the fix.

The competitive wedge is that loop applied to the thing that became a monthly cash decision in 2026:

```
GST / ITC control  ->  Business Attention Center  ->  Automated resolution (WhatsApp)
```

Regulatory context that makes this urgent, not optional:

| When | Change | Effect on this plan |
|---|---|---|
| 22 Sep 2025 | GST 2.0 -- four slabs collapse to 5% / 18% / 40% | Every product master needed re-rating on one date; billing the old rate is a Section 122 exposure. Drives **B-06**. |
| 1 Oct 2025 | Invoice Management System (IMS) mandatory | Inward invoices must be Accept / Reject / Pending; no action = deemed accept. GSTR-2B is now **built from your actions**. |
| Apr 2026 | GSTN ships an Excel offline tool for IMS | The portal caps bulk accept/reject at 500 rows -- a product-shaped hole. Drives **B-03**. |
| Jul 2026 | GSTR-3B Table 4A hard-locked to GSTR-2B | ITC you claim = ITC you accepted in IMS. Miss an invoice -> working capital gone until fixed upstream, or permanently once the Section 16(4) window closes. |

The old B-03 ("2B decision board, no auto-claim, human decides each row") predates the July
hard-lock. It is rewritten below as **B-03 -- IMS + ITC control**. Two new tickets, **B-05 Attention
Center** and **B-06 effective-dated rate engine**, complete the loop.

---

## Consolidated priority ladder

One canonical order. Maps a product-tier review onto this plan's tickets. The only new scope is the
B-03 rewrite plus B-05 / B-06 / D-04; the rest is a reading order.

| Tier | Theme | Tickets |
|---|---|---|
| **0 -- Trust (solid first)** | Financial + inventory + accounting consistency, audit trail, tenant isolation, offline recovery guarantee, migration reliability | W0-01..W0-08, X-01, X-02, D-03, C-01 (recovery guarantee), D-02 (validation + reconciliation + rollback) |
| **1 -- Killer differentiation** | IMS + ITC control, credit-at-risk, effective-dated GST, "what needs my attention" | **B-03**, **B-06**, **B-05** |
| **2 -- Signal into outcome** | Supplier-defect, collection, missing-document workflows over WhatsApp + payment links | B-03 supplier loop, A-06, A-07, **D-04** |
| **3 -- Business intelligence (rules, not AI)** | Customer-credit view, supplier scorecard, margin / revenue / inventory / cash leakage | A-07 risk view, B-03 supplier scorecard, B-05 leakage rules |
| **4 -- Segment moat (charter-gated)** | Trade-scheme / QPS engine, pharma workflow, CA practice console | C-04 note (QPS = charter), E-L Wave K / Practice Console ticket |
| **5 -- Adoption multiplier** | Hindi + local languages, photo->draft, transparent pricing / entitlement | A-02, A-02b, photo->draft (D-02 step 6), pricing note in Concessions |
| **6 -- AI layer (last, on reliable data)** | Explanations, recommendations, NL queries, assisted resolution | E-L Wave F (assistant exists; stays propose-only) |

**Voice billing** and **live Marg/Busy importers** are deliberately *not* on this ladder --
post-pilot, demand-gated (see [Concessions](#concessions-acceptable-gaps-for-this-icp)).

---

## Concessions (acceptable gaps for this ICP)

We stay behind Zoho/Tally/ERPNext on purpose. Do not schedule these until a written charter **after** a Regular-GST shop pilot has live IRN + GSTR-1 GSP upload.

| We stay behind | Why that is acceptable |
|---|---|
| Statutory payroll (PF/ESI/PT/LOP) | ICP is billing+stock shops, not HR. Payroll in-tree stays dark. |
| Manufacturing / MES | Do not compete with ERPNext/Tally mfg. Flags stay off. |
| Full CRM / ONDC / DigiLocker / eSign | Distribution is WhatsApp + payment links, not a marketplace. |
| Busy / Zoho **adapters** | Import CSV/Tally migrate-once is the leave-Tally path. No live sync. |
| Live Tally sync / second gateway / live AA bank feed | Razorpay + manual/CSV bank is enough for the shop ICP. |
| GSTR-4/6/7/8/9 as **filing engines** | Honesty stubs. GSTR-9 remains a books worksheet. Composition: block Regular packs (already shipped); do not build a CMP filing engine until a composition pilot is named. |
| Certified PAN/UDYAM portal | Format + sandbox only. |
| iOS App Store | Android WebView is the counter. iOS config may exist; not a shipping target. |
| Tamil/Gujarati/Marathi/… at Wave A start | Hindi + i18n infra first; A-02b is the fast-follow (Tamil + Gujarati). |
| Generic AI chatbot / "AI accountant" | Assistant stays propose-only, grounded, tax-refusing (E-L Wave F). AI is Tier 6, after the data is reliable. |
| Large custom-report / dashboard library | The Attention Center (B-05) answers "where's my data", not 200 report templates. |
| Live Marg / Busy importers | Same `AccountingMigration` interface as Tally, **charter only** (L-05). Tally migrate-once is the leave-Tally path. |
| Voice billing | Photo->draft yes (D-02 step 6); speak-the-invoice is a post-pilot adoption item. |
| Trade-scheme / QPS engine, pharma depth | Charter-gated after a **named** distributor or pharma beachhead (C-04 forward note). |
| Sophisticated credit / supplier scoring | Start with buckets + a scorecard (A-07, B-03). Models come after real data. |

The freeze list is **examined**, not permanent: re-open only with a charter after P0 IRN is in production for one paying pilot.

---

## Effort reconciliation (this plan vs FUTURE_ROADMAP §0.2)

These are **not** the same queue. Mixing them produced the ~10× headline gap.

| Queue | What it is | Remaining |
|---|---|---|
| FUTURE_ROADMAP §0.2 GAP-001–010 | Aug-21 gap-closure (AA mock, dashboard AR, UQC, B2CL, payment-link cancel, cess GL, …) | **~0 product weeks.** GAP-010 is “re-run concurrency suite”. Do not re-estimate as 70 weeks. |
| This plan Wave 0 **verify-first** (W0-01, W0-05, W0-08) | Unique GL, idempotency, Docker/CD, opening unique — **partly in tree** | **2–4 weeks** of tests, data migrations, leftover holes. |
| This plan Wave 0 **construction** (W0-02, W0-03, W0-04, W0-06, W0-07) | GSTIN recompute, webhook holding, FY series policy, WAVG ledger, outstanding | **12–16 weeks.** Not in GAP-001–010. |
| Wave A shop (incl. parallel) + WhatsApp + dunning + telemetry | Counter competitiveness | **14–18 weeks** |
| P0 GSP + GSTR-1/3B upload (eng) | Competitive compliance ceiling | **8–10 weeks eng** + procurement calendar |
| Wave B remainder (2B board, guardrails) | After P0 plumbing | **5 weeks** |
| Wave C + DIST-01 | Stock + distributor schemes | **12–13 weeks** |
| Wave D + audit + DPDP | CA practice + trust | **12–14 weeks** |
| X-01 performance harness | Cross-cutting | **2 weeks** (plus soak on a 50k fixture) |

**Headline to use:** remaining construction **~55–65 eng-weeks**, plus **30–50% integration/QA tail** (merge, golden month, GSP sandbox→prod, Play, CA pack) = **~75–95 person-weeks**.

**Honest solo calendar to a beat-competitors pilot** (live IRN for one Regular B2B shop + CA files GSTR-1 via GSP + Hindi Android counter + WhatsApp invoice/pay-link + AR reminders): **9–15 months**, dominated by GSP KYC and CA sign-off, not by W0-01. If P0-01 slips past T+6 weeks, the eng calendar still runs but **marketing must not claim e-invoice** (see slip plan).

Do not quote “~70 eng-weeks” as if GAP-001–010 were unstarted. Do not quote “1.5–2.5 weeks” as if webhook holding and WAVG ledger were already done.

---

## Locked product decisions (resolve before the ticket starts)

These replace “leave a comment in code.” An agent that sees an unsigned `Signed` cell still **implements the Adopted rule** (it is the spec). A human must still sign before merge to `main` for money-path tickets.

### PD-01 — Idempotency 4xx (W0-05)

**Adopted:** Split 4xx by class. Do **not** retain every 4xx.

| Response | Store on key? | Client |
|---|---|---|
| 2xx | Yes | Replay |
| 5xx after `build()` returned (side effects may have committed) | Yes | Replay; do not Complete again with same key |
| 4xx **deterministic** (validation, missing lines, credit-limit, GSTIN required) | Yes | Replay; **user** Complete click must send a **new** UUID |
| 4xx **transient** (period locked, rate-limit, 429, “try again”) | **No — release** | Auto-retry may reuse the same key |
| Raised exception + rollback | Release | Retry same key is OK |

FE rule: network auto-retry reuses `Idempotency-Key`; an explicit user gesture (Complete, Save, Pay) generates a new key. Document this in the POS/invoice client in the same PR.

**Signed:** name ________ date ________

### PD-02 — Customer outstanding (W0-07a)

**Adopted** (matches FUTURE_ROADMAP §0.1 #9). The agent does **not** pick.

- `accounting_enabled=True`: `customer_outstanding` = GL AR **1200** net of advances **2300** (and 1250 if used). `customer_statement` **foots the same number**, with advances as labeled lines (not a second secret total).
- `accounting_enabled=False`: document-derived outstanding (invoices − allocations − auto-CNs). Statement matches that formula.
- Health `AR_CONTROL_MISMATCH` / `AP_CONTROL_MISMATCH` stay in CI.
- Do not enable books for a new pilot until CA signs this formula on a golden month.

**Signed:** PM ________ CA ________ date ________

### PD-03 — Invoice numbers and GST gaps (W0-04)

**Adopted:** Missing numbers are an audit event, not an “eng documented gap.”

1. Allocate `next_number` **inside the same DB transaction as Complete**. If Complete rolls back, the series row rolls back — the number was never issued.
2. Do **not** increment a sequence outside that transaction.
3. Cancelled **completed** invoices **keep** their number. They appear on an FY **cancelled-number register** (report + CSV) for the CA.
4. Never silently skip a number. If a crash after commit leaves a COMPLETED invoice, that number is used (not a gap).
5. FY-boundary new series starting at 1 is expected; warn, do not treat as a gap.

**CA sign-off** on the cancelled-number register layout is required before W0-04 merges.

**Signed:** CA ________ date ________

---

## P0 track — GSP / e-invoice / GSTR-1·3B filing

This is the gap that decides whether BizBoard can be the **primary** billing tool for Regular GST. Sandbox IRN in `test_sprint_e_gsp_protocol.py` does **not** close it.

**Owners (fill on plan adoption — empty = P0 is RED, not “later”):**

| Role | Name | Accountable for |
|---|---|---|
| PM | ________ | ICP, marketing claims, slip plan |
| Eng | ________ | B-01 / B-02 fail-closed + live switch |
| Ops | ________ | Secrets, `GSP_LIVE_BASE_URL`, no placeholder keys |
| Legal / KYC | ________ | GSP contract, GSTN/GSP onboarding |
| CA | ________ | First month GSTR-1 upload + 2B board |

**Calendar (T0 = date this revision is adopted, currently targeting 2026-08-30):**

| Milestone | Date | Slip |
|---|---|---|
| Owners named | T0 + 2 weeks (2026-09-13) | If unnamed, stop all “e-invoice” / “file GST” copy in product and README |
| GSP contract + sandbox tenant | T0 + 6 weeks (2026-10-11) | **Fallback:** CA files from `gstn-json` download; product banner “e-invoice not live”; restrict new Regular B2B pilots |
| First **production** IRN for a named pilot GSTIN | T0 + 12 weeks (2026-11-22) | Same fallback; P0 stays RED |
| First GSTR-1 **GSP upload** (or filing-partner handoff with logged JSON) for that GSTIN | T0 + 16 weeks (2026-12-20) | JSON-only is a **concession month**, not Done |

**B-01 / B-02 eng DoD is not P0 Done.** P0 Done = production IRN + one GSTR-1 submitted via GSP (or a named filing partner with the JSON we produced). Until then, UI stays fail-closed and honest.

Ticket **P0-01** is the human procurement checklist. Tickets **B-01** and **B-02** are the eng slices. Eng may merge fail-closed code **before** the contract; **live HTTP** requires P0-01 sandbox tenant.

---

## Product freeze (do not build)

From `FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.3, **except** live GSP / GSTR-1·3B GSP upload which this revision promotes to P0.

| Frozen | Allowed in this plan |
|---|---|
| Statutory payroll (PF Basic+DA, LOP, PT) | Nothing. R4-007/008/010 stay frozen. |
| Manufacturing / MES / full CRM enablement | Nothing. |
| ONDC, DigiLocker, Aadhaar eSign | Nothing. |
| Busy / Zoho adapters | Nothing. |
| Live Tally **sync** | Tally **import once** (Wave D) only. UI must say migration, not sync. |
| Second live gateway | Razorpay only. Cashfree/PayU stay disabled + fail-closed. |
| GSTR-4/6/7/8/9 filing engines | Honesty stubs + watermark. **GSTR-1 and GSTR-3B GSP upload** are P0/B-02. |
| Certified PAN/UDYAM portal | Format + sandbox only. |
| Live NIC **direct** | No. GSP only, fail-closed (`BB-000624`) until P0-01 secrets exist. |

---

## Sequencing

Shop-floor and P0 procurement run **beside** Wave 0. Only A-03 (preview_totals) and live GSP traffic wait on money-engine tickets.

```
P0-01 GSP procurement (human) ─────────────────────────────────────┐
                                                                    │
W0-01 GL unique     ─┐                                              │
W0-04 Doc numbers    │  parallel (after PD-03 sign for W0-04 merge) │
W0-05 Idempotency    │  (PD-01)                                     │
W0-08 Ops / CD / SEC X-02 DPDP can start                            │
X-01 Performance SLO ┘                                              │
        │                                                           │
        ├── W0-02 GSTIN recompute  ── must before live IRN          │
        ├── W0-03 Gateway holding  ── must before live payment claim│
        ├── W0-06 Valuation ledger ── must before C-03 FEFO hot path│
        └── W0-07 Money surfaces   ── PD-02 signed                  │
                                                                    │
PARALLEL with Wave 0 (do not wait 22 weeks):                        │
  A-01 Native Capacitor                                             │
  A-02 Hindi money screens → A-02b Tamil+Gujarati                   │
  A-04 POS recover                                                  │
  A-06 WhatsApp invoice + pay link                                  │
  A-07 AR reminder cadence                                          │
  A-08 Product telemetry                                            │
                                                                    │
A-03 preview_totals ── after billing.py stable (can overlap W0-02)  │
A-05 GO_NO_GO artefacts                                             │
                                                                    │
        ▼                                                           ▼
B-01 Live IRN/e-way     ── fail-closed until P0-01; live after W0-02
B-02 GSTR-1/3B GSP      ── same
B-03 IMS + ITC control  ── GSTN offline-tool path needs no GSP; live pull after P0-01
B-06 Effective-dated rate engine ── after billing.py stable (overlaps W0-02)
B-04 Complete guardrails
B-05 Attention Center   ── after B-03/B-04/A-07 emit money-tagged signals
        │
        ▼
C-01 Offline godown (8h target + conflict UI)
C-02 Lot identity
C-03 Find stock / FEFO
C-04 Distributor schemes / party pricing
        │
        ▼
D-01 CA multi-company + cashier home + 409 clients
D-02 Tally migrate-once + backup parity
D-03 Invoice audit trail UI
```

**Do not enable live GSP HTTP** until W0-02 DoD and P0-01 sandbox tenant.  
**Do not unfreeze payroll/MES/CRM** until P0 production IRN + CA GSTR-1 upload.  
**Do not claim “pass Vyapar”** until Wave A **measurable** exit (taps, offline hours, telemetry) is green.

---

## Repo map (where work lives)

| Area | Paths |
|---|---|
| Tax engine | `backend/core/services/billing.py` |
| Sales Complete | `backend/sales/services.py` (`complete`, `set_items`) |
| Purchase Complete | `backend/purchases/services.py` |
| GL post | `backend/accounting/services.py` `PostingService.post` |
| Journals | `backend/accounting/models.py` `JournalEntry` |
| Doc numbers | `backend/core/services/document_numbers.py` |
| Idempotency | `backend/core/idempotency.py` |
| Payments / webhooks | `backend/payments/services.py`, `backend/payments/gateway.py` |
| Ledgers / outstanding | `backend/ledgers/services.py` |
| Stock / valuation | `backend/inventory/services.py`, `backend/inventory/models.py` |
| GSP / e-invoice | `backend/core/services/gsp_adapters.py`, `backend/sales/einvoice_eway_actions.py` |
| GSTR-1 / 2B | `backend/reporting/` (`gstr*.py`, `gstr2b.py`) |
| Company / GSTIN | `backend/accounts/models.py` `Company`, `CompanyGstin` |
| Permissions / company | `backend/core/permissions.py` |
| Tenant backup | `backend/accounts/tenant_backup.py` |
| Imports / Tally | `backend/imports/services.py` |
| SPA invoice | `web/src/pages/sales/NewInvoicePage.tsx` |
| POS | `web/src/pages/pos/PosPage.tsx` |
| i18n | `web/src/i18n/en.ts`, `web/src/i18n/hi.ts` |
| Company switch | `web/src/hooks/useCompanySwitcher.ts` |
| WhatsApp | `backend/core/services/whatsapp.py` (Cloud API + `wa.me`; templates `invoice_ready`, `payment_reminder`, `invoice_share`) |
| Audit | `backend/core/models.py` `AuditEvent`, `backend/core/services/audit.py` |
| Price lists | `backend/masters/` (`PriceList`, `PriceListItem`); party FK on customer |
| Load | `load/k6_smoke.js`, `load/README.md` — smoke only, not 50k soak |
| Capacitor | `mobile/` (config-only today; no `@capacitor/network` etc.) |
| CI/CD | `.github/workflows/ci.yml`, `.github/workflows/cd.yml` |
| Compose prod | `docker-compose.prod.yml` (or equivalent compose.prod) |
| Pilot gates | `docs/pilot/GO_NO_GO.md` |
| Ticket logs | `docs/roadmap/ticket-logs/<ID>.md` |

Tests live in `backend/tests/` and `web/` vitest. Prefer extending `test_concurrency_races.py`, `test_sprint_e_gsp_protocol.py`, `test_wave17_gst_books.py`.

---

## Ticket catalog

Each ticket uses the same shape: **ID, effort, source, verify-first, files, steps, tests, DoD, out of scope, agent prompt.**

---

# P0-01 — GSP procurement (human)

| | |
|---|---|
| Effort | Calendar, not eng-weeks |
| Source | 18_COMPETITOR_ANALYSIS win-blocker #1 · BB-000624 |
| GATE | **human** |

Eng does not mark P0 Done. Fill the owner table in [P0 track](#p0-track--gsp--e-invoice--gstr-13b-filing). Deliver: signed GSP contract, sandbox GSTIN, production secrets in the secret store (not git), named pilot company.

**Slip:** if contract missing at T0+6w, enable only JSON download + CA portal upload; banner that e-invoice is not live; no new Regular B2B “primary billing” pilots.

### Agent-allowed work

None except documenting env var names in `.env.example` (empty values). Do not put live keys in the repo.

---

# Wave 0 — Money integrity (~14–20 weeks remaining)

Verify-first tickets (W0-01/05/08) are **not** 22 weeks of greenfield. Construction tickets (W0-02/03/04/06/07) are. Several items are **partially in tree**; the agent’s first job is to prove the remaining gap.

Every money-math ticket has a **Rollback** subsection. Do not merge without it.

---

## W0-01 — GL cannot double-post

| | |
|---|---|
| Effort | 2 weeks |
| Source | R3-009 |
| GATE | eng + migration |

### Verify first

`JournalEntry` already has `uniq_accounting_source_posting` on `(company, source_type, source_id, purpose)` where `source_id IS NOT NULL` and `status=POSTED`. `PostingService.post` catches `IntegrityError` and returns the winner. Remaining work is **data hygiene + concurrency proof + REVERSED/repost behaviour**, not a greenfield unique index.

### Files

- `backend/accounting/models.py`
- `backend/accounting/services.py` (`PostingService.post`)
- `backend/accounting/migrations/` (new if constraint must change)
- `backend/tests/test_concurrency_races.py` (or new `test_w0_gl_unique.py`)

### Steps

1. Query production-like fixtures for duplicate POSTED rows on the same `(company, source_type, source_id, purpose)`. Add a data migration `RunPython` that **reverses or flags** duplicates (keep lowest `id`, reverse the rest) **before** tightening the constraint. Fail the migration if duplicates remain.
2. Confirm the unique condition still allows a new POSTED row after the original is `REVERSED` (cancel/void path). If it does not, the constraint is wrong.
3. If `post()` ever creates `DRAFT` then updates to `POSTED`, two DRAFTs can still race — create as `POSTED` in one insert (already the case) and keep the IntegrityError replay.
4. Add a concurrency test: two threads/processes call `PostingService.post` with the same source; exactly one POSTED journal; the other returns that same pk. Use `tenant_a` with `accounting_enabled=True`.

### Tests

- `pytest backend/tests/test_concurrency_races.py -k journal -q` (or the new file)
- `pytest backend/tests/test_wave15d_books.py -q` (control-balance health still green)

### DoD

- [ ] No two POSTED journals share the unique key.
- [ ] Concurrent Complete of the same invoice produces one GST/AR journal.
- [ ] Cancel → reverse → re-complete (if product allows) still posts once per purpose.
- [ ] `makemigrations --check` clean after the data+schema migration.

### Rollback

If the data migration mis-classifies duplicates, revert the migration on a restore from backup taken immediately before deploy. Do not “delete extra journals” by hand in prod.

### Out of scope

New CoA accounts; changing purpose strings; historical backfill of missing journals (`backfill_accounting_postings.py` already exists).

### Agent prompt

```
Implement W0-01 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Verify uniq_accounting_source_posting and PostingService.post IntegrityError path first.
Add duplicate-cleanup data migration if needed. Add a concurrency test: two posts,
one POSTED journal. Do not change CoA. Stop when DoD is met.
```

---

## W0-02 — Complete uses the filing GSTIN

| | |
|---|---|
| Effort | 2.5 weeks |
| Source | R2-001 / R2-010 |
| GATE | eng + CA matrix |

### Verify first

`SalesInvoice.complete` stamps `company_gstin` when unset. `set_items` already passes `seller_state` / `seller_gstin` from `invoice.company_gstin`. Confirm whether **Complete** recomputes `compute_document_totals` **after** the stamp. If draft was computed against HO `company.state` and Complete stamps a branch GSTIN in another state, CGST/SGST vs IGST can be wrong.

Same pattern on `purchases/services.py` `complete`.

### Files

- `backend/sales/services.py` (`complete`, `set_items`)
- `backend/purchases/services.py` (`complete`)
- `backend/core/services/billing.py` (`compute_document_totals`)
- `backend/accounts/models.py` (`CompanyGstin`)
- `backend/tests/` new `test_w0_multi_gstin_complete.py`

### Steps

1. After `company_gstin` is stamped on Complete (sales and purchase), call `compute_document_totals` with that GSTIN’s state. Persist line and header tax fields, then post GL/GSTR from those fields.
2. Do not recompute if the document is already COMPLETED.
3. **Grand-total guard:** compare `grand_total` (and tax heads) before vs after recompute. If `|Δ grand_total| > ₹0.01` (more than rounding), **do not Complete**. Return 409 with `{ code: "GSTIN_TOTAL_CHANGED", before, after, lines }` and require `confirm_gstin_total_change=true` on a second call. FE must show a pre-Complete diff (CGST/SGST vs IGST and grand total) and get an explicit confirm. i18n.
4. Test matrix (minimum):
   - Single GSTIN tenant: intra (CGST+SGST) and inter (IGST) unchanged vs today.
   - Two active GSTINs: draft under GSTIN-A (MH), Complete with GSTIN-B (DL) and customer in MH → IGST (or the CA-correct split). Inverse case. If grand total changes, confirm path required.
   - Legacy company with `company.gstin` only and zero `CompanyGstin` rows: no crash.
5. GSTR-1 preview for that invoice must show the same heads as the completed document.

### Tests

- New pytest covering the matrix above, including **block without confirm** when totals change and **Complete with confirm**.
- Existing GSTR-1 / invoice complete tests still pass: `pytest backend/tests/test_sprint_a_prod_gst_p1.py backend/tests/test_wave17_gst_books.py -q`

### DoD

- [ ] Filed tax head matches the **stamped** GSTIN, not draft-time HO state.
- [ ] Line CGST/SGST/IGST sum to header; GL tax legs match header (or follow W0-07 if line-sum work is still open).
- [ ] Multi-GSTIN without stamp still fail-closed (already BB-000708).
- [ ] Customer-facing grand total cannot flip silently; confirm or no Complete.

### Rollback

Company flag `recompute_tax_on_complete` (default **on** for new companies, **off** until CA pack for existing books-on tenants). Off = today’s stamp-without-recompute behaviour. Document in the migration notes.

### Out of scope

Live IRN (B-01). Changing place-of-supply rules.

### Agent prompt

```
Implement W0-02 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
After Complete stamps company_gstin, recompute compute_document_totals for sales
and purchases. If grand_total changes by more than ₹0.01, block without
confirm_gstin_total_change. Add single vs multi-GSTIN pytest matrix + confirm path.
Rollback flag recompute_tax_on_complete. Do not touch GSP. Stop when DoD is met.
```

---

## W0-03 — Gateway money always lands

| | |
|---|---|
| Effort | 4 weeks |
| Source | R3-001 / R3-002 / R3-003 · D-018 |
| GATE | eng |

### Why

Razorpay can capture while BizBoard refuses the webhook (period lock, UTR unique, partial refund). Provider retries forever; the shop has money and no receipt.

### Files

- `backend/payments/models.py` (`GatewayPayment`, `PaymentLink`, statuses)
- `backend/payments/services.py` (capture / webhook handler)
- `backend/payments/gateway.py` (verify stays as-is)
- `backend/payments/tasks.py` (new reconcile / dead-letter if missing)
- `backend/tests/` new `test_w0_webhook_holding.py`

### Steps

1. Introduce a **holding** status on `GatewayPayment` (e.g. `CAPTURED_PENDING_BOOKS`) used when signature verifies and capture is real but `create_receipt` cannot post (closed period, UTR clash, allocation `BusinessRuleError`).
2. Always persist the provider payment id + amount + raw event id **before** books side effects. Webhook handler must be idempotent on provider payment id.
3. Period lock: do **not** drop the capture. Park it; Celery job retries when the period is reopened or posts to the next open period **only if CA-approved** — default is “park until period open”, not silent next-period post. If product call is unset, park + alert, do not invent a period.
4. UTR uniqueness: if clash, store capture with a suffixed internal reference; surface Health warning; do not 4xx the webhook (Razorpay will retry).
5. Partial refund: capture remaining amount; never delete the original capture row.
6. Dead-letter + `reconcile_gateway_captures` management command / beat task: list holding rows older than N minutes; retry books; page ops via existing Health/Sentry.
7. Razorpay only. Do not enable Cashfree/PayU.
8. **Shop + customer surfaces (required, not ops-only):**
   - Invoice / POS / payment-link status: distinguish **Unpaid** vs **Paid — receipt pending books** (`CAPTURED_PENDING_BOOKS`) vs **Paid**. Cashier must not chase the customer.
   - Public pay-page / thank-you: “Payment received” even if books are parked.
   - Optional WhatsApp/SMS confirmation uses A-06 templates when that ticket has landed; this ticket at least exposes API `payment_state` for the UI.

### Tests

- Webhook with closed period → 200 to provider, `CAPTURED_PENDING_BOOKS`, no receipt yet; after period open, job creates one receipt.
- Duplicate webhook → one receipt.
- UTR clash → holding or receipt with warning, not dropped capture.
- Invoice retrieve while holding: `payment_state` is not `UNPAID`.
- Existing gateway tests still pass.

### DoD

- [ ] Verified capture never disappears.
- [ ] Provider always gets 2xx after signature OK (or 4xx only on bad signature).
- [ ] Ops can list and retry holding captures.
- [ ] Shop UI and customer pay-page show payment received while books are pending.
- [ ] Cashfree/PayU still dark.

### Rollback

Flag `gateway_holding_state` (default on). Off = today’s fail-the-webhook behaviour (worse for money; only for emergency). Prefer fixing the job, not turning the flag off in prod.

### Out of scope

Second gateway; MDR fee redesign (already posted when books-on).

### Agent prompt

```
Implement W0-03 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Add a holding state for verified Razorpay captures that cannot post books.
Webhook 2xx + idempotent. Reconcile job. Invoice and public pay-page must show
payment received while receipt is pending books. Razorpay only. Stop when DoD is met.
```

---

## W0-04 — Document numbers are one FY policy

| | |
|---|---|
| Effort | 2 weeks |
| Source | R1-013 / R1-014 / R1-015 · Q-094 |
| GATE | eng + **PD-03 CA sign-off** before merge |

### Verify first

`DocumentNumberService` keys by GSTIN + FY **when `gstin` or `on_date` is passed**. Callers that omit `gstin` still get a legacy series (`INV-00001`). That is the bug: two sequences in one FY.

### Files

- `backend/core/services/document_numbers.py`
- All `next_number(` call sites (grep)
- `backend/sales/services.py` Complete (must pass stamped GSTIN + invoice date)
- Cancelled-number register report (new reporting endpoint + FE CSV)
- `backend/tests/` numbering tests

### Steps

1. Follow **PD-03** (do not invent a gap-on-rollback). If the company has any GSTIN, **always** key series by GSTIN+FY. No GSTIN → legacy unscoped series.
2. Allocate inside the **same DB transaction as Complete**. Series `select_for_update` must not span PDF/stock/GL that can fail **after** a committed number — either the whole Complete commits or the number is unused.
3. On FY boundary, new series at 1 is expected; emit a structured warning.
4. Cancelled completed invoices keep their number; list them on `GET /api/v1/reports/cancelled-document-numbers/?fy=` (CSV). CA sign-off on columns: number, doc type, GSTIN, date, reason, user.
5. Do not scan `_max_existing_seq` on the hot path (already BB-000646).

### Tests

- Company with GSTIN: Complete without passing gstin in a stray caller still uses FY+GSTIN series.
- Two Completes in parallel: two distinct numbers; rollback of one does **not** leave a hole (series.next_number consistent with issued COMPLETED+CANCELLED numbers).
- FY rollover: new series; warning present.
- Cancelled invoice appears on the register; its number is not reused.

### DoD

- [ ] One INV sequence per GSTIN per FY.
- [ ] No silent skipped numbers; cancelled-number register exists.
- [ ] FY jump is visible to CA.
- [ ] PD-03 signed.

### Rollback

Do not ship a second numbering policy behind a flag (that recreates two series). Rollback = revert the PR and restore `DocumentSeries.next_number` from backup if a bad deploy issued numbers.

### Agent prompt

```
Implement W0-04 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Follow PD-03: allocate inside Complete’s DB transaction; cancelled-number register;
never document gap-on-rollback. Grep every next_number caller. Stop when DoD is met.
```

---

## W0-05 — Idempotency keeps terminal results

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | R1-010 · Q-070 |
| GATE | eng · **PD-01 binding** |

### Verify first

`wrap_idempotent` already **stores 2xx and 5xx** and **releases 4xx**. Implement **PD-01**, not “retain all 4xx.”

### Files

- `backend/core/idempotency.py`
- Call sites: sales/purchase complete, CN/DN complete (`wrap_idempotent`)
- Invoice/POS FE: new UUID on user Complete; reuse key on network auto-retry
- `backend/tests/` idempotency tests

### Steps

1. Classify 4xx: deterministic (`BusinessRuleError` validation, 400/409 credit-limit, GSTIN required) → `store_record`. Transient (period locked, 429, “retry”) → `release_record`. Use an explicit allowlist of transient error codes in one module — do not guess from status int alone if the payload has `code`.
2. Keep storing 5xx after `build()` returns. Raised exception + rollback → release.
3. FE: `crypto.randomUUID()` (or equivalent) on each user-initiated Complete/Pay; interceptors must not reuse that key on a second click.
4. Tests for both 4xx classes plus post-commit 500.

### Tests

- Deterministic 409 stored; same-key retry returns stored 409; `complete` not called twice.
- Transient period-lock 409 released; same-key retry after period open can succeed.
- Post-commit 500 stored; only one invoice.
- FE unit test: second Complete click ≠ same idempotency key.

### DoD

- [ ] PD-01 behaviour, not blanket retain-4xx.
- [ ] User retry cannot double-complete; auto-retry can recover from transient 4xx.
- [ ] True crash (exception + rollback) still allows retry.

### Rollback

Revert `wrap_idempotent` to pre-ticket behaviour (store 2xx+5xx, release all 4xx). Safer than retaining the wrong 4xx class.

### Agent prompt

```
Implement W0-05 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Follow PD-01: store deterministic 4xx; release transient 4xx; store 5xx-after-commit.
FE: new Idempotency-Key on user Complete, reuse on network retry. Tests for both
4xx classes. Stop when DoD is met.
```

---

## W0-06 — Valuation is a ledger, not a full replay

| | |
|---|---|
| Effort | 4 weeks |
| Source | R2-022 / R2-023 |
| GATE | eng |

### Why

`InventoryValuationService.valuation` replays **all** `StockMovement` rows ordered by `created_at`, on Complete/report hot paths. WAVG must become a perpetual running-cost (mirror `InventoryCostLayer` for FIFO). Order by **business date** (`movement_date` or document date), not insert time.

### Files

- `backend/inventory/models.py` (new `InventoryRunningCost` or fields on `StockBalance`)
- `backend/inventory/services.py` (`post_movement`, `valuation`, COGS)
- `backend/sales/cogs_service.py`
- migrations
- `backend/tests/` FIFO/WAVG tests

### Steps

1. Add perpetual WAVG state per `(company, warehouse, product, batch)`: `qty`, `value` (and thus unit cost). Update it inside `post_movement` in the same transaction as the movement.
2. FIFO already has `InventoryCostLayer` — do not replace; keep peel on outbound.
3. **Hot path:** Complete COGS reads running-cost / layers — **never** full movement replay.
4. **Historical `as_of`:** if movement count for the filter **> 10,000**, use a **period snapshot** table (month-end qty/value per key), then replay only movements after the snapshot. If **≤ 10,000**, replay `WHERE business_date <= as_of ORDER BY business_date, id` is allowed. Do not leave “prefer (b) if volume is OK” undefined.
5. Backfill command: replay once into running-cost; fail if qty vs `StockBalance` drifts.
6. Zero-cost SALE already warns (R2-007) — keep.
7. **Books restatement:** switching order from `created_at` to business date **changes historical COGS** for backdated tenants. Default **off** for existing companies (`valuation_business_date_order=False`). New companies default on. Enabling requires a CA note in company settings + optional “recompute closed periods” **not** in this ticket (report-only until they opt in). Migration notes must say: “turning this on can restatement inventory/COGS; take a backup.”

### Tests

- Complete after 1000 movements: query count on Complete does not scan all movements.
- Backdated receipt then issue: with flag on, cost uses business date order.
- 10,001 movement fixture: `as_of` uses snapshot path (mock or assert).
- FIFO regression suite still green.
- Flag off: behaviour matches current `created_at` replay (characterization test).

### DoD

- [ ] Complete COGS does not O(all movements).
- [ ] Snapshot path in scope above 10k movements.
- [ ] Existing tenants not restated unless they opt in.
- [ ] FIFO unchanged when flag off.

### Rollback

`valuation_business_date_order=False` restores insert-time replay for reports; running-cost table can stay as a cache for Complete if it still matches flag-off COGS — if not, Complete must use the old path when the flag is off.

### Agent prompt

```
Implement W0-06 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Perpetual WAVG running-cost on post_movement. Historical as_of: snapshot if >10k
movements else business-date replay. Flag valuation_business_date_order default
off for existing tenants. Do not silently restate COGS. Stop when DoD is met.
```

---

## W0-07 — Money surfaces agree

| | |
|---|---|
| Effort | 4 weeks |
| Source | R2-015 / R2-017 · D-006 / D-003 / D-037 |
| GATE | eng + **PD-02 signed** (formula is adopted; signature before merge) |

Split into four sub-tickets. **W0-07a must follow PD-02.** Do not pick a different outstanding definition.

### W0-07a — One outstanding definition

**Files:** `backend/ledgers/services.py` (`customer_outstanding`, `customer_statement`, `company_receivables`); every other caller (grep `customer_outstanding` — historically many).

**Steps:** Implement PD-02. One function, all surfaces call it. Docstring is the formula. Health `AR_CONTROL_MISMATCH` stays. If a caller still inlines 1200-only or documents-only while books are on, that is a bug in this ticket.

**DoD:** Fixture: invoice + unallocated receipt → statement total == outstanding. Advance line visible. Books-off fixture uses documents.

### Rollback

`outstanding_basis` company setting: `GL_WHEN_BOOKS` (PD-02) vs `DOCUMENTS_ALWAYS` (old document-derived even when books on). Default PD-02. Emergency = `DOCUMENTS_ALWAYS`.

### W0-07b — Partial-return auto-CN header discount

**Files:** `backend/purchases/services.py` (auto CN), sales return auto-CN path

**Steps:** Spread invoice-level discount/charges on partial qty so repeated partials do not leave paise on AP/AR.

**DoD:** Two 50% returns fully relieve the bill; remainder 0.00.

### W0-07c — Sales-return TCS reverses 2266

**Files:** accounting posting for sales CN / sales return

**DoD:** Completed sales return with TCS credits/debits 2266 so net TCS liability matches remaining invoices.

### W0-07d — Note e-invoice OthChrg includes TCS; TDS not double-credited

**Files:** e-invoice payload builder; payment vs invoice TDS posting (`2265`)

**DoD:** IRN JSON OthChrg includes TCS when TCS is on the note. Paying a bill that already withheld TDS does not credit 2265 twice.

### Agent prompt (run as four sessions if needed)

```
Implement W0-07a (then b, c, d in later sessions) from
docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Follow PD-02 exactly. Do not invent a third outstanding formula.
Stop at the sub-ticket DoD.
```

---

## W0-08 — Ops integrity

| | |
|---|---|
| Effort | 2 weeks |
| Source | R5-007 / R5-009 · R2-026 · R4-013 |
| GATE | eng + ops |

### Sub-tickets

**W0-08a Gunicorn non-root** — `backend/Dockerfile`: create user, `USER` before CMD. HEALTHCHECK already removed; do not run as root.

**W0-08b CD green-CI gate** — `.github/workflows/cd.yml`: `workflow_dispatch` already requires `confirm_ci_green`. Verify image **digest pin** in prod compose (`scripts/pin_image_digests.sh`). Fail the workflow if digest missing.

**W0-08c Opening-stock unique** — partial unique on `StockMovement` OPENING_STOCK per `(company, warehouse, product, batch)` excluding `import_voided`. Data migration pre-check for dupes.

**W0-08d Import void** — `backend/imports/services.py`: void must **not** delete/deactivate products that existed before the import (only deactivate rows created by that import id).

### Tests

- Dockerfile: grep/test that USER is not root (or a small CI script).
- Opening duplicate insert → IntegrityError.
- Import update-then-void leaves pre-existing product.

### Agent prompt

```
Implement W0-08 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Non-root Docker user, CD digest pin, opening-stock unique constraint with dupe
pre-check, import void must not delete pre-existing products. Stop when DoD is met.
```

---

# Wave A — Counter (parallel with Wave 0)

Goal: daily Android + Hindi + collections on WhatsApp. **Measurable** vs Vyapar — not slogans.

**Starts now (no Wave 0 wait):** A-01, A-02, A-02b, A-04, A-06, A-07, A-08.  
**Waits on tax engine stability:** A-03.  
**Human:** A-05.

---

## A-01 — Native counter app

| | |
|---|---|
| Effort | 5.5 weeks |
| Source | Q-063 / Q-078 |
| GATE | eng (+ Play listing human) |

### Verify first

`mobile/` is Capacitor 6 **config + android/ios packages only**. No Network, Camera, Preferences, Push plugins. Do not claim “Play app” in README until A-05 / listing.

### Files

- `mobile/package.json`, `mobile/capacitor.config.ts`
- `mobile/android/` (generate via `npx cap add android` if missing from git)
- `web/src/` — thin wrappers: `web/src/lib/native.ts` (isNative, getNetworkStatus, scanBarcode, prefs, push register)
- POS / invoice scan entry points
- ProGuard/R8 rules for release

### Steps

1. Add `@capacitor/network`, `@capacitor/camera` (or barcode plugin), `@capacitor/preferences`, `@capacitor/push-notifications`. Sync android.
2. Wire POS barcode to the plugin when `Capacitor.isNativePlatform()`; keep HTML input fallback on web.
3. Persist offline invoice drafts in Preferences **and** existing IDB path; document which wins. **Offline target (with A-04 / C-01):** a shop can bill for **8 hours** with no WAN: drafts queue, Complete of queued sales when online is idempotent, zero silent drops. If the queue exceeds device storage, block new lines with an i18n error — do not evict FIFO of unpaid sales.
4. Network listener: show existing offline outbox chip when offline (do not invent a second queue).
5. Push: register device; reuse existing notification backend if any; otherwise store token on User and stop. Do not build a new notification product.
6. R8/minify enabled on release; test login + Complete on a release APK (or emulator).
7. `android:allowBackup` — already a known issue; set `false` or exclude Cookie/IDB via BackupAgent rules.
8. Honest store copy lives in A-05; this ticket only makes the binary real.
9. Thermal print: from tap Print to data on the printer **< 2s** on a local Bluetooth printer in the lab (measure; file a follow-up if the PDF path cannot meet it — then use the existing 80mm thermal renderer).

### Tests

- Vitest: `native.ts` web fallbacks.
- Manual DoD: scan barcode on emulator; kill network; draft survives; online flush.

### DoD

- [ ] Release APK installs, logs in, Completes a POS sale.
- [ ] Plugins used; web still works without them.
- [ ] README does not say “on Play Store” until listing exists.
- [ ] 8-hour offline bill queue documented and tested at least 50 queued drafts on emulator.
- [ ] D-01 409 `COMPANY_REQUIRED` handled (picker or single-company no-op) — if D-01 not merged yet, leave a `TODO` interceptor and land the handler in D-01.

### Out of scope

iOS shipping (config may exist; **not** a shipping target). Rewriting UI in native widgets.

### Agent prompt

```
Implement A-01 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Add Capacitor Network, Camera/barcode, Preferences, Push to mobile/.
Web fallbacks in web/src/lib/native.ts. Wire POS scan. allowBackup false or
exclude session. Do not claim Play Store. Stop when DoD is met.
```

---

## A-02 — Hindi on every money screen

| | |
|---|---|
| Effort | 3 weeks |
| Source | Q-050 / Q-051 / Q-081 |
| GATE | eng |

### Files

- `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`, `web/src/i18n/index.ts`
- Money screens: `NewInvoicePage.tsx`, `PosPage.tsx`, receipts, sales/purchase returns, `EinvoiceEwayPanel.tsx`, credit notes
- Zod schemas / `getErrorMessage` paths — map through `t()`

### Steps

1. Inventory English strings on those screens (raw `'...'` and leftover English in `hi.ts` missing keys).
2. Add every key to `hi.ts`. GST lock, Complete, amend, F2 shortcuts included.
3. Zod `message:` must be i18n keys or mapped in the error renderer — no English-only schema messages on money screens.
4. Spot-check: switch locale to `hi`, walk Complete, POS pay, e-invoice cancel.

### Tests

- Vitest: locale `hi` + a money form validation snapshot or key-existence test (`Object.keys(en)` ⊆ keys used, `hi` has those keys). Optional: fail CI if `hi` missing keys that `en` has for a prefix `invoice.` / `pos.` / `einvoice.`.

### DoD

- [ ] Hindi Complete shows no English GST warning.
- [ ] `en` and `hi` parity for money namespaces.
- [ ] i18n loader is **locale-file based** (not Hindi-hardcoded) so A-02b can add `ta.ts` / `gu.ts` without rewriting screens.

### Agent prompt

```
Implement A-02 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
All invoice, POS, receipt, return, e-invoice user-visible strings through t().
hi.ts parity with en for those namespaces. Zod errors too. Stop when DoD is met.
```

---

## A-03 — One tax engine (SPA binds preview_totals)

| | |
|---|---|
| Effort | 2.5 weeks |
| Source | Q-005 / Q-006 / Q-018 / Q-083 · R5-005 |
| GATE | eng |

### Verify first

`POST .../preview_totals/` exists on sales invoices. Inclusive+cess+EXPWOP were fixed on the server. SPA editors may still compute locally.

### Files

- `backend/sales/views.py` `preview_totals`
- `web/src/pages/sales/NewInvoicePage.tsx` (+ purchase editor equivalent)
- `web/src/lib/tax.ts` — POS optimistic only
- Purchase / CN / DN editors if they duplicate tax math

### Steps

1. Debounced POST `preview_totals` on line/header change for invoice, purchase bill, CN, DN editors. Bind displayed GST/grand total to the response.
2. Keep local `tax.ts` **only** on POS for sub-100ms tap feel; on Complete, server wins (already).
3. If preview fails, show error and disable Complete — do not silently use stale local totals.
4. Charges, RCM, supply type, inclusive+cess must round-trip (already on backend — assert from SPA).

### Tests

- Vitest: mock preview endpoint, totals render from response.
- Pytest: preview matches Complete for a fixture with inclusive + cess + freight.

### DoD

- [ ] Screen total == saved invoice == GSTR line for the fixture.
- [ ] POS may optimistic-compute; Complete still server.

### Agent prompt

```
Implement A-03 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Bind SPA invoice/purchase/CN/DN totals to preview_totals. tax.ts POS-only.
Disable Complete if preview fails. Add preview==complete pytest. Stop when DoD is met.
```

---

## A-04 — POS that does not lose the sale

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | Q-054 / Q-084 / Q-090 |
| GATE | eng |

### Verify first

Cart keep-until-UPI-confirm/collect-later may already be in. Remaining: Saved / Offline / Unsaved chip; recover unpaid invoice CTA; walk-in local-state confirm.

### Files

- `web/src/pages/pos/PosPage.tsx`
- Offline helpers under `web/src/pages/sales/invoice/useInvoiceOffline.ts` (or POS equivalent)
- Backend only if recover-unpaid list endpoint is missing

### Steps

1. Persistent chip: Unsaved (local only) / Offline queued / Saved draft / Completed.
2. If UPI started and invoice exists unpaid: banner CTA “Open unpaid invoice {number}” (do not duplicate Complete).
3. Walk-in customer: confirm before Complete if party is generic walk-in (local modal; i18n).
4. Blank POS + intra assumption is **B-04**, not this ticket — only the recover UX here.

### Tests

- Vitest: chip state transitions; unpaid CTA shown when mocked unpaid id present.

### DoD

- [ ] Cashier can recover an aborted UPI sale.
- [ ] Chip matches queue vs posted.

### Agent prompt

```
Implement A-04 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
POS status chip (Unsaved/Offline/Saved). CTA to recover unpaid invoice after UPI abort.
Walk-in confirm. i18n. Stop when DoD is met.
```

---

## A-05 — Pilot is allowed to exist

| | |
|---|---|
| Effort | 2 weeks |
| Source | docs/pilot · Q-028 |
| GATE | **human** (PM/CA/ops). Agent prepares only. |

### Agent-allowed work

- Fill SHA placeholders in `docs/pilot/GO_NO_GO.md` from `git rev-parse HEAD` (do not fake signatures).
- Run / document `scripts/pin_image_digests.sh`.
- TLS terminator notes in `docs/pilot/RUNBOOKS.md` if missing (facts only).
- Golden-month **harness** (pytest that loads CA CSV when present); skip if file absent.

### Human-only

Signatures on GO_NO_GO, CA letter, UAT ≥5 companies, Sentry, SMTP, Play listing text.

### Agent prompt

```
Implement A-05 agent slice from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Prepare digest pin, runbook TLS notes, golden-month test harness that skips without
CA fixtures. Do NOT tick signature boxes. Stop when artefacts exist.
```

---

## A-02b — Tamil and Gujarati fast-follow

| | |
|---|---|
| Effort | 1.5 weeks after A-02 |
| Source | Competitive gap #9 |
| GATE | eng |

Depends on A-02 locale-file infra. Add `web/src/i18n/ta.ts` and `gu.ts` for the **same money namespaces** as A-02 (`invoice.`, `pos.`, `einvoice.`, receipts, returns). Locale picker lists English, Hindi, Tamil, Gujarati. Missing keys fall back to English and **fail CI** for those prefixes. Quality: unsigned locales are **beta** per `docs/roadmap/charters/locale-reviewers.md` (CI keys ≠ native review).


Marathi / Telugu / Kannada: not this ticket; repeat the same pattern later.

### Agent prompt

```
Implement A-02b from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Add ta.ts and gu.ts money-namespace parity with en; locale picker; CI missing-key
check. After A-02. Stop when DoD is met.
```

---

## A-06 — WhatsApp: invoice + payment link

| | |
|---|---|
| Effort | 2 weeks |
| Source | 18_COMPETITOR_ANALYSIS WhatsApp row · BB-000026 honesty |
| GATE | eng + Meta template approval (human) |

### Verify first

`backend/core/services/whatsapp.py` already has Cloud API + `wa.me` fallback and templates `invoice_ready`, `payment_reminder`, `invoice_share`. Invoice detail has a share button. This ticket makes **Complete → send invoice PDF + payment link** a first-class, reliable path — not a dead Cloud flag.

### Files

- `backend/core/services/whatsapp.py`, `backend/core/services/notifications.py`
- Invoice detail, POS post-pay, payment-link create
- Feature flag `ENABLE_WHATSAPP_CLOUD` (already)

### Steps

1. After Complete (and after payment-link create): offer Send WhatsApp (invoice number, amount, PDF link or attach if Cloud allows, pay-link URL). Fail to `wa.me` with the same text if Cloud is off or errors — never a silent no-op.
2. Use only `APPROVED_WHATSAPP_TEMPLATES`. Do not invent marketing templates.
3. Store send status on the invoice (queued / sent / fallback_link / failed).
4. DPDP: send only if customer has a phone and company WhatsApp opt-in is recorded (X-02 may land later — if no consent field yet, add `Customer.whatsapp_opt_in` default False; do not send Cloud messages without True. `wa.me` open-in-app is user-initiated and allowed).
5. Honest UI: “WhatsApp Cloud” vs “Open WhatsApp with message” — no “delivered” unless Cloud returned an id.

### Tests

- Cloud mocked send on Complete; fallback when token missing.
- Opt-in False → no Cloud send.

### DoD

- [ ] Cashier can send invoice + pay link in ≤2 taps after Complete.
- [ ] Flag off → wa.me only, copy honest.

### Agent prompt

```
Implement A-06 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Wire invoice + payment-link WhatsApp send through existing whatsapp.py templates.
Opt-in for Cloud; wa.me fallback; honest status. Stop when DoD is met.
```

---

## A-07 — AR dunning cadence (WhatsApp / SMS)

| | |
|---|---|
| Effort | 2.5 weeks |
| Source | 18_COMPETITOR_ANALYSIS Wave 8 collections · myBillBook pitch |
| GATE | eng |

W0-03 makes captured money land. This ticket makes **unpaid invoices get collected**.

### Files

- New `payments/dunning.py` or `core/services/notifications.py` cadence
- Celery beat; company settings (days 3/7/14, channels)
- `payment_reminder` WhatsApp template; SMS via existing `core/services/sms.py` if present
- Assistant `draft_payment_reminder` stays propose-only for AI; this ticket is **system cadence**, Owner-configurable, not the LLM.

### Steps

1. Company settings: enable dunning, aging buckets, max reminders, quiet hours IST.
2. Beat job: invoices with outstanding > 0, past due, not holding-gateway-paid; send reminder via WhatsApp (A-06) then SMS fallback.
3. Idempotent per invoice per day; skip if payment_state is paid-pending-books.
4. Owner can disable per customer. Default **off** until they opt in (DPDP / spam).
5. Do not auto-send from the AI assistant.
6. **Per-customer risk view (start simple):** outstanding, ageing, overdue amount, average
   payment delay, credit limit, available credit, promised-vs-actual, a `collection_status`, and
   a recommended next step (follow up / send statement / send link / reduce credit / stop
   credit). Feeds the B-05 Attention Center. No credit-scoring model -- buckets and averages only.

### Tests

- Due invoice: one reminder per configured day; paid invoice: none.
- Holding gateway capture: no “please pay” reminder.

### DoD

- [ ] Owner can turn on 3/7/14 day WhatsApp/SMS reminders.
- [ ] Default off. No dunning of already-paid-at-gateway invoices.
- [ ] Per-customer risk view surfaces ageing + recommended action into B-05.

### Agent prompt

```
Implement A-07 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Owner-opt-in AR reminder cadence (WhatsApp then SMS). Skip paid-pending-books.
Default off. Do not use the LLM to send. Stop when DoD is met.
```

---

## A-08 — Product telemetry (falsifiable shop-floor)

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | Competitive gap #5 |
| GATE | eng |

Without this, “pass Vyapar” is unfalsifiable.

### Steps

1. First-party events only (no extra ad SDK): `invoice_complete`, `pos_line_added`, `offline_enqueue`, `offline_flush_fail`, `complete_duration_ms`, `time_to_first_invoice_ms` (session).
2. Post to existing metrics endpoint if authenticated (`R1-003`); else store company-scoped rollups daily.
3. **No PII** in event props (no GSTIN, phone, line descriptions). DPDP minimize.
4. Dashboard for Owner: last-7-day Complete p95, offline fail count, median taps-per-bill if POS events include tap count.
5. Wave A exit reads these numbers — not a screenshot.

### DoD

- [ ] Complete p95 and offline_flush_fail are queryable for a pilot company.
- [ ] Events contain no customer PII.

### Agent prompt

```
Implement A-08 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
First-party telemetry for Complete duration, taps-per-bill, offline failures.
No PII. Owner can see 7-day p95. Stop when DoD is met.
```

---

# Wave B — GST ops

**P0 track owns live IRN and GSTR-1/3B GSP upload.** B-01/B-02 are the eng slices. Do not mark them DONE on sandbox CI alone. Live HTTP requires P0-01 sandbox tenant + W0-02.

---

## B-01 — Live IRN and e-way

| | |
|---|---|
| Effort | 5 weeks |
| Source | Q-035 · vs Zoho/Tally |
| GATE | eng + **GSP/KYC** |

### Verify first

Sandbox GSP adapters and `submit-einvoice` exist (`test_sprint_e_gsp_protocol.py`). Production must stay fail-closed without certification (`BB-000624`).

### Files

- `backend/core/services/gsp_adapters.py`
- `backend/sales/einvoice_eway_actions.py`
- `web/src/components/EinvoiceEwayPanel.tsx` (cancel reason — D-010)
- env examples: `GSP_LIVE_BASE_URL`, dedicated secrets (no all-A placeholders)

### Steps

1. Production path: only named provider + encrypted credentials + `GSP_LIVE_BASE_URL`. Reject placeholder secrets.
2. Generate + cancel IRN and e-way; cancel requires a **reason code** in UI and API.
3. Fail closed: missing cert / sandbox-in-prod / incomplete KYC → no live HTTP.
4. Do not implement NIC direct as a second stack; GSP only.
5. Async already queued — keep; surface QUEUED/FAILED in Hindi+English.

### Tests

- Existing cassette tests stay.
- New: prod settings + empty credentials → no HTTP (mock).
- Cancel without reason → 400.

### DoD (eng slice — not P0 Done)

- [ ] Regular B2B Complete can generate IRN against **sandbox** in CI (already partly true — keep green).
- [ ] Prod live call is impossible without named GSP secrets.
- [ ] Cancel reason required in UI.
- [ ] Ticket log says **LIVE_BLOCKED** until P0-01 names a sandbox tenant; then a **staging IRN** against that tenant.
- [ ] **P0 Done** (human): production IRN for the named pilot GSTIN by T0+12w or slip plan active.

### Agent prompt

```
Implement B-01 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Live IRN/e-way via existing GSP adapters, fail-closed without cert/secrets.
UI+API cancel reason. Do not call real NIC. Do not mark P0 Done on CI sandbox
cassettes alone. Stop when eng DoD is met.
```

---

## B-02 — Month-end GSTR-1 and GSTR-3B via GSP (not hand-portal)

| | |
|---|---|
| Effort | 4 weeks |
| Source | Q-034 / Q-059 · competitor GSTR via GSP |
| GATE | eng + GSP/CA · P0 track |

### Files

- `backend/reporting/` GSTR-1 and GSTR-3B builders
- Upload via GSP (`upload_gstr1` / 3B equivalent in adapters)
- FE reports pages; hide stub nav for 4/6/7/8/9 filing
- Watermark incomplete GSTR-9 tables

### Steps

1. Export CA-signed GSTR-1 **and GSTR-3B** JSON (`format=gstn-json`). Document `ENABLE_GSTN_JSON` for download-only months (P0 slip).
2. **GSP upload is in-scope**, not optional-nice-to-have: same fail-closed gate as B-01. Persist upload job id / ack. Not a GSTN portal bot.
3. Filing partner fallback: download JSON + logged SHA256 so CA can prove what was filed if GSP upload is down.
4. GSTR-4/6/7/8/9 remain **honesty stubs**. Watermark GSTR-9: “books worksheet, not filing pack”.
5. Do not build GSTR-9 portal upload. Composition: keep Regular packs hidden (already shipped).

### Tests

- JSON schema snapshot / existing GSTN JSON tests.
- GSP upload mocked success + fail-closed without secrets.
- Stub endpoints still `supported: false`.

### DoD

- [ ] CA can download GSTR-1 **and** GSTR-3B JSON for a closed month.
- [ ] With P0-01 secrets: GSP upload path works in staging (cassette or sandbox).
- [ ] UI never claims GSTR-9 is complete.
- [ ] **P0 Done** (human): one real GSTIN GSTR-1 submitted via GSP (or filing-partner handoff with logged JSON) by T0+16w.

### Agent prompt

```
Implement B-02 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
GSTR-1 and GSTR-3B JSON + GSP upload behind fail-closed GSP (not hand-portal only).
Keep 4/6/7/8/9 as stubs; watermark GSTR-9. Stop when eng DoD is met.
```

---

## B-03 — IMS + ITC control (credit-at-risk board)

| | |
|---|---|
| Effort | 6 weeks (was 3.5 -- scope grew with the Jul-2026 hard-lock) |
| Source | R3-014 * GST IMS mandatory 2025-10 * GSTR-3B Table 4A hard-lock 2026-07 |
| GATE | eng + CA. **Live GSP pull needs P0-01 sandbox tenant.** The GSTN offline-tool file path has no GSP dependency. |

### Why this replaced the old "decision board"

Since July 2026, GSTR-3B Table 4A is auto-populated from GSTR-2B and cannot be typed over. GSTR-2B is
built from IMS actions. The monthly reconcile is now a cash decision, and "no auto-claim, human
decides each row" without volume tooling means a distributor with 300+ purchase invoices either
bulk-accepts blindly (credit claimed on invoices nobody checked) or loses eligible credit. The portal
caps bulk actions at 500 rows; GSTN's own answer is a spreadsheet. That is the gap.

### Verify first

`backend/reporting/gstr2b.py` already has `match_gstr2b_to_purchases` and `claimable_itc_from_2b`;
`Gstr2bIngest` + upload/match APIs exist; UNREVIEWED ITC parks in `1390`. That is the matching engine
-- roughly the hard half. **Missing entirely:** any IMS *action state*
(accept / reject / pending / no-action), the remark field, a JSON round-trip, the Section 16(4)
countdown, and the supplier loop.

### Files

- `backend/reporting/gstr2b.py`, `backend/reporting/models.py` (new `ImsInvoiceAction` or fields on the 2B line)
- `backend/reporting/ims_offline.py` (new -- parse + emit the GSTN offline-tool file)
- `backend/accounting/services.py` ITC reclass (`1390` -> `1310/1320/1330`)
- `backend/core/services/gsp_adapters.py` (IMS pull, behind the B-01 fail-closed gate)
- FE: reports GSTR-2B / IMS page (rebuild); a `credit-at-risk` widget for B-05

### Steps

1. **Ingest.** Pull IMS + 2B for the period via GSP when P0-01 is live; **fallback:** accept the
   GSTN offline-tool file (Excel in, JSON out) so this works with no GSP. Import / refresh the
   purchase register for the period.
2. **Match** each row on GSTIN + document number + document date + taxable value + tax amount.
   Classify: `exact`, `value_mismatch`, `missing_in_books`, `missing_in_ims`, `wrong_gstin`,
   `duplicate`, `potentially_ineligible`, `other`.
3. **IMS action state** per invoice: `ACCEPT` / `REJECT` / `PENDING` / `NO_ACTION` -- with `remark`,
   `acted_by`, `acted_at`, `submitted_payload`, `response`. Append-only history. **Never auto-accept
   silently** -- deemed acceptance is shown as a decision the user made, always.
4. **Bulk accept** the `exact` bucket in one action; handle the 500-row portal cap by **chunking**,
   not by asking the user to paginate. Idempotent: a retried push must not double-action a row.
5. **Pending is a clock.** Track the Section 16(4) eligibility expiry per invoice; count down;
   escalate as it nears. Pending credit that quietly dies is the worst outcome.
6. **Credit-at-risk numbers:** total ITC, matched ITC, unresolved ITC, ITC at risk (Rs), expiring ITC
   (Rs + count), days remaining. These feed B-05.
7. **On `ACCEPT` of a claimable row:** reclass `1390` -> input GST codes; idempotent if already
   reclassed. **On `REJECT`:** CA-correct GL (reuse the existing reverse-ITC path; do not invent codes).
8. **Supplier loop (a scorecard, not procurement AI):** per supplier -- purchase value, mismatch
   count, missing invoices, rejections, ITC affected (Rs), average correction time. For every
   rejected / mismatched invoice: identify the supplier, name the defect, generate a WhatsApp message
   (A-06 templates), track the reply, re-match after correction.
9. **Books stay the source.** IMS actions annotate a purchase document; they never edit it.

### Tests

- Existing `test_gstr2b_claim_requires_claimable_itc` still green.
- Offline-tool file round-trips: import -> act -> export JSON that re-imports identically.
- `NO_ACTION` at period lock is recorded as deemed-accept, not silently dropped.
- 600-row period: bulk accept chunks into <= 500 and is idempotent on retry.
- `exact` accept reclasses `1390` -> `1310..`; reject leaves `1390` cleared per CA rule.
- Section 16(4) countdown: an invoice past the window is flagged ineligible, not "pending forever".

### DoD

- [ ] A distributor with 300+ purchase invoices clears a real month's IMS in **one sitting**.
- [ ] "Credit at risk this month = Rs X" is a single number, per company, backed by invoice rows.
- [ ] Every rejection produces a supplier message with the exact defect.
- [ ] No auto-accept without a recorded decision. Books unchanged by IMS actions.
- [ ] Works from the GSTN offline-tool file with **no** GSP configured.

### Out of scope

Auto-claim heuristics; full supplier procurement intelligence / price benchmarking (scorecard only);
portal login automation.

### Agent prompt

```
Implement B-03 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
IMS + ITC control: ingest (GSP or GSTN offline-tool file), match + classify, IMS action state
(accept/reject/pending/no-action) with remarks + audit + JSON round-trip, bulk-accept with
500-row chunking, Section 16(4) countdown, credit-at-risk rupee number, supplier defect scorecard
+ WhatsApp message. No auto-accept. Books stay the source. Stop when DoD is met.
```

---

## B-04 — GST Complete guardrails

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | Q-090 · R2-011 |
| GATE | eng + CA rule |

### Files

- `backend/sales/services.py` Complete (POS / place of supply)
- `backend/purchases/services.py` `_unregistered_rcm_gate`
- POS + purchase FE warnings
- Nav: hide GSTR stub routes (started)

### Steps

1. Blank POS on intra assumption: **hard warn**; Complete requires confirm flag `confirm_blank_pos` (default block in API, FE modal).
2. Unregistered supplier with blank taxpayer_type: RCM gate **on** (R2-011 default hard gate) — confirm still in code; close any remaining hole.
3. Hide nav entries that 404 or `supported: false`.

### Tests

- Complete walk-in blank POS without confirm → 400.
- URD purchase without RCM confirm → 400.

### Agent prompt

```
Implement B-04 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Block/warn blank POS intra Complete unless confirm_blank_pos.
Keep unregistered RCM hard gate. Hide GSTR stub nav. i18n. Stop when DoD is met.
```

---

## B-05 — Business Attention Center

| | |
|---|---|
| Effort | 3 weeks |
| Source | one-level-up thesis * consolidates existing alerts + hints |
| GATE | eng |

### Why

The owner should not hunt through modules. One screen answers **"what needs my attention today?"** --
a ranked work queue, not another dashboard. Every item: **Problem -> Money -> Reason -> Action -> Fix**.
Downstream waves (M-01, M-03, M-04, Q-02, Q-03, R-01–04) emit **only** the AttentionRow contract
below — they do not invent a second alert shape.

### Verify first

`backend/insights/alerts.py` `build_business_alerts` and `backend/insights/services.py`
`build_growth_hints` already exist (customer concentration, margin proxy, health score). This ticket
**consolidates and ranks** them and adds a money figure + a resolve CTA -- it is not a new alert engine.

### Attention-row contract (frozen — every later wave emits this shape)

M–S (and F-04/F-06) **must not invent a second alert format**. One row:

```
AttentionRow {
  code               str            # stable, e.g. "ITC_AT_RISK", "SCHEME_LIABILITY_HIGH"
  severity           "critical" | "warning" | "info"
  title              str            # <= 80 chars
  money_impact_paise int            # signed; 0 if not monetary  (JSON field: money_impact_paise)
  currency           "INR"
  reason             str            # one line, why this fired
  action_label       str            # button text
  action_href        str            # deep link INTO the fix, not a report
  source_ticket      str            # "B-03", "M-01", "Q-02", ...
  entity_ref         {type, id}     # invoice / party / scheme / branch / ...
  dedupe_key         str            # re-runs update, do not duplicate
  first_seen         datetime
  snooze_until       datetime | null
}
```

API/serializer uses `money_impact_paise`. Do not add ad-hoc fields per source without versioning
this contract.

### Files

- `backend/insights/attention.py` (new -- merge alerts + hints + B-03 credit-at-risk + due AR + guardrail hits into one ranked list)
- `backend/insights/alerts.py`, `services.py` (add the missing rules)
- FE: dashboard "Needs attention" queue; deep links into the fix

### Steps

1. One ranked feed. Each row **is** an `AttentionRow` (contract above). Rank by `severity` then
   `|money_impact_paise|` then recency / days remaining if present in `reason` or source payload.
2. Sources: ITC at risk + expiring (B-03), GST Complete exceptions (B-04), overdue customers (A-07),
   paid-pending-books captures (W0-03), stock discrepancies / expiring inventory (Wave C), IRN issues
   (B-01), missing documents (D-04), plus **rules-based leakage detectors:**
   - margin compression (last purchase price up, selling price flat),
   - sale below expected margin / below cost,
   - discount over a company threshold or stacked twice,
   - dead / slow-moving stock, abnormal stock adjustment,
   - duplicate payment, unusual supplier price jump.
   All deterministic -- **no LLM in this ticket.**
3. Rank by `severity` then `|money_impact_paise|` then recency. Do not add a `days_remaining` field
   outside the contract — put remaining days in `reason` if needed.
4. "Needs me" filter; snooze with reason + audit; a dismissed item reappears if the condition returns.
5. Owner-scoped; respects capability flags (a cashier does not see margin leakage).

### Tests

- A fixture with an overdue invoice + an at-risk ITC row + a dead-stock item -> three ranked rows
  with correct `money_impact_paise` and working deep links.
- Snooze hides a row; the condition recurring un-hides it.
- No PII in the payload beyond what the target screen already shows the user.

### DoD

- [ ] One screen lists every actionable issue, ranked, each with a Rs figure and a one-click fix.
- [ ] Payload is exactly the AttentionRow contract; no extra per-source shapes.
- [ ] Reuses `build_business_alerts` / `build_growth_hints`; no duplicate alert logic.
- [ ] Leakage detectors are rules, not AI.

### Agent prompt

```
Implement B-05 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
One ranked "needs attention" queue using the frozen AttentionRow contract
(code, severity, title, money_impact_paise, currency, reason, action_label, action_href,
source_ticket, entity_ref, dedupe_key, first_seen, snooze_until).
Consolidate build_business_alerts + build_growth_hints + B-03 credit-at-risk + due AR + guardrail
hits + rules-based leakage detectors. Deep links, snooze-with-reason, capability scoped. No LLM.
Stop when DoD is met.
```

---

## B-06 — Effective-dated GST rate engine

| | |
|---|---|
| Effort | 2.5 weeks |
| Source | GST 2.0 (22 Sep 2025) * one-level-up thesis |
| GATE | eng + **a named rate-table owner** (below) |

### Why

After GST 2.0 the correct rate depends on the **invoice date**. `backend/masters/hsn_catalog.py` is a
static code+description list with **no rate on it**, and a repo-wide search finds no effective-dated
rate history anywhere. A cloud product can ship a rate change overnight and prove past invoices were
right; a desktop product ships it next release. This is the clearest structural edge available.

### Rate-table owner (fill on adoption -- empty = B-06 ships without the "automatic correctness" claim)

| Role | Name | Accountable for |
|---|---|---|
| Rate curator | ________ | HSN/SAC rate table kept current through every GST Council meeting. A stale table is worse than none. |

### Files

- `backend/masters/models.py` -- new `HsnRate` (`hsn_sac`, `rate`, `cess`, `valid_from`, `valid_to`, `version`, `source_ref`)
- `backend/masters/hsn_catalog.py` -- resolver `rate_for(hsn, on_date)`
- `backend/core/services/billing.py` -- resolve at Complete using the **document date**, never `today`
- Sales / purchase line -- snapshot `applied_rate` + `rate_version` onto the line
- New report: rate-exposure back-scan

### Steps

1. `HsnRate` table, versioned, seeded with the pre- and post-22-Sep-2025 sets. Shipped by the curator,
   not typed by the shopkeeper.
2. `compute_document_totals` resolves the rate from the **document date**. A completed document is
   never re-rated by a later table change (the line snapshot is authoritative for filed months).
3. Company / user overrides allowed (classification disputes are real) but **flagged**, with a reason,
   audited (D-03).
4. **Back-scan report:** "you billed 12% on N invoices dated after 22 Sep 2025; estimated exposure
   Rs X; review". Feeds B-05. Also runnable against a freshly imported Tally/Marg history -- that demo
   closes migrations.

### Tests

- Invoice dated 21 Sep 2025 resolves the old rate; 23 Sep resolves the new one.
- Editing `HsnRate` does not change any completed invoice's stored `applied_rate`.
- An override is recorded with a reason and appears in the audit trail.
- Back-scan on a mixed-date fixture lists exactly the mis-rated invoices with a Rs delta.

### DoD

- [ ] Rate applied = rate legally in force on the document's own date, snapshotted on the line.
- [ ] A later table change never rewrites a filed month.
- [ ] Back-scan report exists and feeds the Attention Center.
- [ ] If no curator is named, the product does **not** claim "GST rates updated automatically".

### Agent prompt

```
Implement B-06 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Effective-dated HsnRate table (valid_from/to, version, source_ref). Resolve rate at Complete from
the document date, snapshot applied_rate + version on the line. Later table edits never re-rate
filed documents. Flagged + audited overrides. Back-scan exposure report feeding B-05.
Stop when DoD is met.
```

---

# Wave C — Stock (~9.5 weeks)

---

## C-01 — Offline godown

| | |
|---|---|
| Effort | 3.5 weeks |
| Source | Q-092 |
| GATE | eng |

### Files

- Inventory count / transfer pages (grep `StockCount`, `transfer` in `web/src`)
- Outbox pattern from purchase/sales offline (`useInvoiceOffline.ts`)
- Backend count complete API (must be idempotent)

### Steps

1. Stock count + warehouse transfer **outbox** using the same outbox primitive as sales (do not invent a third sync protocol).
2. Hide outbox badge on pages that cannot flush.
3. **Conflict UI (required):** server qty changed → modal: Show server qty, Show local count, actions **Keep server** / **Keep local and resubmit** / **Cancel**. Never last-write-wins. i18n.
4. **Duration target:** godown can count/transfer **8 hours** offline (same as A-01 POS), then flush. State this in the UI (“Last synced … · N pending”).

### Tests

- Vitest outbox enqueue/flush + conflict modal branches.
- Pytest: double-flush same count id is idempotent.

### DoD

- [ ] Count saved offline; 8h target documented.
- [ ] Conflict is a choice, not an error toast only.

### Agent prompt

```
Implement C-01 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Offline outbox for stock count and transfer. Conflict modal (keep server / keep
local). 8-hour offline target. Hide badge where flush does not exist.
Stop when DoD is met.
```

---

## C-02 — Lot identity through the document chain

| | |
|---|---|
| Effort | 2.5 weeks |
| Source | Q-039 · R2-007 / R2-026 |
| GATE | eng |

### Verify first

Challan→invoice serial match may have started (Q-039). Opening unique is W0-08c — if W0-08c not done, do the unique constraint here **or** depend on W0-08c.

### Files

- Delivery challan → invoice convert (`sales` services)
- `backend/sales/cogs_service.py` zero-cost warning
- Batch/serial fields on challan lines

### Steps

1. Convert challan to invoice: product + batch + serial must match remaining challan qty; mismatch → 400.
2. Opening-stock unique if not done in W0-08c.
3. Zero-cost SALE: warning on Complete (and FE); do not block unless `block_zero_cogs` product flag exists — default warn.

### Tests

- Challan serial A, invoice serial B → 400.
- Opening twice same SKU/warehouse/batch → IntegrityError.

### Agent prompt

```
Implement C-02 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Challan→invoice must match product+batch+serial. Opening unique if not in W0-08.
Keep zero-cost SALE warning. Stop when DoD is met.
```

---

## C-03 — Find stock the way the shop talks

| | |
|---|---|
| Effort | 3.5 weeks |
| Source | ITEM_CUSTOM_FIELDS · Q-023 |
| GATE | eng |

### Files

- `backend/masters/custom_fields.py`, product list API
- POS finder in `PosPage.tsx`
- Inventory list columns
- FEFO allocation in `InventoryService.reserve_stock` / Complete (already FEFO for SO — default for `track_batch` sales)

### Steps

1. Company item custom fields appear as **default columns** and POS search keys (brand/rack/licence).
2. Sales Complete for `track_batch`: default allocate FEFO (earliest expiry) unless user picked a lot.
3. Expiry alerts: action “write off” creates the existing expiry/write-off movement type (grep; do not invent a new GL).

### Tests

- API filter `custom_fields.brand=`.
- FEFO: two lots, Complete without batch pick consumes earlier expiry.

### Agent prompt

```
Implement C-03 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Custom fields as default list/POS search. FEFO default for track_batch.
Expiry write-off from alerts using existing movement types. Stop when DoD is met.
```

---

## C-04 — Distributor schemes and party-wise pricing

| | |
|---|---|
| Effort | 3 weeks |
| Source | PRD wholesaler/distributor · Busy/Marg turf · gap #8 |
| GATE | eng |

### Verify first

`PriceList` / `PriceListItem` and `Customer.price_list` already exist. This ticket is **schemes / slabs / qty breaks**, not a second price-list model.

### Files

- `backend/masters/` price list items (add min_qty / max_qty / discount_pct if missing)
- Sales `resolve_unit_price` path
- FE price-list editor + invoice line showing applied scheme name

### Steps

1. Quantity slabs on a price list (e.g. 1–10 @ ₹100, 11+ @ ₹92) applied at line qty. Document GST: discount is BEFORE_TAX unless price_mode says otherwise (match existing invoice discount).
2. Party-wise: customer price list already — ensure POS and invoice both resolve it; show “List: {name}” on the line.
3. Optional invoice-header scheme (one promotional % or amount) using existing header discount — do not invent a parallel discount engine.
4. CN/DN must **not** re-price off today’s list (SALES-01) — copy original unit_price.

### Tests

- Slab: qty 12 picks the 11+ rate.
- Customer without list uses product selling price.
- CN from invoice keeps original rate.

### DoD

- [ ] Wholesaler can maintain qty slabs and party lists without a spreadsheet.
- [ ] Not a Busy clone (no batch-scheme combinatorics beyond qty slab + party list).

### Forward note -- full scheme / QPS engine is charter-gated

buy-X-get-Y, free goods, value/qty slabs with achievement tracking, quarterly purchase incentives
(QPS), supplier/customer-specific schemes with validity dates and settlement calc -- potentially
the biggest distributor moat, and **out of scope until a named distributor beachhead pilot exists**
(charter, `WAVES_E_TO_L` Wave K). C-04 ships qty slabs + party lists only.

### Agent prompt

```
Implement C-04 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Qty slabs on price lists + party list on POS/invoice. Do not re-price CNs.
Stop when DoD is met.
```

---

# Wave D — CA practice (~9.5 weeks)

---

## D-01 — Accountant practice workspace

| | |
|---|---|
| Effort | 4.5 weeks |
| Source | R1-008 · Q-019 / Q-087 · Phase 7.2 |
| GATE | eng |

### Verify first

`useCompanySwitcher` and memberships API exist. `permissions.py` may auto-pick `active_company` when multiple memberships and none selected (comment vs R1-008 409). Decide: **force picker on 409** (review) vs current auto-pick. This plan: **409 + FE modal** when memberships > 1 and no `active_company` and no valid `X-Company-Id`. Remove silent auto-pick.

### Files

- `backend/core/permissions.py`
- `web/src/hooks/useCompanySwitcher.ts`, `CompanySwitcher.tsx`
- `web/src/api/client.ts` (409 interceptor)
- `mobile/` native wrapper / same SPA client
- Dashboard / home route for cashier (no P&L) — Q-087
- LimitedAccessLanding if relevant

### Steps

1. BE: multi-membership + no active company → **409** `{ code: "COMPANY_REQUIRED", memberships: [...] }` not 403 loop. Remove silent auto-pick.
2. FE: on 409, open company picker; then retry with `X-Company-Id`.
3. **Client compatibility sweep (required):**
   - Single-membership users: **no 409**, same as today (auto company).
   - SPA interceptor handles 409 once (no retry loop).
   - Capacitor WebView uses the same SPA — verify picker on a phone-sized viewport.
   - Grep other API clients (`load/`, scripts, OpenAPI samples) for missing `X-Company-Id`.
4. Cashier / sales-only role: default landing = today’s POS/sales, **not** P&L/reports.
5. One user, many companies: switcher + memberships, not a new Tenant model.
6. **Forward note:** the cross-company *Practice Console* (one board across all client companies --
   IMS actioned, ITC at risk, missing bills, GSTR-1/3B ready, books tie, next deadline, "needs
   me" filter, deep links) is **Phase 2 / post-pilot** (`WAVES_E_TO_L`). Every query today is
   single-company scoped; the console needs a separately-audited aggregation path, not a loosened
   filter. D-01 delivers the switcher + 409 + cashier home only.

### Tests

- API: user with 2 memberships, `active_company=null`, no header → 409.
- API: user with 1 membership, `active_company=null` → 200 with that company (no lockout).
- FE: mock 409 shows picker (vitest).
- FE: single-membership fixture never opens picker.

### DoD

- [ ] CA runs 10 companies without lockout.
- [ ] Cashier never lands on Access denied / P&L.
- [ ] Single-membership and mobile WebView still work.

### Rollback

Restore auto-pick of `memberships[0]` behind `auto_pick_company_on_empty=True` (default False after this ticket). Emergency on for broken mobile builds.

### Agent prompt

```
Implement D-01 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Multi-membership without active_company returns 409 + picker payload.
Single-membership unaffected. SPA + mobile handle 409. Cashier home = sales/POS.
Stop when DoD is met.
```

---

## D-02 — Leave Tally once + backup parity

| | |
|---|---|
| Effort | 5 weeks |
| Source | Q-004 / Q-065 / Q-069 |
| GATE | eng |

### Files

- `backend/imports/services.py` (Tally CSV/XLSX)
- Import UI copy (must say **migration**, never **sync**)
- `backend/accounts/tenant_backup.py`
- Restore path; wipe/destroy-in-place

### Steps

1. Harden import: masters + openings land; void rules from W0-08d; report row-level errors; no partial silent skip of openings without a summary.
2. Every Tally UI string: “Import / migrate from Tally”. Grep `sync` in import pages and kill live-sync implication.
3. Backup JSON covers the same model set restore applies. If wipe-in-place would delete rows not in backup, **refuse** unless `confirm_destroy_unbacked=true`.
4. Do not build live Tally XML sync.
5. **Treat migration as a product, not an import screen:**
   - **Pre-import validation summary** before commit: `N records / N valid / N warnings / N errors`.
   - **Post-import reconciliation proof:** opening stock, receivables, payables and balances each
     assert-match the source totals; show a pass/fail line per bucket.
   - **Row-level, human-readable error report** with fix-and-re-upload.
   - **Documented rollback** of a bad import (reuse the W0-08d import-void rules).
6. **Photo / handwritten challan -> draft:** the `core/services/bill_images.py` enhance/split
   pipeline + `imports/` already back purchase-bill OCR -- expose a "photograph a bill -> draft
   transaction, user confirms, then post" path for sales too. Small, high adoption value.
7. Marg / Busy importers reuse the same `AccountingMigration` interface but stay **charter-gated**
   (`WAVES_E_TO_L` L-05) -- do not build them here.

### Tests

- Import golden CSV → openings match.
- Restore after wipe ⊆ backup keys.
- Grep test or i18n: no “Tally sync” in `en.ts` import namespace.

### DoD

- [ ] Tally import lands openings on a fixture.
- [ ] Pre-import counts + post-import reconciliation (stock/AR/AP/balances) shown; documented rollback.
- [ ] Restore cannot silently drop extra live rows.
- [ ] UI never says live sync.

### Agent prompt

```
Implement D-02 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Harden Tally CSV/XLSX import. Copy = migration not sync. Backup/restore parity
or refuse destroy-in-place. No live Tally API. Stop when DoD is met.
```

---

## D-03 — Invoice audit trail (“who changed this”)

| | |
|---|---|
| Effort | 1.5 weeks |
| Source | Competitive gap #10 · `AuditEvent` already exists |
| GATE | eng |

### Verify first

`AuditEvent` + `AuditService` exist; completed-invoice edits are audited (`test_completed_invoice_audited_edit_allows_line_change`). Missing: **Owner/CA UI** on the invoice: who, when, before/after money fields.

### Steps

1. `GET /api/v1/sales/invoices/{id}/audit/` company-scoped, role Owner/Admin/CA (or existing audit capability).
2. Render a timeline: user, action, timestamp, field diffs from `metadata` (ensure Complete/amend writes diffs — R2-002 already wanted this).
3. i18n. No PII beyond user display name + field names + amounts (already on the invoice).

### DoD

- [ ] Owner can answer “who changed line 2 GST” from the invoice screen.

### Agent prompt

```
Implement D-03 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Invoice audit timeline API + UI from existing AuditEvent. Stop when DoD is met.
```

---

## D-04 — Missing-document chase (CA time sink)

| | |
|---|---|
| Effort | 2 weeks |
| Source | one-level-up thesis * CA month-end pain |
| GATE | eng * needs A-06 templates + B-03 IMS match |

### Why

A week of every accountant's month is chasing clients for purchase bills that appear in IMS/2B but
not in the client's books. Automate the loop.

### Files

- `backend/reporting/` -- "in IMS/2B, not in books" diff (reuse the B-03 `missing_in_books` bucket)
- `backend/core/services/whatsapp.py` + A-06 templates
- `backend/imports/` -- accept a photo reply into the import queue
- FE: "Documents your books are missing" list; client-facing "What my CA needs" view

### Steps

1. Generate the list of purchase invoices present in IMS/2B for the period but absent from books,
   grouped by supplier, with GSTIN + document number + date + taxable value.
2. One-tap WhatsApp to the client (or supplier) asking for exactly those bills; accept a photo reply.
3. Photo -> `bill_images` pipeline -> draft purchase in the import queue -> user confirms -> re-match
   in B-03.
4. Client-side "What my CA needs from me" screen mirrors the request so the chase has two ends.
5. Track state per requested document: requested / received / imported / matched.

### Tests

- A period with 5 IMS invoices absent from books produces a 5-item request list.
- A photo reply lands as a draft purchase and, once confirmed, clears from the missing list.

### DoD

- [ ] The missing-bill list is generated automatically from the IMS/books diff.
- [ ] One tap sends the request; a photo reply reaches the import queue.
- [ ] The client sees the matching "what my CA needs" list.

### Agent prompt

```
Implement D-04 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Auto-generate the "in IMS/2B not in books" list, WhatsApp the client for exactly those bills,
accept a photo reply into the import queue, re-match in B-03, mirror a client-side "what my CA
needs" view. Stop when DoD is met.
```

---

## X-01 — Performance budget and 50k-invoice soak

| | |
|---|---|
| Effort | 2 weeks + soak machine time |
| Source | Competitive gap #6 · PERFORMANCE_REPORT.md unknown at 10k |
| GATE | eng |

### Files

- `load/k6_smoke.js` (extend; today 5 VU × 30s — not a soak)
- `load/README.md`
- Optional pytest query-count on Complete

### Steps

1. **SLOs (adopted):** Complete p95 **< 800ms** on a 50k-invoice tenant (ex-PDF, ex-GSP) in staging. Invoice list p95 **< 2s** (PERFORMANCE_REPORT P0-620). Dashboard **< 500ms**.
2. Seed script or documented fixture for 50k invoices / 1k products (do not commit 50k SQL dumps).
3. k6 scenario: list + Complete draft; publish results in `load/results/` (gitignored) and a one-line summary in the ticket log.
4. If Complete misses SLO, file a follow-up — likely W0-06 not done; do not “fix” by removing indexes randomly.

### DoD

- [ ] SLOs written in `load/README.md`.
- [ ] One soak run attached to the ticket log (pass or fail with numbers).

### Agent prompt

```
Implement X-01 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Document Complete/list/dashboard SLOs. Extend k6 beyond smoke. 50k fixture
instructions. Do not claim pass without numbers. Stop when DoD is met.
```

---

## X-02 — App-sec / DPDP posture

| | |
|---|---|
| Effort | 2 weeks |
| Source | Competitive gap #11 · §0.5 DPDP opt-in `[OPEN]` · W0-08 is ops not app-sec |
| GATE | eng + legal (opt-in copy) |

### Steps

1. Customer/company **consent records**: WhatsApp Cloud, SMS dunning, LLM bill import (already should be Owner-only — confirm opt-in).
2. Privacy notice URL in settings; export/delete request stub that creates a support ticket (full erasure is a later charter — do not fake GDPR-grade delete).
3. Audit access to invoice PDFs / GSTR JSON (who downloaded).
4. Document posture in `docs/pilot/` one pager: data categories, retention, subprocessors (Razorpay, GSP, Meta Cloud). Honest: not a certified DPDP audit.
5. Do not enable Cloud WhatsApp or dunning without opt-in fields from A-06/A-07.

### DoD

- [ ] Opt-in gates Cloud WhatsApp and dunning.
- [ ] One-pager exists; no claim of DPDP certification.

### Agent prompt

```
Implement X-02 from docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md.
Consent fields for WhatsApp Cloud and SMS dunning. Honest DPDP one-pager.
Do not claim certification. Stop when DoD is met.
```

---

## Frozen tickets (do not implement)

| ID | Topic | Why |
|---|---|---|
| FZ-01 | Payroll PF Basic+DA, LOP, PT slabs | R4-007/008/010 — freeze until P0 IRN + charter |
| FZ-02 | MES / manufacturing enablement | Freeze flags — concession |
| FZ-03 | Full CRM | Freeze flags — concession |
| FZ-04 | ONDC / DigiLocker / eSign | Spike only |
| FZ-05 | Busy / Zoho adapters | Demand charter |
| FZ-06 | Live Tally sync | D-02 is import-only |
| FZ-07 | Cashfree/PayU live | Second gateway frozen |
| FZ-08 | GSTR-4/6/7/8/9 filing engines | Stubs only (B-02). GSTR-1/3B GSP is **not** frozen. |
| FZ-09 | Certified PAN/UDYAM | Sandbox only |
| FZ-10 | iOS App Store | Concession |

If an agent is asked to do these: reply with this table and stop.

---

## Definition of Done (every eng ticket)

1. Ticket tests added and passing locally.
2. No new tenant-isolation holes (queryset without `company=`).
3. Locale files updated if UI copy changed (`en` + `hi` minimum).
4. Append `docs/roadmap/ticket-logs/<ID>.md` — **not** the table below.
5. No freeze-list features enabled.
6. Money-math tickets include the **Rollback** path in the PR description.

### Wave exits (measurable — replace “pass Vyapar”)

| Wave | Exit (all must be true) |
|---|---|
| **0** | Two Completes → one JE. Multi-GSTIN Complete: tax heads match stamp; grand-total change requires confirm. Closed-period webhook: shop shows paid-pending-books; receipt posts after reopen. Outstanding (books on) matches statement (PD-02). |
| **A** | Release APK Completes a sale. Hindi Complete has no English GST warning. POS Complete in **≤ 8 taps** from empty cart to paid (measure via A-08). **8 hours** offline with **zero lost** queued sales on a 50-draft test. Thermal print **< 2s** in lab or documented exception. Preview totals = saved = GSTR for one golden invoice. WhatsApp invoice+pay-link send works (Cloud or honest wa.me). |
| **P0 / B** | **Production IRN** for a named Regular B2B pilot (not CI cassette). **GSTR-1 uploaded via GSP** (or filing-partner with logged JSON) for that GSTIN. **B-03:** a 300+-invoice month's IMS cleared in one sitting from the GSTN offline-tool file, with a "credit at risk = Rs X" number and supplier-defect messages. **B-06:** rate resolved from document date + snapshotted; back-scan report runs. **B-05:** one ranked money-tagged attention queue on the dashboard. GSTR-3B JSON download exists. |
| **C** | Count saved **8h** offline; conflict modal used. Challan–invoice lot mismatch blocked. POS search by custom field. Qty slab price list applies on a wholesale fixture. |
| **D** | Accountant switches 10 companies; **single-membership** users never 409. Tally import openings. Wipe ⊆ restore. Invoice audit timeline answers “who changed GST.” |

**Beat-competitors pilot** = Wave A exit **and** P0/B production IRN **and** A-07 dunning available (even if Owner leaves it off). Calendar: **9–15 months** solo including GSP/CA waits.

**After that pilot:** books enablement, AI honesty, Tally export, composition, payroll/MES charters — [`WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md`](WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md). Do not start E-02 or J/K/L from this file.


---

## Progress log (this file — humans only)

Agents **must not** edit this table. Use `docs/roadmap/ticket-logs/<TICKET-ID>.md`.

| Date | Ticket | Status | SHA | Notes |
|---|---|---|---|---|
| 2026-08-29 | (plan authored) | — | — | High-level feature plan + DEEP_CODE_REVIEW deferred |
| 2026-08-30 | (plan revised) | — | — | Competitive review: P0 GSP, WhatsApp, dunning, telemetry, SLOs, PD-01..03, parallel Wave A |
| 2026-08-30 | (plan revised r2) | — | — | One-level-up review: B-03 -> IMS+ITC control; new B-05 Attention Center, B-06 effective-dated rates, D-04 missing-doc chase; priority ladder; QPS/console = charter |
| 2026-08-31 | B-05 | plan | — | Frozen AttentionRow contract (`money_impact_paise` + source_ticket/entity_ref/dedupe_key); merge target `main` |

---

## Appendix — session cheat sheet

| If the user says | Start ticket |
|---|---|
| Double journals / concurrent Complete | W0-01 |
| Wrong CGST vs IGST after branch GSTIN | W0-02 |
| Razorpay paid but no receipt / UI still unpaid | W0-03 |
| Invoice numbers jump / GST number gaps | W0-04 (PD-03) |
| Retry created two invoices | W0-05 (PD-01) |
| Complete slow / wrong WAVG | W0-06 |
| Statement ≠ outstanding | W0-07a (PD-02) |
| Android / barcode / Play | A-01 |
| Hindi billing | A-02 |
| Tamil / Gujarati | A-02b |
| Screen total ≠ GST | A-03 |
| POS lost cart | A-04 |
| WhatsApp invoice | A-06 |
| Payment reminders / dunning | A-07 |
| Taps-per-bill / p95 | A-08 / X-01 |
| GSP contract / live IRN date | P0-01 (human) then B-01 |
| File GSTR-1 / 3B | B-02 |
| 2B ITC / IMS accept-reject / credit at risk / supplier chased | B-03 |
| What needs my attention / money leakage / one work queue | B-05 |
| Wrong GST rate after GST 2.0 / rate on a past date | B-06 |
| Walk-in GST wrong | B-04 |
| Godown offline | C-01 |
| Wrong batch on invoice | C-02 |
| Search by brand/rack | C-03 |
| Wholesale slabs / party price | C-04 |
| CA many companies | D-01 |
| Leave Tally / migration validation / photo -> bill | D-02 |
| CA chasing missing purchase bills | D-04 |
| CA cross-company console (one board, all clients) | E-L (post-pilot) |
| Who changed this invoice | D-03 |
| DPDP / consent | X-02 |
| Payroll / CRM / ONDC / Tally sync / iOS | FZ-* stop |
