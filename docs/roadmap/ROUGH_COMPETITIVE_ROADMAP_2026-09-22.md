# BizBoard — rough competitive roadmap

**Superseded for execution by:**
[`COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md`](COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md)
(2026-09-23) — resolves the two open calls below, cross-references what's
already a live ticket elsewhere in `docs/roadmap/`, and turns the rest into
tickets. This file stays as the original strategy note / evidence trail;
the other file is where to look for what to actually build next.

**Status:** rough strategy note, 22 Sep 2026, cross-checked against the full
[Competitive Analysis](../COMPETITIVE_ANALYSIS_BIZBOARD.md) (also 22 Sep
2026). Not a build schedule, not a commitment, and not a replacement for
[FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md](FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md).
Code and tests still decide what exists. Do not make pilot or commercial
claims until `docs/pilot/GO_NO_GO.md` is signed.

**Source:** competitive analysis the same day, plus the market-gap table
(Phases 1–10, feature, flow, category) supplied the same evening.
Principle: a competitor feature is not a BizBoard feature. Sequence is
customer problem, then weekly value, then gap, then fit.

**Evidence tags:** bracketed notes like `[COMP-005]` or `[§15]` point at the
gap-register IDs and section numbers in the full competitive analysis. They
support or qualify a line already decided here — they don't reopen it,
except where marked "tension" below, which is flagged rather than resolved.

**Posture:** operator system for Indian trading and distribution.
GST, payments, and filing are country packs. Own the owner's day.

The market-gap phases are a narrative, not a build calendar. Phase 1 in
that table is the system of record already in the product. Do not reopen
it. The progression we are following:

1. System of record — shipped.
2. System of visibility and action — the near-term list below.
3. System of automation — only the four loops (collect, reorder, route cost, GST warning).
4. System of intelligence — after those loops store outcomes.
5. Business operating system — not a workflow engine. It is those loops as a habit.

---

## Must-have parity

A buyer still finishes the statutory month in Tally until these exist.

- Production GSP for IRN and e-way bills (India pack: GST, e-invoice, e-way, returns). The e-invoice/e-way code is already architecturally complete (adapter pattern for sandbox vs. live GSPs) but sandbox-gated by design — this is a GSP contract and certification step, not new engineering. Partner with a licensed GSP (ClearTax, GSTHero, GSTZen) rather than building GSP infrastructure from scratch; the overhead there is compliance/licensing, not code. [§12, §18, COMP-010]
- CA-readable GSTR pack, with filing due dates on the same screen. GSTR-1 and GSTR-2B builders already exist and are advanced (1,000+ lines covering B2B/B2CL/rate buckets/amendments) but flagged dark by default — this is closer to "turn it on and add due dates" than new construction.
- WhatsApp and email for the invoice PDF and for collection reminders. Vyapar and TallyPrime both ship WhatsApp natively; it's a confirmed India-SMB expectation, not a nice-to-have, and BizBoard's WhatsApp Cloud integration is already listed as a flagged-dark surface. [§12]
- Bank statement import a clerk can finish, then an unmatched queue. The matching engine behind this (scored matching plus a learned payee-memory bonus) is already advanced — the gap here is the import/queue UX, not the matching logic. [§9]
- Tally import with a difference report the CA will sign (masters, opening balances, vouchers, trial balance). BUSY ships a one-way Tally-XML importer; Vyapar ships a one-way Tally export (Gold tier only). Nobody researched has a full two-way, CA-signable migration engine — this reads as parity but is real differentiation against the two India desktop incumbents specifically. [§12, §15 "Migration Engine"]

## Near-term differentiation

The code is closest here, and the value shows up every week.

- Today / Action Center as the home screen, ranked by money. Flow: business data, then the exception, then the amount, then one next action. The morning form is a daily brief: what changed, what is at risk, what to do today. Already the most mature surface in the codebase — dashboard, attention-queue widget, collection-attention card, and a dedicated Insights hub all exist and rate advanced in the audit. This item is mostly "make it the home screen and keep it ranked by money," not new construction.
- Every row names the source documents and the arithmetic. No row that cannot be checked.
- Receivables on that list, then the collections loop: invoice due, reminder, promise date, payment, match. A missed promise comes back onto the list. This matches the rule-based tier of Chaser/Upflow, which is exactly where the analysis says to stop: real ML delinquency prediction (HighRadius-tier "payer rating") needs cross-tenant payment-behaviour data at a scale no single-tenant SMB product has. Building the promise/missed-promise loop and stopping there is the right scope, not a shortfall. [§9 "Category verdict", Appendix A #2]
- Payables due this week on the same list, next to cash on hand. A list, not a second command center and not a forecast.
- Dead stock, overstock, and expiry as rows (quantity, value, age or date). No automatic discount, transfer, or return. Extends the single heuristic "slow/dead stock" alert that already exists today from a basic flag into a real list.
- Replenishment suggestion that shows on hand, velocity, lead time, and safety stock. If another godown has the stock, the row says transfer. A purchase order is created only after the owner approves. This is the most-cited gap in the whole analysis: today's reorder logic is a threshold alert with no suggested quantity, while Cin7 and NetSuite both auto-draft a PO for the owner to review — the same human-approval gate this item already specifies. Sits in the analysis's own "must-have parity" tier; closing it is higher-leverage than most AI feature work. [COMP-002, §7, §18, §20]
- GST guard on save, before the filing week. A mismatch that is saved anyway appears on Today. The single strongest evidence-backed opportunity in the entire analysis. The government's IRP validation rules (GSTIN checksum, HSN/SAC validity, duplicate invoice numbers, active-GSTIN check) are public and documented — this is a rules engine, not ML — and BizBoard originates the invoice data natively, unlike ClearTax/GSTHero, which reconcile against a third-party ledger after the fact. [COMP-006, §15, §18]
- Route completion that asks for the actual fuel and driver cost, then shows trip profit. Planning a route from sales orders is already in. This item is the cost and the result. The other strongest whitespace finding: no route-optimization vendor researched (Onfleet, Circuit, Locus, FarEye) was confirmed to tie route cost back to the margin of what was delivered — one vendor (Mapline) claims "profitability" in marketing copy only, unverified by any case study found. BizBoard already holds both halves (route cost fields, sales-order margin) that pure logistics tools structurally lack. [COMP-005, §15, §18, §21]
- Outcome record for those loops: paid or not, promised date, stockout, and real route cost. This is the gate for every later model. Correct instinct per the moat analysis: BizBoard has no cross-tenant data moat today, only workflow/execution advantages — per-tenant outcome history is the honest foundation for anything later claimed as "predictive," not a shortcut around building it. [§21]

## Medium-term

This is how accountants distribute the product, and how GST stays a country pack.

- One CA login across many companies. Not group consolidation. Not directly covered by the competitive research — flag as a gap in the analysis's own coverage, not a validated call either way. Adjacent, not equivalent: BUSY supports up to 150 companies on its top licence, Zoho uses a "Branches" model for multi-GSTIN — neither was researched deeply enough to compare against a CA-specific multi-company login pattern.
- Bank auto-match only after the match rate is measured. Good instinct, and the analysis backs the caution specifically: Xero's own claimed auto-match rate is inconsistent across its own sources (97% in one place, 80%+ in another), and every vendor's accuracy/automation percentage found across the whole research pass was vendor-reported, not independently audited. Measure before trusting is the right posture here, not excess caution. [§9]
- Cash forecast from open receivables, payables, and expected receipts, only after bank import is trusted. Note: a cashflow forecast already exists in the codebase today — AR-aging-weighted cash-in plus AP-due-date cash-out over 7/14/30/90-day horizons, with an explicit heuristic disclaimer, refreshed daily. This item is about gating it on bank-import trust, not building it from zero.
- Supplier price history (jump and creep), not a reliability score. **Tension, flagged not resolved:** the analysis's own gap register recommends a rule-based supplier reliability scorecard (on-time %, lead-time variance, PO-to-invoice discrepancy) as real whitespace — the category is real and almost entirely absent below enterprise procurement suites. This roadmap narrows that to raw price history with no judged score, which fits the roadmap's broader pattern of showing checkable rows rather than a system that judges ("no row that cannot be checked," "no automatic discount, transfer, or return" above). Both readings agree the underlying PO/GRN/invoice-timestamp data is valuable; they differ on whether to ever present it as a score. Worth a deliberate call, not a default. [COMP-007, §15, §18, Appendix A #6 — see also "Leave off the roadmap" below]
- Customer and product margin already on the bill. Add delivery cost to that margin only after route cost is real. Confirms the analysis's own sequencing — route-cost capture has to exist before route profitability means anything, same order this roadmap already has. [§15]
- Country-pack boundary in the codebase, while still shipping only India. The single highest architectural-priority finding in the whole analysis. GST math today lives in `core/services/billing.py` with an inline India state-code table — not behind a swappable interface. Two reference patterns are worth studying directly before designing the boundary: Dynamics 365 Business Central's base-app-plus-country-extension model, and NetSuite's SuiteTax-engine-plus-country-SuiteApp model. The pattern to avoid is SAP Business One's patch-coupled localization, where GST currency depends on being on the latest patch. [COMP-009, §13, §18]

## Long-term bets

Only after the loops store outcomes (paid or not, promised date, stockout, real route cost).

- Collection and replenishment models trained on promises, receipts, and stockouts. One nuance worth flagging: these are not the same data problem. Per-tenant replenishment/demand forecasting only needs that tenant's own sales history — no cross-tenant data required, which is why the analysis rates it moderate effort. Genuine collections-delinquency prediction (the HighRadius tier) needs behaviour pooled across many customers to be more than a recency heuristic — a harder and different bet. Fine to sequence together since both wait on outcome records existing, but they won't become buildable on the same timeline once that gate clears. [§9 "Category verdict", both categories]
- A second country pack, with a design partner. Do not schedule UAE, UK, or USA packs, multi-currency, or group consolidation before that partner exists. QuickBooks and Xero — far better-resourced than a design-partner-led single-country expansion — still ship as separate, non-migratable country editions rather than one modular multi-country product, and even they lean on a third party (Avalara) for jurisdictions beyond their core one. One country at a time, with a real partner, is the conservative and validated path here, not the compromise one. [§13]
- Assistant that answers from source documents and runs an Attention action only after the user confirms. An AI daily summary comes after the rules-based brief is a habit. Anomaly detection and automatic root-cause are the same bet, not a separate product. This exact design already exists in the codebase, not only as a long-term aspiration: the AI assistant is tool-grounded, refuses tax advice via an explicit pattern match, and requires re-authentication before any money-moving action, with per-company usage metering. It's currently gated behind a view permission and not positioned as a headline feature — the real "long-term bet" here may be adoption and positioning of something already built, not net-new construction; worth checking before scoping it as new work. It's also already more conservative than several 2026 competitor rollouts (QuickBooks' AI Agents, Xero's expanding JAX roadmap) that are still mid-rollout with thin adoption evidence — being behind on marketing an AI feature is not the same as being behind on having one. [§10, Appendix A #12]

## Already in the product — do not schedule again

These are Phase 1, and parts of Phases 3, 6, and 7, in the market-gap table.

- Customers, vendors, items, quotation, sales order, delivery challan, invoice, POS, purchase bill, godown stock, ledgers, GST calculation, registers, roles, and tenant isolation. Worth being precise about "tenant isolation" specifically: today it means application-code `company_id` scoping on every queryset. Postgres row-level security is migration-complete but ships disabled by default — a deliberate, not partial, choice — so the real isolation boundary in production today is the application layer, not the database. Matters if this list is ever used in a security or compliance conversation.
- Credit-limit hold, FEFO and expiry block, payment links, Excel import, basic dashboard
- GSTR worksheets and inward match as reports. The gap is the warning on save and the row on Today, listed above.

## Leave off the roadmap

- Payroll, CRM, and manufacturing MRP. All three already exist as feature-flagged-dark modules in the codebase, not unbuilt — this is a scope decision, not a capability gap, worth knowing if it's ever second-guessed.
- A customer profile product (frequency, margin, payment behaviour as a CRM record). Payment behaviour belongs to the collections loop.
- Supplier reliability scores. See the tension flagged under "supplier price history" above — the analysis's default recommendation was a rule-based scorecard; this roadmap's answer is no, and "price history" without a score is the resolved, narrower form. Flagging the difference rather than silently picking a side.
- A recommendation engine that executes. Suggestions stay on Today until the owner approves.
- Approval center, workflow engine, rules engine, and event engine as platforms. The analysis reached the same conclusion independently, for its own reason: no user-configurable "if X then Y" rule builder exists in the codebase today (only fixed cron jobs and read-only alerts), and a general rule-engine platform rates high effort relative to value at this segment. Odoo's Studio is the one real competitive example done well, and it's gated to Odoo's Enterprise-tier customers with technical or partner support most of BizBoard's buyers won't have. [COMP-008, §18, §20]
- Warehouse task management, pick and pack control tower, vehicle-capacity routing, and live delivery tracking. Consistent with the analysis's own call to partner for route optimization rather than build a solver (Google OR-Tools, Mapbox, and OSRM are the commodity building blocks if this is ever revisited) — "route completion asks for the actual cost" above captures the profitability value without needing the optimization/dispatch stack this line correctly avoids. [§18]
- In-transit warehouse management
- Open API as a public platform. Payment and GSP callbacks that already exist are enough.
- ONDC and marketplace hubs
- Autonomous journals
- A public app store
- Matching Zoho One's suite breadth. Consistent with the analysis's read that BizBoard's actual buyer isn't shopping for platform breadth — Odoo's 80+ apps and Zoho One's 45+ apps are table stakes for a different kind of buyer (technical or partner-backed, or suite-shopping), not this one. [§16 "Avoid"]
- Generic chatbot. If a question cannot point at a document, it does not ship. Independently confirmed: general natural-language chat over business data is now GA and often free at Zoho (Zia), QuickBooks (Intuit Assist), and Xero (JAX) — competing on chat breadth means competing against already-shipped incumbent features. "Must point at a document" is exactly the design difference that makes the existing assistant more defensible than a general chatbot would be. [§10]

## Points from the analysis not yet triaged here

Flagging, not deciding — these are real findings from the 2026-09-22
competitive analysis that don't map cleanly onto any line above.

- **Customer self-service portal.** A confirmed parity gap [COMP-003]: Zoho
  Books (Premium+), Odoo, QuickBooks, and Xero all give a customer a "log in
  and see my invoices" view; BizBoard has only a public pay-link page. Not
  named as must-have, near-term, medium-term, or leave-off above — needs an
  explicit call rather than defaulting by omission.
- **Batch and serial tracking on the same SKU, simultaneously.** Not a
  gap — a confirmed advantage [COMP-011]. Zoho Inventory can only do one or
  the other per item; BizBoard already does both. Worth knowing this is a
  real, checkable differentiator, not just an internal engineering detail.
