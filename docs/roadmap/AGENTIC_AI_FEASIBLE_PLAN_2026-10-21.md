# Agentic AI for Bizboard — feasible plan

**Date:** 2026-10-21. **Status:** PROPOSAL, no code written. Needs founder decisions in section 6.
**Source:** the "Bizboard Agentic AI — Consolidated Implementation Plan" pasted by the founder, checked against the tree.

## 1. Verdict on the pasted plan

The pasted plan is sound in direction. Its sequencing (Action Center first, one agent, then expand) fits the tree. Its architecture is mostly already built here. Three corrections:

- **Phase 1 (Business Action Center) already exists** as Dashboard "Needs attention" (`insights/attention.py`, DAN-00..19). It has evidence rows, severity ranking, dedupe keys, assign / dismiss / snooze / reopen, and outcome tracking (`insights/outcomes.py`). We extend it. We do not build a new screen.
- **Phase 0 is a gate, not a rewrite.** Money-path regression, RLS and idempotency are in place (`core/idempotency.py`, RLS migrations, `docs/TESTING_STRATEGY.md`). The remaining gate items are the open sign-offs (QOS-0129..0148, Postgres runs). The agent layer ships behind a flag until those are closed for the flows it touches.
- **Rank by data readiness, not by the pasted P0..P3.** Order below follows what the tree can already support.

## 2. What already exists (reuse, do not rebuild)

| Need from the plan | Already in the tree |
| --- | --- |
| Business events and evidence | `insights/event_schema.py` (`EVENT_SOURCES`), attention rows with `dedupe_key`, severity, `href`, paise amounts |
| Recommendations and approvals | `AttentionRowState` (assign, dismiss, snooze), `AttentionOutcome`, `AssistantMessage.proposed_action` + `confirm_proposed_action` |
| Collections signals | `_overdue_customer_rows`, `_promise_to_pay_rows`, `tool_draft_payment_reminder`, `billing/dunning.py` (SaaS dunning, a pattern only) |
| Inventory signals | expiry rows, reorder / lead-time quantity in `inventory/services.py`, `ENABLE_PURCHASE_PLANNING` |
| Customer growth | `insights/customer_actions.py` (churn, repeat-order, cross-sell), `crm/campaigns.py`, `crm/forecast.py` |
| Cash flow | `CashflowForecastRun`, `tool_get_cashflow_forecast` |
| GST exceptions | `_itc_and_gst_rows`, `_gst_rate_exposure_rows`, `_irn_rows`, `reporting/gst_guard.py` |
| Order intake from documents | `imports/` bill extraction (`core/services/llm.py`), `QUICK_ORDER_ENTRY` flow, injection guard tests (`test_llm_injection_guard.py`) |
| LLM budget, cost, consent | `AiUsageLedger`, `assert_within_budget`, budget alerts, Insights consent toggle (D12), role-scoped `TOOL_ACCESS` |
| Safety hard-stop | `MONEY_MOVING_ACTION_TYPES` cannot be confirmed through the assistant |
| Duplicate protection | `wrap_idempotent`, `MONEY_IDEMPOTENCY_SCOPES` |
| Not available | WhatsApp send (`ENABLE_WHATSAPP_CLOUD` off, no provider), bank feed, GSTN filing, camera vision |

## 3. Architecture: a thin agent layer, new Django app `agents/`

Do not add an agent framework. Add one small app with four pieces:

1. **Tool catalogue** (`agents/tools.py`). Each tool is a registered function with a name, JSON schema, required role, autonomy level (L1/L2/L3) and a `money` flag. Read tools wrap existing services (the `ToolExecutor` tools move here or are re-exported). Write tools only ever create **drafts** or call existing service functions. Tools never touch models directly.
2. **Run and step record** (`AgentRun`, `AgentStep`, tenant-scoped, RLS-enrolled). It stores trigger (attention row key, schedule or user), tool calls, inputs, outputs, tokens, model and prompt version. This is the audit trail and the evaluation dataset.
3. **Proposal** (`AgentProposal`): the L2 object a human approves. Fields: `kind`, `payload`, `evidence` (rows and documents cited), `status` (PENDING / APPROVED / REJECTED / EXPIRED / EXECUTED / FAILED), `expires_at`, `idempotency_key`, `approved_by`, `result_ref`. Approve runs the executor through `wrap_idempotent`. Reject and expire are first-class. Execution re-validates against live data, because the world may have changed since the draft.
4. **Runner** (`agents/runner.py`). A bounded loop: at most N tool calls, a wall-clock timeout, a token budget through `assert_within_budget`, and a retry limit. Deterministic code computes every number. The LLM selects tools, ranks and writes text. Tool results are redacted before they reach the model, as `_redact_tool_result_for_llm` does today. Any text from uploaded documents or customer messages is wrapped as untrusted data.

Triggers: Celery beat sweep (the same task pattern as `sweep_attention_state`), plus an "Ask agent to prepare" button on an attention row.

UI: no new page. Proposals appear inside Needs attention as a row action ("Review draft") and in a small "Agent drafts" tray. Ops views (run log, failure rate, cost per run) go in Django admin, per the standing rule.

## 4. Autonomy ladder (applies to every feature)

- **L1** read and explain. Default for all agents.
- **L2** draft for approval. Reminder text, draft sales order, draft purchase request, draft transfer note.
- **L3** bounded execution. **Only** "send an already-approved reminder", and only when the channel exists. Everything else stays L2.
- **Never by an agent:** payments, receipts, stock adjustments, credit overrides, journal postings, GST filing or attestations. These keep the existing human flow and the `MONEY_MOVING_ACTION_TYPES` block.

## 5. Features, in build order

> **Superseded for sequencing and dates** by [AGENTIC_AI_ROADMAP_2026-10-21.md](AGENTIC_AI_ROADMAP_2026-10-21.md). After the competitive analysis, Order Intake moves ahead of Inventory Risk, and a Bill Protection check and an AI credits add-on are added. The wave content below still describes the scope.

### Wave A: foundation (about 3 weeks)
- **A1** `agents/` app: models, migrations, RLS enrolment, tool registry, runner, proposal approve / reject / expire. Feature flag `ENABLE_AGENTS`, per-company, default off.
- **A2** Move the assistant's existing tools onto the registry without changing behaviour. Keep the assistant tests green.
- **A3** Safety regression suite: cross-tenant (expects 404), role denial, prompt injection in documents, duplicate approve, timeout and retry, stale-data re-validation, budget exhaustion. This suite gates every later agent.
- **A4** Admin run log plus cost per run. Telemetry events extend `event_schema` and `ATTENTION_DEDUPE_KEYS`.

### Wave B: Collections Agent (about 3 weeks, first pilot)
- Input: overdue and promise-to-pay rows already in Needs attention.
- L1: rank customers by amount, age, broken promises and payment history. Cite invoices.
- L2: draft a reminder per customer in English or Hindi, polite or firm, using the existing `draft_payment_reminder`. Copy-to-clipboard and share link (already supported); the send path stays off until a provider exists.
- Track promise-to-pay: when the user records a promise, the agent re-checks on the date and re-surfaces the row.
- Measure with `AttentionOutcome`: drafts accepted, receipts within 7 days of an accepted draft, against a baseline of rows without drafts.
- Hindi strings need review, like the other `*_HINDI_REVIEW.csv` files.

### Wave C: Inventory Risk Agent (about 3 weeks)
- L1: stockout risk (velocity vs on-hand and lead time), dead stock, near-expiry. All calculations come from the existing reorder service.
- L2: draft purchase request or reorder list grouped by supplier. It creates a draft in the existing purchase-planning flow, behind `ENABLE_PURCHASE_PLANNING`.
- Multi-godown transfer suggestions: L2 note only, in the same wave if the customer has more than one warehouse. Execution uses the normal stock transfer screen.

### Wave D: Order Intake Agent (about 4 weeks)
- Reuse the Quick Order Entry flow and the extraction pipeline. Input: pasted WhatsApp text, an uploaded image or PDF.
- The LLM parses to structured lines. Deterministic code matches customers and products (fuzzy match with confidence), applies price lists and credit-limit checks, and flags unmatched or ambiguous lines.
- Output: a **draft** sales order only. The user reviews and confirms through the normal create path (`sales_invoice_create` idempotency scope).
- No inbound WhatsApp automation until a provider is chosen. Paste and upload cover the pilot.

### Wave E: Purchase Matching and Margin Guard (about 3 weeks each, only on pilot demand)
- **Purchase matching:** compare PO, GRN and supplier bill (`purchases/grn_service.py`). Deterministic mismatch rows; the LLM explains and drafts a supplier query. Read and draft only.
- **Margin protection:** rows for low-margin lines, high discounts and cost jumps. Respects `cu_can_see_margins`. Read only.

### Wave F: coordination and cash flow (after two agents show value)
- Cash Flow Agent explains the existing forecast and links collections drafts to expected inflow. Cross-agent summary in the daily brief.
- Optional bounded L3 for sending approved reminders once a messaging provider is live.

### Deferred (not feasible now, and why)
- **Warehouse Vision Agent:** needs cameras and a CV pipeline. No tree support.
- **GST Compliance Guard as an agent:** the rows exist. Filing and attestations are out of scope. Only add "explain this mismatch" through the L1 assistant.
- **Autonomous multi-agent coordination, auto-send on WhatsApp, bank-feed cash positions:** need external providers or consent infrastructure.

## 6. Decisions needed from the founder

1. **First pilot agent:** Collections (recommended, since the signals and drafts exist) or Order Intake?
2. **LLM provider and data policy.** The tree supports openai, deepseek and claude through `LLM_PROVIDER`. Agent tool use needs a provider with reliable tool calling. Which provider for production, and does customer data leaving the country need a consent line beyond D12?
3. **Messaging channel.** Pick a WhatsApp provider now (long lead time) or stay on copy and share for the pilot.
4. **Pilot customer** and the baseline period for measurement.
5. **Packaging.** Agents as a paid tier is the pasted plan's idea. Confirm only after the pilot; the code uses one flag either way.

## 7. Release gates per agent

Each agent ships only when all pass: business-correctness tests on totals, balances and ages; cross-tenant and role tests; injection tests on every untrusted input; duplicate-approval and stale-data tests; AI quality set (a fixed dataset of 30+ cases per agent with expected rankings, and a check that every claim cites a row); cost per run under budget; admin run log working; existing suites green; Hindi review; and a flag-off check that the product behaves exactly as before.

## 8. Risks

- **Mid-flight tree:** many uncommitted programmes. Land or commit those before starting Wave A, or build on a clean branch off main.
- **Provider tool-calling quality** in Hindi and Hinglish: budget time for evaluation.
- **Alert fatigue:** agent rows must reuse the dedupe, snooze and outcome machinery, so they cannot flood Needs attention.
- **Cost:** per-run caps and the existing monthly budget alerts.
