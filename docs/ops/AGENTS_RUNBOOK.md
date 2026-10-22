# Agents runbook

For founder and support staff. The agents platform lives in `backend/agents/`. The design is in
[AGENTIC_AI_IMPLEMENTATION_PLAN_2026-10-21.md](../roadmap/AGENTIC_AI_IMPLEMENTATION_PLAN_2026-10-21.md).
Ops views are in Django admin (`/admin/agents/` and `/admin/insights/aiusageledger/`), never in the customer app.

## What an agent can and cannot do

- It reads the company's books through registered tools, and writes **drafts** for a person to approve.
- It never posts money, adjusts stock, changes a credit limit, files tax, or sends a message by itself.
  In R2 the reminder is copied or shared by the user; EXECUTED means "the user took it to send".
- Every draft shows the invoices or rows it is based on. Numbers in the text come from the books.

## Turn agents off

| Scope | How | Effect |
| --- | --- | --- |
| One company | Admin → Agent runs → select a run of that company → action **Kill switch**; or set `ENABLE_AGENTS` to false in the company's `feature_flags` | The catalogue is empty, "Prepare draft" disappears, runs fail with `AGT_E_DISABLED`, approve of open drafts is refused. Open drafts stay readable and expire on their own. |
| One agent, one company | Set that agent's flag (for example `AGENT_COLLECTIONS`) to false in `feature_flags` | Same, for that agent only |
| Everyone | Set env `AGENTS_GLOBAL_KILL=1` and restart web and workers | Every agent API call returns `AGT_E_GLOBAL_KILL` |
| The model only | Set `LLM_AGENT_PROVIDER` to something else, or turn the company's AI consent off | Agents still work in rules-only mode: template drafts, no model call |

Rollback of code is a plain revert. The migrations only add tables and one column, so nothing has to be undone in the database.

## Turn an agent on for a company

1. In the company's `feature_flags` set `ENABLE_AGENTS` and the agent's flag (for example `AGENT_COLLECTIONS`) to true.
2. Collections measures outcomes with a held-out group. To start that, also set `AGENT_COLLECTIONS_HOLDOUT` to true. About one customer in five then gets no scheduled drafts. Tell the pilot owner.
3. Check Admin → Agent runs after the first scheduled run (08:30 IST).
4. Order Intake (`AGENT_ORDER_INTAKE`) has no schedule. It appears as a "Paste an order" panel in Quick Order Entry for users who can create sales. It runs while the person waits, keeps only a hash of the pasted text on the run, and creates a DRAFT sales order only when the draft is approved. Learned wording is in `AgentAlias` (admin); delete a wrong alias there and the next order is matched afresh.

## Where things are

| Question | Look at |
| --- | --- |
| Did the run work? Why not? | Admin → Agent runs. `status` and `error_code`; the steps show each model turn and tool call (arguments are redacted). |
| What did we send to the model? | Steps hold redacted arguments and result summaries only. Raw prompts are not stored. |
| Why was a draft refused? | Admin → Agent proposals: `failure_code`, `decision_note`, `attempts`, `revision`. |
| Cost | Admin → Ai usage ledger. Filter `feature = AGENT`, then `agent_kind`. A cost of "unpriced" means the model is missing from `agents/pricing.py`. |
| Which prompt version? | `prompt_version` on the run, e.g. `system.v1`. Prompts are files in `agents/catalog/<agent>/prompts/`. |

## Error codes

| Code | Meaning | What to do |
| --- | --- | --- |
| `AGT_E_DISABLED` / `AGT_E_GLOBAL_KILL` | Flag off or kill switch on | Check the flags above |
| `AGT_E_ROLE` | The user's role cannot do this | Reminder drafts need the same access as payment reminders |
| `AGT_E_STALE` | The books changed after the draft was written (customer paid, amount changed) | Nothing to fix; prepare the draft again |
| `AGT_E_EXPIRED` | Draft older than its expiry (reminders 72 h) | Prepare again |
| `AGT_E_REVISION` | Someone edited the draft since this screen loaded | Reload and review |
| `AGT_E_BAD_TRANSITION` | Already approved, rejected or cancelled | Usually a double click; no action |
| `AGT_E_ATTEMPTS` | Failed three times | Prepare again; look at `failure_code` |
| `AGT_E_PROVIDER` / `AGT_E_TIMEOUT` | Model provider error or slow | Retry; if it persists, switch `LLM_AGENT_PROVIDER` or rely on rules-only |
| `AGT_E_BUDGET` | The run used more than `AGENTS["PER_RUN_TOKEN_CAP"]` tokens | Inspect the steps; raise the cap only if the run was legitimate |
| `AGT_E_DAILY_CAP` | The company hit `PER_COMPANY_DAILY_RUNS` | Wait until tomorrow or raise the agent's `per_company_daily_runs` |
| `AGT_E_STEP_LIMIT` | The model kept calling tools | Look at the steps; usually a prompt problem |

## Provider failover

Set `LLM_AGENT_PROVIDER` (`claude`, `openai`, `deepseek`) and `LLM_AGENT_MODEL`, then restart workers. If the provider is down
agents fall back to template drafts by themselves. `fake` is for tests only and must never be set in production.

## Workers

Agent tasks use two queues: `agents_interactive` (a user pressed Prepare) and `agents` (scheduled sweeps, expiry, purge).
Start workers for both. Without a dedicated worker the tasks stay in the queue; there is no silent failure, but drafts
will not appear. Schedules: dispatcher every 15 min, expiry every 15 min, cancel-resolved hourly, step purge Sundays.

## Investigating a wrong draft

1. Find the proposal (Admin → Agent proposals) and note `run`.
2. Open the run: was it `rules_only`? If not, which prompt version and model?
3. Compare the draft's numbers with the evidence rows it cites. If a number is not in the books, that is a bug in the
   number check (`agents/numbers.py`): add the case to `tests/agents/test_text_safety.py` first.
4. If the facts were wrong, the bug is in the context builder, not the model.

## Data

Runs, proposals and aliases are included in the tenant backup and wiped on restore. Step records are purged after 180 days.
