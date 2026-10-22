# Agentic AI — roadmap

**Date:** 2026-10-21. **Status:** PROPOSED. Dates assume work starts 2026-11-02 with one team on agents, and that the founder decisions in section 7 land by 2026-11-13.
**Built from:**
- [AGENTIC_AI_COMPETITIVE_ANALYSIS_2026-10-21.md](AGENTIC_AI_COMPETITIVE_ANALYSIS_2026-10-21.md): why this order.
- [AGENTIC_AI_FEASIBLE_PLAN_2026-10-21.md](AGENTIC_AI_FEASIBLE_PLAN_2026-10-21.md): architecture, autonomy ladder, release gates.

Where this roadmap and section 5 of the feasible plan disagree, this roadmap wins.

**Tags:**
- **[P]** parity: a buyer expects it because competitors ship it.
- **[D]** differentiator: no India-direct rival ships it well.
- **[F]** foundation.

D1–D5 refer to section 5 of the competitive analysis.

---

## 1. Strategy in one paragraph

Ship the agent foundation and a Collections Agent quickly, to reach parity with Zoho, Intuit and Xero, and prove value with one pilot. Then put most of the effort into the two India gaps nobody fills:
- **distributor order intake from WhatsApp, text and photos** (D2);
- **multi-godown inventory risk with transfer suggestions** (D3).

Keep every agent approve-first (D1) and market that against auto-executing rivals. Start the WhatsApp provider track now, because it gates L3 sending and has the longest lead time.

## 2. Timeline at a glance

| Quarter | Phase | Main outcome | Tag |
| --- | --- | --- | --- |
| Nov 2026 | **R0 Gate and decisions** | Branch hygiene, Phase-0 gate for agent-touched flows, provider decisions, pilot picked, baselines started | F |
| Nov–Dec 2026 | **R1 Agent foundation** | `agents/` app, tool registry, runs, proposals, safety suite, admin run log | F |
| Dec 2026–Jan 2027 | **R2 Collections Agent** (pilot 1) | Ranked worklist, Hindi/English drafts, promise tracking, outcome measurement | P + D4 |
| Feb–Mar 2027 | **R3 Order Intake Agent** (pilot 2) | WhatsApp, text or photo to a validated draft sales order | **D2** |
| Mar–Apr 2027 | **R4 Inventory Risk and Godown Transfer Agent** | Stockout / dead-stock / expiry worklist, reorder drafts, transfer suggestions | **D3** |
| May 2027 | **R5 Purchase Matching and Bill Protection** | PO/GRN/bill mismatches, bank-detail and amount anomaly checks, supplier query drafts | P |
| Jun 2027 | **R6 Packaging and channel** | AI credits add-on, WhatsApp send (L3, approved reminders only), daily agent brief | P |
| H2 2027 | **R7 Coordination and connectors** | Cash-flow actions linking agents, margin guard, read-only MCP connector, expansion by gate | P + D5 |

The WhatsApp provider track runs in parallel from R0 to R6. It is a business and compliance process, not engineering work.

---

## 3. Phases in detail

### R0: gate and decisions (2026-11-02 → 2026-11-13)
- **Branch hygiene.** The working tree carries many uncommitted programmes. Commit or land them, then branch `feat/agents-foundation` from main.
- **Phase-0 gate, scoped to agents.** For receivables, sales orders, stock and purchases, close or explicitly waive the open Postgres concurrency runs and sign-offs that touch those flows. Record the result in `qos/backlog/`.
- **Decisions** from section 7 are taken.
- **Baselines start** with the pilot customer, using existing telemetry and `AttentionOutcome`. Measure for 4 weeks before R2 goes live:
  - overdue amount and age;
  - days sales outstanding (DSO);
  - time from receiving a WhatsApp order to the invoice;
  - stockout count.
- **Exit:** decisions recorded, baseline collection running, foundation branch open.

### R1: agent foundation [F] (2026-11-16 → 2026-12-18, 5 weeks)
Deliverables (detail in the feasible plan, section 3, Wave A):
- `agents/` app:
  - `AgentRun`, `AgentStep` and `AgentProposal` models;
  - RLS migration (copy the existing pattern);
  - `ENABLE_AGENTS` per-company flag, default off.
- Tool registry, with role, autonomy level and `money` flag on every tool. The assistant tools are re-homed here with no behaviour change.
- A bounded runner with step cap, timeout, token budget (`assert_within_budget`), retries, and untrusted-input wrapping.
- Proposal lifecycle:
  - approve, reject, expire, cancel;
  - re-validation against live data at approve time;
  - `wrap_idempotent` on execute.
- Per-company kill switch, and an Admin run log with failure rate and cost per run (ops tooling stays in Django admin).
- **Safety regression suite**, the gate for every later phase:
  - cross-tenant access (expects 404);
  - role denial;
  - injection in documents and messages;
  - duplicate approve;
  - stale-data approve;
  - timeout and partial failure;
  - budget exhaustion;
  - flag-off equals today's behaviour.
- **Exit:**
  - safety suite green on SQLite;
  - race tests green on Postgres;
  - assistant suites unchanged;
  - lint and `tsc -b` clean.

### R2: Collections Agent [P + D4] (2026-12-21 → 2027-01-29, 6 weeks including 3 weeks of pilot)
- L1: a ranked worklist inside Needs attention. Ranking uses amount, age, broken promises and payment history, all computed deterministically. Every rank cites invoices.
- L2: a reminder draft per customer, in Hindi or English, polite or firm, with the payment link. Approve leads to copy/share; send stays off until R6.
- Promise-to-pay loop: the agent re-checks on the due date and re-surfaces the row with its history.
- An "Ask agent to prepare" action on attention rows, and an "Agent drafts" tray.
- Hindi review CSV, the same process as other modules.
- **Pilot exit criteria:**
  - zero unauthorized or duplicate actions;
  - at least 60% of drafts approved with only light edits;
  - receipts within 7 days of an approved draft beat the control rows;
  - cost per run within budget.
- *Competitive note:* this is parity with Zoho's invoicing agent, Intuit's Payments Agent and Xero's Payment Follow Ups. We differentiate on Hindi, promise tracking and approve-first.

### R3: Order Intake Agent [D2] (2027-02-01 → 2027-03-26, 8 weeks including pilot)
- Inputs: pasted WhatsApp or SMS text, a photo of a handwritten or printed order, a PDF. Voice notes come later, through a transcript.
- The LLM parses lines into structured lines. Deterministic code then:
  - matches the customer and products, using the alias memory from bill import;
  - applies the price list and schemes;
  - checks the credit limit, stock and expiry rules.
  Ambiguous lines are flagged with alternatives.
- Output: a **draft** sales order in the Quick Order Entry screen. The user confirms through the normal create path (existing idempotency scope).
- A correction memory, like Tally Ira's learned mappings: per-company aliases, so the second order from the same retailer needs fewer edits.
- An accuracy dataset of 50+ real orders, anonymised from the pilot.
- **Exit:**
  - at least 95% of lines correctly matched on the dataset;
  - zero orders created without a human confirm;
  - median time from message to confirmed draft cut by half against the baseline.
- *Competitive note:* the only comparable products are MS BC's Sales Order Agent (email, mid-market) and SalesCode (brand side). This is the headline feature for distributor sales.

### R4: Inventory Risk and Godown Transfer Agent [D3] (2027-03-29 → 2027-04-30, 5 weeks)
- L1 rows:
  - stockout risk, from velocity, on-hand, lead time and safety stock in the existing reorder service;
  - dead or slow stock;
  - near-expiry by batch.
  Every row cites movement history.
- L2:
  - a reorder draft grouped by supplier, in the purchase-planning flow behind `ENABLE_PURCHASE_PLANNING`;
  - a **godown transfer suggestion** when one godown is short and another holds excess. It is a draft note only; execution uses the normal transfer screen.
- Works with short history: rules first, so it does not need Cin7-style 6 months of history.
- **Exit:** recommendations reviewed on a fixed dataset with no wrong-quantity suggestions; pilot stockouts measured against the baseline.

### R5: Purchase Matching and Bill Protection [P] (2027-05-03 → 2027-05-28, 4 weeks)
- Deterministic PO / GRN / bill mismatch rows: quantity, rate, tax, and missing GRN.
- **Bill Protection checks**, borrowed from Xero:
  - changed supplier bank details;
  - an amount far above the supplier's norm;
  - a new supplier GSTIN;
  - a duplicate bill number.
- The LLM explains each mismatch and drafts a supplier query (L2). It never posts or pays.
- **Exit:** precision of 90% or better on a seeded mismatch dataset; no false block on a clean bill.

### R6: packaging and channel [P] (June 2027)
- **AI credits add-on:**
  - built on `AiUsageLedger`, with a monthly pool per company;
  - page-metered extraction, like Tally packs;
  - the admin sees spend per agent.
- **WhatsApp send, L3:** only for reminders already approved, through the chosen provider, with per-company daily caps, opt-out handling and a delivery log. Turn on `ENABLE_WHATSAPP_CLOUD` per company after a compliance review.
- **Daily agent brief:** one summary of open drafts, results and money recovered.
- **Exit:** a pricing test with at least 3 pilot customers; zero sends without an approval record.

### R7: coordination and connectors (H2 2027, by gate)
- **Cash-flow actions:**
  - Xero-style plans that link expected inflows from collections drafts with payables timing;
  - review and adjust only;
  - payments stay human.
- **Margin guard [P]:** low-margin, high-discount and cost-jump rows, respecting `cu_can_see_margins`.
- **Read-only MCP / Claude connector [P]:** exposes registry read tools to outside AI clients under per-company consent. Zoho, Intuit and Xero already ship one.
- **Expansion rule:** a new agent starts only when the previous one has met its exit criteria for 4 consecutive weeks.

---

## 4. Parallel tracks

| Track | Owner | Start | Done when |
| --- | --- | --- | --- |
| WhatsApp provider (BSP selection, template approval, opt-in policy) | Founder / ops | R0 | Provider live in staging by R6 |
| LLM provider and data policy (tool-calling quality in Hindi and Hinglish; data residency) | Founder + eng | R0 | Eval report before R2 pilot |
| AI evaluation datasets (collections 30+, orders 50+, inventory 30+, matching 30+) | Eng + pilot customer | R1 | Each dataset exists before its phase starts |
| Hindi review of agent strings | Reviewer | R2 | CSV signed off per phase |
| CA review of anything touching tax text | CA | R2 | Before R5 |

---

## 5. KPIs (targets set after baseline, per the founder's brief)

| Dimension | Metric | Source |
| --- | --- | --- |
| Value | Overdue recovered within 7 days of an approved draft; DSO change; order-entry minutes saved; stockouts avoided | `AttentionOutcome`, telemetry, ledgers |
| Accuracy | Draft approval rate; line-match accuracy; matching precision | `AgentProposal` status, eval datasets |
| Safety | Unauthorized actions (target 0); duplicate executions (target 0); data discrepancies (target 0) | Safety suite, audit log |
| Adoption | Weekly active approvers; proposals approved per company per week | `AgentProposal`, `ShopFloorEvent` |
| Reliability | Run failure rate; timeout rate; p95 run time | `AgentRun` |
| Economics | LLM cost per completed workflow; credits consumed per company; support tickets per agent | `AiUsageLedger`, support |

---

## 6. Competitive watch-list (review every quarter)

| Watch | Trigger to react |
| --- | --- |
| Zoho CoCreate / Agent Studio gains WhatsApp or distributor ordering | Pull R3 polish forward; push distributor-specific depth (schemes, credit, godowns) |
| Tally Ira extends beyond documents (collections, WhatsApp) | Lead with cloud, multi-user and mobile; publish a Tally migration path |
| Vyapar brings TaxOne / AI into the billing app | Hold the distributor and multi-godown segment; do not chase micro-billing |
| An India-direct rival ships auto-send collections | Market approve-first and evidence (D1) |
| LLM price drops | Widen L1 coverage; lower credit prices |

---

## 7. Decisions needed by 2026-11-13

1. **Pilot customer and segment:** distributor or wholesaler, ideally multi-godown with WhatsApp ordering, so that R2, R3 and R4 can share one pilot.
2. **LLM provider for agents.** `LLM_PROVIDER` already supports openai, deepseek and claude. Pick on tool-calling reliability and Hindi quality after a short evaluation.
3. **Data policy:** whether agent prompts may leave India, and the consent wording beyond the existing Insights consent toggle (D12).
4. **WhatsApp provider:** start the selection now, or stay on copy/share through R5.
5. **Order change:** confirm Order Intake (R3) ahead of Inventory Risk (R4), as the competitive analysis recommends.
6. **Packaging hypothesis to test in R6:** included alerts, an agents add-on and metered extraction.

## 8. Not on this roadmap (and why)

- **Warehouse vision agent:** no camera or CV stack, and no proven demand.
- **Autonomous payments, postings, stock adjustments, credit overrides or GST filing:** these stay human, by policy.
- **A custom agent builder for customers:** SMB buyers want outcomes; Zoho, Xero and MS target a different buyer.
- **Deep AI GST reconciliation to compete with ClearTax or TaxOne:** keep rule rows plus "explain".
