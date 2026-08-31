# BizBoard — Waves M–S implementation plan (scale, moat, platform)

**Audience:** Cursor Agent, Cursor Cloud Agent, or a human following the same tickets.
**Companions (do these first, in order):**
1. [`WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md`](WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md) — money integrity, counter, GST ops (incl. **B-03 IMS+ITC**, **B-05 Attention Center**, **B-06 rate engine**), stock, CA practice, P0 GSP.
2. [`WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md`](WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md) — books-on, insights, ecosystem leftovers, composition/branch/payroll/MES charters, **F-06 Practice Console**. **Wave L (demand-gated stubs) is superseded by Wave P below.**

**Date:** 2026-08-31 (rev 3 — charter stub + B-05 contract in 0–D + Wave L retired)
**Branch:** M–S PRs target **`main`**.
**Source of truth for code:** the repo. Intent: this file + the [one-level-up thesis](WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md#the-one-level-up-thesis) + `FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.3 freeze list.

---

## What this file is — and is not

This is a **direction document**, not a build schedule. Everything here is gated on a **customer or
revenue milestone**, not a calendar date. If you are reading this while Waves 0–L are still open:
close those first. Nothing in M–S is on the critical path to the beat-competitors pilot.

The competitive wedge is set in 0–D and E–L: **Detect → quantify money → explain → help fix**, applied
to GST/ITC control. That wedge is **specified** in the companion plans (B-03 / B-05 / B-06 / A-06 /
A-07 / C-04) — it is **not yet shipped code**. M–S starts only when it is (see **G-SPINE**). M–S then
does exactly two things with it:

| Job | Waves |
|---|---|
| **Finish one segment** so the wedge is a moat, not a demo | **M** (distributor **or** pharma — one) |
| **Scale the wedge** — sell it without hand-holding, run it at 1M invoices, complete India Stack | **N** (platform), **O** (scale), **P** (India Stack), **Q** (intelligence GA), **R** (mid-market) |

**S** (adjacent / international) is explicitly not scheduled — it exists so nobody treats it as an
oversight.

### Status of every ticket in this file

`PROPOSED`. No ticket here is implementable until its start gates are ticked (below). An agent asked
to implement an M–S ticket with blank gates must reply **`BLOCKED — start gate not met`** and stop
(contract rule 20). The only work available now is **thickening this markdown** and **writing the
charter / gate scaffolding** — not product code.

---

## Start gates (milestones, not dates)

M–S does not begin until **all five** hold. Fill the blanks on adoption; blank = the wave is
*proposed*, not started.

| Gate | Threshold | Current |
|---|---|---|
| **G-EXIT** | Waves E + F + G exit tests green (see E–L §Wave exits) | ________ |
| **G-SPINE** | **B-03, B-05, B-06, A-06, A-07, C-04 all shipped and flag-on for ≥ 1 pilot** — the wedge is real code, not plan text | ________ |
| **G-REV** | **≥ ₹5,00,000 MRR sustained 2 months** (authoritative). ≥ 25 paying companies is a floor sanity-check, not a trigger on its own — 12 larger companies at ₹5L+ counts; 25 companies below ₹5L does not | ________ |
| **G-RETAIN** | ≤ 5% monthly logo churn across those companies | ________ |
| **G-WEDGE** | **B-03 flag-on in production** AND ≥ 10 companies completed a real month-end on the IMS board with no support ticket | ________ |

Per-wave gates on each wave header are **in addition** to these five.

### Milestone ladder (revenue gates escalate per wave)

| Milestone | Threshold | Unlocks |
|---|---|---|
| **G-REV** | ₹5L MRR / 2 months | Waves M, N, O, P, Q |
| **R-GATE** | **≥ ₹25,00,000 MRR OR ≥ 100 paying companies, plus one named mid-market reference customer** | Wave R |
| **S-GATE** | ≥ ₹1 crore MRR OR ≥ 500 paying companies, M-moat live, O-scale proven | Wave S (own plan file) |

---

## Global agent contract (additive to 0–D and E–L)

```
You are on Waves M–S from WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Rules 1–19 from the 0–D and E–L contracts still apply. Additionally:

20. Do not start ANY M–S ticket unless G-EXIT, G-SPINE, G-REV, G-RETAIN,
    G-WEDGE are ALL ticked in this file AND the wave's own gate is signed.
    Reply "BLOCKED — start gate not met" and stop.
21. Wave M is charter-gated on ONE named beachhead segment. A distributor
    charter = M-01 + M-02 + M-04 (M-03 excluded). A pharma charter = M-01 +
    M-03 + M-04, and MAY include M-02 if that customer runs vans. Never build
    for two different beachhead customers at once.
22. Scale work (Wave O) never changes money math, tax heads, or GL postings.
    If a partitioning/replica change would alter a number, stop — that is a bug.
23. Public API (Wave N) is versioned from day one, served under /ext/v1/
    (NOT /api/v1/ — that is the internal API). A breaking change ships a new
    version; the old one gets a >=180-day deprecation window and a Sunset header.
24. New India Stack / gateway / adapter work (Wave P) each needs its own charter
    copied from charters/_TEMPLATE.md AND >=3 rows in charters/demand-log.md.
25. AI that writes (Wave Q) stays propose -> human confirm. It never executes a
    money movement, an IMS submission, a GSP call, or a filing on its own.
    Q-04 only PRE-FILLS the B-03 form; the human submits via B-03's own flow.
    Tax/GSTR free-text answers stay refused (rule 15).
26. Every ticket leaves Verify-first, Files, Steps, Tests, DoD, Out of scope,
    Rollback in the PR description. Thin tickets in this file must be brought to
    that shape BEFORE they are implemented.
27. Scale work must not regress: money/stock totals byte-identical before and
    after any O-wave migration, checked by a golden reconciliation test + a
    CA-reviewed before/after pack.
28. Data export is ALWAYS available — including when premium modules are locked
    for non-payment and during a billing dispute. Non-payment locks features,
    never the customer's own data. O-04 export is in the free floor.
```

---

## Sequencing

```
G-EXIT + G-SPINE + G-REV + G-RETAIN + G-WEDGE   (all five start gates)
        │
        ├─ Wave M — distributor OR pharma charter signed (ONE beachhead)
        │     M-01 scheme/QPS engine (v1 subset)  → M-02 field order-taking (SO, offline)
        │     M-03 pharma depth (pharma charter only) → M-04 control dashboard
        │
        ├─ Wave N — manual provisioning is now a support cost
        │     N-01 Public API v1 (/ext/v1/)  ─┬→ N-02 outbound webhooks
        │     N-03 self-serve billing (BizBoard GST-registered first)  N-04 connector scaffold
        │                                     │
        ▼                                     ▼
   Wave O — scale signal: a tenant > 200k invoices/yr OR report p95 > frozen SLO budget
        O-01 large-tenant path · O-02 job maturity · O-03 SLOs · O-04 DR + always-on export
        │
        ├─ Wave P — each item its own charter + demand-log ≥3 (independent; retires E–L Wave L)
        │     P-01 live AA · P-02 gateway 2 · P-03 GSTR-9/9C (GSP-blocked) · P-04 iOS
        │     P-05 Busy/Zoho/Marg adapters · P-06a ONDC · P-06b DigiLocker · P-06c eSign
        │
        ▼
   Wave Q — after O-03 SLOs green + F-01/F-02 shipped
        Q-01 assistant GA · Q-02 predictive cashflow (harden) · Q-03 anomaly v2 (in-process) ·
        Q-04 agentic — fills the B-03 form only
        │
        ▼
   Wave R — R-GATE met + N-03 shipped + I-01 (branch) shipped + a mid-market charter
        R-01 branch consolidation · R-02 inter-company · R-03 budgets · R-04 approvals
        │
        ▼
   Wave S — NOT scheduled. Only after S-GATE (see §Wave S).
```

**Do not** build for two beachhead customers at once (rule 21). **Do not** start Q before O-03 SLOs
are green. **Do not** start R before N-03 and I-01 are in production.

---

## Effort (direction, not a schedule)

Solo-senior eng-weeks, assuming the segment/scale signal actually arrived. Ranges are wide on purpose.

| Wave | Eng-weeks | Dominated by |
|---|---:|---|
| M — moat | 10–16 (**v1 subset**; full Busy-class scheme engine is another 8–10) | scheme v1 correctness + field-sales offline conflict model + pharma claim cycle |
| N — platform | 12–18 | API surface + versioning + webhook retry/DLQ + billing state machine + BizBoard GST registration (non-eng, on the calendar) |
| O — scale | 12–20 | partitioning migration risk + replica routing + DR drills |
| P — India Stack | 4–8 **per item**, 8 items (P-06 split into 3) | each is its own KYC/contract calendar |
| Q — intelligence | 14–22 | eval harness + model cost + agentic-confirm safety suite |
| R — mid-market | 12–18 | consolidation correctness + inter-company reconciliation |
| S — adjacent | n/a | not scheduled |

**Do not sum these into a headline.** They will not all happen, and the ones that do are triggered
months apart by different signals.

---

## Repo map (additions)

| Area | Paths |
|---|---|
| Schemes / pricing | `backend/masters/` (price lists today), new `backend/schemes/` |
| Field sales | new `backend/fieldsales/`, reuse `web/src/pages/offline/` outbox primitive |
| Pharma | `backend/inventory/`, `backend/purchases/` (returns), new `backend/pharma/` register |
| Public API | new `backend/api_public/` (`/ext/v1/` router), `backend/core/throttles.py` (exists), new token model |
| Webhooks | new `backend/webhooks/` (event catalog + delivery + DLQ) |
| Billing | `backend/billing/` (`Plan.modules`, `Subscription` exist — extend), new `SaasInvoice` |
| Connectors | new `backend/connectors/` (registry + OAuth app model) |
| Scale | migrations, `backend/core/db_router.py` (new), `backend/*/tasks.py` |
| Observability | `backend/core/metrics.py` (extend), infra dashboards |
| Intelligence | `backend/insights/` (`assistant.py`, `services.py`, `alerts.py` exist) |
| Consolidation | `backend/accounting/`, `backend/practice/` (**created by E–L F-06 — a plan name today**) |
| Charters | `docs/roadmap/charters/` (per P-item, per M beachhead, per R customer) |

---

## Shared contract — the B-05 attention row

Half of M–S "feeds B-05". So B-05 **must define one row contract**, in the B-03/B-05 work in the 0–D
plan, and every downstream wave emits exactly that shape. No wave invents its own alert format.

Canonical copy lives in 0–D **B-05**. Downstream emitters (M-01, M-03, M-04, Q-02, Q-03, R-01–04) copy it; they do not extend it.

```
AttentionRow {
  code               str            # stable, e.g. "SCHEME_LIABILITY_HIGH"
  severity           "critical" | "warning" | "info"
  title              str            # <= 80 chars, human
  money_impact_paise int            # signed; 0 if not monetary
  currency           "INR"
  reason             str            # one line, why this fired
  action_label       str            # button text
  action_href        str            # deep link INTO the fix, not a report
  source_ticket      str            # "M-01", "Q-02", ...
  entity_ref         {type, id}     # invoice / party / scheme / branch
  dedupe_key         str            # so re-runs update, not duplicate
  first_seen         datetime
  snooze_until       datetime | null
}
```

If B-05 has not shipped (G-SPINE not ticked), no M–S ticket that "feeds B-05" can start.

---

# Wave M — Finish one segment (distributor OR pharma moat)

**Charter stub:** [`charters/WAVE_M_SEGMENT.md`](charters/WAVE_M_SEGMENT.md) — copy to
`WAVE_M_DISTRIBUTOR.md` or `WAVE_M_PHARMA.md` when a paying customer signs. Names **one** beachhead
segment, the pilot company ids, the written demand, the plan slug that unlocks it, **and the golden
fixtures** (10–20 of that customer's real historical Marg/Busy invoices with the scheme behind each —
see M-01). Pick distributor **or** pharma. **Who picks:** the first paying customer in either segment
who signs the charter. Do not pick in the abstract; a blank charter = Wave M never starts.

**Why now:** the 0–D thesis says "three segments is two more than a solo team can win — build the
shared spine, then finish ONE." The spine is specified (G-SPINE gates on it being shipped). Wave M is
that finish.

**Competitive role:** turn "cloud billing that also does GST" into "the tool a Marg/Busy distributor
cannot leave" — because the scheme history and the claim receivables live here.

**Why this is not vertical ERP:** every M ticket deepens **billing / sales / stock** for one vertical.
It adds no new domain. MES (production planning, BOM explosion, work-order scheduling — *making*
things) and payroll (HR) are different domains and stay frozen. See §What stays frozen.

---

## M-01 — Trade scheme / QPS engine (v1 subset)

| | |
|---|---|
| Effort | 5–7 weeks (**v1 subset below**; full combinatorics is another 8–10) |
| GATE | Wave M charter **AND** a named CA has signed the scheme GL codes (liability, free-goods COGS). **BLOCKED for all GL-posting steps until that signature exists** — agent must not invent 2xxx/5xxx accounts. |
| Supersedes | C-04 "forward note — full scheme / QPS engine is charter-gated" |

### v1 subset (what is in / out)

**In:** buy-X-get-Y (same or cross SKU), quantity slab, value slab, one QPS accrual per party, free
goods at cost, settlement credit note.
**Out of v1 (later charter):** multi-level distributor hierarchies, principal claim portals,
scheme-on-scheme stacking, retrospective scheme recalculation, per-company configurable resolution
order.

### Verify first

C-04 shipped **qty slabs + party-wise price lists** on `PriceList` / `PriceListItem` and stopped there
("not a Busy clone"). Confirm the sales `resolve_unit_price` path and the invoice discount model
(BEFORE_TAX vs `price_mode`) before touching them — schemes must not create a second tax engine.
**Golden fixture:** the charter must supply 10–20 real Marg/Busy invoices + the scheme that produced
each; without it the "matches Marg to the paisa" DoD softens to "matches a CA-reviewed manual
calculation."

### Files

- `backend/schemes/models.py` (new) — `Scheme`, `SchemeTier`, `SchemeReward`, `SchemeLedger`
- `backend/schemes/services.py` — `apply_schemes(document)` called from Complete, after totals, before GL
- `backend/sales/services.py`, `backend/purchases/services.py` — hook points
- `backend/accounting/services.py` — scheme liability / free-goods COGS posting (**CA-signed codes only**)
- FE: scheme admin; invoice line shows applied scheme; "₹X to unlock ₹Y" nudge (emits a B-05 row)

### Steps

1. **Scheme types** = the v1 subset above. Scope: customer-specific, supplier-specific,
   SKU / brand / category, `valid_from` / `valid_to`.
2. **Resolution order is ONE fixed preset, not configurable in v1:**
   `price list (incl. C-04 qty slab) → line discount → scheme → header discount`. One pass.
   C-04 qty slabs run **first, as the base price**; a scheme applies **on top** — slabs are not
   disabled, not merged. Free-goods and scheme-discount GST treatment: BEFORE_TAX unless `price_mode`
   says otherwise (same rule as C-04).
3. **Stacking:** at most **one** auto-applied line scheme **plus** at most **one** header/party QPS.
   buy-X-get-Y + QPS + party list → party list sets the base price, buy-X-get-Y applies on the line,
   QPS accrues to the `SchemeLedger` without changing the invoice. Two line-schemes never stack.
4. **Free goods (v1): always a non-taxable stock issue at cost** with a scheme-COGS line — **never** a
   ₹0 taxable line and never a taxable FOC line. (FOC without consideration → no supply; input-ITC
   reversal on the free qty is the CA's call, flagged not enforced.) Taxable-FOC is a charter
   exception, not v1. Zero-cost SALE still warns (C-02 rule).
5. **QPS period = the company's financial-year quarter** (Apr–Jun, Jul–Sep, …), `invoice_date` in
   period, company timezone (IST). Custom periods = charter exception. `SchemeLedger` accrues progress
   per party per scheme per period; the nudge ("₹84,000 more unlocks ₹42,000") posts a B-05 row.
6. **Settlement:** at period end, compute earned benefit; post per the **CA-signed** treatment
   (credit note vs claim receivable). BLOCKED until signed.
7. **CN/DN** never re-price off a scheme (SALES-01 rule) — copy original line values.

### Tests

- buy-10-get-1 on a 25-unit line issues 2 free units at cost with a scheme-COGS line; header foots.
- QPS ledger: three invoices across a company-FY quarter accrue correctly; settlement CN matches.
- Free goods appear in stock movement and COGS, not as a taxable invoice line.
- A party with no scheme is unaffected (regression vs C-04 qty slab).
- Scheme past `valid_to` does not apply.
- Golden fixture: each supplied Marg invoice reproduces to the paisa (or matches the CA manual calc).

### DoD

- [ ] A scheme-heavy distributor invoice matches the charter's golden Marg fixtures (or CA manual calc).
- [ ] Free goods never distort taxable value or GSTR.
- [ ] QPS progress + settlement are a `SchemeLedger`, auditable, feeding B-05.
- [ ] One resolution pass; no second tax engine; one fixed preset (no per-company config).
- [ ] The CA has signed the scheme liability + free-goods-COGS GL codes.

### Out of scope

Everything in "Out of v1" above.

### Rollback

`ENABLE_SCHEMES` company flag, default off. Off = C-04 behaviour exactly (qty slab + party list).

### Agent prompt

```
Implement M-01 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
v1 subset only: buy-X-get-Y, qty/value slabs, one QPS accrual, free goods at cost (non-taxable stock
issue, never a taxable/Rs0 line), settlement CN per CA-signed codes. ONE fixed resolution preset
(C-04 slab is the base price, scheme on top). QPS period = company FY quarter, IST. No GL posting
until the CA signs the codes. Charter + golden fixtures required. ENABLE_SCHEMES off. Stop at DoD.
```

---

## M-02 — Field order-taking (offline, Sales Order — not invoice)

| | |
|---|---|
| Effort | 4–6 weeks |
| GATE | Wave M charter. In a distributor charter: required. In a pharma charter: only if that customer runs vans. |

### Verify first

The counter offline outbox (A-01 / A-04 / C-01) is the primitive — visible outbox, deterministic
flush, idempotent server, conflict modal. **Reuse it. Do not invent a third sync protocol.** Field
sales differs only in: it produces **Sales Orders**, taken against a price-list + credit-limit
snapshot, flushed at end-of-round.

### Files

- `backend/fieldsales/` (new) — `FieldRoute`, `FieldOrder` (DRAFT on device → SUBMITTED on flush)
- reuse `web/src/pages/offline/` outbox; new route-runner FE
- `backend/sales/services.py` — convert a `FieldOrder` → **Sales Order (DRAFT)** on the server (SO
  reservation is the existing `reserve_stock` primitive)

### Steps

1. Salesman downloads a route: assigned parties, their price lists, credit limits, outstanding, last
   3 orders. Snapshot taken at download; staleness shown ("synced 4h ago").
2. Take orders offline against the snapshot. The app **warns** if a party is over its snapshot credit
   limit; it does **not** hard-block (the server re-checks on flush).
3. **Flush → Sales Order, never a direct invoice.** Field staff do not complete money. Stock is
   **reserved on SO confirm** (server, `select_for_update` on the customer — same lock as
   credit-limit Complete), and **consumed only when the counter completes the invoice from the SO**.
   No stock move on flush.
4. **Partial flush:** each `FieldOrder` is independent. 17 of 20 confirm as SOs; the other 3 go to an
   exceptions queue with the reason (credit / price / stock), never silently dropped.
5. **Re-price:** the **server price is authoritative** and posts (same rule as A-03 preview_totals).
   The snapshot price is retained on the `FieldOrder` for audit and shown as "quoted ₹X, confirmed
   ₹Y". The salesman does not re-confirm each at flush; if the delta exceeds a company threshold the
   SO lands DRAFT so the **counter** reviews before converting.
6. 8-hour offline target (same as A-01).
7. **No location capture in v1** — no GPS, no coordinates. Route verification (opt-in per-staff, with
   consent and a stated DPDP retention window) is a later charter, not v1.

### Tests

- Order offline for a party at snapshot ₹0-available credit → flush → exceptions queue, no SO posted.
- Server price differs from snapshot → SO uses server price; both prices retained; SO lands DRAFT if
  over the delta threshold.
- Double-flush of the same `FieldOrder` id → one SO (idempotent).
- No stock movement occurs on flush; movement occurs only when the counter completes the invoice.

### DoD

- [ ] A salesman walks a market with no signal, takes 20 orders, flushes at end of round to DRAFT SOs.
- [ ] No order is silently lost or silently re-priced; stock moves only at counter Complete.
- [ ] Reuses the counter outbox primitive; no location data captured.

### Out of scope

Route optimisation / mapping; **van inventory as a separate warehouse — accepted v1 concession: v1 is
order-taking (SO), not van-stock selling**; commission calculation; any GPS/location.

### Rollback

`ENABLE_FIELD_SALES` flag, default off. Route-runner FE hidden.

### Agent prompt

```
Implement M-02 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Offline field order-taking reusing the counter outbox primitive. Flush -> DRAFT Sales Order (never a
direct invoice); stock reserved on SO confirm, consumed only at counter Complete. Partial flush ->
exceptions queue. Server price authoritative; snapshot retained; over-threshold -> DRAFT for counter
review. 8h target. NO location capture. ENABLE_FIELD_SALES off. Charter required. Stop at DoD.
```

---

## M-03 — Pharma depth (expiry claims, breakage returns, licence, register)

| | |
|---|---|
| Effort | 3–5 weeks |
| GATE | **Pharma** charter only. Excluded from a distributor charter (later, separate charter). |

### Verify first

Batch / expiry / FEFO / serials are **shipped** (roadmap §0.4). Block-expired-stock defaults True.
FEFO is already the default allocation for `track_batch` (C-03). This ticket is the pharma-distribution
*money cycle* on top of that, not a batch rebuild. The **register column list and the states in scope
are charter inputs**, signed by the customer's CA / drug-licence consultant.

### Files

- `backend/purchases/` — breakage/expiry return type
- `backend/pharma/` (new) — `ExpiryClaim` (lightweight doc: `raised` / `accepted` / `credited`, links
  to a purchase return or purchase CN), `DrugLicence`, `ScheduleHRegister`
- Invoice PDF — one conditionally-rendered licence block
- FE: expiry-claim workflow; Schedule-H register report

### Steps

1. **Returns split:** saleable return (back to stock) vs breakage/expiry return (quarantine, not
   saleable). Different GL treatment; **CA-signed codes only**, do not invent.
2. **`ExpiryClaim` is a new lightweight document type** — it exists *before* the supplier
   acknowledges. States: `raised → accepted → credited`. When the supplier issues credit it **links
   to** a purchase return / purchase CN; it is not a CN-with-extra-status. Unclaimed claim value
   posts a B-05 row.
3. **Drug licence** numbers on the company and on the invoice. v1 covers **the beachhead's state +
   Maharashtra**; the invoice PDF gets **one conditionally-rendered block** (both parties' licence
   numbers), not template variants.
4. **Schedule-H / H1 register:** v1 ships the **union superset** of columns that Maharashtra + the
   beachhead's state require, filtered/labelled per state. The column list is a **charter deliverable**
   signed by the customer's CA / drug-licence consultant. Export.

### Tests

- Breakage return quarantines stock (not saleable) and posts the breakage GL, not a normal return.
- `ExpiryClaim`: raise → accept → link to a supplier CN → reconciles; unclaimed value shows in B-05.
- Schedule-H register export contains the charter-signed columns for a sample month.

### DoD

- [ ] A pharma distributor runs expiry claims against principals end to end, with unclaimed ₹ in B-05.
- [ ] Breakage vs saleable returns post differently and correctly (CA-signed codes).
- [ ] Schedule-H register export exists with the charter-signed column list.

### Out of scope

E-pharmacy / delivery; prescription image capture; NPPA price-ceiling enforcement; a generic
all-India register (charter picks the states).

### Rollback

`ENABLE_PHARMA` flag, default off. Register nav + claim workflow hidden.

### Agent prompt

```
Implement M-03 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Pharma money cycle on shipped batch/expiry: saleable vs breakage returns (CA-signed GL), a new
lightweight ExpiryClaim doc type (raised/accepted/credited, links to a supplier CN) with unclaimed
value in B-05, one conditional drug-licence block on the invoice (beachhead state + MH), Schedule-H
register export with the charter-signed columns. Do not rebuild batch/FEFO. ENABLE_PHARMA off.
Pharma charter required. Stop at DoD.
```

---

## M-04 — Distributor / pharma control dashboard

| | |
|---|---|
| Effort | 2–3 weeks |
| GATE | Wave M charter · after M-01 (+ M-03 if pharma) |

### Verify first

M-01's `SchemeLedger` and (pharma) M-03's `ExpiryClaim` are the data sources. This ticket is a
read-only aggregation view + B-05 emitters — no new write model.

### Files

- `backend/schemes/reports.py` / `backend/pharma/reports.py` — aggregation queries (company-scoped)
- FE: one dashboard route; deep links into M-01 / M-03 / purchases
- B-05 emitter for threshold crossings

### Steps

1. **Primary vs secondary sales — v1 simple definition:** primary = purchases from suppliers tagged
   `is_principal`; secondary = sales. **No principal-SKU mapping in v1** — the number is "purchases
   from principals", labelled as such, not "matched primary". State the limitation on the screen.
2. Scheme liability outstanding (earned-but-unsettled QPS from the `SchemeLedger`).
3. Claim receivables from principals (M-03 `ExpiryClaim` + scheme claims) — aged buckets.
4. **Fill rate = ordered qty vs invoiced qty** (not delivered — challan is optional), rolling
   **28-day window**, per party per SKU.
5. Every tile is a deep link; every ₹ figure posts a B-05 `AttentionRow` when it crosses a
   company-configured threshold.

### Tests

- Aggregates reconcile to `SchemeLedger` totals and `ExpiryClaim` totals on a fixture.
- Fill rate on a fixture with partial invoicing computes ordered-vs-invoiced over 28 days.
- A threshold crossing emits exactly one B-05 row with the shared contract shape.

### DoD

- [ ] One screen: primary/secondary (labelled "purchases from principals"), scheme liability, aged
      claim receivables, fill rate.
- [ ] Figures reconcile to M-01 `SchemeLedger` and M-03 `ExpiryClaim`.
- [ ] Threshold crossings emit valid B-05 rows.

### Out of scope

Principal-SKU mapping; delivered-qty fill rate (needs mandatory challans); forecasting.

### Rollback

Dashboard route behind `ENABLE_SCHEMES` (distributor) / `ENABLE_PHARMA` (pharma). No data model to revert.

### Agent prompt

```
Implement M-04 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Read-only control dashboard: purchases-from-principals vs sales (labelled, no SKU mapping v1), scheme
liability, aged claim receivables, ordered-vs-invoiced fill rate over 28 days. Deep links; threshold
crossings emit B-05 rows (shared contract). Reconciles to M-01 SchemeLedger + M-03 ExpiryClaim.
Charter required. Stop at DoD.
```

---

# Wave N — Platform (sell it without hand-holding)

**Gate:** manual provisioning has become a measurable support cost — the founder is hand-toggling
`Plan.modules` / feature flags for customers more than ~2×/week (the founder measures this; no
instrumentation needed), **or** an integration partner has asked for an API in writing (a single
`charters/demand-log.md` row is sufficient).

**Competitive role:** Zoho's real moat is not features, it is the ecosystem around Zoho Books. This
wave is the smallest credible version: a versioned API, webhooks, self-serve billing, a connector
registry — so BizBoard scales past what one founder can onboard.

---

## N-01 — Public REST API v1 (`/ext/v1/`)

| | |
|---|---|
| Effort | 5–7 weeks |
| GATE | Wave N gate |

### Verify first

`backend/core/throttles.py` exists. The **internal** API is already `/api/v1/` — the public API must
**not** collide with it. There is **no** API-token model and **no** public router today. Public API
needs its own auth, its own namespace (`/ext/v1/`, or an `api.` subdomain if infra allows), and a
stable contract.

### Files

- `backend/api_public/` (new) — **`/ext/v1/`** router, versioned serializers (decoupled from internal ones)
- `backend/api_public/auth.py` — `ApiToken` model (company-scoped, hashed, scoped `read` / `write` per resource, `revoked_at`, `last_used_at`)
- `backend/api_public/openapi.py` — generated spec; a public docs page
- `backend/core/throttles.py` — per-token rate limits

### Steps

1. `ApiToken` — created by an Owner in Settings, shown once, hashed at rest, company-scoped, resource
   scopes. No token = no access; a revoked token 401s immediately.
2. v1 resources: customers, suppliers, items, invoices (**read + create-draft only**), payments
   (read), stock (read), **GST status (read)** = GSTR **period status** (open/filed) + **IRN status
   per invoice**. **NOT** IMS actions (mid-workflow, sensitive).
3. **No programmatic Complete in v1.** The public API creates drafts, full stop; a human completes
   in-app. (A future `invoice:complete` scope is its own charter, not v1.)
4. Versioned serializers — never reuse internal serializers; an internal field rename must not change
   `/ext/v1/`.
5. Rate limits per token; `429` + `Retry-After`; quotas per plan tier (N-03).
6. Every write idempotent on an `Idempotency-Key` header (reuse the existing pattern).
7. Tenant isolation: a token only ever sees its own company. Cross-token isolation test.
8. OpenAPI spec + static docs page + changelog; `Sunset` + `Deprecation` headers on anything retired
   (rule 23: ≥ 180 days).

### Tests

- Revoked token → 401. Wrong-company id in a path → 404, never another tenant's row.
- `read`-scoped token cannot POST. Rate limit trips at the documented number with `Retry-After`.
- Same `Idempotency-Key` twice → one draft. No endpoint completes or pays.
- An internal serializer field rename does not change the `/ext/v1/` response (contract test).

### DoD

- [ ] An external developer creates a token, lists customers, creates a draft invoice, hits a rate
      limit — all from docs alone.
- [ ] No public endpoint completes an invoice or moves money.
- [ ] v1 contract pinned by tests independent of internal serializers.

### Out of scope

GraphQL; bulk import (that is D-02 / P-05); partner OAuth (N-04); programmatic Complete.

### Rollback

`ENABLE_PUBLIC_API` flag, default off. Router not mounted when off.

### Agent prompt

```
Implement N-01 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Public /ext/v1/ (NOT /api/v1/): company-scoped hashed ApiToken with read/write scopes, versioned
serializers decoupled from internal, create-draft-only (NO programmatic Complete), GST status = GSTR
period + IRN status only (no IMS), per-token rate limits, Idempotency-Key, cross-token isolation test,
OpenAPI + docs + Sunset policy. ENABLE_PUBLIC_API off. Stop at DoD.
```

---

## N-02 — Outbound webhooks

| | |
|---|---|
| Effort | 3–4 weeks |
| GATE | Wave N gate · after N-01 (shares the token / company model) |

### Verify first

No outbound webhook infrastructure exists — GSP / Razorpay / WABA code is all *inbound*. Greenfield;
build it once, properly, with a dead-letter queue.

### Files

- `backend/webhooks/` (new) — `WebhookEndpoint` (company, url, secret, events[], active), `WebhookDelivery` (attempt log, status, next_retry_at)
- `backend/webhooks/tasks.py` — Celery delivery with exponential backoff + DLQ
- event emitters at the source (invoice completed, payment received, IMS action needed, stock low, …)

### Steps

1. Event catalog — a fixed, documented list. Each event has a stable JSON schema, versioned with the
   API (N-01 rules).
2. Per-company endpoints subscribe to a subset. Payload signed (HMAC over body + timestamp);
   documented verification recipe.
3. Delivery: at-least-once, exponential backoff (1m, 5m, 30m, 2h, 12h), then dead-letter with an
   Owner-visible failure list and a manual replay button.
4. Never block the originating transaction — enqueue **after commit**.
5. Redact: no bank account numbers, no full card data, no GSTIN of *other* parties beyond what the
   subscriber already sees in-app.

### Tests

- Endpoint 500s 4× then 200s → delivered; attempt log shows the retries.
- Endpoint permanently down → dead-letter after the last attempt; replay works after recovery.
- Signature verifies with the documented recipe; a tampered body fails.
- Completing an invoice does not wait on webhook delivery (after-commit enqueue).

### DoD

- [ ] A subscriber receives `invoice.completed` within seconds, signed, verifiable.
- [ ] A failing endpoint dead-letters and can be replayed; the transaction is never blocked.

### Out of scope

Inbound webhooks from third parties; a webhook-driven automation builder.

### Rollback

`ENABLE_WEBHOOKS` flag. Emitters no-op when off.

### Agent prompt

```
Implement N-02 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Outbound webhooks: fixed versioned event catalog, per-company signed endpoints, at-least-once
delivery with exponential backoff + dead-letter + manual replay, after-commit enqueue, redaction.
ENABLE_WEBHOOKS off. Stop at DoD.
```

---

## N-03 — Self-serve billing and entitlement maturity

| | |
|---|---|
| Effort | 4–6 weeks |
| GATE | Wave N gate **AND** — external prerequisite — BizBoard operates as a registered GST supplier: a registered legal entity, GST registration, SaaS HSN/SAC (likely 997331), place-of-supply logic, and e-invoice-threshold handling **signed off by a CA**. **BLOCKED until that exists.** Interim SaaS billing runs through the payment provider's own invoicing (Razorpay/Stripe issues the invoice). |
| Builds on | E-00 (`Plan.modules` enforced), `billing.Plan` / `billing.Subscription` exist |

### Verify first

E-00 made `Plan.modules` the entitlement authority. `billing/` has `Plan` (slug, `modules` JSON) and
`Subscription`. Plan changes are manual today. This makes them self-serve, metered, and dunned — for
BizBoard's own SaaS revenue, on the Razorpay integration the product already has.

### Files

- `backend/billing/services.py` — plan change with proration, seat counting, usage metering
- `backend/billing/models.py` — **`SaasInvoice`** (BizBoard → customer; **separate model**, never `SalesInvoice`), supplier GSTIN from `settings.BIZBOARD_GSTIN`
- `backend/billing/dunning.py` — SaaS subscription dunning
- FE: Settings → Plan & billing (compare tiers, upgrade/downgrade, payment method, invoices)

### Steps

1. Published tiers with **published limits** (companies, seats, API calls/mo, WhatsApp templates,
   modules). The limit is visible before it is hit — no surprise gating.
2. Self-serve upgrade / downgrade with proration; a downgrade that would exceed the new tier's limits
   is blocked with the specific reason (which users / companies / data to remove first).
3. **Seat count = active `CompanyUser` rows** (`is_active=True`); pending invites and blocked users do
   not count. **Per membership** for a multi-company CA — each company pays for its own members. A
   practice bundle is an R-wave / F-06 concern, not N-03 v1.
4. Usage metering for metered items (API, WhatsApp): Owner-visible meter, soft cap → hard cap.
5. **Dunning → free floor.** Failed renewal → retries → grace period → lock premium. **Free floor
   stays on:** invoicing + stock + customers/suppliers. **Locked:** books, AI, B-03/IMS, schemes,
   public API, webhooks. **A customer's own configured GSP stays up** — do not break their legal
   compliance over a billing dispute; BizBoard-provided GSP credits pause. **Data is never deleted**,
   retained per X-02 DPDP policy, and **always exportable (O-04, rule 28) even while premium is
   locked.**
6. GST-valid `SaasInvoice` from BizBoard to the customer.

### Tests

- Upgrade mid-cycle prorates; downgrade over-limit is blocked with the specific reason.
- Seat count tracks `CompanyUser` add/remove; pending invites excluded.
- Failed renewal → grace → premium locks; invoicing + a customer-configured GSP still work; no data
  deleted; export still works.
- A `SaasInvoice` is a valid GST invoice.

### DoD

- [ ] A customer upgrades, downgrades, and updates their card without contacting support.
- [ ] Limits visible before they bite; non-payment locks premium, never data, and never export.
- [ ] E-00 `Plan.modules` remains the single entitlement authority.

### Out of scope

Partner / reseller billing; multi-currency SaaS pricing; annual-contract paperwork.

### Rollback

`ENABLE_SELF_SERVE_BILLING` flag → falls back to manual `Plan` assignment (E-00 behaviour).

### Agent prompt

```
Implement N-03 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Self-serve SaaS billing on billing.Plan/Subscription + E-00: published tiers/limits, self-serve
up/downgrade with proration + over-limit block, seat = active CompanyUser (per membership), usage
metering, dunning -> free floor (invoicing/stock/parties on; books/AI/B-03/schemes/API/webhooks
locked; customer's own GSP stays up; data never deleted; export always works). SaasInvoice is a
separate GST-valid model. BLOCKED until BizBoard is a CA-signed GST supplier. ENABLE_SELF_SERVE_BILLING
off. Stop at DoD.
```

---

## N-04 — Connector marketplace scaffold

| | |
|---|---|
| Effort | 3–4 weeks |
| GATE | Wave N gate · after N-01 + N-02 |

### Verify first

No connector registry exists. The GSP-credential pattern (Owner-approved encrypted config, fail-closed)
is the model to mirror. "Thin" first connectors mean **CSV/XLSX download only** until a real OAuth
app charter exists.

### Files

- `backend/connectors/` (new) — registry (`id`, `name`, `scopes`, `config_schema`, `fail_closed`, first/third-party), OAuth app model
- FE: Settings → Connectors (list, configure, run, revoke)

### Steps

1. Registry: each connector declares its shape and `fail_closed` behaviour.
2. OAuth app model so a third party can request scoped access to a company (Owner approves, like a
   GSP credential).
3. Every connector runs **fail-closed**: missing / invalid config → off and says so, never a silent
   partial.
4. First connectors (**thin**):
   - **Report export** — CSV/XLSX download for the reports that still lack it (no Google OAuth; a real
     Google Sheets connector with a Cloud project + `spreadsheets` scope + a Google DPA is **its own
     charter**).
   - **Webhook recipe** — "push completed invoices to an outbound webhook" (reuses N-02).
   - **Razorpay settlement pull** — the daily settlement report (which captures batched into which
     bank credit, minus MDR) for bank reconciliation. **Complementary to the existing payment
     webhooks, not a replacement.** Low priority — build only if a customer asks for settlement recon.
5. Connector failures never block a billing Complete (same rule as GSP adapters).

### Tests

- A connector can be listed, configured by an Owner, run, and revoked.
- A misconfigured connector is visibly off, not silently broken.
- Killing a connector mid-run does not block or corrupt a Complete.

### DoD

- [ ] Registry + Owner-approved OAuth app model; every connector fail-closed.
- [ ] Three thin connectors work (CSV export, webhook recipe, settlement pull).
- [ ] No connector failure blocks Complete.

### Out of scope

A real Google Sheets OAuth connector (own charter); an app store / third-party publishing flow;
inbound sync.

### Rollback

`ENABLE_CONNECTORS` flag, default off. Registry hidden; no emitters.

### Agent prompt

```
Implement N-04 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Connector registry + Owner-approved OAuth app model, fail-closed per connector, three THIN connectors
(CSV/XLSX report export — no Google OAuth; webhook recipe; Razorpay settlement pull — complementary,
low priority). No connector failure blocks Complete. ENABLE_CONNECTORS off. Stop at DoD.
```

---

# Wave O — Scale and reliability

**Gate:** a real scale signal — a tenant exceeds ~200,000 invoices/year, **or** report-endpoint p95
exceeds the **frozen SLO budget** (see O-01 step 0) on a production tenant, **or** the DR restore drill
has never been run on a dataset over ~1 GB.

**Competitive role:** "not slow at 50k invoices" was the X-01 bar. This wave is "not slow at 1M, and
provably recoverable" — the thing that keeps a growing customer instead of losing them to Tally's
local-file speed.

**Rule 22 / 27:** none of this changes a number. If a partitioning or replica change alters money
math, tax heads, or a GL posting, it is a bug — stop.

---

## O-01 — Large-tenant data path

| | |
|---|---|
| Effort | 5–8 weeks |
| GATE | Wave O gate |

### Verify first

X-01 built a 50k-invoice soak fixture and a performance budget. If X-01 never ran against a real
production tenant, **that is step 0**: run its harness against the largest real tenant, record the
numbers, and **freeze those as the SLO budget**. No frozen number → O-01 cannot proceed.

### Files

- `backend/core/db_router.py` (new — read-replica routing)
- migrations (partitioning), `backend/*/tasks.py` (rebuild commands)
- reuse X-01's fixture generator, extended

### Steps

1. **Step 0:** freeze the SLO budget from a real tenant (Verify first).
2. **Profile at the gate size (~200k) first** — fix what is actually slow there. **Build a 1M-invoice
   fixture as the DoD ceiling** to prove headroom, but do not engineer for 1M if 200k shows the
   bottleneck is elsewhere. Likely offenders: reports, ledgers, GSTR builders, the B-03 match.
3. Least-invasive fix that works, in order:
   a. missing indexes / query rewrites / `select_related` / materialised summary rows;
   b. FY time-partitioning the append-heavy tables (`StockMovement`, `JournalLine`, invoice lines);
   c. **read-replica routing for reports** — **never for B-03 ITC decisions, GSTR filing builds, or
      period-close** (those read primary). Replica-eligible reads get a **< 5s lag SLO** and a
      "lag over threshold → fall back to primary" rule;
   d. per-tenant schema isolation is **forbidden under this ticket**. If (a)–(c) are exhausted, stop
      and write a standalone ADR for the founder to sign — do not implement (d) here.
4. Whatever is chosen: a rebuild/backfill command, a dry-run on a production clone, and a
   number-for-number reconciliation (TB, GSTR-1 taxable total, stock on-hand, P&L) before and after
   — **plus a CA-reviewed before/after pack** and an automated golden-reconciliation CI test.

### Tests

- Golden reconciliation: TB / GSTR-1 taxable / stock on-hand / P&L byte-identical before and after
  any migration, on the 1M fixture.
- The endpoints that blew the frozen budget now meet it.
- FY-boundary queries still correct after partitioning.
- A replica-eligible read with lag over threshold falls back to primary.

### DoD

- [ ] SLO budget frozen from a real tenant.
- [ ] A 1M-invoice tenant meets the budget on reports, ledgers, GSTR, B-03 match.
- [ ] Every money/stock total byte-identical before/after; CA before/after pack signed.
- [ ] No replica read on B-03 / GSTR-filing / period-close.
- [ ] Tested dry-run + rollback. Option (d) not implemented (ADR if reached).

### Rollback

Each step independently revertible (drop the partition scheme, disable replica routing).

### Agent prompt

```
Implement O-01 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Step 0: freeze the SLO budget from the largest real tenant. Profile at ~200k, prove headroom at 1M.
Fix least-invasive first (indexes/rewrites -> FY partitioning -> replica routing for REPORTS ONLY,
never B-03/GSTR-filing/period-close, <5s lag SLO + primary fallback). Schema isolation forbidden here
— ADR instead. Reconcile every total byte-for-byte + CA before/after pack. Rule 22: no number
changes. Stop at DoD.
```

---

## O-02 — Async / job maturity

| | |
|---|---|
| Effort | 3–4 weeks |
| GATE | Wave O gate |

### Verify first

Celery + beat are in use across `backend/*/tasks.py`. There are no priority lanes and no per-tenant
fairness today — a large backfill can starve foreground work.

### Files

- `backend/core/queues.py` (new — lane definitions), `backend/*/tasks.py` (route to lanes)
- `backend/core/jobstatus.py` (new — Owner-visible job status)

### Steps

1. Priority lanes: **interactive** (PDF for a just-completed invoice) / **batch** (nightly digests,
   GSTR builds) / **bulk** (backfills, imports, O-04 exports). A slow bulk job never starves an
   interactive one.
2. Per-tenant fairness: one large tenant's bulk job cannot monopolise a worker pool.
3. Every task idempotent and safe to retry; poison messages dead-letter **with context**, not
   infinite retry.
4. Owner-visible: "your export is queued / running / done", not a silent wait.
5. Backpressure: queue depth over a threshold → shed the lowest lane and alert (O-03).

### Tests

- A 30-minute bulk backfill does not delay a foreground invoice PDF (measured).
- Two tenants; one floods the bulk lane; the other's interactive jobs still meet SLO.
- A deliberately poisoned task dead-letters with its args + traceback, no retry storm.

### DoD

- [ ] Lanes enforced; a bulk job never starves interactive.
- [ ] One tenant cannot starve others.
- [ ] Every task idempotent; poison messages dead-letter with context; job status visible to Owner.

### Out of scope

Changing money math, tax, or GL; adding a second broker; rewriting Celery itself.

### Rollback

Lane routing behind a setting; default routing = today's single queue.

### Agent prompt

```
Implement O-02 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Job priority lanes (interactive/batch/bulk), per-tenant fairness, idempotent retryable tasks,
poison-message dead-letter with context, Owner-visible job status, queue-depth backpressure -> shed
lowest lane + alert. Rollback = single-queue routing. Stop at DoD.
```

---

## O-03 — Observability SLOs and error budgets

| | |
|---|---|
| Effort | 2–4 weeks |
| GATE | Wave O gate |

### Verify first

`backend/core/metrics.py` + A-08 first-party telemetry exist. No named SLOs, no error budgets, no
tenant-scoped tracing today.

### Files

- `backend/core/metrics.py` (extend — RED metrics per endpoint class, tenant-tagged)
- infra dashboards + alert rules (repo-tracked config)

### Steps

1. RED metrics (rate, errors, duration) per endpoint class, **tenant-tagged**. First-party; no
   third-party APM unless the X-02 DPDP note allows it.
2. Named SLOs — Complete p95, report p95, webhook delivery success %, job lag — each with a number
   (from O-01's frozen budget where applicable). Error budgets; alert on **burn rate**, not single
   spikes.
3. Tenant-scoped tracing so "company X's reports are slow" is answerable from a trace.
4. Capacity dashboard: DB connections, queue depth, worker saturation, storage growth — with
   headroom for the next 2× of growth.

### Tests

- Each SLO renders on a dashboard with its number and a burn-rate alert wired.
- A synthetic slow request for one tenant is attributable to that tenant in a trace.

### DoD

- [ ] Every SLO has a number, a dashboard, and a burn-rate alert.
- [ ] "Tenant X is slow" is answerable from a trace, not guesswork.
- [ ] Capacity dashboard shows 2× headroom.

### Out of scope

Third-party APM unless X-02 allows it; inventing SLO numbers without O-01's frozen budget.

### Rollback

Metrics/dashboards are additive; nothing to revert. Alerts can be silenced individually.

### Agent prompt

```
Implement O-03 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
RED metrics per endpoint class (tenant-tagged, first-party), named SLOs + error budgets + burn-rate
alerts, tenant-scoped tracing, capacity dashboard with 2x headroom. Stop at DoD.
```

---

## O-04 — DR, backup, and always-on data portability

| | |
|---|---|
| Effort | 3–5 weeks |
| GATE | Wave O gate |

### Verify first

`accounts/tenant_backup.py` + restore exist (D-02 hardened them for migration parity). This ticket is
the *disaster* case and the *anti-lock-in* case.

### Files

- infra: PITR configuration (repo-tracked), restore-drill runbook
- `backend/accounts/export.py` (new — full per-tenant export as an async bulk job, O-02 lane)

### Steps

1. **Adopted targets** (not "e.g."): **RPO ≤ 15 minutes** (WAL / PITR), **RTO ≤ 4 hours**. Document
   the actual infra that delivers them; PITR is a line item in hosting cost.
2. **Restore drills** on a schedule, on a real-sized dataset (≥ 1 GB), timed against the RTO. A drill
   that fails or overruns is an incident.
3. **Full per-tenant export**, self-serve, **as an async bulk job** (O-02 lane — never sync HTTP),
   open formats (CSV/JSON + PDFs), covering every model a restore would. One running export per
   company; downloadable via an expiring link. **Always available — including when premium is locked
   or during a billing dispute (rule 28).**
4. Backup covers the same model set restore applies (D-02 parity check stays green at scale).
5. Region / provider failure runbook.

### Tests

- A restore drill on a ≥ 1 GB dataset completes within the RTO (recorded).
- Backup ⊇ restore model set at scale (D-02 parity test).
- A company with premium locked (N-03 dunning) can still run a full export.
- A second concurrent export request for the same company is queued/rejected, not run in parallel.

### DoD

- [ ] RPO ≤ 15 min / RTO ≤ 4 h adopted and backed by real infra.
- [ ] A timed restore drill on ≥ 1 GB met the RTO.
- [ ] Self-serve full export in open formats, async, always available (rule 28).

### Rollback

Export behind `ENABLE_SELF_SERVE_EXPORT` (default on — it is a right, not a feature); PITR config is
infra, reverted via infra.

### Agent prompt

```
Implement O-04 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Adopted RPO <=15min / RTO <=4h backed by infra, scheduled timed restore drills on >=1GB data,
self-serve full per-tenant export as an async bulk job (O-02 lane, open formats, ALWAYS available
incl. when premium is locked — rule 28), D-02 parity at scale, region-failure runbook. Stop at DoD.
```

---

# Wave P — India Stack and compliance completeness

**Supersedes E–L Wave L.** Each item was a one-line stub there; here it is a real ticket — but each
still needs its **own charter** (`charters/P-0x.md`) and **≥ 3 rows in `demand-log.md`** before an
agent starts it (rule 24). Independent; do them in demand order, not list order. When this file is
adopted, E–L's Wave L table gets a one-line "→ moved to WAVES_M_TO_S Wave P".

| ID | Was | One-line scope |
|---|---|---|
| **P-01** | L-01 | Live Account Aggregator bank feed — real FIU, fail-closed without `FIU_BASE_URL`, no prod mocks (GAP-001 rule). Consent flow, DPDP retention. Feeds Phase 3 bank recon + E-04. |
| **P-02** | L-02 | Second live payment gateway (Cashfree / PayU). **W0-03 holding state must apply to the new provider** before any live traffic. Adapter parity tests vs Razorpay. |
| **P-03** | L-03 | GSTR-9 / 9C **filing pack** via GSP. **BLOCKED until the P0 GSP contract exists AND that GSP offers GSTR-9/9C annual endpoints.** Until then it stays a watermarked worksheet (B-02) — no "filed" status, no "we file your GST" claim. |
| **P-04** | L-04 | iOS as a shipping target (A-01 shipped Android only). Capacitor iOS build, Apple review, App Store listing, the data-protection review. Own KYC calendar. |
| **P-05** | L-05 | Busy / Zoho / **Marg** migration adapters on the **same `AccountingMigration` interface** as Tally (D-02). Import once, not live sync. **Marg formats differ** (Marg CSV + a proprietary `.marg` backup) — a Marg-specific parser on the shared interface. Pre-import validation + post-import reconciliation (D-02 step 5) mandatory. Fewer than 3 demand-log rows → stays a manual CSV-mapping exercise. |
| **P-06a** | L-06 | ONDC seller node — own sub-charter, own demand-log ≥ 3. Spike ADR first. |
| **P-06b** | L-06 | DigiLocker — own sub-charter, own demand-log ≥ 3. |
| **P-06c** | L-06 | Aadhaar eSign — own sub-charter, own demand-log ≥ 3. |

### Per-P-item ticket shape (fill on charter)

```
## P-0x — <name>
| Effort | 4–8 weeks | GATE | own charter + demand-log >=3 (P-03 also: named GSP annual product) |
### Verify first   — what exists today (usually a fail-closed adapter or a stub)
### Files          — the adapter, the settings UI, the fail-closed gate
### Steps          — 1) named provider + encrypted creds only  2) fail-closed without config
                     3) the happy path  4) honesty copy (no fake live/filed/sync)
### Tests          — no config -> no live HTTP; sandbox happy path; isolation
### DoD            — real provider works in sandbox+prod config; impossible without named secrets
### Rollback       — ENABLE_<X> flag, default off
```

### Agent prompt (any P-item)

```
If docs/roadmap/charters/P-0x.md is missing, or demand-log has <3 rows for it, or (P-03) no named
GSP annual product exists, reply "BLOCKED - need charter + demand" and stop. Otherwise implement only
that charter's scope using the 0-D + E-L + M-S global contracts. Fail-closed without named provider
secrets. No fake live/filed/sync copy. Stop at DoD.
```

---

# Wave Q — Intelligence GA (on top of reliable data)

**Gate:** O-03 SLOs green (data reliable at scale) **and** F-01/F-02 shipped (assistant honest and
budgeted). AI is Tier 6 for a reason — only as good as the numbers under it.

**Competitive role:** the assistant and the predictions are the "one level up" made conversational —
a *multiplier on a working loop*, never the loop itself.

---

## Q-01 — Grounded assistant to GA

| | |
|---|---|
| Effort | 4–6 weeks |
| GATE | Wave Q gate |

### Verify first

`insights/assistant.py` is a tool-calling agent, propose-only for writes, tax-refusing (F-01). This
ticket **hardens it to GA quality — it does not rebuild it.**

### Files

- `backend/insights/assistant.py` (harden), `backend/insights/eval/` (new — fixture + runner)
- CI wiring for the eval gate

### Steps

1. **Eval harness** — a fixture of 30–50 real pilot questions with expected tool calls + expected
   answer shape. **The founder authors the fixture.** A CA reviews the ~10 borderline tax questions
   to confirm refuse-vs-answer-from-report; the "must-refuse" golden answer is the canned refusal
   string. Merge gate: grounded-answer rate ≥ 95% (a money answer without a tool citation fails).
2. Per-tenant tool allowlist, audited; a cross-tenant tool call is impossible and tested.
3. Multi-turn context; "show me the invoices behind that number" drills into the real list.
4. Tax / GSTR-liability / place-of-supply free-text stays refused with the canned redirect (rule 15).
5. Every call metered against the F-02 budget; budget = 0 → assistant off even if the flag is on.

### Tests

- Eval fixture ≥ 95% top-line grounded-answer rate in CI.
- Every "must-refuse" fixture row returns the canned refusal.
- A cross-tenant tool call fails.
- With `ai_monthly_token_budget = 0`, the assistant is off.

### DoD

- [ ] Grounded-answer rate ≥ 95% on the founder-authored fixture; borderline refusals CA-reviewed.
- [ ] Every money answer carries an openable citation; cross-tenant impossible; cost bounded by F-02.

### Out of scope

Rebuilding the agent; new tools beyond what F-wave shipped; voice.

### Rollback

`ai_features_enabled` (existing) — off = today's F-wave assistant.

### Agent prompt

```
Implement Q-01 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Harden the existing assistant to GA: founder-authored eval fixture (CA-reviewed borderline refusals)
gating grounded-answer rate >=95% in CI, per-tenant tool allowlist + isolation test, multi-turn
drill-down, tax refusal, F-02 budget enforcement. Do NOT rebuild the agent. Stop at DoD.
```

---

## Q-02 — Predictive cashflow and collection-rate model

| | |
|---|---|
| Effort | 4–6 weeks |
| GATE | Wave Q gate. Per tenant: ≥ 90 calendar days history AND ≥ 30 completed invoices AND ≥ 10 receipts — otherwise a "limited data" watermark that **clears automatically** once all three pass. |

### Verify first

`insights/services.py` has `build_growth_hints` + a health score; the historical Phase 6 / E–L F-wave
plan has a cashflow forecast. **Q-02 hardens whatever F-wave shipped** and adds the collection-rate
model + confidence bands + thin-data watermark + B-05 feed. If F-wave cashflow never shipped, Q-02
absorbs it. Not a rebuild.

### Files

- `backend/insights/cashflow.py` (harden or create), `backend/insights/collectionrate.py` (new)

### Steps

1. Collection-rate stats from real payment history — average delay per customer, seasonality.
2. 7 / 14 / 30-day cashflow projection from open AR/AP + historical collection lag. **Confidence
   band, never a single false-precise number.** Relative mode by default (no bank balance);
   optional absolute mode from Owner-entered opening cash.
3. Property test: horizon conservation (30-day total ≈ sum of the three 10-day slices, within band).
4. Thin-data gate (see GATE thresholds) → watermark; clears automatically.
5. Feeds B-05 ("projected shortfall in 12 days — ₹X", shared contract) and the F-04 digest.

### Tests

- Projection with a confidence band; relative mode works with no opening cash.
- A tenant under any one threshold → watermark; crossing all three → watermark clears.
- Horizon-conservation property test green.

### DoD

- [ ] 7/14/30-day projection with a confidence band; relative mode works with no opening cash.
- [ ] Thin data → auto-clearing watermark, not a confident wrong number.
- [ ] Horizon-conservation property test green; feeds B-05 + F-04.

### Out of scope

A rebuild of F-wave cashflow if it exists; ML forecasting (in-process stats only, like Q-03).

### Rollback

Behind `ai_features_enabled` + a `cashflow_prediction` sub-flag; off = F-wave behaviour.

### Agent prompt

```
Implement Q-02 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Harden (not rebuild) F-wave cashflow: collection-rate stats + 7/14/30-day projection with confidence
bands, relative mode default, thin-data watermark (>=90 days AND >=30 invoices AND >=10 receipts;
auto-clears), horizon-conservation property test, feeds B-05 + F-04. Stop at DoD.
```

---

## Q-03 — Anomaly / leakage detection v2 (in-process learned baselines)

| | |
|---|---|
| Effort | 4–6 weeks |
| GATE | Wave Q gate |

### Verify first

B-05 already has deterministic leakage rules. Q-03 adds **per-tenant statistical baselines only —
in-process, no hosted ML, no cross-tenant training, no shared model.** DPDP-clean by construction.

### Files

- `backend/insights/anomaly.py` (new — nightly job computing rolling stats per tenant)
- `backend/insights/models.py` — `AnomalyBaseline`, `AnomalyFeedback`

### Steps

1. Rolling mean / stddev / percentiles per `(tenant, customer, SKU, supplier)`, computed nightly,
   stored **per tenant**. Flags: unusual discount for this customer, price jump vs this supplier's
   history, margin drift on this SKU, duplicate-payment likelihood, round-tripping / circular-trade
   pattern, GST-mismatch clusters.
2. Every flag links to the evidence rows. No flag without a "why".
3. **False-positive feedback is per company** (a business fact, not a user preference), persisted on
   that company's baseline, tuning that company's threshold only. Never crosses tenants.
4. Detection only — surfaced as B-05 rows. Never blocks a transaction, never auto-acts.

### Tests

- A fixture with a 3σ discount for one customer produces a flag with evidence.
- Marking it "not an issue" raises that company's threshold; another company is unaffected.
- No baseline or feedback row is readable across tenants (isolation test).

### DoD

- [ ] Learned flags carry evidence + a per-company false-positive tuning path.
- [ ] In-process stats only; no ML service, no cross-tenant data.
- [ ] B-05 rows only; never blocks or auto-acts.

### Out of scope

Hosted ML / a shared model (separate charter + DPIA); auto-blocking; auto-remediation.

### Rollback

Behind `ai_features_enabled` + an `anomaly_v2` sub-flag; off = B-05 deterministic rules only.

### Agent prompt

```
Implement Q-03 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Per-tenant in-process statistical baselines (nightly) on top of B-05 rules (discount/price/margin
drift, duplicate payment, round-tripping, GST clusters), each with evidence + PER-COMPANY
false-positive tuning. NO hosted ML, NO cross-tenant data. Detection only, B-05 rows only, never
blocks. Stop at DoD.
```

---

## Q-04 — Agentic exception resolution (fills the B-03 form only)

| | |
|---|---|
| Effort | 4–6 weeks |
| GATE | Wave Q gate · after Q-01 + B-03. **If D-04 has not shipped, Q-04 covers only the B-03-exception and A-07-overdue paths** — the missing-document branch is conditional on D-04, not a blocker. |

### Verify first

B-03 has the IMS board + action form; A-07 has overdue invoices; D-04 (if shipped) has the
missing-bill list. Q-04 **pre-fills** those existing forms — it does not build new submission paths.

### Files

- `backend/insights/assistant.py` — a `propose_resolution(exception)` tool
- FE: a "suggested action" panel on the B-03 board / A-07 list (pre-filled, not submitted)

### Steps

1. For a **B-03 exception**: the assistant pre-populates the accept/reject/pending selection **and the
   remark text** in the **existing B-03 form**. It does **not** call the GSP, does **not** create a
   GSP draft, does **not** submit. The human reviews the pre-filled B-03 board and submits via
   **B-03's own flow** (rule 25).
2. For an **A-07 overdue**: pre-fills the supplier/customer WhatsApp message with the exact defect
   (A-06 templates); the human sends.
3. For a **D-04 missing bill** (only if D-04 shipped): pre-fills the request message; the human sends.
4. An audit row per proposal: what the model suggested, what the human did, when.
5. Measure: % of exceptions resolved in one human confirm vs abandoned.

### Tests

- A B-03 `value_mismatch` row → the form is pre-filled with `pending` + a remark; nothing is submitted
  until the human clicks B-03's own submit.
- No GSP call is made by Q-04 under any path (network assertion / mock).
- Every proposal writes an audit row.

### DoD

- [ ] Q-04 only pre-fills existing forms (B-03, A-06 message, D-04 request); it never submits, never
      calls the GSP, never moves money.
- [ ] Every proposal is audited; the human confirms each via the form's own flow.

### Out of scope

Batch auto-confirm; a Q-04-owned submission path; anything D-04-dependent if D-04 has not shipped.

### Rollback

Behind `ai_features_enabled` + an `agentic_suggestions` sub-flag; off = no pre-fill.

### Agent prompt

```
Implement Q-04 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Assistant PRE-FILLS existing forms only: the B-03 accept/reject/pending + remark, the A-06 supplier
message, the D-04 request (if D-04 shipped). It NEVER submits, NEVER calls the GSP, NEVER moves money
— the human submits via each form's own flow. Full audit per proposal. If D-04 is not shipped, skip
that path. Stop at DoD.
```

---

# Wave R — Mid-market and multi-entity

**Gate:** **R-GATE** met (≥ ₹25L MRR OR ≥ 100 paying companies + one named mid-market reference
customer) **AND** N-03 shipped (a mid-market customer is a paid plan, not a hand-toggle) **AND** I-01
branch model shipped in production **AND** a mid-market charter with a named customer.

**Competitive role:** one notch up from the shop ICP toward businesses that currently need Tally + a
consultant — without becoming an ERP (no manufacturing, no full HR).

---

## R-01 — Multi-branch consolidation

| | |
|---|---|
| Effort | 3–5 weeks |
| GATE | Wave R gate · after I-01 in production |

### Verify first

I-01 added `Branch` as an **org/filing dimension referencing `CompanyGstin`**, with `branch_id` on
documents as **reporting-only**, stock still `(company, warehouse, product)` (contract rule 14). A
branch-to-branch stock transfer is a **stock move only** — it posts no AR/AP. So **R-01 has no GL
elimination to do**; summing branch-tagged P&L/BS lines is the whole job. (GL elimination between
*real companies* is R-02.)

### Files

- `backend/accounting/consolidation.py` (new — sum branch-tagged lines; no new model)
- FE: branch P&L/BS, branch comparison

### Steps

1. Branch-level P&L and Balance Sheet from the existing `branch_id` stamp on documents / journal
   lines.
2. Company-level view = **sum of branches**. No inter-branch elimination needed — transfers are
   stock-only and post no GL. (If R-02 inter-company invoices exist, their elimination is R-02's job.)
3. Branch comparison view; a branch metric crossing a threshold emits a B-05 row ("Branch B margin
   down 4 pts").
4. GSTR stays keyed by the stamped `CompanyGstin` (W0-02), never by branch name (contract rule 14).

### Tests

- Branch P&L lines sum to the company P&L (no double-count, no gap).
- A branch-to-branch transfer changes neither company-level P&L nor GSTR.
- GSTR output is byte-identical with and without branch tagging.

### DoD

- [ ] Branch P&L/BS + a company view that is the exact sum of branches.
- [ ] Branch transfers are stock-only; no GL elimination logic exists in this ticket.
- [ ] GSTR unchanged — still `CompanyGstin`-keyed.

### Out of scope

Inter-*company* elimination (R-02); a `Group` / holding entity; branch-level tax filing.

### Rollback

Consolidation view behind `ENABLE_BRANCH_CONSOLIDATION`; off = per-branch reports only (I-01).

### Agent prompt

```
Implement R-01 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Branch P&L/BS from the I-01 branch_id stamp; company view = exact sum of branches (NO elimination —
branch transfers are stock-only and post no GL); branch comparison + B-05 feed. GSTR stays
CompanyGstin-keyed; do not re-key stock or add Branch.gstin. Charter required. Stop at DoD.
```

---

## R-02 — Inter-company transactions

| | |
|---|---|
| Effort | 3–5 weeks |
| GATE | Wave R gate · needs D-01 multi-company in production |

### Verify first

D-01 memberships let one login administer several companies. **v1 has no `Group` / holding entity** —
the mirror is a convenience between companies one person controls, with an explicit per-transaction
opt-in. A real group-consolidation entity is a later charter.

### Files

- `backend/accounting/intercompany.py` (new — mirror + reconciliation)
- FE: "mirror to company B" action on a completed sale; an inter-company reconciliation report

### Steps

1. One group company (A) sells to another (B) — **both administered by the same login**. On explicit
   per-transaction confirm, A's sales invoice **mirrors** as a **DRAFT purchase in B**.
2. Mirror **copies A's invoice lines** (qty, rate, tax) as B's draft purchase; B's user then adjusts
   landed cost / expense heads before completing. **Tax is re-evaluated against B's GSTIN and B's
   RCM / registration state** — never blindly copied from A (B's state may differ).
3. Reconciliation report: inter-company balances between A and B must agree; a mismatch is a B-05 row.
4. The cross-tenant write is explicit, scoped, and audited (F-06-style aggregation rules) — never
   silent.

### Tests

- An inter-company sale mirrors as a DRAFT purchase in B on confirm; B in a different state gets B's
  tax treatment, not A's.
- Inter-company balances reconcile on a fixture; an injected mismatch surfaces in B-05.
- A user who administers A but not B cannot trigger the mirror into B.

### DoD

- [ ] Mirror is per-transaction opt-in, same-admin only, explicit + scoped + audited.
- [ ] B's purchase uses B's tax treatment; A's lines are copied, not A's tax.
- [ ] Inter-company balances reconcile; mismatches surface in B-05.

### Out of scope

A `Group` / holding-company model; automatic mirroring; consolidated group financial statements
(later charter).

### Rollback

`ENABLE_INTERCOMPANY` flag, default off. Mirror action hidden.

### Agent prompt

```
Implement R-02 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Inter-company: sale in A mirrors as a DRAFT purchase in B (same-admin login only, per-transaction
opt-in, explicit + scoped + audited). Copy A's lines; RE-EVALUATE tax for B's GSTIN/state. No Group
entity in v1. Inter-company balance reconciliation with mismatches in B-05. ENABLE_INTERCOMPANY off.
Charter required. Stop at DoD.
```

---

## R-03 — Budgets vs actuals

| | |
|---|---|
| Effort | 3–4 weeks |
| GATE | Wave R gate |

### Verify first

Cost centres exist (roadmap §0.4). Branches come from I-01. This ticket adds a budget model + a
variance report — no change to posting.

### Files

- `backend/accounting/models.py` — `Budget`, `BudgetLine` (account / cost-centre / branch / period)
- FE: budget entry; actual-vs-budget-vs-prior-year variance report

### Steps

1. Budget per account / cost centre / branch / period.
2. Actual vs budget vs prior-year, variance %, drill-down to the transactions.
3. A threshold breach emits a B-05 row ("Marketing spend 140% of budget, ₹X over").

### Tests

- A fixture budget + actuals produces the correct variance % and drill-down list.
- A breach emits exactly one B-05 row (shared contract).

### DoD

- [ ] Budgets by account/cost-centre/branch/period; variance view with drill-down.
- [ ] Breaches post to B-05.

### Out of scope

Rolling forecasts; budget approval workflow (use R-04 if needed); driver-based budgeting.

### Rollback

`ENABLE_BUDGETS` flag, default off. Nav + report hidden; model retained.

### Agent prompt

```
Implement R-03 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Budget/BudgetLine per account/cost-centre/branch/period; actual-vs-budget-vs-prior-year variance with
drill-down; threshold breach -> B-05 row. ENABLE_BUDGETS off. Charter required. Stop at DoD.
```

---

## R-04 — Approval workflows (maker-checker)

| | |
|---|---|
| Effort | 3–4 weeks |
| GATE | Wave R gate · after D-03 audit trail |

### Verify first

`CompanyUser` has capability flags (`can_*`). D-03 has the audit trail. Period-lock overrides already
need Owner + reason (E-03 / D-03). This generalises that pattern with a **new `can_approve`
capability bit** + per-rule approver assignment (not Owner-only — a mid-market business has a finance
manager who approves).

### Files

- `backend/core/approvals.py` (new — `ApprovalRule`, `ApprovalRequest`)
- `backend/accounts/models.py` — `CompanyUser.can_approve`
- hook points in PO / journal / supplier-payment / non-POS credit-note complete paths
- FE: approver queue; maker status view

### Steps

1. Configurable rules: a **PO / journal voucher / supplier payment / non-POS credit note** above ₹X,
   or a discount above Y%, requires a `can_approve` user's approval before it posts.
2. **POS is exempt** — the counter's ≤ 8-tap Complete never waits on approval.
3. The pending item is visible to approvers (and in B-05); the maker sees its status.
4. Every approval / rejection is a D-03 audit row — who, when, note.

### Tests

- A PO over the threshold routes to the approver queue and does not post until approved.
- A POS sale over the same rupee amount posts immediately (POS exempt).
- Approve / reject each write a D-03 row; the maker sees the status change.

### DoD

- [ ] A configurable threshold routes PO/journal/payment/non-POS CN to a `can_approve` checker before
      posting; POS is exempt.
- [ ] Approvals/rejections audited via D-03; maker sees status; approvers see the queue.

### Out of scope

Multi-step approval chains; POS approvals; approval on sales invoices (POS/counter speed wins).

### Rollback

`ENABLE_APPROVALS` flag, default off. No rules → today's behaviour.

### Agent prompt

```
Implement R-04 from docs/roadmap/WAVES_M_TO_S_CURSOR_IMPLEMENTATION_PLAN.md.
Maker-checker: new can_approve capability bit + configurable thresholds (amount / discount %) routing
PO / journal / supplier payment / non-POS credit note to a checker before posting. POS EXEMPT.
Pending queue for approvers + B-05; every decision audited via D-03. ENABLE_APPROVALS off. Charter
required. Stop at DoD.
```

---

# Wave S — Adjacent / international (NOT scheduled)

No tickets, on purpose. It exists so nobody treats its absence as an oversight.

**Do not start any of this until S-GATE is demonstrably true:** ≥ ₹1 crore MRR OR ≥ 500 paying
companies, with the M-wave moat live and O-wave scale proven — and even then only against a written
market-entry charter. S gets its own plan file.

| Candidate | Plausible later because | Not now because |
|---|---|---|
| GCC VAT (UAE / KSA) e-invoicing | Same compliance-forcing-function playbook; large Indian-diaspora SMB base | Different tax engine, portal, language — a second product |
| SE Asia e-invoicing (Malaysia MyInvois, Philippines) | Rolling mandates mirror India's 2020–26 arc | No distribution, no local entity, no support |
| Vertical spin-outs (pharma-only, distributor-only) | The M-wave moat could stand alone | Splits a solo team's focus; revisit at scale |
| Embedded finance (lending on BizBoard's ledger / GST data) | The data asset is real; NBFC partnerships exist | Regulatory weight; needs a partner and a compliance function |

---

## What stays frozen through M–S

Carried from `FUTURE_ROADMAP` §0.3 and the 0–D / E–L freeze lists. M–S does **not** unfreeze these:

- Manufacturing / MES beyond E–L K-01 enablement UAT (no MRP, no planning, no shop-floor scheduling).
- Full HR / statutory payroll beyond E–L Wave J charters.
- Full CRM beyond E–L K-02 lead→invoice convert.
- Generic AI chatbot / "AI accountant" positioning — the assistant stays propose-only and grounded.
- Live two-way Tally sync — import/migrate-once only (D-02, P-05).
- Any "we file your GST" claim without a GSP contract + CA sign-off (P-03 is BLOCKED on exactly this).
- A large custom-report / dashboard-builder library — B-05 is the answer to "where's my data".

**Why Wave M is not a breach of this.** The line is **depth within the billing/GST/stock loop vs
breadth into a new domain.** Schemes = pricing on an invoice (billing). Field order-taking = sales.
The pharma register = a compliance report on stock you already track. None adds a new domain. MES is
production planning / BOM explosion / work-order scheduling — *making* things, a genuinely different
domain. Payroll is HR. Wave M is "the billing/GST/stock product, deep enough that one vertical will
not leave" — not an ERP.

---

## Wave exits (measurable)

| Wave | Exit (all must be true) |
|---|---|
| **M (distributor charter)** | The named distributor runs a full month: scheme-heavy invoices match the charter's golden Marg fixtures to the paisa; QPS ledger + settlement CN reconcile; field staff flush a route to DRAFT SOs offline with zero lost orders. `ENABLE_SCHEMES` / `ENABLE_FIELD_SALES` **off** in demo. CA has signed the scheme GL codes. |
| **M (pharma charter)** | The named pharma distributor runs a full month: schemes reconcile (M-01); expiry claims run raise→accept→credit end to end with unclaimed ₹ in B-05; Schedule-H register exports the charter-signed columns. `ENABLE_SCHEMES` / `ENABLE_PHARMA` **off** in demo. |
| **N** | An external developer builds a working integration from the `/ext/v1/` docs alone (token → draft invoice → webhook). A customer upgrades/downgrades their plan with no support contact; non-payment locks premium, never data or export. BizBoard issues a GST-valid `SaasInvoice`. Every connector fail-closed. |
| **O** | SLO budget frozen from a real tenant. A 1M-invoice tenant meets it on reports/ledgers/GSTR/B-03. A timed restore drill on ≥ 1 GB met RTO ≤ 4 h. Self-serve full export works, incl. when premium is locked. No money/stock total changed (CA before/after pack signed). |
| **P** | Each shipped P-item works against its **real** provider in sandbox + prod config, is impossible without named secrets, carries no fake live/filed/sync copy. P-03 stays a watermarked worksheet until a named GSP annual product exists. |
| **Q** | Assistant grounded-answer rate ≥ 95% on the founder-authored fixture; borderline refusals CA-reviewed; tax refused; cross-tenant impossible; cost bounded by F-02. Cashflow projection ships with confidence bands + an auto-clearing thin-data watermark. Q-03 is in-process only. Q-04 never submits / never calls the GSP. |
| **R** | R-GATE met. A mid-market customer on a paid N-03 plan runs branch consolidation (exact sum of branches, no elimination logic); GSTR still `CompanyGstin`-keyed; inter-company mirror re-evaluates B's tax; approvals route (POS exempt) and audit via D-03. |
| **S** | — (not scheduled) |

---

## Progress log (this file — humans only)

Agents append `docs/roadmap/ticket-logs/<ID>.md`. Integrator: `docs/roadmap/ticket-logs/INTEGRATOR.md`.

| Date | Note |
|---|---|
| 2026-08-30 | Waves M–S authored. Direction document; every wave gated on a customer/revenue milestone, not a date. |
| 2026-08-31 | rev 2 — applied the pre-implementation Q&A (G-SPINE, MRR-authoritative G-REV, R-GATE, M-01 v1 subset, `/ext/v1/`, Wave P retires L, freeze depth-vs-breadth, `main`). |
| 2026-08-31 | rev 3 — charter stub `WAVE_M_SEGMENT.md`; B-05 AttentionRow frozen in 0–D (canonical); E–L Wave L agent prompt retired → Wave P; 0–D / INTEGRATOR merge target = `main`. |

---

## Cheat sheet

| If the user says | Start |
|---|---|
| Buy-X-get-Y / QPS / free goods / scheme settlement | M-01 (charter + CA codes) |
| Salesman takes orders in the market with no signal | M-02 (charter) — produces DRAFT Sales Orders |
| Expiry claims to the principal / breakage returns / drug licence | M-03 (pharma charter) |
| Distributor primary vs secondary / claim receivables | M-04 (charter) |
| "Do you have an API?" | N-01 — served at `/ext/v1/`, create-draft only |
| Notify my system when an invoice is completed | N-02 |
| Let customers pick their own plan / stop hand-toggling modules | N-03 (needs BizBoard GST registration first) |
| Connect BizBoard to <third-party> | N-04 (thin = CSV) or a P-item |
| Reports are slow on a huge tenant | O-01 (freeze the SLO from a real tenant first) |
| A backfill is blocking invoice PDFs | O-02 |
| "What's our p95 / are we about to run out of capacity" | O-03 |
| "Can we actually restore from backup" / "let me export everything" | O-04 (export always works, even when locked) |
| Live bank feed / gateway 2 / GSTR-9 filing / iOS / Busy or Marg import / ONDC / DigiLocker / eSign | P-01..P-06c (each: own charter + demand-log ≥3; P-03 also needs a named GSP annual product) |
| Make the assistant production-grade | Q-01 |
| Predict my cash next month | Q-02 (harden, not rebuild) |
| "This discount looks wrong for this customer" (learned) | Q-03 (in-process stats only) |
| "Just fix the exception for me" | Q-04 — pre-fills the B-03 form; human submits |
| Branch-wise P&L / consolidation | R-01 (needs I-01; no GL elimination) |
| One group company bills another | R-02 (same-admin only; no Group entity v1) |
| Budget vs actual | R-03 |
| Payments above ₹X need my approval | R-04 (`can_approve` bit; POS exempt) |
| Middle East / SE Asia / spin-out / lending | S — not scheduled; needs S-GATE + its own plan file |
| Manufacturing MRP / full payroll / full CRM / AI accountant / Tally live sync | frozen — see §What stays frozen |
