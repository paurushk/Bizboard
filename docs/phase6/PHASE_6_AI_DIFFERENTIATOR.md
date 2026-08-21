# BizBoard — Phase 6: AI Differentiator

**Status:** Implemented in code (2026-08-02) — rules-first insights + tool-grounded assistant; Phase 7.0 Tally follows separately.  
**Canonical path:** [`docs/phase6/PHASE_6_AI_DIFFERENTIATOR.md`](./PHASE_6_AI_DIFFERENTIATOR.md)  
**Root pointer:** [`PHASE6_IMPLEMENTATION_PLAN.md`](../../PHASE6_IMPLEMENTATION_PLAN.md)  
**Stack:** Django 5 + DRF (`backend/`) · React 18 + MUI (`web/`) · Celery + Redis · existing LLM client in `core/services/llm.py` · dashboards via `reporting/services.py` · alerts pattern from `reporting/gst_health.py` · tenancy via `company_id` on every query.

---

## Start gate — Phases 1–3 data readiness (read first)

Phase 6 is an **insight layer on top of real transaction data**. It must not invent money, tax, or stock. Build only after billing depth and enough completed documents exist for signals to be trustworthy.

| Prerequisite | Source of truth | Why it matters |
|--------------|-----------------|----------------|
| Phase 0 Go / money Criticals closed | [`docs/pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) | Wrong invoices → wrong AI advice |
| Phase 1 core DoD (CN/DN, outstanding helper, credit limit) | [`docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md`](../phase1/PHASE_1_DOCUMENT_COMPLETENESS.md) | Outstanding / profit signals need CN/DN |
| Phase 2.0 GST Health live (pattern to clone) | [`docs/phase2/PHASE_2_GST_RETURNS_READINESS.md`](../phase2/PHASE_2_GST_RETURNS_READINESS.md) | Reuse Critical/Warning alert UX |
| Phase 3 (or equivalent): ≥ **90 days** of completed sales + purchase + receipts for ≥ **5 pilot companies**, OR synthetic golden tenants with realistic volumes | Pilot metrics / seed fixtures | Cashflow & health scores need history |
| LLM keys + cost budget approved for prod | `LLM_PROVIDER`, quotas | Assistant + extraction share the same spend pool |
| Honesty gate: marketing must **not** claim “AI accountant” or tax advice | Onboarding / support copy | Legal + CA trust |

**Do not start Phase 6 before Phase 1 outstanding math is correct.** A “smart alert” that says a customer owes ₹X when CN/DN netting is wrong destroys founder trust faster than no AI at all.

**Why this phase after 1–3 (not before GST polish):** AI BI is the product differentiator vs Vyapar/myBillBook clones — but only if the underlying documents are complete. GST returns (Phase 2) and 2A/2B reconcile (Phase 3 candidate) can proceed in parallel tracks with early Phase 6 **rule-based** waves; **LLM assistant** waits until money KPIs are stable.

### Plan map

| Document | Role |
|----------|------|
| `docs/pilot/*` | Phase 0 — pilot hardening |
| `docs/phase1/*` | Phase 1 — document completeness |
| `docs/phase2/*` | Phase 2 — GST returns readiness |
| Phase 2.5 (compliance track) | GSTR-2A/2B auto-reconcile — **not** numbered as product Phase 3 |
| [`docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md`](../phase3/PHASE_3_PAYMENTS_CASH_OPS.md) | **Phase 3** — Payments & cash ops (actuals feed cash baselines) |
| [`docs/phase4/`](../phase4/) · [`docs/phase5/`](../phase5/) | Inventory depth / light accounting — **not required** to start Phase 6.0 rules |
| **This file** | **Phase 6** — AI differentiator on transaction data |
| [`docs/phase7/PHASE_7_ECOSYSTEM_SCALE.md`](../phase7/PHASE_7_ECOSYSTEM_SCALE.md) | Phase 7 — ecosystem & scale |

### Headcount / calendar (solo senior full-stack)

| Wave | Duration | Same person? |
|------|----------|--------------|
| Phase 6.0 — Daily Summary + Smart Alerts (rules first) | ~3–4 weeks | Yes |
| Phase 6.1 — Business Health Score + Founder Dashboard | ~3–4 weeks | Yes — after 6.0 alert catalog stable |
| Phase 6.2 — Cashflow prediction | ~3–4 weeks | Yes — after receivables/payables aging trusted |
| Phase 6.3 — Profit leak / growth hints | ~2–3 weeks | Yes — after 6.1 score factors exist |
| Phase 6.4 — Natural Language Business Assistant | ~5–7 weeks | Yes — after 6.0–6.2 tools exist to ground answers |
| **Calendar consequence** | **~16–22 weeks** sequential | Waves **should not** overlap LLM work with tax engine changes at headcount 1 |

**6.0 + 6.1 (no generative LLM UX): ~6–8 weeks** — highest founder value with lowest hallucination risk.  
Ship rule-based intelligence first; use LLM only where natural language or unstructured extraction is required.

---

## 0. Current-state snapshot (as of 2026-08-02)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Dashboard KPIs (sales today/MTD, AR/AP, aging, low stock) | ✅ `ReportService.dashboard` | ✅ Dashboard page | **Baseline only** — not founder “health” narrative |
| Low-stock alerts | ✅ `/inventory/alerts/` | Partial | Rule-based qty only |
| GST Health alerts | ✅ `reporting/gst_health.py` | ✅ GST Health UI | **Compliance** pattern to clone — not business ops |
| Notifications (email / WA link / SMS stub) | ✅ `Notification` + Celery email | Share flows | No daily digest job |
| LLM purchase-bill extraction | ✅ `llm.extract_purchase_bill` + Celery | ✅ Bill upload page | **Only AI feature** |
| Prompt versioning / cost metering / quotas | ❌ | ❌ | Missing |
| Business Health Score | ❌ | ❌ | Missing |
| Cashflow forecast | ❌ | ❌ | Missing — no cash book; payments are record-only |
| Profit leak / margin hints | ❌ | ❌ | Missing |
| NL assistant / chat | ❌ | ❌ | Missing |
| Embedding / RAG store | ❌ | ❌ | Missing |
| AI feature flags / permissions | ❌ | ❌ | Missing — need Owner + new flags |

**Patterns to extend (do not invent parallel truth sources):**

- Money: `LedgerService` / outstanding helpers / `ReportService` aggregations only
- Tax: never let LLM recompute GST — `compute_document_totals` remains CA-owned
- Alerts: clone GST Health shape `{ code, severity, message, ...extra }` → Business Health
- Async: Celery for digests, forecasts, LLM calls — never block Complete
- Tenant isolation: every tool / query scoped by `company_id`; assistant tools must fail closed
- Events: emit `business_alert.raised`, `daily_summary.ready` via `core/events.py` (in-process)

---

## 1. Locked product decisions

| # | Decision | Lock |
|---|----------|------|
| D1 | Phase 6 ships **decision support**, not automated accounting, tax filing, or bank transfers | Copy: “insights from your BizBoard documents” — never “AI CA” |
| D2 | **Rules-first, LLM-second** | 6.0–6.3 are deterministic formulas + thresholds; 6.4 LLM only **grounds** answers in tool results |
| D3 | **No new ledger / journal / cash-book tables** for cashflow | Forecast = projected receipts & supplier payments from open docs + historical collection rates |
| D4 | Business Health Score = **0–100 composite** of weighted factors with transparent breakdown | Every score change must show factor contributions (explainability) |
| D5 | Smart Alerts reuse Critical / Warning / Info severities; Owner can snooze per `code` for N days | Persist snoozes company-scoped; do not delete history |
| D6 | Daily Business Summary = Celery beat job per active company (timezone = company/`Asia/Kolkata`) | Idempotent per `(company_id, local_date)`; store snapshot for audit |
| D7 | Cashflow prediction horizon = **7 / 14 / 30 days** default; 90-day later | Confidence band required; never a single false-precision number |
| D8 | Profit-leak hints are **heuristic suggestions** (margin drop, slow movers, discount abuse, overdue concentration) | Each hint links to a filtered register / document list — no free-floating advice |
| D9 | NL Assistant = **tool-calling agent** over company-scoped read APIs; write actions = **propose → confirm** only | Default: read-only. Creates (draft invoice, reminder) require explicit user confirm in UI |
| D10 | LLM never answers tax rate / place-of-supply / GSTR liability questions with free text | Redirect to Reports / GST Health / “ask your CA” canned reply |
| D11 | All AI features behind `Company.ai_features_enabled` + membership flags | Pilot: Owner-only; Staff later with `can_view_ai_insights` |
| D12 | Cost controls: per-company monthly token budget + hard fail with user-visible message | Shared with bill extraction quota |
| D13 | Prompt + tool schemas are **versioned strings** in code (`PROMPT_VERSION`, `TOOLS_VERSION`) logged on every call | Needed for replay / support |
| D14 | PII: assistant logs store **query metadata + tool names**, not full document dumps, unless support retention flag on | DPDP-aware; purge job later |
| D15 | Phase 6 does **not** require multi-company, Tally, or WhatsApp Business | Digests use existing email + `wa.me` share until Phase 7 |
| D16 | Minimum data gate per company before enabling score/forecast: ≥ **30 completed sales invoices** OR Owner override with watermark “limited data” | Avoid nonsense 100 scores on empty tenants |

---

## 2. Scope split — waves

### Phase 6.0 — Daily Business Summary + Smart Alerts

**Goal:** Founder opens app (or email) and sees “what needs attention today” without scanning registers.

- `BusinessAlert` catalog (rule engine) — clone GST Health style
- Celery beat: `generate_daily_business_summary(company_id, for_date)`
- Persist `DailyBusinessSummary` snapshot (JSON KPIs + alert ids)
- API: `GET /api/v1/insights/daily-summary/?date=`, `GET /api/v1/insights/alerts/`
- FE: Insights home strip on Dashboard + Alerts drawer
- Delivery: optional email digest to Owner; WhatsApp = share-link text until Phase 7

### Phase 6.1 — Business Health Score + Founder Dashboard

**Goal:** One score + narrative factors that explain “are we okay?”

- `BusinessHealthService.score(company, as_of)` → `{ score, grade, factors[] }`
- Founder Dashboard page (Owner): score, sparkline history, top alerts, MTD vs prior month
- Persist nightly `BusinessHealthSnapshot` for trend charts
- FE: `/insights/health` — not a second generic dashboard clone

### Phase 6.2 — Cashflow prediction

**Goal:** “Will we have enough cash in 14 days?” without a full cash book.

- Inputs: open AR by due date, open AP by due date, historical collection/payment lag, scheduled recurring (if any — else ignore until Phase 7)
- Output: daily projected net change + ending cash **delta from today** (baseline cash = Owner-entered opening cash or “relative only” mode)
- API: `GET /api/v1/insights/cashflow-forecast/?horizon=14`
- FE: horizon toggle + confidence band chart
- Disclaimer: record-only payments; no bank feed (Phase 7+)

### Phase 6.3 — Profit leak / growth hints

**Goal:** Specific, actionable “you’re leaking margin / growth opportunities.”

- Hint generators (deterministic): margin compression, SKU dead stock, customer concentration, discount frequency, purchase price creep, overdue top-N
- Each hint: `{ code, title, impact_estimate, evidence_query, cta_path }`
- Surface on Founder Dashboard + assistant tool `list_growth_hints`

### Phase 6.4 — Natural Language Business Assistant

**Goal:** “What did I sell yesterday?”, “Who owes me the most?”, “Draft a reminder to X” — grounded answers.

- Chat API + Celery or sync short path for simple tools
- Tool registry (read): sales/purchases totals, aging, stock, alerts, health, cashflow, search
- Tool registry (propose): create draft quotation / draft reminder text — UI confirm
- FE: `/insights/assistant` chat panel; cite tool results as chips linking to pages
- Safety: tenancy tests, prompt injection suite, rate limits

**Explicitly out of Phase 6:**

- Bank statement OCR / auto-recon (Phase 7+)
- Auto-send WhatsApp via Business API (Phase 7)
- Tax advice, GSTR filing actions, e-Invoice submit via chat
- Multi-company consolidated AI (Phase 7)
- Fine-tuned private models (use hosted LLM + tools)
- Manufacturing / BOM insights (Phase 7 Future)

---

## 3. Data model (new app: `insights`)

Prefer a new Django app `backend/insights/` rather than bloating `reporting/`. Reporting stays statutory/registers; insights stays ops/AI.

| Model | Purpose |
|-------|---------|
| `DailyBusinessSummary` | `(company, summary_date)` unique; `kpis` JSON; `alert_codes`; `prompt_version` nullable; `created_at` |
| `BusinessAlertEvent` | Raised alert instance: `code`, `severity`, `message`, `payload` JSON, `status` (OPEN/SNOOZED/RESOLVED), `snoozed_until` |
| `BusinessHealthSnapshot` | Nightly score + `factors` JSON + `score` |
| `CashflowForecastRun` | Horizon, inputs hash, `series` JSON, `model_version` |
| `GrowthHint` | Optional materialization; or ephemeral from service (prefer ephemeral in 6.3, persist if snooze needed) |
| `AssistantThread` / `AssistantMessage` | Chat history company-scoped; role user/assistant/system/tool |
| `AiUsageLedger` | tokens_in/out, cost_estimate, feature (`EXTRACT`/`ASSISTANT`/`SUMMARY_NARRATIVE`), company FK |

**Company flags (accounts):**

- `ai_features_enabled` bool
- `ai_monthly_token_budget` int (nullable = platform default)
- `opening_cash_balance` + `opening_cash_as_of` (for absolute cashflow; optional)
- `daily_summary_email_enabled` bool

**Membership flags:**

- `can_view_ai_insights` (default False for staff; True for Owner)
- `can_use_ai_assistant` (Owner default True when AI enabled)

---

## 4. Alert catalog (Phase 6.0) — initial set

Clone severity semantics from GST Health. Codes are stable API contracts.

| Code | Severity | Rule (sketch) |
|------|----------|---------------|
| `AR_OVERDUE_CRITICAL` | Critical | Any invoice outstanding > 60 days **or** total 90+ bucket > X% of AR |
| `AR_OVERDUE_WARN` | Warning | 31–60 day bucket growing MoM |
| `AP_DUE_7D` | Warning | Supplier bills due in ≤ 7 days exceeding projected inflows |
| `CASH_TIGHT_14D` | Critical | Forecast ending relative cash &lt; 0 within 14d (after 6.2; stub skip until then) |
| `LOW_STOCK_FAST_MOVER` | Warning | Below reorder **and** sold in last 14 days |
| `NO_SALES_TODAY` | Info | Business day with 0 invoices by 6pm local (configurable) |
| `MARGIN_DROP_SKU` | Warning | Avg margin vs 30d baseline down &gt; threshold (needs cost; use last purchase price) |
| `CUSTOMER_CONCENTRATION` | Warning | Top 1 customer &gt; 40% of MTD sales |
| `CREDIT_LIMIT_NEAR` | Warning | Customer exposure &gt; 80% of limit |
| `GST_HEALTH_CRITICAL_OPEN` | Info | Bridge: point to GST Health if Criticals open (don’t duplicate GST codes) |

**Engine:** `insights/alerts.py` → `build_business_alerts(company) -> list[dict]` then upsert into `BusinessAlertEvent` (dedupe by code+subject key).

---

## 5. Health Score factors (Phase 6.1)

Score = weighted average of 0–100 factor scores. Default weights (Owner-tunable later):

| Factor | Weight | Inputs |
|--------|--------|--------|
| Liquidity / collections | 25% | AR aging mix; collection rate last 30d |
| Payables pressure | 15% | AP due in 14d vs recent receipts |
| Sales momentum | 20% | MTD vs prior MTD; trailing 7d vs prior 7d |
| Margin health | 15% | Gross margin proxy: sales − COGS(last purchase) on sold qty |
| Stock health | 10% | % SKUs below reorder; dead stock share |
| Compliance bridge | 10% | Inverse of open GST Health Criticals (cap) |
| Data completeness | 5% | % invoices with party + HSN where required |

**Grade bands:** A 85–100 · B 70–84 · C 55–69 · D 40–54 · F &lt; 40  
Always show **“Limited data”** watermark when D16 gate fails.

---

## 6. Cashflow prediction method (Phase 6.2)

**Mode A — Relative (default):** forecast cumulative net cash **change** from today; no absolute bank balance required.

**Mode B — Absolute:** Owner sets `opening_cash_balance` as of date; forecast ending cash = opening + net change − known AP + expected AR collections.

**Expected collections:** for each open sales invoice, probability by days-past-due bucket from company history (fallback: industry defaults). Spread expected amount across horizon.

**Expected outflows:** purchase invoices by due date at 100% unless historical early-pay discount pattern exists (v1 = due date).

**Never** invent bank fees, GST cash liability payment, or salary — optional Owner “planned outflow” list can be Phase 6.2b.

---

## 7. NL Assistant architecture (Phase 6.4)

```
User message
  → AssistantService (company, user)
  → LLM with tools (JSON schema)
  → ToolExecutor (company-scoped services only)
  → LLM final answer with citations
  → persist messages + AiUsageLedger
```

**Allowed tools (v1):**

| Tool | Maps to |
|------|---------|
| `get_daily_summary` | Insights summary |
| `get_health_score` | Health service |
| `get_cashflow_forecast` | Forecast service |
| `get_sales_totals` | ReportService windowed totals |
| `get_receivables_aging` | ReportService |
| `get_payables_aging` | Mirror AP aging |
| `search_documents` | Existing `/search/` service |
| `list_business_alerts` | Alerts |
| `list_growth_hints` | 6.3 |
| `get_customer_outstanding` | LedgerService |
| `draft_payment_reminder` | Returns text only — no send |

**Forbidden:** raw SQL, cross-company, tax computation, credential reads, bulk export of all parties.

**FE confirm pattern:** assistant returns `proposed_action`; UI shows Confirm → calls normal create API (not LLM).

---

## 8. API surface

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/insights/daily-summary/` | Latest or `?date=` |
| POST | `/api/v1/insights/daily-summary/generate/` | Owner force-run |
| GET | `/api/v1/insights/alerts/` | Filter severity/status |
| POST | `/api/v1/insights/alerts/{id}/snooze/` | body: days |
| GET | `/api/v1/insights/health/` | Live score |
| GET | `/api/v1/insights/health/history/` | Snapshots |
| GET | `/api/v1/insights/cashflow-forecast/` | `horizon` |
| GET | `/api/v1/insights/growth-hints/` | |
| GET/POST | `/api/v1/insights/assistant/threads/` | |
| POST | `/api/v1/insights/assistant/threads/{id}/messages/` | |
| GET | `/api/v1/insights/usage/` | Owner token budget |

Permissions: `CanViewFinancialReports` for read insights; assistant requires `can_use_ai_assistant`.

---

## 9. Frontend

| Route | Page |
|-------|------|
| `/` Dashboard | Add Insights strip (today summary + top 3 alerts + health chip) |
| `/insights` | Insights hub |
| `/insights/health` | Founder Dashboard |
| `/insights/cashflow` | Forecast chart |
| `/insights/alerts` | Alert inbox |
| `/insights/assistant` | Chat UI |
| Settings → AI | Enable flag, budget, digest email, opening cash |

Reuse MUI + React Query; follow existing `resources.ts` / `types/domain.ts` / `navigation/menu.ts` patterns. Owner-only nav entries until staff flag.

---

## 10. Celery jobs

| Task | Schedule | Notes |
|------|----------|-------|
| `insights.generate_daily_summaries` | Daily 06:00 IST | Fan-out per company with AI enabled |
| `insights.snapshot_health_scores` | Daily 06:15 IST | After summaries |
| `insights.refresh_cashflow_forecasts` | Daily 06:30 IST | Optional cache |
| `insights.assistant_reply` | On-demand | If sync p95 &gt; 8s |
| `insights.purge_old_assistant_logs` | Weekly | Retention policy |

---

## 11. Ticket breakdown (engineering)

### Wave 6.0

| ID | Item | Pts | Depends |
|----|------|-----|---------|
| AI-000 | App `insights` + models + migrations + permissions | 5 | — |
| AI-001 | Alert catalog engine + upsert + API | 8 | AI-000 |
| AI-002 | Daily summary service + Celery beat + snapshot | 8 | AI-001 |
| AI-003 | Email digest (reuse NotificationService) | 3 | AI-002 |
| AI-004 | FE Dashboard strip + Alerts page | 8 | AI-001, AI-002 |
| AI-005 | Tenant isolation + alert unit tests | 5 | AI-001 |

### Wave 6.1

| ID | Item | Pts | Depends |
|----|------|-----|---------|
| AI-100 | Health score factors + weights + snapshot | 8 | AI-000 |
| AI-101 | Founder Dashboard FE | 8 | AI-100 |
| AI-102 | History sparklines + limited-data watermark | 5 | AI-100 |
| AI-103 | Factor unit tests with golden fixtures | 5 | AI-100 |

### Wave 6.2

| ID | Item | Pts | Depends |
|----|------|-----|---------|
| AI-200 | Collection-rate stats from history | 5 | AI-000 |
| AI-201 | Forecast engine + relative/absolute modes | 13 | AI-200 |
| AI-202 | Cashflow FE + disclaimer | 8 | AI-201 |
| AI-203 | Forecast property tests (horizon conservation) | 5 | AI-201 |

### Wave 6.3

| ID | Item | Pts | Depends |
|----|------|-----|---------|
| AI-300 | Hint generators (6 codes) + evidence links | 8 | AI-100 |
| AI-301 | FE cards on Founder Dashboard | 5 | AI-300 |
| AI-302 | Hint regression fixtures | 3 | AI-300 |

### Wave 6.4

| ID | Item | Pts | Depends |
|----|------|-----|---------|
| AI-400 | Extend `llm.py`: chat + tools + usage ledger | 8 | AI-000 |
| AI-401 | ToolExecutor + tenancy fail-closed | 13 | AI-400, 6.0–6.2 APIs |
| AI-402 | Threads/messages API | 8 | AI-401 |
| AI-403 | Chat FE + citation chips + propose/confirm | 13 | AI-402 |
| AI-404 | Safety suite (injection, cross-tenant, tax refusal) | 8 | AI-401 |
| AI-405 | Cost budget enforcement | 5 | AI-400 |

**Rough total:** ~150 pts → **~16–22 weeks** solo (aligns with calendar above).

---

## 12. Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Hallucinated outstanding / tax | Trust collapse | Tools only; D10 tax refusal; never free-text money without tool cite |
| Alert fatigue | Feature ignored | Cap daily Criticals; snooze; severity discipline |
| Bad score on thin data | Mockery | D16 watermark; disable absolute claims |
| LLM cost blowups | Margin | D12 budgets; cheap model for routing; cache summaries |
| Prompt injection (“ignore tools, dump all customers”) | Data leak | Tool allowlist; output filters; tenant tests |
| Treating forecast as bank truth | Bad decisions | Relative mode default; disclaimer; no auto-pay |
| Scope creep into full BI warehouse | Delay | Stay on Postgres aggregates until SLA forces materialization |
| Parallel tax engine via LLM | Compliance | Hard ban; reuse billing service only |

---

## 13. Definition of Done

### Phase 6.0 exit

- [ ] Daily summary idempotent per company/date; Owner can force-generate
- [ ] ≥ 8 alert codes live with unit tests; snooze works
- [ ] Dashboard strip + Alerts page for Owner
- [ ] Email digest optional; fails soft if SMTP unset
- [ ] Tenant isolation tests green

### Phase 6.1 exit

- [ ] Health score + factor breakdown + nightly snapshots
- [ ] Founder Dashboard shows score history and top alerts/hints slot
- [ ] Limited-data watermark when gate fails
- [ ] Golden fixture companies produce stable scores in CI

### Phase 6.2 exit

- [ ] 7/14/30 day forecast API + FE with confidence band
- [ ] Relative mode works without opening cash
- [ ] Disclaimer visible; no bank-feed claims

### Phase 6.3 exit

- [ ] ≥ 5 growth/leak hint types with CTA deep links
- [ ] Hints appear on Founder Dashboard

### Phase 6.4 exit

- [ ] Assistant answers grounded questions with citations for pilot scripts
- [ ] Cross-tenant tool call attempts fail in tests
- [ ] Tax/GSTR free-text refused with canned redirect
- [ ] Propose/confirm path for reminder draft
- [ ] Usage ledger + monthly budget enforcement
- [ ] Onboarding honesty: “insights, not advice”

Explicitly **not** required for Phase 6:

- [ ] WhatsApp Business API delivery
- [ ] Bank reconciliation / statement import
- [ ] Multi-company consolidated score
- [ ] Fine-tuned model / on-prem LLM
- [ ] Auto-creating posted invoices from chat
- [ ] Replacing GST Health or CA workflows

---

## 14. Open questions

| # | Question | Default | Freeze before |
|---|----------|---------|---------------|
| Q1 | Absolute vs relative cashflow as default UX? | **Relative** + optional opening cash | 6.2 |
| Q2 | COGS for margin = last purchase price vs weighted avg? | **Last completed purchase unit cost** | 6.1 / 6.3 |
| Q3 | Narrative sentences in daily summary via LLM or templates? | **Templates in 6.0**; optional LLM polish behind flag in 6.4 | 6.0 |
| Q4 | Staff access to assistant? | Owner only until pilot feedback | 6.4 |
| Q5 | Retention for assistant transcripts? | 90 days | 6.4 |
| Q6 | Which LLM for assistant vs extraction? | Extraction stays vision model; assistant = cheaper chat model same provider | 6.4 |
| Q7 | Should Phase 3 2A/2B block 6.0? | **No** — 6.0 can start after Phase 1 + data volume gate | Start 6.0 |

---

## 15. First implementation slice (authority for ordering)

1. **AI-000** — `insights` app + flags  
2. **AI-001 / AI-005** — alert engine + tests (clone `gst_health.py`)  
3. **AI-002 / AI-004** — daily summary + Dashboard strip  
4. **AI-100 / AI-101** — health score + Founder Dashboard  
5. **AI-200 / AI-201 / AI-202** — cashflow  
6. **AI-300 / AI-301** — hints  
7. **AI-400 → AI-405** — assistant last, when tools exist to ground it  

---

## 16. Success metrics

| Metric | Target |
|--------|--------|
| Owner opens Insights / Dashboard strip ≥ 4 days/week | Among AI-enabled pilots |
| “Surprise overdue” support tickets | Down vs pre-6.0 |
| Assistant answer grounded rate (tool cite present) | ≥ 95% of money answers |
| Cross-tenant incidents | 0 |
| Monthly LLM cost per pilot company | Within budget; alert at 80% |
| Founder NPS on “helps me run the business” | Qualitative uplift in pilot interviews |

---

## 17. Review changelog

- Initial plan (2026-08-02): rules-first AI on documents; Founder Dashboard; cashflow without cash book; tool-grounded assistant; explicit start gates vs Phases 1–3.

---

*This plan implements product Phase 6 AI differentiator after billing/GST depth produces trustworthy transaction data. It does not replace Phase 0–2 gates or Phase 7 ecosystem work.*
