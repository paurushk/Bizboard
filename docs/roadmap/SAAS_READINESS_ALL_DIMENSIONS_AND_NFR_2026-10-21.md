# SaaS readiness — all 9 dimensions and non-functional requirements

**Date:** 2026-10-21 · **Status:** proposal, nothing built · **Owner:** Founder + Eng + Ops + CA + Counsel

This is the one-page view across **every readiness dimension** and **every
non-functional requirement (NFR)**. It does not replace the detailed trackers;
it scores them on one scale and orders the work.

| Source | What it holds |
|---|---|
| [BUSINESS_ARCHETYPES_AND_PERSONAS.md §9](../BUSINESS_ARCHETYPES_AND_PERSONAS.md) | The 9 readiness dimensions |
| [SAAS_READINESS_EXECUTION_PLAN.md](../SAAS_READINESS_EXECUTION_PLAN.md) | 17 phases, 148 steps, gates G1–G17 (status as of 16 Sep) |
| [OBSERVABILITY_IMPLEMENTATION_PLAN.md](../OBSERVABILITY_IMPLEMENTATION_PLAN.md) | O-Gates 1–3 |
| [SAAS_READINESS_DIM6_ACCOUNTING_CORRECTNESS_2026-10-21.md](SAAS_READINESS_DIM6_ACCOUNTING_CORRECTNESS_2026-10-21.md) | Detailed plan for dimension 6 |
| `docs/ops/*.md`, `qos/backlog/*.yaml` | Runbooks and per-item status |
| [SAAS_READINESS_IMPLEMENTATION_PLAN_2026-10-21.md](SAAS_READINESS_IMPLEMENTATION_PLAN_2026-10-21.md) | Work packages, files, tests and order for everything below |

---

## 1. The scale

Every row is scored on **evidence**, not on code written.

| Level | Meaning |
|---|---|
| **L0** | Not built |
| **L1** | Built and tested in the repo / CI |
| **L2** | Proven on a **hosted** staging environment (not a laptop) |
| **L3** | Proven with **real tenants** (beta businesses) |
| **L4** | Gate **signed** by the named human |

SaaS launch needs every row at **L4**. Paid beta needs every row at **L3**, or
waived in writing.

**Update 2026-10-22:** the engineering half of every row below is now built and tested (see
[SAAS_READINESS_HANDOVER_2026-10-22.md](SAAS_READINESS_HANDOVER_2026-10-22.md)). Levels do not
change until hosted staging and people produce dated evidence, so the rows still read L1/L0.

The main finding: **almost everything is at L1.** The repo work is broad and
deep. What's missing is a hosted environment, real users and signatures. Today
staging runs only on a local Compose stack (port 8081), and every gate G1–G17 is
unsigned.

---

## 2. Readiness dimensions (business view)

| # | Dimension | Level | Evidence today | Gap to SaaS |
|---|---|---|---|---|
| 1 | Functional | **L1** | CI green; coverage gate 83%; strict invariants lane; OpenAPI drift check | Much of the latest work (manufacturing, agents, jobwork, quality) is **uncommitted** on `feat/mfg-p0-foundations`. CI can't vouch for code it hasn't seen. |
| 2 | Workflow | **L1** | WF chains, golden e2e, 51 journey cells, persona tests | No end-to-end loop run by a real operator on hosted staging (QOS-0097: "UX fixes not verified on a real backend"). |
| 3 | Data / migration | **L1** | Idempotent imports, opening balances, `cutover_recon`, dry-run harness | No real customer files imported (steps 6.1–6.5 are "Human open"). |
| 4 | UX | **L1** | axe passes on audited routes; UX waves done | Untested with non-technical staff (QOS-0029). Keyboard/touch gaps (QOS-0096), missing states and English text in Hindi screens (QOS-0098), Hindi review of many modules still open. |
| 5 | Reliability | **L1** | Offline outbox, idempotency keys, circuit breakers, DLQ + replay, 10 Postgres concurrency suites | No soak test. Offline outbox not proven on real devices (H-03). |
| 6 | Accounting correctness | **L1** | See the [Dim 6 roadmap](SAAS_READINESS_DIM6_ACCOUNTING_CORRECTNESS_2026-10-21.md) | Two truth models (books on/off), flag-gated postings, nightly sweep doesn't scale, no CA letter. |
| 7 | Compliance (GST/TDS) | **L1** | Tax parity corpus F1–F8 automated; GSTR worksheets snapshot-pinned | No CA has filed from our worksheets (QOS-0004). CA sign-offs QOS-0129/0130/0136/0138/0141 open. |
| 8 | Operational | **L0–L1** | Runbooks exist for most ops tasks | No business has run a full day without an engineer (QOS-0030). |
| 9 | Commercial | **L1** | Razorpay subscriptions, entitlements, quotas, dunning, write-block | No paying customer, no prices or trial length signed (8.1), no live gateway recon (QOS-0031). |

---

## 3. Non-functional requirements

| NFR | Level | What exists | Gap to SaaS |
|---|---|---|---|
| **Observability** | **L1** | Sentry wiring for API, worker and browser with `request_id` + `company_hash`; `/metrics`; JSON task logs; Support ID shown to users; Complete-journey funnel; `observability_gate_check` | No Sentry project or DSN on a host (OG1-H1..H5). `/metrics` counters are **per-process** (no `prometheus_client`), so with several gunicorn workers they undercount. No dashboards. No per-tenant health view. No burn-rate alerts (O-Gate 3 not started). Nightly invariant failures only reach the log. |
| **Alerting & on-call** | **L0–L1** | `ALERTS.md`, Telegram paging fallback, `ONCALL_ROSTER.md` template | No named on-call person. No test page ever received. No incident-response tabletop. |
| **Availability (SLO)** | **L1** | Draft `SLO.md` (99.5% API, PDF within 120 s, …), health + ready probes | SLOs unsigned. No external uptime probe. No status page live. |
| **Performance** | **L1** | k6 smoke/SLO/mixed and locust scripts in `load/`; large-tenant seed | No executed load, soak or large-tenant run on hosted infra (QOS-0003). Dashboard render budget unmeasured (QOS-0016). Wall-clock import test was 10.2 s against a 10 s SLA on local staging. |
| **Scalability** | **L1** | Separate Celery queues (`high_priority`, `media_heavy`, `reports`), `WORKER_SCALE.md`, tenant rate limits, noisy-neighbor tests | Several nightly jobs loop over **every company in one task** (e.g. `nightly_invariants_task`). Fine at 10 tenants, not at 5,000. No pgbouncer in a real deployment. No capacity numbers signed. |
| **Multi-tenancy & isolation** | **L1** (L2 not yet: see gaps) | `company_id` everywhere, IDOR route matrix, schema constraints, RLS with a non-superuser app role (enforced on local staging), quotas, suspension, erasure | RLS proven only on local staging. `docker-compose.prod.yml` would run as the DB owner with RLS off. The pgbouncer template uses transaction mode, which isn't safe with the session-level tenant setting. Agent beat tasks (`expire_proposals`, `cancel_resolved`) see no rows under FORCE RLS. CI runs RLS tests as a superuser. Pre-auth tenant writes may hide the same RLS gap the sign-in audit had. Every new module needs RLS migrations (0064–0066 uncommitted). |
| **Security** | **L1** | httpOnly JWT cookies, CSRF, lockout, throttles, pip-audit, npm audit, STRIDE draft, audit hash chain, MFA (TOTP) for owners | No independent pentest (10.6). MFA already challenges on the password, phone-OTP and invite paths, but QOS-0103 isn't closed and there's no policy for non-owner roles. No WAF/DDoS in front. No secrets manager or KMS. Secret-rotation drill never run on a host. |
| **Privacy & legal** | **L0** | DPDP posture note, data categories, subprocessors list, erasure playbook | ToS, privacy policy, DPA, DPIA, data-residency commitment all unwritten by counsel (G16). WhatsApp consent policy needs counsel. No record of ToS/privacy acceptance and no self-serve export or erasure request in the product. |
| **Messaging registrations** | **L0** | SMS, email and WhatsApp integrations behind sandbox flags | No TRAI DLT entity or templates, no SPF/DKIM/DMARC, no approved WhatsApp templates. Phone-OTP login fails on real Indian phones without DLT. |
| **Backup & DR** | **L1** | Tenant backup/restore, local restore drill PASS (2026-09-12), BCP, DR cadence template | RPO/RTO unsigned. No off-host encrypted backup. No PITR. No failover drill. Restore isn't followed by a per-tenant invariant sweep. |
| **Data portability** | **L1** | Export, tombstone erasure, `erase_company` playbook | Not exercised for a real departing customer. Export format not documented for customers. |
| **Deployability (CI/CD)** | **L1** | Required CI jobs, SHA-tagged images, post-deploy smoke, expand/contract SOP, flag lifecycle | No hosted CD. No canary or rollback drill on a host. No release owner named. Big uncommitted tree means the next release is large and risky. |
| **Maintainability** | **L1** | Ruff and lint gates at 0 errors, `tsc -b`, Q-OS backlog, generated docs | ~100 uncommitted files across several programmes on one branch. Very large planning docs. `manufacturing/services.py` mid-split into a package. |
| **Cost efficiency** | **L1** | `UNIT_ECONOMICS.md` draft (10 / 1k / 10k tenants) | No real hosting bill. LLM spend per tenant not capped or reported on a host (agents runtime is new and uncommitted). |
| **Supportability** | **L1** | Support ID end to end, support macros, ticket taxonomy, no-impersonation test, Django admin ops tools | No staffed support channel or SLA (15.6, 16.5). Support-ID grep walk not done on staging (OG2 walk). |
| **Integrations** | **L1** | Circuit breakers, HMAC webhooks, DLQ, sandbox flags | No signed replay tests on staging. No vendor contracts. SMS DLT registration and SPF/DKIM not done. |
| **Accessibility & i18n** | **L1** | axe on audited routes, Hindi strings for most screens | Native Hindi review open in about 8 modules. Real-device and screen-reader passes open (QOS-0132). |
| **AI agents (new)** | **L0–L1** | LLM gateway with provider adapters and timeouts, agent policy, RLS on agent tables, `AGENTS_RUNBOOK.md` | Uncommitted. Daily run caps, a budget check and redaction exist in `agents/`, but none of it has been shown working on a host. Spend isn't visible in admin, there's no platform-wide cap, no test proves PII never reaches the provider, and there's no prompt-injection test set. |
| **Mobile client** | **L1** | `mobile/` app, offline stock hooks | No version-compatibility policy (oldest supported app vs newest API). No store release process. |

---

## 4. What these rows have in common

1. **Commit first.** Nothing below can be signed against a working tree. Land and tag the uncommitted programmes before starting anything new.
2. **One hosted staging moves ~15 rows from L1 to L2.** It's the single most useful step: TLS, managed Postgres with PITR, Redis, Sentry, uptime probe, off-host backups, RLS on.
3. **Per-company loops are the main scalability risk.** Nightly sweeps and reports that loop over every company must fan out per tenant before onboarding beyond a few dozen.
4. **Metrics must survive more than one worker.** Process-local counters give wrong numbers under gunicorn. Use a multi-process-safe exporter (Prometheus multiprocess mode, or push to a collector).
5. **Most remaining blockers are people:** CA, counsel, on-call person, pentester, beta businesses. Book them now; they take longest.

---

## 5. Roadmap

Item IDs use **SR-** plus the wave number. Lanes: **LLM** (built here), **Split**
(built here, a person must run or sign), **Human**.

### Wave 0 — Clean baseline (weeks 1–2)

| ID | Item | Area | Lane | Done when |
|---|---|---|---|---|
| SR0-01 | Commit the uncommitted programmes in reviewable chunks onto `main` (manufacturing, jobwork, quality, agents, money/inventory fixes, staging fixes) with CI green; tag `v1.0.0-beta`. | Functional, Maintainability | Split | Clean tree; tag on a green SHA. |
| SR0-02 | Re-baseline this scorecard and `SAAS_READINESS_EXECUTION_PLAN.md` status against the tagged SHA (that plan's status is from 16 Sep). | All | LLM | Both docs dated after the tag. |
| SR0-03 | Make every `*_concurrency_postgres.py` suite run (not skip) in required CI. | Reliability | LLM | CI log shows them executed. |
| SR0-04 | Book the long-lead people now: CA engagement, counsel (ToS/privacy/DPA/DPIA), pentester, on-call primary, 5–10 beta businesses. | Compliance, Legal, Security, Ops, Commercial | Human | Dates in the calendar. |
| SR0-05 | Start SMS DLT registration, email SPF/DKIM/DMARC and WhatsApp template approval (WP-B6). | Messaging | Human | Applications submitted. |
| SR0-06 | Fix the configs that would break isolation on a real host: prod compose overlay uses the app role with RLS on; pgbouncer in session mode; workers consume the agent queues; agent beat tasks fan out per tenant. | Tenancy | LLM | Guards and tests in the plan pass. |

### Wave 1 — Hosted staging, everything observable (weeks 2–6)

Target: every NFR row at **L2**.

| ID | Item | Area | Lane | Done when |
|---|---|---|---|---|
| SR1-01 | Stand up hosted staging from the IaC: managed Postgres with PITR, pgbouncer, Redis, object storage, TLS, India region. | Architecture, DR, Privacy | Split | `edge_tls_smoke.sh` PASS on the host. |
| SR1-02 | RLS on, non-superuser app role, the full tenancy + RLS suites run against the host DB. Hunt for pre-auth writes like the sign-in audit bug. | Tenancy | Split | Suite log from the host; no bypass. |
| SR1-03 | **Observability O-Gate 1 + 2 human steps**: Sentry project, DSNs, release tagging, `METRICS_TOKEN`, test event, Support-ID grep walk. | Observability | Split | OG1-H1..H5 and the OG2 walk closed with evidence. |
| SR1-04 | **Multi-process metrics**: replace process-local counters with a multi-process-safe exporter; scrape from a collector; add queue depth, task latency, DB pool and per-tenant request-rate series. | Observability | LLM | Counters correct with 4 workers in a test. |
| SR1-05 | **Dashboards and alerts**: one ops dashboard (RED per endpoint group, queue depth, DB, backups, invariant results) and alerts in `ALERTS.md` wired to the on-call channel. | Observability, Alerting | Split | Test alert reaches a named phone. |
| SR1-06 | External uptime probe + public status page. | Availability | Split | Probe history visible; status page URL. |
| SR1-07 | **Fan out per-company jobs** (invariant sweep, nightly reports, digests): one task per tenant, chunked, with a time limit and a result row per tenant. Shown in Django admin. | Scalability, Observability | LLM | 1,000-tenant seeded sweep finishes inside its window. |
| SR1-08 | Off-host encrypted backups, alert on a missed backup, restore drill on the host ending with a per-tenant invariant sweep. | DR | Split | Dated drill log with measured RTO. |
| SR1-09 | Hosted CD from SHA, post-deploy smoke, one rehearsed rollback to the previous image. | Deployability | Split | Rollback timed and logged. |
| SR1-10 | Secrets in a secrets manager; one rotation drill (DB password, JWT key, MFA key). | Security | Split | Drill log. |
| SR1-11 | Load, soak (8 h) and large-tenant runs with the existing k6/locust scripts against hosted staging; fix anything over budget (QOS-0003, QOS-0016). | Performance | Split | Results file + p95 table vs `SLO.md`. |
| SR1-12 | AI agents: per-tenant spend cap and kill switch, PII redaction test, prompt-injection test set, usage per tenant in admin. | AI, Cost, Privacy | LLM | Tests pass; cap enforced on staging. |
| SR1-13 | Prove MFA on the password, phone-OTP and invite paths by test and close QOS-0103; decide MFA policy for non-owner roles. | Security | LLM + decision | QOS-0103 verified. |

### Wave 2 — Closed beta, 5–10 real businesses (weeks 6–12)

Target: dimensions 2–9 at **L3**.

| ID | Item | Area | Lane | Done when |
|---|---|---|---|---|
| SR2-01 | Import real customer books; `cutover_recon` variance 0 or explained (6.1–6.5). | Data, Accounting | Split | Signed recon per company. |
| SR2-02 | Watch unaided onboarding and the core loop (purchase → sale → return → reports) with non-technical staff. | UX, Workflow | Human | Session notes; QOS-0029 resolved. |
| SR2-03 | One full business day with no engineer (QOS-0030). | Operational | Human | Day log; zero manual DB fixes. |
| SR2-04 | Parallel month vs Tally/Busy for 2–3 pilots; CA review of their GST worksheets (QOS-0004). | Accounting, Compliance | Human + Split | Zero unexplained difference; CA notes. |
| SR2-05 | Offline outbox on real phones in poor network (H-03). | Reliability | Split | Zero duplicates, zero lost drafts. |
| SR2-06 | Support channel staffed with an SLA; every ticket tagged by taxonomy; weekly triage into P0–P3. | Supportability | Human | Response-time numbers. |
| SR2-07 | Native Hindi review across all modules; real-device and screen-reader pass (QOS-0098, QOS-0131, QOS-0132). | Accessibility, i18n | Human | Review CSVs signed. |
| SR2-08 | Journey Health weekly review (O-Gate 3, product side only): which journeys start but don't finish. | Observability | Split | Four weekly reviews held. |
| SR2-09 | Independent pentest on hosted staging; fix every High. | Security | Human + LLM | Report + retest. |
| SR2-10 | Incident-response tabletop with the on-call person. | Ops | Human | Postmortem from the exercise. |

### Wave 3 — Paid beta (weeks 12–16)

| ID | Item | Area | Lane | Done when |
|---|---|---|---|---|
| SR3-01 | Prices, trial length and GST on our own SaaS invoices signed; live Razorpay with daily recon (8.1, 8.6, 8.9). | Commercial | Human + Split | First paid renewal reconciled. |
| SR3-02 | ToS, privacy policy, DPA, refund policy published by counsel; DPIA decision (G16). | Privacy, Legal | Human | URLs live. |
| SR3-03 | Sign SLOs, RPO/RTO and capacity numbers (11.4, 13.1, 12.7). | Availability, DR, Performance | Human | Signed `SLO.md`. |
| SR3-04 | Mobile version policy: oldest supported app, forced-update path, API compatibility test in CI. | Mobile | LLM + decision | CI job; policy doc. |
| SR3-05 | Hypercare: named owners for days 1–7 and 8–30 (17.4). | Ops | Human | Roster filled. |

### Wave 4 — Public launch

All of G1–G17 signed, every row in sections 2–3 at **L4** or waived in writing,
then open sign-up (17.5–17.6).

### Continuous after launch

- Monthly scorecard refresh (this doc) and the SLO drift report.
- Every new module that moves money, stock or personal data ships with: RLS migration, invariant, ledger-coverage row, metrics, alert, Hindi strings, runbook line. Enforce it with the `config_consistency` guard.
- Quarterly: restore drill, secret rotation, access review, CA spot check.

---

## 6. Critical path

```
SR0-01 commit/tag ─ SR1-01 hosted staging ─┬─ SR1-02..13 (parallel, ~4 weeks)
                                           └─ SR2-* closed beta ─ SR3-* paid beta ─ Launch
SR0-04 book people ── CA ── counsel ── pentester ── beta businesses ──┘ (longest lead time)
```

Engineering can reach "every row at L2" in about 6 weeks. The calendar is set
by people: the CA, counsel, the pentester and the beta businesses. Book them in
week 1.

---

## 7. Decisions needed from the founder

| # | Question | Recommendation |
|---|---|---|
| Q1 | Hosting provider and India region for hosted staging and prod? | Managed Postgres with PITR in an Indian region (DPDP and latency). |
| Q2 | Metrics stack: Prometheus + Grafana (self-hosted) or a managed service? | A managed service at first. It's less to run with a one-person on-call. |
| Q3 | Who is on-call primary and backup? | A named person. Without one, G11 can't be signed. |
| Q4 | Shadow books for every company (Dim 6 Q1)? | Yes. |
| Q5 | Should AI agents be in paid beta, or stay off until after launch? | Off by default per tenant; allow opt-in only after SR1-12. |
| Q6 | Freeze new feature programmes until Wave 1 is done? | Yes. Every new programme adds to the uncommitted tree and to the sign-off queue. |
