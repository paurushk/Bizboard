# BizBoard Product Health & Observability — implementation plan

**Status:** executable. **As of:** 16 Sep 2026.
**What this is:** a mechanism to learn what is working, what is failing, where
users struggle, and what to improve next — not an operations-only dashboard.
**Stores:** System · Experience (derived) · User/Journey (central) · Business.
**Verdict:** usable **system** foundation; production incident response is not
complete; journey / experience / business signals are fragmented and not
reviewed as a diagnostic chain.

This file is the git source of truth. The Cursor canvas
`observability-implementation-plan.canvas.tsx` is an IDE working board only —
do not treat it as launch evidence.

The goal is not to install an APM tool. The goal is:

> **Is BizBoard helping users successfully run their business, and where
> should we improve it?**

That is the stabilization question: stop adding features, get real users,
observe their journeys, use evidence to decide what to fix next.

| Area | Assessment | This plan |
|---|---|---|
| System | Strong foundation | Finish O-Gate 1 |
| Error investigation | Strong design | Request-id chain (O-Gate 2) |
| User journey | Good direction | Central layer; expand after Complete is proven |
| Experience / friction | Missing as a named layer | Derived insight, not a fifth store |
| Performance | Good targets | Convert to production SLIs (O-Gate 3); name FE UX vs API p95 |
| Business | Needs strengthening | First-class outcome layer (adoption / engagement / retention / value) |
| Founder insight | Very good concept | Journey Health table after real pilot traffic |
| Privacy | Very good | Keep strict allowlist; no client-sent persona labels |
| Scope | Excellent | Do not introduce OTel/APM yet |

---

## 1. Purpose — diagnostic chain, not four equal quadrants

**User / Journey is the central layer.** System and Experience explain *why*
a journey failed. Business asks whether success became a habit.

```text
                    BUSINESS OUTCOME
                    Adoption / retention / value
                         ↑
                  Did the user succeed?
                         ↑
                   USER JOURNEY   ← central
                   success / fail / abandon / retry / help
                         ↑
              EXPERIENCE / PERFORMANCE
              latency · UX wait · PDF · friction
                         ↑
                SYSTEM / INFRASTRUCTURE
                Sentry / logs / DB / Redis / Celery
```

| Layer | Question | Output |
|---|---|---|
| **System** | Is the platform technically healthy? | Page a human |
| **Experience** | Did it *feel* fast and unblocked? (derived) | UX wait, retries, help, validation — even when the API returned 200 |
| **User / Journey** | Can users finish the important task? | Funnel + **why they failed** |
| **Business** | Did BizBoard become daily operations? | Adoption, engagement, retention, value |

Do not conflate **stores**: Sentry/logs/`/metrics` are ops. `ShopFloorEvent`
and `HelpEvent` are product analytics. **Experience** is not a new table —
it is computed from journey events + help + duration. The founder **Product
Health** screen sits above all of them.

A system can be 100% healthy while the product is failing users. Abandonment
and help-opens are a **product review**, never a 3am page.

### Two diagnostic chains (the point of the model)

```text
Invoice completion ↓ 18%
        ↓
Users abandoning Complete
        ↓
Complete latency 0.8s → 2.4s
        ↓
DB query latency up
        ↓
Specific endpoint/query   → SYSTEM fix
```

```text
Invoice completion ↓
        ↓
No system errors
        ↓
Help opens ↑
        ↓
Users are confused        → UX / workflow fix
```

---

## 2. Principles

1. **Journey first.** Instrument critical workflows, not every button. Journey
   is the hub; other layers explain it.
2. **Combine signals, do not conflate stores.** Ops vs product analytics stay
   separate; Product Health reads both.
3. **Privacy by design.** `company_hash`, `session_id`, `request_id`. Never
   GSTIN, customer names, invoice numbers, raw company IDs, or other PII.
4. **Small canonical event model.** One envelope; reuse it. Reject unknown keys.
5. **Observe SLIs, not just targets.** `list p95 < 2s` and `Complete p95 < 800ms`
   become production series, not only `load/k6_slo.js`.
6. **Users feel wait, not p95.** “API p95 = 700ms” is not the same as “click,
   nothing happens for 3 seconds.” Name both.
7. **Action over dashboards.** Every signal has a decision, an owner, or an
   investigation.
8. **Page on System. Review Journey / Experience / Business.**

---

## 3. Experience Health (derived — not a fifth store)

Track proxies of perceived friction. A journey that eventually succeeds can
still be high-friction:

```text
Open → error → retry → help → back → try again → success
Technical: SUCCESS    User: HIGH FRICTION
```

**Signals (reuse events; do not invent a “friction score” in Gate 2).**
Retry counts per `session_id` **depend on the Gate 2 migration** (OG2-E7
adds `session_id` to `ShopFloorEvent`). Do not implement Experience
rollups until that column exists and Complete started/failed is shipping.

| Proxy | Source |
|---|---|
| Time to complete journey | `duration_ms` on completed / failed |
| Retries / repeated Complete clicks | count of `journey_started` per `session_id` before a terminal event (**needs OG2-E7 `session_id`**) |
| Validation failures | `failure_reason=validation` |
| Help opened | `HelpEvent` in **`core.models`** (not `insights`) — screen only; query text stays on-box. Gate 3 is a **cross-app** join to `ShopFloorEvent` |
| Abandonment | started with no completed/failed in session |
| 5xx / timeout / offline | `failure_reason` enum |
| Successful completion | existing `event=invoice_complete` rows |

**Gate 3 Product Health exposes (not a weighted index at first):**

- average retries per starter
- % starters who retry
- % starters who open help
- % starters who fail validation
- median and p95 journey duration (started → terminal)

Do **not** instrument back-navigation or “unexpected workflow exits” until
Complete started/failed is proven (Gate 2). Those are Gate 3 STEP-lite, still
allowlisted.

---

## 4. Why did the user fail? (core Product Health view)

Do not stop at `Complete success = 82%`. Split the 18%:

```text
Complete failure = 18%
├── validation       7%
├── timeout          4%
├── 5xx              2%
├── offline          3%
├── help_code        1%
└── unknown          1%
```

`failure_reason` is already in the canonical enum (`validation`, `help_code`,
`timeout`, `5xx`, `offline`, `unknown`). **Require it on every
`journey_failed`.** Unknown must shrink over time; do not add free-text
messages or invoice numbers.

Gate 2: persist the enum on Complete failed. Gate 3: this breakdown is a
first-class tile on Product Health (alongside Journey Health).

---

## 5. Current coverage (do not rebuild)

| Dimension | What exists | Gap |
|---|---|---|
| **System** | `HealthView` + beat heartbeat; JSON access logs; `trace_span` on Complete/PDF/webhook; optional Sentry SDK; 1 process-local `/metrics` counter; DLQ + circuit breaker | Sentry not live; no 5xx/queue/DLQ gauges; SPA does not send `request_id`; workers unstructured |
| **Experience** | ShopFloor `complete_p95_ms` (success only); k6 synthetic | No retries/help/validation split; user wait ≠ API p95; no FE interaction delay |
| **User / Journey** | `ShopFloorEvent` (`insights`): signup_completed, wizard_*, invoice_complete (success only), POS, offline. `HelpEvent` lives in **`core.models`** | No started/failed for Complete; no envelope columns; `failure_reason` unused; Gate 3 help join is **cross-app** |
| **Business** | Funnel counts; Smart Alerts inbox (AR/stock) | Not a first-class outcome layer: no adoption / engagement / retention / “daily operations” |

Privacy already in place (keep): hashed user/company on access logs, GSTIN and
document-number redaction, no query strings, telemetry allowlist,
`send_default_pii=False`.

---

## 6. Canonical event model

One envelope for **User/Journey** and **Business** product events. System
logs/metrics do not use this table.

```text
USER_ACTION → JOURNEY_STARTED → STEP_* (Gate 3 only)
           → JOURNEY_COMPLETED | JOURNEY_FAILED | ABANDONED
```

**Allowed fields** (reject anything else, same posture as today’s telemetry POST):

| Field | Notes |
|---|---|
| `event` | Existing enum **plus** `journey_started` / `journey_failed`. Success continues to use `invoice_complete` (see write/read semantics below). `journey_completed` is reserved for a later FE migration; Gate 2 does **not** write it |
| `journey` | Allowlisted name. **Stored** (new column). Server stamps on `invoice_complete` POSTs |
| `feature` | Optional. **Stored** (new column). Same allowlist as journey or a child (`pos`, `offline`) |
| `role` | **Stored** (new column). Server may overwrite from `CompanyUser.role`; never a person name |
| `company_hash` | **Not a stored column.** Derive on read/export from `ShopFloorEvent.company_id` with the same 12-char SHA as `RequestIdMiddleware._hash_id`. Never accept it from the client; ignore if sent. Store the FK only. |
| `session_id` | Opaque UUID from SPA; **stored** (new column). Not a user pk |
| `request_id` | Same UUID as `X-Request-ID`; **stored** (new column, indexed) |
| `duration_ms` | Existing column |
| `success` | bool on completed/failed; **stored** (new column, nullable on legacy rows) |
| `failure_reason` | **Required** on `journey_failed`. Enum only (`validation`, `help_code`, `timeout`, `5xx`, `offline`, `unknown`). **Stored** (new column). Not a message, not an invoice number |
| `timestamp` | Server `created_at` / `occurred_on` — already on the model. Do not add a duplicate client timestamp field |

**Never:** GSTIN, customer names, invoice numbers, raw company IDs, query text,
line descriptions, phone, email. **Never** accept a client-sent persona /
archetype / “kirana” label.

### Freeze journey allowlist (Gate 2)

Instrument these only. Not every button.

| Journey | Started | Completed | Failed / abandoned |
|---|---|---|---|
| `signup` | wizard tax click; empty Regular GSTIN | existing `signup_completed` / wizard_* | `journey_failed` (validation / help_code) |
| `invoice_complete` | **add** | existing `invoice_complete` | **add** (today success-only) |
| `pdf` | enqueue (`journey_started`) | `pdf_status=READY` (not dual-write) | generate fail → `journey_failed` |
| `payment` | `create_payment_link` | `allocation_reconciled` | DLQ park → `journey_failed` `5xx` |

Gate 3 may add: `add_item`, `invoice_draft`, `sales_return`, `search`,
`stock_adjustment`. Help stays on `HelpEvent` (`core.models.HelpEvent`;
query text on-box). Weekly insight is a **cross-app** join to
`insights.ShopFloorEvent` — do not assume same-app queryability.

**Store split:** keep writing product events to `ShopFloorEvent`. Do not
write them to Sentry. Do not page on-call on `abandoned`.

### Locked write/read semantics (decide now, before data lands)

**Do not dual-write.** One Complete success = **one** row. Existing FE keeps
POSTing `event=invoice_complete`. The server **stamps** `journey=invoice_complete`
and `success=true` on that row. New FE also POSTs `journey_started` /
`journey_failed` (new `Event` enum values). Do **not** also insert
`event=journey_completed` for the same success — that would double-count.

**Read-side UNION (OG2-E8 summary and later Journey Health):**

| Funnel bucket | Query |
|---|---|
| Started | `event=journey_started` AND `journey=invoice_complete` |
| Completed | `event=invoice_complete` **OR** (`event=journey_completed` AND `journey=invoice_complete`) — the OR is for a later FE migration; Gate 2 writers only produce the first form |
| Failed | `event=journey_failed` AND `journey=invoice_complete` |

**Historical caveat:** pre-Gate-2 `invoice_complete` rows have **no started
denominator**. Journey Health completion rate is only valid for
`occurred_on` on/after the Gate 2 ship date (record that date in the
sign-off table). Do not compute 82% against all-time completes.

### OG2-E7 is a migration, not an allowlist one-liner

Today `ShopFloorEvent` has `event`, `duration_ms`, `tap_count`, `occurred_on`
plus the company FK (`insights/models.py`). Canonical envelope fields that
must be **new nullable columns**:

| Column | Index |
|---|---|
| `journey` | composite `(company, journey, occurred_on)` for funnel queries |
| `feature` | none |
| `role` | none |
| `session_id` | optional `(company, session_id)` if retry counts need it |
| `request_id` | **yes** — OG2-E9 Support-ID join |
| `success` | none |
| `failure_reason` | none (filter after journey) |

**Do not add `company_hash`.** Derive it when serializing or exporting, same
helper as access logs.

Also: extend `ShopFloorEvent.Event` with `journey_started`, `journey_failed`
(and `journey_completed` only if/when FE migrates; not required for Gate 2
writes). Extend POST allowlist: `event`, `duration_ms`, `tap_count`,
`journey`, `feature`, `role` (optional; server may overwrite from
`CompanyUser`), `session_id`, `request_id`, `success`, `failure_reason`.
Reject unknown keys. Ignore client `company_id` / `company_hash`.

This is the **largest engineering unit in Gate 2**. Size it as a migration +
model + view + FE telemetry helper + tests, not a one-line allowlist change.

---

## 7. Implementation gates

Gates serialize **how** we build. The diagnostic chain describes **what** we
are building toward. Do not skip Gate 1 to instrument journeys.

```text
O-Gate 1  SYSTEM can tell me something broke
O-Gate 2  I can reconstruct what happened
          (request_id + Complete started/failed + failure_reason)
O-Gate 3  I can explain why users struggle
          (Experience, Journey Health, SLIs, cohorts, business depth)
          ↓
          Founder Product Health — I know what to improve
```

The **mandatory stop after Gate 2** stands. Do not build an observability
platform before users. Do **not** implement roadmap O-03 (OpenTelemetry,
burn-rate engine, capacity dashboard) until Gate 1 and 2 have evidence.

---

## 8. Out of scope until the named gate

| Do not | Until |
|---|---|
| OpenTelemetry / Jaeger / Tempo | O-Gate 3 |
| Datadog / New Relic | After Sentry is live and `/metrics` answers 5xx + queues |
| Grafana + Loki cluster | O-Gate 3 (log ship) |
| Per-route / per-tenant histogram labels | O-Gate 3; hashed ids on logs/events only |
| Signed customer SLO / error-budget freeze automation | Human signs `docs/ops/SLO.md`, then O-Gate 3 |
| Instrument every button / STEP_* events | O-Gate 3, still allowlisted |
| Page on-call for journey abandonment, help opens, or high friction | Never — product review |
| Treat `ShopFloorEvent` as ops monitoring | Never — combine only at insight |
| Client-sent persona / archetype / shop-name labels | Never |
| Weighted “Friction Index” formula | Never in Gate 2; Gate 3 may still prefer raw proxies |
| Dual-write `invoice_complete` + `journey_completed` for one success | Never |
| Stored `company_hash` column on `ShopFloorEvent` | Never — derive from FK |
| Queryable Support-ID join UI / Loki | O-Gate 3 |

---

## O-Gate 1 — System: I know something is broken

**Dimension:** System. **Must have:** production Sentry, backend + frontend +
Celery errors, a test event that notifies a named human, health/readiness
(already done), basic operational metrics.

Until this lands, a 500 is a JSON log line. Journey analytics cannot save a
dark error path.

### Human

| ID | Action | Evidence |
|---|---|---|
| OG1-H1 | Create a Sentry org/project (one project is enough; tag `runtime=django\|celery\|browser`). | Project URL |
| OG1-H2 | Set `SENTRY_DSN` on API/worker/beat. Set `VITE_SENTRY_DSN` for the SPA **image rebuild**. Set `SENTRY_RELEASE` to the deploy SHA/tag. | Env on the host, not committed |
| OG1-H3 | Fill `docs/ops/ONCALL_ROSTER.md` weekday IST 09–21 (name + how they are paged). Sentry email or Slack is enough; PagerDuty is optional. | Named primary |
| OG1-H4 | Run `python manage.py sentry_test_event`. Confirm the event in Sentry **and** that the on-call person was notified. Paste the event id into `docs/ops/HYPERCARE.md` day-0 and `docs/pilot/GO_NO_GO.md` / ENV_CHECKLIST row 18. | Event id + “I received the page” |
| OG1-H5 | Set a non-empty `METRICS_TOKEN` on the API. Scrape `/metrics` with `Authorization: Bearer …`. | Token in host env; scrape 200 |

### Engineering

| ID | Action | Files | Done when |
|---|---|---|---|
| OG1-E1 | Tag every Sentry event with `request_id` (if present), `company_hash` (12-char SHA, same as access logs), `environment`, `release`. Do not set `user.email`. | `backend/config/settings.py`; `web/src/main.tsx` / `ErrorBoundary.tsx` | Events have `environment` + `release`; joinable by `request_id` once Gate 2 lands |
| OG1-E2 | Expand `MetricsView` — still Prometheus text, still Bearer `METRICS_TOKEN`, still no `prometheus_client`. | `backend/core/views.py`, `middleware.py`, `config/celery.py`, `tests/errors/test_ops_contracts.py` | `/metrics` includes the series below |
| OG1-E3 | Document `METRICS_TOKEN`, `SENTRY_DSN`, `SENTRY_RELEASE`, `SENTRY_TRACES_SAMPLE_RATE`, `VITE_SENTRY_DSN` in env examples. | `.env.production.example`, `.env.staging.example`, `web/.env.example` | Operator can copy without reading settings.py |
| OG1-E4 | Optional owner-ready flag `sentry_configured: bool`. Never the DSN. | `HealthView` | Owner sees whether error reporting is configured |

### Minimum `/metrics` series (System)

Process-local HTTP counters are acceptable for gunicorn. Gauges that already
live in Redis/DB must be read from there.

| Series | Type | Source |
|---|---|---|
| `bizboard_http_requests_total` | counter | existing, keep |
| `bizboard_http_5xx_total` | counter | `RequestIdMiddleware` when `status >= 500` |
| `bizboard_http_request_duration_ms_sum` + `_count` | counter | same middleware — mean only; histograms are Gate 3 |
| `bizboard_pdf_queue_depth` | gauge | existing `probe_infra` Redis `LLEN` |
| `bizboard_celery_task_failure_total` | counter | Celery `task_failure` signal |
| `bizboard_dead_letter_events` | gauge | `DeadLetterEvent` count |
| `bizboard_circuit_open` | gauge | `1` if any `cb:*:open_until` is in the future |
| `bizboard_health_db` / `_redis` / `_celery` / `_beat` | gauge 0/1 | reuse `HealthView` / `probe_infra` (~15s cache) |

No per-route or per-tenant labels.

### O-Gate 1 DoD

- [ ] `sentry_test_event` id pasted; on-call confirms they were notified
- [ ] Unhandled Django 500, SPA render error, and Celery PDF failure appear in Sentry
- [ ] `GET /metrics` with Bearer returns the series table
- [ ] `GET /api/v1/health/` and `?ready=1` still behave as today
- [ ] ENV_CHECKLIST row 18 / GO_NO_GO Sentry row can be checked by a Human

---

## O-Gate 2 — I know what happened

**Dimensions:** System correlation **and** the freeze canonical event model.
**Must have:** end-to-end `request_id`, worker `task_id`, Support ID on the
error screen, Complete **started / succeeded / failed** with **required
`failure_reason`**.

**Correlation is manual.** Gate 2 DoD is: a human can grep the same
`request_id` in (1) the UI Support ID, (2) API JSON access log, (3) worker
JSON log, (4) Sentry search, (5) `ShopFloorEvent`. There is **no** queryable
join view, Loki index, or support console. That join view is Gate 3 (log
ship). Do not promise a founder “reconstruct what happened” as a product
feature in this gate.

```text
Browser  →  X-Request-ID  →  API  →  Complete / webhook
                │                      ↓
                │                 Celery JSON log
                │                      ↓
                ├──────── Sentry tags (System)
                └──────── ShopFloorEvent (Journey), same request_id
                grep by hand  ←  Gate 2
                indexed join  ←  Gate 3
```

### Engineering — System correlation

| ID | Action | Files | Done when |
|---|---|---|---|
| OG2-E1 | SPA: generate a UUID; send `X-Request-ID`; persist last id for the error screen. | `web/src/api/client.ts` | Network tab shows the header on Complete |
| OG2-E2 | ErrorBoundary and hard API 500 toast: “Support ID: …”. Copy-friendly. No stack traces in production. | `ErrorBoundary.tsx`; API error helper | Owner can read the id without DevTools |
| OG2-E3 | JSON 500 envelope includes `error.request_id`. Known 4xx unchanged. | `core/exceptions.py` | Contract test on unhandled exception |
| OG2-E4 | Pass `request_id` on money-path `.delay()`. Celery prerun/postrun/failure emit one JSON line: `task, task_id, request_id, company_hash, status, duration_ms, retry_count, error`. | `config/celery.py`; `sales/services.py`; notifications; payments | Worker log greps the same id as the API access log |
| OG2-E5 | Sentry tags: `request_id`, `task_id`, `company_hash`. | middleware + celery prerun + ErrorBoundary | Sentry search `request_id:<uuid>` hits API and worker |
| OG2-E6 | Keep `trace_span`. Add `request_id` to span extra. No new money-path span inventory. | `core/tracing.py` callers | Existing span tests pass |

### Worker log schema

```json
{
  "event": "celery.task",
  "task": "sales.tasks.generate_invoice_pdf",
  "task_id": "…",
  "request_id": "…",
  "company_hash": "a1b2c3d4e5f6",
  "status": "success|failure|retry",
  "duration_ms": 412,
  "retry_count": 0,
  "error": null
}
```

Never log invoice numbers, GSTIN, or recipient email on this line.

### Engineering — Journey event model (migration + write/read rules)

| ID | Action | Files | Done when |
|---|---|---|---|
| OG2-E7 | **Migration** on `ShopFloorEvent`: add nullable `journey`, `feature`, `role`, `session_id`, `request_id`, `success`, `failure_reason`. Indexes: `request_id`; `(company, journey, occurred_on)`. Do **not** add `company_hash`. Extend `Event` with `journey_started`, `journey_failed`. Extend POST allowlist; reject unknown keys; ignore client `company_hash`/`company_id`. Server stamps `journey` + `success` on legacy `invoice_complete` POSTs. | `insights/models.py`, new migration, `insights/views.py`, `web/src/lib/telemetry.ts`, tests | Schema + allowlist tests green; extra keys 400; hash not stored |
| OG2-E8 | Complete funnel writes: `journey_started` on click; keep **one** `invoice_complete` row on success (no dual-write of `journey_completed`); `journey_failed` + required `failure_reason` on blocked / 5xx / timeout / offline / help_code. Summary query uses the UNION in §6. Owner dashboard Counter table shows started / completed / failed and Complete reason chips. | Complete-gate UI + `DashboardPage`; `insights/views.py` GET summary | Owner summary: started vs completed vs failed, **failed grouped by reason**; `complete_count` still matches one row per success |
| OG2-E9 | Attach `request_id` / `session_id` on those events. Join to Support ID is **grep**, not a UI. | same | One failed Complete: the id appears in UI, access log, worker log (if PDF), Sentry, and `ShopFloorEvent.request_id` |

Do **not** add STEP events, search, add-item, sales-return, back-navigation,
cohort labels, or a friction formula in this gate. Help joins and Journey
Health table are Gate 3.

### O-Gate 2 DoD

- [ ] Failed Complete: UI shows Support ID; **manual grep** finds that id in the API JSON access log, worker JSON log (if PDF), Sentry, and `ShopFloorEvent.request_id`. No join UI.
- [ ] Complete started vs completed is visible on the telemetry summary for **post-cutover** days only
- [ ] One success still produces **one** `invoice_complete` row (no dual-write)
- [ ] Failed rows always have `failure_reason` in the allowlisted enum
- [ ] `company_hash` is not a DB column; export/serializer uses `_hash_id(company_id)`
- [ ] Beat / periodic tasks log `request_id: null` and still include `task_id` + derived `company_hash`
- [ ] Telemetry still rejects GSTIN / invoice number / unknown keys / client-sent persona / client-sent `company_id`
- [ ] Tests: middleware echo, 500 envelope, client header, celery JSON log, migration columns + indexes, Complete started/failed + reason, allowlist, no dual-write count

---

## O-Gate 3 — I know why users struggle (Product Health)

Start only after Gate 1 and 2 are evidenced **and** at least one real pilot
tenant is generating traffic. This is roadmap O-03 **plus** Experience
proxies **plus** Journey Health **plus** deeper business **plus** a founder
Product Health view.

### Journey Health (primary founder instrument)

Not a generic KPI strip. One row per freeze journey:

| Journey | Started | Completed | Failed | Abandoned | p95 | Help % | Health |
|---|---:|---:|---:|---:|---:|---:|---|
| Invoice Complete | 1,000 | 820 | 80 | 100 | 1.7s | 12% | Investigate |
| PDF | 820 | 790 | 20 | 10 | 110s | 4% | Monitor |
| Payment | 500 | 465 | 25 | 10 | 2.1s | 3% | Monitor |

Numbers above are **illustrative**. Health is a Human label (Investigate /
Monitor / OK), not an auto-page. Drill-down on Failed is the
`failure_reason` breakdown from §4.

**Baseline:** completion rate (completed / started) is only valid on/after
the Gate 2 ship date recorded in the sign-off table. Pre-cutover
`invoice_complete` rows have no `journey_started` parent — do not use them
as the denominator.

Invoice journey shape (add steps only if Complete funnel is already trusted):

```text
Started → Draft → Validation → Complete → PDF → Payment → Done
```

Example: 100 started → 94 draft → 88 attempted Complete → 76 completed →
71 PDF → 65 payment. That is more useful than “APIs returned 200.”

### Experience / friction (still derived)

Expose the proxies in §3 **after OG2-E7 `session_id` exists**. Join
`core.HelpEvent` (screen only, no query text in the rollup) to
`insights.ShopFloorEvent` — **cross-app**; do not assume a single queryset.
Optional first-party FE timings:

| Backend (user does not see this) | Frontend (user feels this) |
|---|---|
| API p50 / p95 / p99 | Page load, first meaningful paint |
| DB / slow query | Route transition |
| Celery / PDF / GSP / Razorpay / SMTP | Interaction delay (“click → wait”) |
| 5xx rate | API wait time on the client, JS error rate |

Frontend RUM stays first-party and PII-free. No third-party session replay.

### Performance — turn targets into SLIs

| SLI | Draft target (unsigned) | Source today | Gate 3 |
|---|---|---|---|
| Invoice list p95 | &lt; 2s | `load/k6_slo.js` | Histogram on route class `invoice_list` |
| Complete p95 | &lt; 800ms | k6 + ShopFloor success p95 | Histogram **including** failures; also **click-to-done** if FE wait is collected |
| PDF ready | 99% within 120s | `docs/ops/SLO.md` draft | From `pdf_status` timestamps |
| Dashboard first paint | observation only | QOS-0016 Playwright 15s | Human signs a p95, then a series |
| Webhook 2xx | 99.5% | SLO draft | From access logs / middleware |

Human must sign `docs/ops/SLO.md` before burn-rate alerts. Alert on 2h/1d
burn, not a single 503.

### Privacy-safe cohorts (not client labels)

Do **not** send “Kirana” / “Medical shop” from the browser. Gate 3 rollups
may **server-join** Journey Health to existing account attributes only:

| Cohort key | Derived from (examples) |
|---|---|
| `role` | `CompanyUser.role` (already on the event as `role`) |
| `registration` | `Company.registration_type` (REGULAR / COMPOSITION / UNREGISTERED) |
| `multi_godown` | godown count &gt; 1 |
| `pos` | POS enabled for the company |
| `pilot_arch` | ops-set freeze cohort on the company (ARCH-01 / ARCH-03 / ARCH-04), **if** that field is added for beta — not guessed from GSTIN or trade name |

82% Complete overall vs 91% / 73% by cohort is how we see where the product
struggles. If no trusted attribute exists, do not invent one in telemetry.

### Business — first-class outcome layer

Repeat usage matters more than signup count.

| Slice | Signals |
|---|---|
| **Adoption** | Registered shops → activated (wizard completed) → first invoice → first payment → recurring (completes on ≥2 distinct days) |
| **Engagement** | Invoices / shop, payments / shop, stock ops / shop, active days / shop |
| **Retention** | D1 / D7 / D30 shops with ≥1 Complete (or login if Complete is too sparse) |
| **Value** | “Did BizBoard become part of daily operation?” — recurring Completes in the last 7 days vs one-and-done |

Still hashed tenant, daily rollups. No GSTIN, no shop names on the chart.

### Founder Product Health (insight layer)

Owner-only. Sits **above** the diagnostic chain. Reads System gauges,
Journey Health, failure-reason split, Experience proxies, business outcomes.
Does not become a second Sentry.

| Column | Asks |
|---|---|
| System | What broke? |
| Journey + Experience | Why did the user struggle? |
| Business | Did value happen? |

Every tile names an **owner** and a **next action** (page / product review /
capacity / ignore).

### Platform (still Gate 3)

| Item | Notes |
|---|---|
| RED metrics per endpoint class | `backend/core/metrics.py` may exist. Route **class** labels, not raw paths. |
| Log ship + retain | Vector/Loki or CloudWatch; index `request_id`. |
| Capacity dashboard | `pg_stat_activity`, Redis memory, Celery active, FileAsset bytes; 2× headroom. |
| OpenTelemetry | Replace `trace_span` **internals** only; keep the contextmanager. |

---

## Sprint sequence (do this next)

| Step | Lane | Gate | Layer | Work |
|---|---|---|---|---|
| 1 | Human | 1 | System | OG1-H1…H3 — Sentry project + roster + env (API **and** SPA rebuild) |
| 2 | LLM | 1 | System | OG1-E2, E3 — `/metrics` series + env docs |
| 3 | LLM | 1 | System | OG1-E1, E4 — Sentry tags + optional `sentry_configured` |
| 4 | Human | 1 | System | OG1-H4, H5 — test event, page received, metrics scrape |
| 5 | LLM | 2 | System | OG2-E1…E6 — request_id chain + worker JSON logs |
| 6 | LLM | 2 | Journey | OG2-E7 **migration** + E8/E9 — no dual-write; failure_reason; grep by request_id |
| 7 | Split | 2 | Combined | Staging: one broken Complete; join UI Support ID → log → Sentry → ShopFloorEvent |
| 8 | **Stop** | — | — | Do not open O-Gate 3 / Journey Health / founder-dashboard / OTel tickets |

Steps 2–3 and 6 may overlap with earlier steps. Step 4 cannot precede step 1.
Step 8 is mandatory: evidence that improves BizBoard, not an observability
platform before users.

---

## Scoreboard

Engineering for O-Gate 1 and O-Gate 2 is in this repo. Human Sentry/on-call
and the staging grep walk stay open. **O-Gate 3 is not started.**

**Gate 2 ship date (for Journey Health denominators):** 16 Sep 2026. Pre-cutover
`invoice_complete` rows have no `journey_started` parent.

| ID | Lane | Status | Evidence |
|---|---|---|---|
| OG1-H1 | Human | Open | Sentry project URL |
| OG1-H2 | Human | Open | Host `SENTRY_DSN` / `VITE_SENTRY_DSN` / `SENTRY_RELEASE` |
| OG1-H3 | Human | Open | Named primary on `docs/ops/ONCALL_ROSTER.md` |
| OG1-H4 | Human | Open | `sentry_test_event` id + page received |
| OG1-H5 | Human | Open | Non-empty `METRICS_TOKEN`; scrape 200 |
| OG1-E1 | Eng | Done | Sentry tags `request_id` + `company_hash`; SPA `beforeSend` |
| OG1-E2 | Eng | Done | `/metrics` series table (no `prometheus_client`) |
| OG1-E3 | Eng | Done | Env examples document `METRICS_TOKEN` + `SENTRY_*` + `VITE_SENTRY_DSN` |
| OG1-E4 | Eng | Done | Owner `?ready=1` includes `sentry_configured` (never the DSN) |
| OG2-E1 | Eng | Done | SPA sends `X-Request-ID`; `getLastRequestId()` |
| OG2-E2 | Eng | Done | ErrorBoundary + 500 `HelpErrorAlert` show Support ID |
| OG2-E3 | Eng | Done | JSON 500 envelope `error.request_id`; 4xx unchanged |
| OG2-E4 | Eng | Done | Celery header inject + JSON task log |
| OG2-E5 | Eng | Done | Sentry tags on API, worker, browser |
| OG2-E6 | Eng | Done | `trace_span` extra `request_id` |
| OG2-E7 | Eng | Done | Migration `insights.0008`; no stored `company_hash` |
| OG2-E8 | Eng | Done | Complete started/failed + UNION summary; owner Counter table |
| OG2-E9 | Eng | Done | Events carry `request_id` / `session_id` for grep |
| OG2 freeze journeys | Eng | Done | signup failed + pdf + payment stamps; no dual-write of PDF complete |
| OG2 help_code | Eng | Done | SPA maps listed 4xx help codes (not all 4xx) |
| OG2 ops docs | Eng | Done | `docs/ops/OGATE_HUMAN.md`, `OGATE_GREP_WALK.md`, `observability_gate_check` |
| OG2 walk | Split | Open | Staging: grep one Support ID across UI / log / worker / Sentry / ShopFloorEvent |
| O-Gate 3 | — | Deferred | Journey Health, RED, OTel, founder dashboard |

DoD checkboxes in §O-Gate 1 / §O-Gate 2 stay Human-owned where they require a
live Sentry page or a staging grep.

---

## Related

| Doc | Role |
|---|---|
| `docs/pilot/GO_NO_GO.md` | Final Gate: Sentry DSN + on-call |
| `docs/pilot/ENV_CHECKLIST.md` row 18 | Same evidence |
| `docs/ops/OGATE_HUMAN.md` | Human Sentry/on-call steps (do not invent names/DSN) |
| `docs/ops/OGATE_GREP_WALK.md` | Staging Support-ID grep (Gate 2 DoD) |
| `docs/ops/ONCALL_ROSTER.md` | Fill names |
| `docs/ops/HYPERCARE.md` | Paste test event id |
| `docs/ops/ALERTS.md` | System runbooks; do not invent GST advice in a page |
| `docs/ops/SLO.md` | Draft SLIs; Gate 3 observes them continuously after Human sign |
| `docs/ops/SLO_DRIFT.md` | Monthly meeting until Gate 3 automation |
| `docs/FREEZE_SCOPE.md` H5 | Health/metrics smoke already SUP |
| `docs/HOLISTIC_VALIDATION_REVIEW.md` | Quality model — this plan supplies production evidence for journeys |
| `qos/backlog/QOS-0016.yaml` | Dashboard render budget; Gate 3 SLI |
| Roadmap O-03 | Subset of O-Gate 3 (RED, burn-rate, OTel, capacity) |

---

## Sign-off

| Gate | Role | Name | Date | Evidence |
|---|---|---|---|---|
| O-Gate 1 | Ops / Founder | | | sentry event id + page received |
| O-Gate 2 | Eng | code 16 Sep 2026 | | Gate 2 ship date recorded; no dual-write. Staging **manual grep** still open |
| O-Gate 3 | Founder | deferred | | Journey Health **post-cutover only**; signed SLOs |
