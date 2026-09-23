# BizBoard Roadmap — Vision vs. Reality

As of 2026-09-23. Companion doc: [BIZBOARD_OS_VISION_IMPLEMENTATION_PLAN_2026-09-23.md](BIZBOARD_OS_VISION_IMPLEMENTATION_PLAN_2026-09-23.md).

## Executive summary

BizBoard is materially further along the vision's 10-layer architecture than a blank-slate read suggests. Of the 10 layers, six already have real, working foundations in the codebase today — several code-complete and one sign-off away from going live — while the vision's own headline correction (Growth & Sales, "start before the Sales Order") is the single biggest true gap.

Key findings:

- **Layer 7, Business Command Center, is the most mature relative to the vision.** `insights/attention.py` already emits rows shaped almost exactly like the vision's Business Action Object (severity, money impact, reason, recommended action, dedupe, snooze) — missing only explicit owner/due-date assignment.
- **Layers 4–6 and 9 (Inventory, Finance/Cash, Compliance, GST Guard) all shipped real building blocks this same week (2026-09-23)** — replenishment suggestions, route profit, GST Guard checks, supplier price history — behind default-off flags, tested, mostly pending only pilot sign-off.
- **Layer 2, Growth & Sales, is the biggest true gap.** No lead scoring, enrichment, dedup, or assignment exists; the Quotation → SalesOrder → Invoice chain is strong but only starts once a customer already exists.
- **Layers 8 and 10 are appropriately thin** — this matches the vision's own doctrine (don't let an LLM calculate financial truth; require approval before automation) more than it reflects unfinished work.
- **The vision's Part 3 (international architecture — "architect now, don't build now") is already underway.** The India tax-engine seam (`core/services/tax_engine/`) shipped this week with no second country pack yet — exactly the sequencing the vision recommends.

The rest of this doc organizes what's next into: what exists today by layer, natural expansions (extend an existing subsystem), fresh builds (genuinely new), decisions where the vision and the codebase's own scope calls disagree, and a phased sequence.

## What exists today, by layer

| Layer | Vision asks for | What exists today | Status |
| --- | --- | --- | --- |
| 1. Business Foundation | Tenant, users, masters, accounting, GST | `accounts` (User/Company/CompanyUser RBAC/OTP), `masters` (Customer/Supplier/Product/price lists/HSN), `accounting` (GL/periods/cost centers/fixed assets); RLS migration present, disabled by default | Done |
| 2. Growth & Sales | Lead → opportunity → order pipeline | `crm` app: Lead (`NEW` / `CONTACTED` / `QUALIFIED` / `LOST`), LeadActivity, Opportunity (no line items) — no scoring, enrichment, dedup, or assignment; dark by default. Separately, `sales` has a strong Quotation → SalesOrder → Invoice chain, but it starts after a customer already exists | Stub — biggest gap |
| 3. Order-to-Cash | Order → stock → delivery → invoice → collection, exceptions not manual review | Full chain: Quotation, SalesOrder, DeliveryChallan, DeliveryRoute, SalesInvoice, returns/credit notes, POS. Route-profit capture just shipped | Strong |
| 4. Inventory & Procurement | What to buy, when, why | Batch/expiry, FIFO costing, stock transfers, reorder levels; replenishment suggestion with transfer-vs-purchase logic just shipped as a Today-row enrichment, not yet a standalone planning screen | Strong foundation, partial delight feature |
| 5. Finance & Cash | Receivables, payments, reconciliation | Receipts/payments/allocations, gateway integrations (Razorpay live, others sandboxed), scored bank-statement reconciliation with learned payee memory, AR dunning with escalating cadence + risk snapshot | Strong |
| 6. Compliance | GST, e-invoice, e-way, controls | GSTR-1/2B/3B builders, IMS credit-at-risk, rate-exposure scan, TDS/TCS worksheets, e-invoice/e-way adapters (sandboxed pending a licensed GSP contract) | Strong, gated on a contract, not engineering |
| 7. Business Command Center | "What needs my attention today", Business Action Objects | Already close to the exact Business Action Object shape: severity, money impact, reason, action, dedupe, snooze — missing only explicit owner + due-date assignment | Most mature vs. vision |
| 8. Intelligence | Customer/supplier/product/employee analytics | Per-invoice/customer profitability exists; dead-stock and margin-drop are single alert heuristics, not full reports; no supplier reliability scoring (deliberate); no employee analytics | Partial, several deliberate stops |
| 9. Business Brain | Recommendations, decision engine | Cashflow forecast, growth hints, a tool-grounded LLM assistant exist; no ML/optimization layer, no formal event → decision → approval pipeline | Seed only, by design |
| 10. Automation | Approved actions executed automatically | Recurring invoices are draft-only; dunning reminders are opt-in; nothing auto-creates a document | Deliberately minimal |

## Natural expansions — extend, don't rebuild

These reuse a subsystem that already exists — the same pattern the five tickets shipped this week already followed — rather than adding a new one.

1. **Command Center → full Business Action Object.** Add `owner` and `due_date` to Attention rows, extending the existing dismiss/snooze state model rather than building a new workflow engine. Closes the one gap versus the vision's Business Action Object shape.
2. **Collections Intelligence v2.** The dunning system already computes a per-customer risk snapshot and runs an escalating cadence. Extend it into a "usually pays N days late" pattern surfaced as its own Today row and a dedicated collections worklist — a richer read on payment history already captured, no new subsystem.
3. **Inventory Autopilot, full screen.** The replenishment suggestion lives as a Today-row enrichment today. Promote it into a standalone Purchase Planning page listing every product needing reorder company-wide — still owner-approves-and-creates, no auto-PO.
4. **Customer 360.** Compose the existing invoice-profitability service, customer sales report, AR aging, and dunning risk snapshot into one page. Pure aggregation — every input already exists as a service. The predictive-dunning pattern is a later enrichment, not an input this page waits on.
5. **Supplier Intelligence v2.** Lead time and fill rate only. No score, no rank, and no switch-supplier suggestion for this program. A narrative sentence can be a later follow-on.
6. **Route optimization.** `DeliveryRouteStop` has no coordinates, address, or pincode. Customer and Supplier have free-text address and state only (`Company.pincode` is the seller). Clustering waits on a nullable `Customer.pincode` (D3a in the implementation plan). Do not cluster on parsed address text or on state.
7. **GST Guard, go live.** Code-complete and tested. CA sign-off covers the format check that runs today. Active-status stays a no-op until `GSTIN_PROVIDER` is a real GSP. The flag can flip as soon as that sign-off exists.
8. **India tax-engine seam → second country, when there's a customer.** The seam is already built. Adding a country is now "write a new pack module," not "refactor the tax code again."

## Fresh builds needed — no existing scaffolding

1. **Real lead pipeline.** Capture channels (WhatsApp/web form/import/walk-in), qualification, assignment/routing, and a Lead → Opportunity → Quotation link. Today's CRM has none of this beyond a 3-state Lead. This is the vision's own headline correction and the largest true gap in the codebase.
2. **Credit check + margin check as order-time gates.** Today these fire as after-the-fact alerts. The vision's Order-to-Cash Control Tower wants them enforced (or at least flagged) at Sales Order confirmation — a new business rule, not an alert.
3. **Picking/packing states.** Out of this program. The chain still jumps from SalesOrder to DeliveryChallan; that stays until a customer pain is confirmed separately.
4. **Customer action generation.** Churn risk and repeat-order due are in this program, computed from order history. Customer 360 is not a technical prerequisite. Cross-sell, price recommendations, and "customers like my best customers" are out of this program.
5. **"Find customers like my best customers."** Needs customer profiling plus geographic/product-mix similarity matching against external business data. Explicitly a later-wave feature per the vision itself — don't build before the lead pipeline (#1) exists.
6. **Archetype packaging.** The vision's Core + Packs model doesn't exist as a product concept — BizBoard today is one app with roughly 30 independent feature flags, not curated packs with persona-based onboarding. A productization layer on top of the existing flag system, not a rewrite, but genuinely new UX/onboarding work.
7. **Business Brain formalization.** The Event → State → Rules/ML/LLM → Recommend → Approve → Execute → Outcome → Learn pipeline doesn't exist as an explicit architecture. The alerts engine and the LLM assistant are the seed of the rules/LLM layers; the event bus, ML/optimization layer, and outcome-tracking loop are net new. Correctly sequenced last, per the vision's own doctrine.
8. **Multi-currency core, payment abstraction beyond current gateways.** Design target is five roles (base, transaction, customer, supplier, reporting); a first cut would be base, transaction, and reporting. FX gain/loss and further gateways stay "architect for, don't build yet." Sandboxed Cashfree/PayU are not a second live provider.

## Decision points — locked 2026-09-23

Ticket-level consequences are in the implementation plan. Summary:

1. **Supplier scoring.** No score, no rank, no switch-supplier suggestion in this program. Ship lead time and fill rate as two numbers.
2. **Payroll.** Do not touch. Do not put the payroll flag in any pack.
3. **Feature flags vs. packaging.** Packs are named flag bundles plus an onboarding wizard. They do not change billing or entitlement. Entitlement wins over a pack default. The Retail vs Trade flag list is not needed until that ticket starts; the first action then is a proposed split for review.
4. **CRM timing.** Phase C proceeds after Phase B. Dark-by-default is the normal flag convention. C1 (CSV + web form) is in this program; WhatsApp inbound is an optional sub-flag.
5. **Credit at sales-order confirmation.** Hard-block, no override, `credit_limit == 0` means no limit. Exposure at the sales order includes open orders and drafts plus today's posted exposure. Invoice and POS keep today's invoice-time block. Margin reuses the 5% `MARGIN_DROP_SKU` formula and warns only.
6. **Picking/packing, lead scoring, enrichment, price recommendations, lookalike customers.** Out of this program.

## Recommended phased roadmap

### Near-term (0–2 months) — ship what's already built

Everything here is code-complete behind a default-off flag; this phase is sign-off and pilot rollout, not new engineering.

- Instrument the five shipped flags (tenant, flag state, core action) before the pilot watch.
- Flip flags for 1–2 pilot tenants with real volume in that area: supplier price history, replenishment (needs multiple warehouses), route profit (needs live routes), customer portal (retest on a staging copy).
- GST Guard flips when CA sign-off lands on the format check that actually runs. Active-status is a no-op while `GSTIN_PROVIDER` is `"null"`. It does not wait on the other four pilots.

### Next (following quarter) — round out Command Center + Cash

- Business Action Object v2: owner + due date on Attention rows.
- Collections Intelligence v2: predictive "usually pays late" pattern.
- Customer 360 page.
- Inventory Autopilot planning screen.

### Mid-term — close the Growth & Sales gap

- Real lead pipeline: CSV and web form, exact-match dedupe, round-robin to `SALES_STAFF`. WhatsApp inbound is optional. Qualification and `convert_lead()` stay as they are.
- Opportunity → Quotation link: customer pre-fill only, won opportunities, many quotations per opportunity.
- Sales-order confirmation: hard credit block, margin warning. Invoice and POS unchanged.

### Mid-to-long-term — Customer/Supplier Intelligence as action generators

- Customer action generation: churn and repeat-order from order history. Cross-sell and price recommendations stay out.
- Supplier Intelligence v2: lead time and fill rate, no score. Can start without Phase B.
- Customer pincode (nullable, no backfill), then route combine-by-pincode. Advisory only.

### Long-term — Business Brain and packaging

- Formalize the event → decision pipeline only after customer actions have shipped. Approval means assignment. Learning in v1 is a report a person reads.
- Archetype packaging: Retail and single-godown Trade flag bundles plus a wizard. Confirm before any flag change. Entitlement and manual deviations win. Payroll is in no pack. The flag split is drafted for review when that ticket starts, not before.

## What not to build right now

Checked against what's already in the codebase, this confirms alignment with the vision's own exclusion list:

- Generic chatbot — not a risk; the existing assistant is tool-grounded and citation-based, not a general chat surface.
- Full CRM/Salesforce clone — the recommended CRM work above is scoped to lead-to-quotation, not a general CRM platform.
- Deep manufacturing — the manufacturing app stays a BOM/work-order stub, dark. No further investment until Trade/Distribution is proven.
- External lead-discovery scraping/directories — the vision itself says don't build this in v1; nothing here changes that.
- Country expansion before India PMF — matches current state (India-only tax pack, seam ready for later).
- Hundreds of reports — 25+ report pages already exist; resist adding more without a specific action attached.
- Automation without an approval gate — purchase orders, transfers, quotations, and invoices still stop on the owner saving the existing create screen. Lead auto-assignment is allowed: it is reversible routing, not a financial document.

**Payroll** stays inert. It is on the vision's "don't build" list and already exists, dark and minimal. This program does not extend it, remove it, or include it in a pack.

## Architecture-only, no build now — international readiness

The vision's Part 3 says: architect globally, launch locally. BizBoard is already ahead of where most SMB SaaS products are at this stage:

- **Tax engine seam — done.** GST logic has been extracted out of the old monolithic billing module into a `base` / `india` / `registry` structure, with sales and purchase document totals now calling through a `get_tax_engine(company)` lookup. The registry is the only place a second country would ever plug in. No second country pack exists yet — correctly, per the vision's own sequencing.
- **Still architecture-only, not started:** multi-currency core (five roles: base, transaction, customer, supplier, reporting; first cut would be base, transaction, reporting), payment abstraction only after a second live provider, and the country-pack contents the vision describes for a second market. Sandboxed extra gateways do not start that work.
- **Recommendation:** don't start any of the above until there's a concrete non-India pilot. The one thing worth doing now, opportunistically, is keeping new India-specific logic inside the India tax pack rather than letting it leak back into sales/purchase call sites — that discipline is what keeps the seam worth having.

Ticket-level build plans, and the international-readiness design notes, are in Implementation Plan.
