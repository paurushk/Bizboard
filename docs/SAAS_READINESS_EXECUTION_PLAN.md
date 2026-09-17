# BizBoard production SaaS execution plan

Git-canonical, trackable copy of the Excel **17-phase** Production SaaS
Readiness Roadmap (plus 4 continuous tracks). Use **Excel IDs** in tickets
(1.6, 3.11, 17.5). Do not mix CSV numbering.

Status is **repo evidence as of 16 Sep 2026**, not the spreadsheet
“Not Started” column, and not a signed launch gate. All **G1–G17 stay
Open** until a human signs them.

Governing rule: freeze, tenant isolation, integrity, security,
reliability, operability, CX, and automated validation **before** feature
expansion (GSTR live, Tally, manufacturing, payroll, CRM). Do not enable
prod RLS from this plan. Do not invent ToS / privacy / DPA / DPIA / GST
opinions.

## Scoreboard

| Metric | Value |
|---|---|
| Steps fully closed | 30 / 148 (LLM-only) |
| LLM engineering half done | 100 / 100 |
| Waiting on Human (Split) | 70 |
| Human-only still open | 48 |
| Launch gates signed | 0 / 17 |
| Lane mix | LLM 30 · Split 70 · Human 48 |

### Status model

| Status | Meaning |
|---|---|
| Closed | Engineering DoD is in the repo and no Human remaining |
| LLM done · Human open | Cursor finished its half; founder / host / CA / counsel still required |
| Open | Human-only not started (including every launch gate) |

When a Human item actually closes, update this file and the canvas
`LLM_CLOSED` / `SPLIT_LLM_CLOSED` sets.

## First 10 actions

These unstick the critical path. None of them is a new product feature.

| # | Lane | Action | Unblocks | Owner | Evidence |
|---|---|---|---|---|---|
| 1 | Human | Ratify FREEZE_SCOPE.md (A/B/C/G/H) and freeze exception process | G1 | Founder | Signed freeze + exception CR path |
| 2 | Split | Cut annotated tag v1.0.0-beta from a green CI SHA | G1 baseline | Eng | git tag + GitHub release notes |
| 3 | Split | Stand up a real hosted staging with TLS, isolated DB/Redis/media | G2, G10, G11 | DevOps | edge_tls_smoke.sh PASS + ENV_CHECKLIST |
| 4 | Split | Classify every open QOS/issue as P0–P3; accept known limitations in writing | G1 | QA/Founder | Zero unclassified; P0=0 P1=0 or waived |
| 5 | Split | Enable RLS on staging only; run tenancy + rls suites against it | G3 | Eng/Security | POSTGRES_RLS_ENABLED=1 soak log, no bypass |
| 6 | Human | Book CA review of F1–F8 tax corpus + practising-CA letter | G5, G10.9 | Founder/CA | Signed CA_SIGN_OFF_CHECKLIST |
| 7 | Split | Wire Sentry + uptime + one on-call phone; fire a test alert | G11 | Ops | sentry_test_event id + page received |
| 8 | LLM | Reconcile billing Plan.modules with freeze: paid plans must not enable dark modules | G8 vs freeze | Product/Eng | seed_plans + entitlement tests vs FREEZE_SCOPE B |
| 9 | Human | Send ToS / privacy / beta agreement to a lawyer; do not invent copy | G16, G15.2 | Founder/Legal | Counsel-reviewed drafts |
| 10 | Human | Recruit 5–10 beta businesses; do not wait for public-launch perfection | G15 | Founder | Signed beta agreements, not demo accounts |

### Already in the repo (do not rebuild)

Company-scoped querysets, URL-conf IDOR suite, erasure + tombstone, L1
invariants, WF chains, RBAC matrix, OTP + lockout, Razorpay subscription
+ write-block, compose DEV/STAGING overlays, GitHub CI (pytest, ruff,
pip-audit, OpenAPI, RLS job), local backup restore drill, circuit-breaker
+ billing DLQ (Cashfree / PayU / GSP / Razorpay fail-closed).

### Still production blockers

No hosted staging/prod, no TLS host, RLS runtime off, no MFA product, no
applied IaC, no PITR/failover, no pentest, DPDP unsigned, CA unsigned,
Go/No-Go unsigned, no real users. JWT in localStorage is accepted only
for pilot.

## Master execution sequence

Gates serialize. Work does not. Do not claim the next gate until the
previous gate is evidenced.

| Order | Gate | Must finish | May run in parallel |
|---|---|---|---|
| 0 | G1 Freeze 1.6 | Signed scope, tag, P0/P1=0 | Legal drafts, CA booking, staging vendor |
| 1 | G2 Architecture 2.7 | Hosted staging + secrets + network | Cost model, HA paper design |
| 2 | G3 Tenant 3.11 | RLS soak + adversarial IDOR + lifecycle | Quota design, admin UX polish |
| 3 | G4 Identity 4.8 | Auth journeys + server RBAC + MFA for owners | Access-review process |
| 4 | G5 Integrity 5.9 | Invariant CI + CA + founder UAT on staging | Recon report UX |
| 5 | G6 Cutover 6.8 | Import/opening-balance playbook (no live prod yet) | Treat as customer onboarding cutover |
| 6 | G7 Database 7.8 | Managed PG, pooling, PITR, failover drill | Zero-downtime migration rehearsal |
| 7 | G8 Billing 8.10 | Sandbox lifecycle + entitlements vs freeze | GST invoice counsel |
| 8 | G9 Integrations 9.7 | Timeouts, signed webhooks, DLQ, no corrupt complete | Vendor SLA sheet |
| 9 | G10 Security 10.11 | Threat model, scans, pentest, DPDP counsel | WAF/DLT/SPF |
| 10 | G11 Ops 11.11 | SLOs, alerts, on-call, IR tabletop | Status page |
| 11 | G12 Perf 12.7 | Load + noisy-neighbor on staging data | CDN for static only |
| 12 | G13 DR 13.7 | Off-host encrypted restore + failover vs signed RPO/RTO | Drill calendar |
| 13 | G14 CI/CD 14.10 | Artifact → staging → smoke → rollback proven | Canary after first paid beta |
| 14 | G15 Beta 15.9 | >80% unaided onboard, ≥95% core journey, P0=P1=0 | Support staffing |
| 15 | G16 Legal 16.8 | ToS, privacy, DPA, refunds, insurance decision | Support SLA live |
| 16 | G17 Launch 17.5 | Paid beta stable, all gates evidenced | GTM + hypercare |

## Launch gates — honest status

| Gate | Step | Repo reality | Missing evidence | Verdict |
|---|---|---|---|---|
| G1 Freeze | 1.6 | FREEZE_SCOPE + coverage + Q-OS = 0 Critical | Founder signature, git tag, exception process | Open |
| G2 Architecture | 2.7 | Compose DEV/STAGING/PROD overlays | Hosted isolation, IaC applied, private DB, cost model | Open |
| G3 Tenant SaaS | 3.11 | company_id + tenancy tests + erasure | RLS on staging, quota/suspend proven on host | Open |
| G4 Identity | 4.8 | JWT, OTP, lockout, RBAC FG-2d | MFA product, session revoke, JWT cookie decision | Open |
| G5 Integrity | 5.9 | L1–L10 tests, CA corpus automated | CA letter, real-user UAT ≥5 companies | Open |
| G6 Migration | 6.8 | Imports + seed_staging exist | Cutover runbook for real books; rollback drill | Reframe |
| G7 Database | 7.8 | PG17 in CI; local restore drill | Managed HA, PITR, pooling under load | Open |
| G8 Billing | 8.10 | Razorpay sub + write-block middleware | Live recon, GST bills, freeze-safe entitlements on host | Open |
| G9 Integrations | 9.7 | Sandbox payment/SMS/GSP flags off live; CB/DLQ in-repo | Signed replay tests on staging | Open |
| G10 Security | 10.11 | pip-audit, headers, tenancy tests | Pentest, KMS, DPDP/DPIA counsel | Blocked |
| G11 Operations | 11.11 | RUNBOOKS.md, health endpoint | Sentry project, on-call, SLOs, IR tabletop | Blocked |
| G12 Performance | 12.7 | k6 scripts + QOS-0003 open | Load/soak/noisy-neighbor evidence on host | Open |
| G13 DR | 13.7 | Local restore PASS 2026-09-12 | Off-host encrypted drill vs signed RPO/RTO | Open |
| G14 CI/CD | 14.10 | Required GitHub CI jobs | Prod CD, canary, migration rollback on host | Open |
| G15 Beta exit | 15.9 | Recruitment + UAT docs only | 5–10 real businesses, metrics | Blocked |
| G16 Commercial | 16.8 | DPDP posture note unsigned | ToS, privacy, DPA, insurance | Blocked |
| G17 Launch | 17.5 | Cannot claim 10/10 yet | All prior gates + paid beta hypercare | Blocked |

## Parallel tracks after freeze

| Track | Work | Owner | Blocks |
|---|---|---|---|
| A Platform | Hosted staging/prod, secrets, TLS, IaC, managed Postgres, backups, PITR, CI/CD, Sentry, on-call | DevOps + Eng | G2, G7, G11, G13, G14 |
| B Correctness and isolation | RLS soak, adversarial tenancy, invariant CI, CA sign-off, MFA, webhook idempotency, freeze-safe entitlements | Eng + QA + Security | G3, G4, G5, G8, G9, G10 |
| C Customer proof | Recruit beta, unaided onboarding, core journey observation, support SLA, paid conversion | Founder + Product | G15, G17 (start recruiting during Track A) |
| D Legal and commercial | Counsel for ToS/privacy/DPA/DPDP, CA for GST, PCI SAQ-A via Razorpay, insurance, refund policy matching billing code | Founder + counsel | G10.7–10.9, G16 (start drafts at freeze) |

### Hidden dependencies

| Gap | Why it is hidden | What to do |
|---|---|---|
| Phase 6 assumes live data | There is no production tenant corpus | Rewrite as opening-balance / import cutover for each beta company |
| Plan.modules vs freeze | Starter/Pro historically seeded GSTR, manufacturing, payroll, CRM | Align entitlements to FREEZE_SCOPE B until post-beta (in-repo) |
| RLS coded, runtime off | CI job required; production still POSTGRES_RLS_ENABLED=0 | Soak on staging; Celery GUC + webhooks are the failure mode |
| JWT localStorage | ENV_CHECKLIST accepts risk for pilot only | Revisit httpOnly/BFF before public launch |
| External timeout vs Complete | Historically no CB/DLQ | Fail-closed money paths now in-repo; hosted confirm still Human |
| Erasure flag default off | ENABLE_TENANT_ERASURE=0 | Ops runbook + flag-on for beta host, tombstone mode |

## Risk register — live overlay

| ID | Risk | P | I | Current mitigation in repo | Still open |
|---|---|---|---|---|---|
| R001 | Cross-tenant leakage | H | C | company_id + IDOR tests | RLS off; file/media/report paths on real host |
| R002 | Migration corrupts books | M | C | Idempotent imports; no live corpus | Per-tenant opening-balance recon |
| R003 | DB failure | M | C | Local restore drill | No managed replica/PITR/failover |
| R004 | Payment webhook drift | M | H | Razorpay signature + dedup | Settlement recon, chargebacks, live mode |
| R005 | Security breach | M | C | pip-audit, CSP notes, tenancy tests | Pentest, WAF, secret rotation, IR |
| R006 | External API outage | H | H | Sandbox flags; GSP live off; CB/DLQ in-repo | Hosted confirm; Complete vs IRN race |
| R007 | Poor adoption | M | H | Onboarding wizard in freeze | No unaided real-user evidence |
| R008 | Runaway cost | M | H | UNIT_ECONOMICS draft | Founder-approved prices vs burn |

### Architecture / integrity risks not in the Excel register

| Risk | Why it matters | Owner |
|---|---|---|
| Completed docs are money-truth; GL is a projection | A dual-write bug silently desyncs reports | Eng |
| Stock balances are a cache of append-only movements | Direct balance writes corrupt inventory | Eng |
| Period close is a hard gate | Back-dated complete after close is a statutory defect | Eng/CA |
| Offline drafts are plaintext on device | Shared-counter POS leakage | Product |
| Support Django admin is a super-tenant | Staff access without impersonation audit | Security |

## Production Go / No-Go

All boxes must be evidenced, not claimed. Human signatures remain final
gates even when engineering is code-complete.

| Must be true | Evidence | Today |
|---|---|---|
| P0=0 and P1=0 or founder-waived in writing | Q-OS + classified register | Code P0=0; governance unsigned |
| Freeze scope signed; dark modules inaccessible | FREEZE_SCOPE + FG-2d flag tests | Doc exists; signature pending |
| Hosted staging ≡ prod topology; TLS+HSTS | edge_tls_smoke.sh + ENV_CHECKLIST | No host |
| Zero cross-tenant read/write/file/report | RLS soak + IDOR on staging | App-layer only |
| Auth + owner MFA + server RBAC | Journey tests + pentest | No MFA product |
| Sales/purchase/return/stock/GL recon = 0 | Invariant CI + CA letter + UAT | Tests yes; CA/UAT no |
| Managed PG backup/PITR/failover drill | Dated restore + RPO/RTO | Local only |
| Billing sandbox lifecycle + freeze-safe entitlements | Webhook replay + write-block tests | Partial |
| External failure cannot complete a money doc | Timeout/DLQ tests | In-repo; hosted confirm missing |
| Pentest critical/high = 0 | Report + remediations | No pentest |
| DPDP/ToS/privacy/DPA counsel-approved | Published URLs + DPA | Posture note only |
| On-call, Sentry, SLOs, IR tabletop | Test page + runbooks | Docs only |
| Load + noisy-neighbor within targets | k6/soak report | QOS-0003 open |
| Rollback of app + migration proven | Staging rollback drill | CI merge only |
| 5–10 real businesses; beta exit metrics | UAT matrix + CSAT | Zero real tenants |
| First paid invoices reconcile to Razorpay | Settlement file vs Subscription | Not live |

### Beta → paid beta → public

| Stage | What | Exit |
|---|---|---|
| Closed beta | 5–10 invited companies, sandbox payments, GSP live off, weekly support, no public signup | Unaided onboard >80%, core journey ≥95%, P0=P1=0 |
| Paid beta | Convert 3+ willing firms to live Razorpay, GST SaaS invoice from BizBoard entity, hypercare daily | Settlement recon 14 days clean, no data-loss incident |
| Public launch | Open signup only after G17 | Feature expansion stays dark until a new freeze |

## Implementation tracker (every Excel step)

Lane: **LLM** = Cursor can close the engineering DoD. **Split** = start
the LLM half now; a named human must provision, approve, or operate.
**Human** = do not ask a model to complete it.

### 1 Freeze

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 1.1 | Feature freeze | Split | LLM done · Human open | Exception SOP, freeze-exception CI/label, flag-guard | Sign FREEZE_SCOPE; stop expansion work | docs/ops/FREEZE_EXCEPTION.md |
| 1.2 | Production baseline | Split | LLM done · Human open | Write baseline from A1–A26 / C1–C8 + SHA | Approve baseline as v1 | scripts/ops/freeze_baseline.py |
| 1.3 | Defect classification | Split | LLM done · Human open | Classify Q-OS + register as P0–P3 | Waive or accept P1s in writing | docs/ops/QOS_FREEZE_CLASS.md |
| 1.4 | Risk register | Split | LLM done · Human open | Draft R001–R008 + repo-specific risks | Own residuals; sign accept-risk | docs/ops/RISK_REGISTER.md |
| 1.5 | Release checklist | Split | LLM done · Human open | Merge GO_NO_GO + ENV + G1–G17 into one sheet | Approve as the only launch artifact | docs/ops/RELEASE_CHECKLIST.md |
| 1.6 | Freeze gate | Human | Open | Prepare tag notes; verify CI green | Sign G1; cut v1.0.0-beta | Sign G1; cut v1.0.0-beta |

### 2 Architecture

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 2.1 | Environment separation | Split | LLM done · Human open | Compose overlays, env examples, isolation docs | Pay/provision hosted staging+prod accounts | Compose overlays, env examples, isolation docs |
| 2.2 | Production architecture | Split | LLM done · Human open | Diagram + ADR from compose/architecture.md | Approve topology (managed PG vs VM) | Diagram + ADR from compose/architecture.md |
| 2.3 | Infrastructure as Code | Split | LLM done · Human open | Write IaC, pin-digest scripts, recreate README | Apply IaC to a real cloud account | Write IaC, pin-digest scripts, recreate README |
| 2.4 | Network/security baseline | Split | LLM done · Human open | SG templates, TLS settings, edge_tls_smoke.sh | Apply SGs; prove DB/Redis not public | SG templates, TLS settings, edge_tls_smoke.sh |
| 2.5 | HA and capacity | Split | LLM done · Human open | Draft SLO/RPO/RTO/capacity numbers | Accept single-AZ residual or fund HA | Draft SLO/RPO/RTO/capacity numbers |
| 2.6 | Cost model | Split | LLM done · Human open | Draft 10 / 1k / 10k unit-economics sheet | Approve prices vs SMS/PG/Razorpay burn | Draft 10 / 1k / 10k unit-economics sheet |
| 2.7 | Architecture gate | Human | Open | Assemble G2 evidence pack | Sign G2 | Sign G2 |

### 3 Tenant

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 3.1 | Tenant model | Split | LLM done · Human open | Domain map: company FK vs global; erasure coverage | Sign ADR (company_id = tenant) | Domain map: company FK vs global; erasure coverage |
| 3.2 | Tenant_id coverage | LLM | Closed | Schema audit, composite uniques, missing company_id tests | None to close the engineering DoD | tests/tenancy/test_schema_constraints.py |
| 3.3 | PostgreSQL RLS | Split | LLM done · Human open | Fix GUC/webhook bypasses; RLS tests; staging compose flag | Hosted PG soak ≥7 days; no superuser bypass | Fix GUC/webhook bypasses; RLS tests; staging compose flag |
| 3.4 | Tenant-aware constraints | LLM | Closed | DB constraints + failing insert tests | None | UTR/SKU/GSTIN UniqueConstraint IntegrityError |
| 3.5 | Tenant provisioning | LLM | Closed | Clean signup→wizard path; no seed_demo in customer path | Unaided rate is 15.3, not this step | Clean signup→wizard path; no seed_demo in customer path |
| 3.6 | Tenant admin | Split | LLM done · Human open | Fix UI-403 (QOS-0001); hide dark modules | Owner UAT of users/roles/billing | Fix UI-403 (QOS-0001); hide dark modules |
| 3.7 | Tenant quotas | LLM | Closed | Seat/storage/complete/API limits server-side + tests | Choose numeric caps (can be a 5-min founder note) | billing/quotas.py |
| 3.8 | Tenant suspension | LLM | Closed | Grace/read-only/reactivate tests on write-block | None | B9-007 cancel grace + write-block tests |
| 3.9 | Export/deletion | Split | LLM done · Human open | Erasure flag runbook, tombstone tests, support CLI | Counsel retention copy; flip flag on beta host | Erasure flag runbook, tombstone tests, support CLI |
| 3.10 | Cross-tenant attack tests | Split | LLM done · Human open | Extend IDOR to files/reports/media; CI suite | Run suite on hosted staging with two companies | sales+purchase+customer export IDOR |
| 3.11 | Tenant gate | Human | Open | Evidence pack | Sign G3 | Sign G3 |

### 4 Identity

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 4.1 | Authentication | Split | LLM done · Human open | Auth/OTP/session tests; OTP_DEBUG_ECHO=0 guards | Live SMS/DLT or keep OTP off | Auth/OTP/session tests; OTP_DEBUG_ECHO=0 guards |
| 4.2 | Password/account protection | LLM | Closed | Lockout, throttles, reset-oracle tests | None | Lockout, throttles, reset-oracle tests |
| 4.3 | MFA / SSO | Split | LLM done · Human open | Implement TOTP + hashed recovery; SSO decision doc | Enroll a real owner device; decide SSO in/out | docs/ops/MFA_SSO.md (decision only; no TOTP product) |
| 4.4 | Role/permission matrix | Split | LLM done · Human open | Diff UI vs backend; complete matrix from FG-2d | Approve role names and Sales Staff limits | Diff UI vs backend; complete matrix from FG-2d |
| 4.5 | Backend authorization | LLM | Closed | API 403/404 suite; admin mixin guards | Named staff-admin allowlist (4.7) | API 403/404 suite; admin mixin guards |
| 4.6 | Support impersonation | Split | LLM done · Human open | Build consented+audited impersonation OR guard that none exists | Decide screenshare-only vs product impersonation | tests/test_no_impersonation.py |
| 4.7 | Access reviews/offboarding | Human | Open | Checklist template | Name people; quarterly review; same-day offboard | Name people; quarterly review; same-day offboard |
| 4.8 | Identity gate | Human | Open | Evidence pack | Sign G4 | Sign G4 |

### 5 Integrity

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 5.1 | Business invariants | LLM | Closed | Close FREEZE_SCOPE_COVERAGE GAPs; keep impact map current | None | Close FREEZE_SCOPE_COVERAGE GAPs; keep impact map current |
| 5.2 | Automated invariant tests | LLM | Closed | Keep L1 strict, WF chains, money, CA parity blocking | None | Keep L1 strict, WF chains, money, CA parity blocking |
| 5.3 | Sales validation | LLM | Closed | WF + golden e2e + CG sales on seed data | Real-user UAT is 5.8 | WF + golden e2e + CG sales on seed data |
| 5.4 | Purchase validation | LLM | Closed | WF + CG purchase + stock/AP recon tests | Real-user UAT is 5.8 | WF + CG purchase + stock/AP recon tests |
| 5.5 | Sales return validation | LLM | Closed | Credit-note stock/GST/AR reversal tests | Real-user UAT is 5.8 | Credit-note stock/GST/AR reversal tests |
| 5.6 | Reconciliation reports | LLM | Closed | Owner/support check_invariants report + nightly job | None | Owner/support check_invariants report + nightly job |
| 5.7 | Audit trail validation | LLM | Closed | Append-only + statutory event coverage tests | None | Append-only + statutory event coverage tests |
| 5.8 | UAT sign-off | Human | Open | UAT scripts, seed_staging, evidence folders | Non-technical operator + CA letter | Non-technical operator + CA letter |
| 5.9 | Data integrity gate | Human | Open | Evidence pack | Sign G5 | Sign G5 |

### 6 Cutover

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 6.1 | Source data inventory | Split | LLM done · Human open | Per-tenant inventory template mapped to A15 imports | Fill with each customer’s real books | Per-tenant inventory template mapped to A15 imports |
| 6.2 | Data mapping | Split | LLM done · Human open | Field map legacy→schema | Customer confirms what is out of scope | Field map legacy→schema |
| 6.3 | Migration scripts | LLM | Closed | Idempotent import/opening-balance commands + tests | None | Idempotent import/opening-balance commands + tests |
| 6.4 | Migration dry run | Split | LLM done · Human open | Dry-run harness + invariant sweep | Provide representative customer files | Dry-run harness + invariant sweep |
| 6.5 | Reconciliation | Split | LLM done · Human open | Count/stock/AR/AP recon sheet automation | Sign variance 0/explained | Count/stock/AR/AP recon sheet automation |
| 6.6 | Cutover/freeze window | Human | Open | Comms + runbook templates | Agree T0 with the customer | Agree T0 with the customer |
| 6.7 | Rollback plan | Split | LLM done · Human open | Snapshot/retry SOP; no untested reverse migrate | Keep old books 30 days | Snapshot/retry SOP; no untested reverse migrate |
| 6.8 | Cutover sign-off | Human | Open | Evidence pack | Founder + customer sign G6 | Founder + customer sign G6 |

### 7 Database

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 7.1 | Postgres production config | Split | LLM done · Human open | Parameter set, statement_timeout, IaC snippet | Apply on managed PG | Parameter set, statement_timeout, IaC snippet |
| 7.2 | Indexes/constraints | Split | LLM done · Human open | Query-plan review, missing-index migrations | Confirm on hosted data volume | Query-plan review, missing-index migrations |
| 7.3 | Connection pooling | Split | LLM done · Human open | Pool math + pgbouncer config | Load-test on hosted PG | Pool math + pgbouncer config |
| 7.4 | Replication/failover | Split | LLM done · Human open | Reconnect/retry app settings + runbook | Execute failover on managed PG | Reconnect/retry app settings + runbook |
| 7.5 | PITR | Human | Open | PITR runbook | Restore to timestamp T on vendor | Restore to timestamp T on vendor |
| 7.6 | Backup encryption/monitoring | Split | LLM done · Human open | Backup-fail alert + encrypt instructions | Off-host bucket + KMS | Backup-fail alert + encrypt instructions |
| 7.7 | Zero-downtime migrations | LLM | Closed | Expand/contract SOP + staging rehearsal | None for the SOP itself | Expand/contract SOP + staging rehearsal |
| 7.8 | DB gate | Human | Open | Evidence pack | Sign G7 | Sign G7 |

### 8 Billing

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 8.1 | Pricing/plans | Split | LLM done · Human open | Align seed_plans modules to freeze Table B | Finalize rupee prices and trial length | Align seed_plans modules to freeze Table B |
| 8.2 | Entitlements | LLM | Closed | Server-side plan→flag matrix; kill dark modules on paid plans | None | entitlements vs freeze Table B |
| 8.3 | Usage metering/quotas | LLM | Closed | Meter seats/storage/completes; HelpCode on overage | None | Meter seats/storage/completes; HelpCode on overage |
| 8.4 | Subscription lifecycle | Split | LLM done · Human open | Trial/renew/upgrade/cancel tests | Razorpay sandbox keys on staging | Trial/renew/upgrade/cancel tests |
| 8.5 | Dunning | Split | LLM done · Human open | SaaS dunning separate from AR dunning; grace tests | Approve grace copy and email sender | billing/dunning.py vs AR dunning |
| 8.6 | Payment reconciliation | Split | LLM done · Human open | Daily recon job vs gateway events | Live settlement files (paid beta) | Daily recon job vs gateway events |
| 8.7 | Webhooks/idempotency | LLM | Closed | Signature, replay, out-of-order tests | Staging webhook secret | Signature, replay, out-of-order tests |
| 8.8 | Proration/coupons/chargebacks | Split | LLM done · Human open | Document v1 out/in; chargeback SOP + tests if in | Finance rules for refunds/chargebacks | Document v1 out/in; chargeback SOP + tests if in |
| 8.9 | PCI/GST billing | Human | Open | Grep/logs for PAN; factual PCI-scope note | Counsel + CA on SAQ-A and SaaS GST | Counsel + CA on SAQ-A and SaaS GST |
| 8.10 | Commercial billing gate | Human | Open | Evidence pack | Sign G8 | Sign G8 |

### 9 Integrations

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 9.1 | Integration inventory | LLM | Closed | Vendor/env/secret/fallback page from code | None | docs/ops/INTEGRATIONS.md |
| 9.2 | Sandbox testing | Split | LLM done · Human open | Contract tests against sandboxes | Vendor sandbox accounts | Contract tests against sandboxes |
| 9.3 | Timeout/retry/circuit breaker | LLM | Closed | Fail-closed money paths; chaos tests | None | circuit_breaker fail-closed + PayU |
| 9.4 | Webhook security | LLM | Closed | HMAC, timestamp, replay tests | None beyond secrets in 8.7 | HMAC, timestamp, replay tests |
| 9.5 | Dead-letter/reprocessing | LLM | Closed | DLQ + audited replay | None | DeadLetterEvent + replay_dead_letter |
| 9.6 | Vendor SLA/dependency plan | Human | Open | Sheet template | Real contacts, contracts, DLT entity | Real contacts, contracts, DLT entity |
| 9.7 | Integration gate | Human | Open | Evidence pack | Sign G9 | Sign G9 |

### 10 Security

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 10.1 | Threat model | Split | LLM done · Human open | STRIDE draft from code (JWT, media, admin, RLS) | Approve threats + residuals | STRIDE draft from code (JWT, media, admin, RLS) |
| 10.2 | SAST/DAST/deps | Split | LLM done · Human open | pip-audit, npm audit, image scan, ZAP job | Accept leftover highs in writing | pip-audit, npm audit, image scan, ZAP job |
| 10.3 | Encryption | Split | LLM done · Human open | TLS/SECURE_* config; backup encrypt docs | KMS/disk encryption on the host | TLS/SECURE_* config; backup encrypt docs |
| 10.4 | Secret rotation | Split | LLM done · Human open | Rotation runbook + staging drill scripts | Rotate prod secrets | Rotation runbook + staging drill scripts |
| 10.5 | WAF/DDoS/rate limiting | Split | LLM done · Human open | App rate limits on auth/Complete | Edge WAF/DDoS product | App rate limits on auth/Complete |
| 10.6 | Penetration test | Human | Open | Fix findings; PENTEST_SOW already exists | Independent pentest | Independent pentest |
| 10.7 | DPDP/privacy readiness | Human | Open | Factual posture from code only — no legal copy | Counsel + DPIA decision | Counsel + DPIA decision |
| 10.8 | DPA/subprocessors/residency | Human | Open | Subprocessor inventory from vendors in use | DPA templates; region commitment | DPA templates; region commitment |
| 10.9 | GST/e-invoice/e-way | Human | Open | Document flags C1/C2 as implemented | CA sign-off of sellable scope | CA sign-off of sellable scope |
| 10.10 | SMS/email compliance | Human | Open | SPF/DKIM/DMARC setup notes | DLT registration; DNS; live send | DLT registration; DNS; live send |
| 10.11 | Security/compliance gate | Human | Open | Evidence pack | Sign G10 | Sign G10 |

### 11 Ops

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 11.1 | Structured logging | LLM | Closed | JSON logs + PII redaction tests | None | GSTIN/query path redaction |
| 11.2 | Error tracking | Split | LLM done · Human open | Sentry SDK + sentry_test_event | Sentry project; confirm event id | Sentry SDK + sentry_test_event |
| 11.3 | Distributed tracing | LLM | Closed | Trace Complete/PDF/webhook spans | None | payments.webhook span |
| 11.4 | SLI/SLO definition | Split | LLM done · Human open | Draft measurable SLIs from health/Complete/login | Approve numbers | Draft measurable SLIs from health/Complete/login |
| 11.5 | Alerting/runbooks | Split | LLM done · Human open | Alert rules + RUNBOOKS.md per alert | Own each alert | Alert rules + RUNBOOKS.md per alert |
| 11.6 | On-call/escalation | Human | Open | Roster template | Named humans who will be paged | Named humans who will be paged |
| 11.7 | Status communication | Split | LLM done · Human open | Status page + incident templates | Publish and send a test update | Status page + incident templates |
| 11.8 | Incident response | Split | LLM done · Human open | Severity/IR draft aligned to counsel later | Tabletop exercise | Severity/IR draft aligned to counsel later |
| 11.9 | Postmortems | Split | LLM done · Human open | Blameless template + action tracker | Run the process after a real incident | Blameless template + action tracker |
| 11.10 | Log retention/PII policy | Split | LLM done · Human open | Retention config + greps | Legal retention window | Retention config + greps |
| 11.11 | Operations gate | Human | Open | Evidence pack | Sign G11 | Sign G11 |

### 12 Performance

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 12.1 | Performance targets | Split | LLM done · Human open | Propose p95 for login/dashboard/Complete/reports | Approve targets | Propose p95 for login/dashboard/Complete/reports |
| 12.2 | Realistic data load | LLM | Closed | Large seed + QOS-0003 dataset generators | None | Large seed + QOS-0003 dataset generators |
| 12.3 | Load/concurrency test | Split | LLM done · Human open | k6/locust Complete-including scenarios | Run soak on paid staging | k6/locust Complete-including scenarios |
| 12.4 | Autoscaling/queue scaling | Split | LLM done · Human open | Worker scale + backpressure config | Enable on host | Worker scale + backpressure config |
| 12.5 | Caching/CDN | Split | LLM done · Human open | Static-only CDN; keep /api uncached | CDN account | docs/ops/CDN.md + API no-store |
| 12.6 | Noisy-neighbor testing | LLM | Closed | Tenant rate-limit tests + fairness assertions | Optional hosted confirmation | Tenant rate-limit tests + fairness assertions |
| 12.7 | Capacity gate | Human | Open | Evidence pack | Sign G12 | Sign G12 |

### 13 DR

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 13.1 | RPO/RTO | Human | Open | Propose 24h/4h beta numbers | Sign numeric RPO/RTO | Sign numeric RPO/RTO |
| 13.2 | Backup policy | Split | LLM done · Human open | Cron/scripts; media+SQL; encrypt instructions | Off-host storage | Cron/scripts; media+SQL; encrypt instructions |
| 13.3 | Restore drill | Split | LLM done · Human open | restore_drill.sh analogue + invariant sweep | Run against real hosted backups and date it | restore_drill.sh analogue + invariant sweep |
| 13.4 | Failover drill | Human | Open | Runbook | Execute and measure RTO | Execute and measure RTO |
| 13.5 | BCP/DR runbook | Split | LLM done · Human open | Scenarios: AZ, ransomware, Razorpay, SMS | Approve | Scenarios: AZ, ransomware, Razorpay, SMS |
| 13.6 | DR cadence | Human | Open | Calendar template | Put drills on a real calendar | Put drills on a real calendar |
| 13.7 | DR gate | Human | Open | Evidence pack | Sign G13 | Sign G13 |

### 14 CI/CD

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 14.1 | CI pipeline | LLM | Closed | Keep required checks; add missing security jobs | None | Keep required checks; add missing security jobs |
| 14.2 | Artifact registry | Split | LLM done · Human open | SHA-tagged image workflow | Registry account | SHA-tagged image workflow |
| 14.3 | Config/secrets management | Split | LLM done · Human open | Remove secrets from examples; GH OIDC wiring | Vault/secret store | Remove secrets from examples; GH OIDC wiring |
| 14.4 | Staging deployment | Split | LLM done · Human open | Deploy-from-SHA workflow | Staging credentials | Deploy-from-SHA workflow |
| 14.5 | Smoke/post-deploy | LLM | Closed | Health, login, one Complete, invariants | None once staging URL exists | scripts/post_deploy_smoke.py |
| 14.6 | Canary/blue-green | Split | LLM done · Human open | Previous-digest rollback compose | Choose strategy for prod | Previous-digest rollback compose |
| 14.7 | Feature flags | LLM | Closed | Flag lifecycle vs freeze list; no forever flags | None | docs/ops/FLAG_LIFECYCLE.md |
| 14.8 | Migration rollback | Split | LLM done · Human open | Forward-fix SOP + unsafe-reverse list | Staging rollback drill | Forward-fix SOP + unsafe-reverse list |
| 14.9 | Change/release approval | Human | Open | Release-notes template from git log | Named release owner approves | Named release owner approves |
| 14.10 | CI/CD gate | Human | Open | Evidence pack | Sign G14 | Sign G14 |

### 15 Beta

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 15.1 | Beta cohort | Human | Open | Archetype checklist from personas doc | Recruit 5–10 real businesses | Recruit 5–10 real businesses |
| 15.2 | Beta agreement | Human | Open | Product-fact sheet for counsel — do not write a contract | Lawyer + signed agreements | Lawyer + signed agreements |
| 15.3 | Unaided onboarding | Human | Open | Telemetry events; funnel dashboard | Users complete setup without Eng | Users complete setup without Eng |
| 15.4 | Core journey success | Human | Open | Fix bugs found; journey instrumentation | Observe purchase→sale→return→reports | Observe purchase→sale→return→reports |
| 15.5 | Critical defect threshold | Split | LLM done · Human open | Triage incoming as P0–P3; patch P0/P1 | Enforce P0=0 P1=0 exit | Triage incoming as P0–P3; patch P0/P1 |
| 15.6 | Support volume | Human | Open | Ticket taxonomy | Staff a channel and measure SLA | Staff a channel and measure SLA |
| 15.7 | Customer satisfaction | Human | Open | Survey form copy from freeze (not legal) | Set target before seeing scores; collect CSAT | Set target before seeing scores; collect CSAT |
| 15.8 | Telemetry/feedback triage | Split | LLM done · Human open | Cluster feedback → freeze-exception vs later | Prioritize; no feature expansion | Cluster feedback → freeze-exception vs later |
| 15.9 | Beta exit gate | Human | Open | Metrics rollup | Sign G15 | Sign G15 |

### 16 Legal

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 16.1 | Terms of Service | Human | Open | Do not invent ToS; list product behaviors for counsel | Lawyer drafts and publishes | Lawyer drafts and publishes |
| 16.2 | Privacy policy | Human | Open | Data-category inventory from DPDP_POSTURE | Lawyer drafts and publishes | Lawyer drafts and publishes |
| 16.3 | DPA/MSA/SLA | Human | Open | SLO numbers from 11.4 once approved | Lawyer/sales templates | Lawyer/sales templates |
| 16.4 | Refund/cancellation policy | Split | LLM done · Human open | Make billing code match the written policy | Finance writes the policy | docs/ops/REFUND_CANCELLATION.md |
| 16.5 | Support readiness | Human | Open | Macros/runbooks | Staff + live SLA | Staff + live SLA |
| 16.6 | Data export/deletion ops | Split | LLM done · Human open | Support playbook on erase_company | Execute a real request | Support playbook on erase_company |
| 16.7 | Insurance/risk review | Human | Open | None material | Broker + founder decision | Broker + founder decision |
| 16.8 | Commercial/legal gate | Human | Open | Evidence pack | Sign G16 | Sign G16 |

### 17 Launch

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| 17.1 | Paid beta | Human | Open | Live-mode checklist; recon job from 8.6 | Convert customers; live Razorpay | Convert customers; live Razorpay |
| 17.2 | GTM readiness | Split | LLM done · Human open | FAQs that match freeze (no GSTN-filing claim) | Positioning, pricing page, demo script | FAQs that match freeze (no GSTN-filing claim) |
| 17.3 | Sales/support training | Split | LLM done · Human open | Training deck from A1–A26 + limitations | Run the training; knowledge check | Training deck from A1–A26 + limitations |
| 17.4 | Hypercare plan | Human | Open | Daily-review checklist | Named owners, 7/30-day coverage | Named owners, 7/30-day coverage |
| 17.5 | Launch gate | Human | Open | Fill RELEASE_CHECKLIST from evidence | All roles sign GO_NO_GO | All roles sign GO_NO_GO |
| 17.6 | Public launch | Human | Open | Flag profile for public; status page | Open signup | Open signup |
| 17.7 | Post-launch review | Split | LLM done · Human open | Incident/adoption rollup | Own 30-day actions | docs/ops/ADOPTION_ROLLUP.md |

### Continuous

| ID | Step | Lane | Status | LLM does | Human does | Evidence |
|---|---|---|---|---|---|---|
| C.1 | Security monitoring | Split | LLM done · Human open | Keep scans in CI | Triage accept-risk | Keep scans in CI |
| C.2 | Observability review | Split | LLM done · Human open | Dashboard/SLO drift report | Monthly review meeting | Dashboard/SLO drift report |
| C.3 | Compliance review | Human | Open | Change-triggered inventory | Counsel/CA when vendors/features change | Counsel/CA when vendors/features change |
| C.4 | Release hygiene | Split | LLM done · Human open | SHA, notes, migrate SOP per release | Approve each prod deploy | SHA, notes, migrate SOP per release |

## How to update

1. Change **Status** / **Evidence** in this file when work lands.
2. Keep Excel IDs stable. Do not renumber to match the CSV.
3. Never mark a G-row Closed without a human signature in
   `docs/pilot/GO_NO_GO.md`.
4. Optional IDE view: Cursor canvas
   `saas-readiness-execution-plan.canvas.tsx` (Implementation tab).

