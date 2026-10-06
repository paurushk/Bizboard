# Bizboard — ISO/IEC 25010 Pre-Production Quality Assessment

**Date:** 2026-10-02 · **Assessor stance:** adversarial, evidence-first · **Scope:** `E:\Bizboard` (Django/DRF backend, React/MUI web, Capacitor Android shell, compose/nginx/CI)
**Status of this document:** one-off audit snapshot. It is *not* a live routing doc (see `docs/TESTING_STRATEGY.md` and `docs/PRODUCT_QUALITY_BACKLOG.md` for those).

## 0. How to read this — evidence legend

| Tag | Meaning |
|---|---|
| **V** | Verified — I read the code/config/script myself in this session |
| **PV** | Partially verified — sampled, or verified one side only |
| **C** | Claimed in docs/backlog; I did not re-verify |
| **NI** | Not implemented (searched; nothing found) |
| **U** | Unknown — **EVIDENCE REQUIRED** |

**What I actually did:** read `config/settings.py` security/Celery blocks, `core/views.py` (health), `core/viewsets.py`, 8 of the 12 non-`CompanyScopedViewSet` viewsets, `core/rls.py`, `nginx/default.conf`, `docker-compose.prod.yml`, `scripts/backup.sh`, `.github/workflows/ci.yml` (job list), `load/README.md`, `docs/pilot/GO_NO_GO.md`, `docs/PRODUCT_QUALITY_BACKLOG.md`, `docs/TESTING_STRATEGY.md` §2, `web/package.json`, the built `dist/`, and `git status`. I grepped for MFA, idempotency, audit immutability, upload validation, float money, observability libs. **What I did not do:** run the full 2,389-test backend suite (too slow in this environment on SQLite — see §15 for what did run), run the app, load-test, pen-test, or review all 112 `APIView`s and ~179 pages individually. Anything outside the "read" list above is C or U.

---

## 1. Executive Summary

**Overall picture.** This is an unusually *self-aware* codebase. Compared with typical pre-pilot SaaS, it has: fail-fast production settings, a tenant-scoped base viewset used by 67 of 80 viewsets, durable idempotency keys, upload magic-byte sniffing plus ClamAV in the prod compose, rotating+blacklisted refresh tokens in httpOnly cookies, an invariant sweep that runs after *every* test in CI, Postgres-in-CI, CodeQL, pip-audit, npm audit, Trivy, digest-pinned images, a weekly backup-restore drill, and ~2,400 backend test functions. The quality-governance layer (Q-OS, freeze-scope coverage ledger) is itself the most mature I have seen at this stage.

**The core problem is not code quality; it is the gap between "built" and "proven".** The strongest evidence in the repo is *engineering-side*. Nearly every item that would convince a paying customer, auditor or CA is either unsigned, unmeasured, or has no environment to run in:

- Go/No-Go: every human signature row blank (V). TLS edge not built (V). Sentry/on-call, SMTP, image-digest-on-host, CA letter, ≥5-company UAT: all unchecked (V).
- Performance SLOs (p95 <800 ms complete / <2 s list / <500 ms dashboard on 50k invoices) are *defined but never measured*: `load/results/` does not exist (V). Prod runs **2 sync gunicorn workers** by default (V).
- Real non-technical-user usability has never been observed (QOS-0029, C).

**Major strengths:** tenant isolation design; money handled as `Decimal` with explicit `ROUND_HALF_UP`; secrets/CORS/CSRF/HSTS guard rails; test *architecture* (invariants, workflow chains, persona journeys, matrices); honest backlog (0 Critical, 21 open).

**Major weaknesses:**
1. **Evidence applies to HEAD, not to what would ship.** `git status` shows ~396 changed paths / **228 modified files, +7,356/−4,019 lines uncommitted** (V). CI results, the Go/No-Go "zero open Criticals" tick, and this assessment's pass/fail all describe a tree that is not the working tree.
2. **Tested runtime ≠ shipped runtime.** CI uses Python **3.13** and Node **22**; the API image is `python:3.14-slim` and the web image `node:26` (V). Memory notes record a 3.13 standardisation decision — the Dockerfile does not follow it.
3. **Recoverability is weaker than the drill suggests.** Backups write to a local `/backups` dir only, fall back to an *unencrypted* dump with just a stderr warning, and retain by count (14), not by time (V). No offsite copy, no PITR/WAL archiving (NI). RTO 4m6s was measured on a one-company demo dataset (C, GO_NO_GO).
4. **No MFA, no tamper-evidence on the audit log** (NI — searched app code excluding venv/tests; `AuditEvent` is a plain model, and erasure/restore code paths `delete()`/`update()` it).
5. **Capacity is unmeasured and probably thin** (2 sync workers × N containers; 120 s timeout; PDF generation and bill extraction are already queued to Celery (V: `pdf_actions.py`, `extract_purchase_bill_task`); other long reports/imports unaudited — PV).

**Critical unknowns:** multi-tenant isolation of the 112 `APIView`/generic views (relies on a baseline file + sweep test I did not audit); behaviour under Postgres concurrency (local suite skips `postgres` tests); real backend behaviour of the UX fixes (QOS-0097); a11y beyond the axe-smoke route list.

**Immediate priorities (in order):** (1) commit/branch-protect and re-run the full gate on a clean tree; (2) align runtime versions CI↔image; (3) stand up a real staging host with TLS + Sentry + SMTP and *execute* the k6 SLO run on a 50k tenant; (4) offsite encrypted backups + a time-based retention policy + a PITR decision; (5) decide MFA/audit-tamper stance for the pilot's risk profile.

**Verdict:** **⚠️ Conditional for a controlled, owner-supervised pilot; ❌ Blocked for general release.** No *confirmed* P0 defect found. Several P1s are ops/governance, not code.

---

## 2. ISO/IEC 25010 Quality Matrix

Severity per §SEVERITY in the brief. "Status" uses the evidence legend.

| Characteristic | Sub-characteristic | Status | Evidence | Gap | Sev | Recommendation |
|---|---|---|---|---|---|---|
| Functional suitability | Completeness | PV | Freeze scope + WF-01..60, 10 presets (C); QOS gaps: milestone billing/job-work unbuilt (QOS-0028), RCM/TDS-TCS returns/fixed assets/BoE deliberately out (C) | Scope is narrow by decision; fine if sales honours it | P3 | Make freeze scope customer-visible at sale |
| | Correctness | PV | `Decimal` + `ROUND_HALF_UP` in `sales/services.py` (V); no float money found in sampled money paths (V); invariants + CA parity guard (C) | AP vs AR aging use different truth models with books on (QOS-0053, C); weighted-cost not FIFO (accepted) | P2 | Resolve QOS-0053; quantify FIFO delta |
| | Appropriateness | PV | Editors "show too many controls at first sight" (QOS-0095, C) | Cognitive load on core create-invoice flow | P2 | Progressive disclosure; time-to-first-invoice test |
| Performance efficiency | Time behaviour | **U** | SLOs defined (V `load/README.md`); `load/results/` absent (V) | **No measured p50/p95/p99 anywhere** | **P1** | Execute k6 SLO on 50k tenant; commit dated result |
| | Resource utilisation | U | 2 sync gunicorn workers default (V); pgbouncer.ini exists (V) | No CPU/RAM/conn budgets | P2 | Define limits; measure |
| | Capacity | U | Dashboard budget unmeasured (QOS-0016, C) | Unknown concurrent-user ceiling | **P1** | Soak + concurrency test |
| Compatibility | Co-existence | PV | Compose stack; documented port/Redis gotchas (memory) | Redis hard-required even for dev | P3 | Document |
| | Interoperability | PV | Webhook-forgery tests (QOS-0002 fixed, C); durable idempotency (V); circuit breaker module (V exists) | GSP live blocked; WhatsApp planned; schema-change handling for third parties U | P2 | Contract tests per provider |
| Usability | Recognisability / learnability | U | Onboarding + help exist (C) | Never tested with real staff (QOS-0029) | **P1** | 5-user unaided task study |
| | Operability | PV | POS keyboard tests (V files exist); lazy routes (139) | Touch-target/keyboard gaps remain (QOS-0096) | P1 | Close QOS-0096 |
| | Error protection | PV | `UnsavedChangesGuard` + regression test (C) | POS reload mid-settlement could double-invoice (CR-091/QOS-0056 "verified" C) | P2 | Re-verify with real backend |
| | Accessibility | PV | axe smoke spec (V); ESLint 0-error CI-gated (C) | Axe covers a route subset only; Hindi coverage gaps (QOS-0098) | P1 | Axe on all routes in CI + manual SR pass |
| Reliability | Maturity | PV | 0 Critical open (C); 375 migrations (V) | Regression history not measured | P3 | Track escaped-defect rate in pilot |
| | Availability | U | `/health/` liveness + `?ready=1` (V); healthchecks in compose (V) | Single-host compose; no HA story, no uptime target | P2 | Declare SLO + failure domains |
| | Fault tolerance | PV | Broker timeouts/retry policy (V); chaos drill QOS-0050 (C) | Beat is a single instance (V compose) | P2 | Drill + doc |
| | Recoverability | PV | Weekly restore-drill CI (V); RTO 4m6s demo-size (C) | Local-only backups, unencrypted fallback, no PITR | **P1** | See F-REL-01 |
| Security | Confidentiality | PV | `CompanyScopedViewSet` ×67 (V); 8/12 others sampled OK (V); RLS disabled by decision (QOS-0070) | 112 APIViews unaudited by me; RLS off = app-layer only | **P1** | Exhaustive isolation proof (F-SEC-01) |
| | Integrity / accountability | PV | `AuditService.log` on CRUD (V) | Audit log not tamper-evident; deletable by erasure path | P2 | Hash-chain or WORM export |
| | Authenticity | PV | JWT in httpOnly cookie, rotate+blacklist, 15 m access (V); login 10/min (V) | **No MFA** (NI); OTP login only | P1 (for money-handling roles) | TOTP for OWNER/ACCOUNTANT |
| | Transport | PV | HSTS/secure cookies conditional on env (V) | **No TLS edge exists** (V, QOS-0020) | **P0 for any internet exposure** | Gate deploy on `edge_tls_smoke.sh` |
| Maintainability | Modularity | PV | 25+ Django apps; `status_semantics.py` canonical predicates (C) | 1,100-line settings; `tenant_backup.py` ≥1,867 lines (V) | P3 | Split |
| | Testability | V | 2,389 test funcs, ~70k LOC; invariants sweep; cov floor 83 %, diff-cover 80 (V) | Mutation testing blocked (QOS-0019 "fixed" C); no static typing in CI (NI in ci.yml grep) | P2 | mypy on money/tax/stock |
| | Analysability | PV | X-Request-ID middleware, Sentry hooks (V) | Token-protected Prometheus `/metrics` exists (V: `core/ops_metrics.py`: requests, 5xx, duration sum/count, Celery failures, queue depth, DLQ, circuit, DB/Redis/Celery/beat health); counters are per-process and there was no latency histogram (added 2026-10-02); `tracing.py` is an in-process span helper, not wired to an exporter (V) | P2 | Pick OTel or Prometheus |
| Portability | Installability | PV | Digest-pinned images, compose profiles (V) | Image/CI runtime skew (V) | **P1** | F-PORT-01 |
| | Adaptability / replaceability | PV | LLM provider switch (V); Postgres-only features (RLS, `select_for_update` ×208) | SQLite used locally masks lock behaviour | P2 | Make Postgres the dev default |
| Quality in use | Effectiveness / efficiency | U | No field data | — | **P1** | Pilot metrics (H-01..H-05) |
| | Freedom from risk | PV | Financial: invariants; compliance: CA letter pending (V unchecked); privacy: DPDP checklist unsigned (C) | Unsigned compliance artefacts | P1 | Sign or waive explicitly |

---

## 3. Detailed Findings

Only significant ones. IDs are local to this document (`F-*`); map to QOS items where one exists.

### F-REL-01 — Backups are local-only, can silently be unencrypted, retention is count-based
- **ISO:** Reliability › Recoverability (also Security › Confidentiality)
- **Observation / Evidence (V):** `scripts/backup.sh` writes to `/backups` inside the container; if neither `BACKUP_GPG_RECIPIENT` nor `BACKUP_AGE_RECIPIENT` is set it writes a plaintext dump with only a stderr `WARNING`; prunes with `ls -1t | tail -n +15` (last 14 files, regardless of age). No upload step; no WAL archiving (searched compose + scripts).
- **Impact:** Host/disk loss = total loss of every tenant's books. A plaintext multi-tenant dump on the same volume as the DB is one volume-snapshot leak away from a DPDP incident. If backups stall, "14 dumps" silently becomes weeks.
- **Severity:** **P1**
- **Root cause:** Backup treated as a script, not a service with an RPO owner.
- **Recommendation:** Fail closed (exit non-zero) when no encryption recipient; ship to object storage in another failure domain; add backup-age alert; decide PITR (WAL-G/managed Postgres) vs daily dump and state RPO.
- **Verification:** Kill the DB host in staging; restore from offsite only; run `check_invariants`.
- **Acceptance:** RPO ≤ 15 min (PITR) *or* ≤ 24 h explicitly accepted by founder in writing; restore from offsite ≤ 60 min at 50k-invoice tenant; alert fires if newest backup > 26 h old.

### F-PERF-01 — No measured performance; thin default capacity
- **ISO:** Performance › Time behaviour, Capacity
- **Evidence (V):** `load/README.md` defines SLOs but says "Do not claim these pass without a dated soak file"; `load/results/` doesn't exist. Compose/prod default `--workers 2` with sync class and `--timeout 120`. CI runs only a 30 s, 5-VU k6 smoke, labelled advisory (C/V).
- **Impact:** Two slow requests (PDF, import, report) occupy a container's entire capacity; the first pilot "month-end GST report" day is the first load test.
- **Severity:** **P1**
- **Recommendation:** Run X-01 on a 50k tenant (see `load/SEED_50K.md`); move to `gthread` or more workers sized from measurement; audit remaining long-running requests (large reports, imports, exports) — PDF and bill extraction are already async (V).
- **Acceptance (amended 2026-10-02, uplift plan D1/D2).** Two tiers. The bullet this amendment replaced required the target SLOs to pass at 25 users for 30 minutes before any score moved.
  - *Gate, required for ISO Performance = 3:* a dated k6 artefact; at 25 concurrent users for 30 min, no endpoint p95 > 8 s, error rate < 0.5 %, no worker OOM. Written acceptance of a miss does not waive this gate.
  - *Target SLOs, required to close this finding:* Complete < 800 ms, list < 2 s, dashboard < 500 ms, recorded at both a 10k-invoice tenant and a 50k-invoice tenant. Passing at 10k is the pilot-Go bar. Passing at 50k closes F-PERF-01. A miss with a root cause, a remediation date, and written founder acceptance can move the ISO score; the finding stays open, and QOS-0003 is re-statused from an unmeasured P1 to a measured, accepted P2.
  - *Async:* index the query or move the work to a task when p95 > 8 s. Flag 2–8 s. This replaces "async anywhere a request is over 2 s".
  - The 2026-09-12 laptop run (list p95 9.33 s) is history. It is not evidence for either tier.

### F-PORT-01 — Tested interpreter is not the shipped interpreter
- **ISO:** Portability › Installability; Reliability › Maturity
- **Evidence (V):** `ci.yml` pins `python-version: "3.13"` (5 places) and Node 22; `backend/Dockerfile` is `python:3.14-slim-bookworm@sha256…`; `web/Dockerfile` is `node:26-alpine…`. Memory records "standardised on 3.13".
- **Impact:** Behavioural/ABI differences (dependency wheels, `decimal`/`asyncio` changes, build tooling) are untested in the artefact customers run. Trivy scans the image but nothing *executes tests* in it (U — I did not read every job; confirm).
- **Severity:** **P1** (cheap to fix, nasty if it bites)
- **Recommendation:** Either pin Dockerfiles to 3.13/Node 22 LTS or move CI matrix to the shipped versions; add a CI job that runs a smoke + `manage.py check --deploy` *inside the built image*.
- **Acceptance:** `guard_config_consistency` (already exists) asserts Dockerfile and CI versions match.

### F-GOV-01 — Evidence is detached from the shipping tree
- **ISO:** Reliability › Maturity; Maintainability › Testability
- **Evidence (V):** `git status` — 396 entries; `git diff --stat`: 228 files, +7,356/−4,019, spanning backend (payments, sales serializers, insights, whatsapp), 100+ web pages, qos YAML, CI workflow itself.
- **Impact:** Nothing about CI, the Q-OS backlog, or Go/No-Go can be attributed to a reproducible SHA. `GO_NO_GO.md` itself says no "Go SHA" has been cut.
- **Severity:** **P1**
- **Recommendation:** Commit in reviewable slices; tag a release-candidate SHA; require green CI on that SHA before any sign-off row is ticked.
- **Acceptance:** `git status` clean on RC; Go/No-Go records RC SHA = deployed image digest.

### F-SEC-01 — Tenant isolation is proven by sampling and by convention, not exhaustively
- **ISO:** Security › Confidentiality
- **Evidence (V/PV):** `CompanyScopedViewSet.get_queryset` filters by company; 67/80 viewsets use it. I read 8 of the 12 that don't — each filters by company explicitly. **112 `APIView`/`generics.*` classes** were counted but not individually read. RLS is intentionally off for the pilot (QOS-0070). A baseline file `tests/tenancy/_isolation_baseline.txt` + `test_endpoint_isolation.py` (20 tests) exist (V exist, not audited).
- **Impact:** A single missed `.objects.get(pk=…)` in an `APIView` is a cross-tenant IDOR — the highest-impact defect class for this product.
- **Severity:** **P1 (EVIDENCE REQUIRED)**
- **Recommendation:** Auto-generate the isolation test from the URL conf: for every route × method, call as tenant A with a tenant-B object id, assert 404/403. Fail CI if a route isn't covered or allow-listed. Then evaluate enabling RLS in staging with a non-superuser DB role (the restore drill already showed the dev role is BYPASSRLS — `core.W001/W002`).
- **Acceptance:** 100 % of routes classified (isolated / public / allow-listed with reason); zero cross-tenant reads/writes.

### F-SEC-02 — No MFA; password+OTP only for roles that move money
- **ISO:** Security › Authenticity
- **Evidence (NI):** no `pyotp`/TOTP in requirements or app code; `accounts/urls_auth.py` exposes OTP *request/verify* for login/registration only.
- **Impact:** A phished OWNER credential = ability to record payments, alter masters, export tenant data.
- **Severity:** **P1** for OWNER/ACCOUNTANT; P3 for others.
- **Recommendation:** TOTP (optional-then-mandatory for OWNER), recovery codes, step-up auth for destructive/export actions.
- **Acceptance:** Enrolment + enforce-by-role flag; replay and brute-force tests; audit event on enrol/disable.

### F-SEC-03 — Audit log is not tamper-evident
- **ISO:** Security › Non-repudiation/Integrity
- **Evidence (V):** `core.models.AuditEvent` is an ordinary table; `accounts/erasure.py:136` and `tenant_backup.py:1867` bulk delete/update it (erasure is a legitimate path). No DB trigger, hash chain, or external sink found (NI).
- **Impact:** A DBA/compromised app credential can rewrite history undetectably; weakens any statutory-audit claim.
- **Severity:** P2 (P1 if sold on "audit trail" to CA-led customers)
- **Recommendation:** Revoke UPDATE/DELETE on the table for the app role (erasure via a separate privileged job); per-row hash chain; nightly export to immutable storage.
- **Acceptance:** App role cannot `UPDATE auditevent`; chain verifier command passes and detects a seeded tamper.

### F-SEC-04 — TLS is a deployment assumption, not an enforced property
- **ISO:** Security › Confidentiality in transit
- **Evidence (V):** `nginx/default.conf` is HTTP-only and says so; production settings set `Secure` cookies (so an HTTP deploy *breaks login rather than leaking* — good fail-closed) but `SECURE_SSL_REDIRECT` defaults off. QOS-0020 is open; Go/No-Go TLS row unchecked.
- **Severity:** **P1 → P0 the moment the app is internet-reachable without an edge.**
- **Acceptance:** `edge_tls_smoke.sh` PASS output pasted against the real pilot host; HSTS preload decision recorded.

### F-SEC-05 — Local secrets hygiene (informational)
- **Evidence (V):** untracked-but-present `.env` (contains non-empty provider API keys: OpenAI/Anthropic/DeepSeek, SMTP, Fernet key) and `.ux-audit-credentials.local` (plaintext passwords for 7 seeded accounts). Both are in `.gitignore`/`.cursorignore` and `git ls-files` shows only `*.example` tracked — **no repo leak found**.
- **Severity:** P3. **Action:** rotate any key that has ever left this machine (backups, screen shares, synced folders, the `backups/`-style dirs); keep `gitleaks` in CI (config exists, V).

### F-REL-02 — Concurrency correctness proven only on Postgres, and only in CI
- **ISO:** Reliability › Maturity; Data integrity
- **Evidence (V/C):** 208 `select_for_update` call sites; tests marked `postgres` are skipped on SQLite; local default test DB is SQLite (`pytest.ini`, `--reuse-db`). QOS-0006 "fixed" (C).
- **Impact:** A developer's green local run says nothing about double-complete/double-allocate races.
- **Severity:** P2. **Action:** docker-compose Postgres as the default dev/test DB; keep the strict sweep.

### F-FUNC-01 — Two "truths" for AR/AP once books are on
- **Evidence (C, QOS-0053, CR-100/101):** AP aging and AR aging use different models; dashboard card vs list can disagree.
- **Impact:** The classic trust-killer: owner sees one payables number on the dashboard and another in the aging report. **P2**, but high perceived severity.
- **Acceptance:** projection-identity test (L10) pins dashboard AP = aging AP across returns/debit notes/part-payments.

### F-UX-01 — First-time usability is unobserved; editors are dense
- **Evidence (C):** QOS-0029 (open, hypothesis), QOS-0095 (open, L), QOS-0096/0098 (in progress). Hindi strings partially missing.
- **Severity:** **P1** for a product whose buyer is a non-technical MSME owner.
- **Acceptance:** 5 target users complete "create GST invoice → receive payment → view outstanding" unaided; median ≤ 4 min; ≥ 4/5 without facilitator help; SUS ≥ 70.

### F-OBS-01 — Detect/diagnose exist; metrics, alerting, on-call do not
- **Evidence (V):** request-id middleware + Sentry tag binding; `ops_metrics.py`, Django-admin health page; Sentry is optional DSN. A hand-rolled Prometheus `/metrics` endpoint exists (V) but had no histogram and per-process counters (histogram added 2026-10-02); no OTel/tracing exporter (V). Go/No-Go Sentry+on-call row unchecked.
- **Severity:** P2. **Acceptance:** defined alerts (5xx rate, p95, queue depth, backup age, failed webhooks); a drill where an injected 500 reaches the on-call phone ≤ 5 min.

### F-TEST-01 — Test volume is strong; behaviour-level gaps remain at the edges
- **Evidence:** CI gate set is excellent (V). Gaps: mutation testing only "unblocked" (C); no static typing job; axe covers a hand-picked route list (V); e2e on Chromium (+webkit install seen in CI at line ~254, PV); concurrency Postgres-only; a "stubs" workflow file with skipped tests (V: `test_wf_extended_stubs.py`).
- **Severity:** P2. See §10.

---

## 4. Critical Workflow Assessment

Ratings: ✅ evidence good · 🟡 partial · ❌ weak/absent · ❓ unknown. Based on docs + sampled code; UX/Perf columns are mostly ❓ because nothing was observed live.

| Workflow | Functional | UX | Perf | Reliability | Security | Data integrity | Result |
|---|---|---|---|---|---|---|---|
| Sales invoice → Complete (stock↓, tax, GL, AR) | ✅ WF chains + invariants (C) | 🟡 dense editor (QOS-0095) | ❓ SLO unmeasured | 🟡 idempotency V, races PG-only | ✅ scoped + RBAC | ✅ Decimal, invariants | ⚠️ |
| POS checkout / offline outbox | 🟡 | 🟡 keyboard tests exist; touch gaps | ❓ | 🟡 reload double-invoice fixed (C) | ✅ | 🟡 | ⚠️ |
| Receipt allocation / credit notes after allocation | ✅ | 🟡 | ❓ | 🟡 | ✅ | 🟡 QOS-0087 "verified" (C) | ⚠️ |
| Purchase bill (OCR/LLM) → GRN → stock | 🟡 | 🟡 | ❓ async extraction (V); latency unmeasured | 🟡 provider outage handling U | ✅ upload sniff + ClamAV | 🟡 second stock-post check QOS-0085 | ⚠️ |
| GST returns worksheets → CA files | 🟡 offline worksheets only | 🟡 | ❓ | ✅ | ✅ | 🟡 H-05 unproven | ⚠️ (CA sign-off ❌) |
| Bank reconciliation | 🟡 two UIs, one state (QOS-0082 C) | 🟡 | ❓ | 🟡 | ✅ | ✅ | ⚠️ |
| Period close / soft-lock | 🟡 | 🟡 | ❓ | 🟡 TOCTOU QOS-0054 "verified" | ✅ | 🟡 | ⚠️ |
| Onboarding / first run | 🟡 | ❓ untested with users | ❓ | ✅ | ✅ | ✅ | ⚠️ |
| Tenant backup/restore, erasure | 🟡 tooling exists (V sizes) | n/a | ❓ | 🟡 | ✅ | 🟡 audit rows mutated by design | ⚠️ |
| Login / session | ✅ | 🟡 | ✅ | ✅ | 🟡 no MFA | ✅ | ⚠️ |

---

## 5. Security Findings (separated)

| ID | Finding | Sev | Attack scenario | Status |
|---|---|---|---|---|
| F-SEC-01 | Isolation not exhaustively proven (112 APIViews, RLS off) | P1 | Tenant-A user calls `/…/<id>` of tenant B on an `APIView` lacking company filter | EVIDENCE REQUIRED |
| F-SEC-02 | No MFA | P1 | Phished OWNER cookie/password → payment/master tampering, exports | NI |
| F-SEC-03 | Audit log mutable | P2 | Insider with DB role edits history | NI |
| F-SEC-04 | No TLS edge | P1/P0 | Pilot exposed over HTTP → cookie/data interception (cookies are `Secure`, so login would fail rather than leak, *unless* an operator disables that) | V |
| F-SEC-06 | Backup plaintext fallback | P1 | Volume snapshot leak = all tenants' PII/finance | V |
| F-SEC-07 | CSRF cookie `HttpOnly=False` (by design for SPA double-submit) with `SameSite=Lax` | P3 | XSS → CSRF token read; mitigated by strict CSP (`script-src 'self'`, V in nginx) | V, acceptable |
| F-SEC-08 | CSP allows `style-src 'unsafe-inline'` (MUI/Emotion) | P3 | Style injection exfil is low-grade; known trade-off | V |
| F-SEC-09 | External pen-test not performed (QOS-0011 note) | P2 | Unknown-unknowns | C |

**Verified positives (V):** DEBUG/ALLOWED_HOSTS/secret-key fail-fast; SameSite=None refused without explicit opt-in; wildcard CORS with credentials refused; refresh rotation + blacklist; throttles (anon 120/min, user 600/min, login 10/min) + nginx `limit_req` zones; `MaxBodySizeMiddleware`; upload magic-byte sniffing (`core/services/files.py`, `attachments.py`); ClamAV healthcheck gating `api` start in prod compose; no tokens in `localStorage`, no `dangerouslySetInnerHTML` in non-test web code (grep empty); `pip-audit`, `npm audit --audit-level=high`, Trivy, CodeQL, gitleaks config; webhook-forgery tests (C).

---

## 6. Performance & SLA Targets

Adopt these (extending the repo's X-01 SLOs). All **U** until measured.

| Surface | p50 | p95 | p99 | Max |
|---|---|---|---|---|
| Invoice Complete (50k-invoice tenant, ex-PDF) | 250 ms | **800 ms** | 1.5 s | 3 s |
| Invoice/purchase list | 400 ms | **2 s** | 3 s | 5 s |
| Dashboard | 200 ms | **500 ms** | 1 s | 2 s |
| Search | 150 ms | 600 ms | 1 s | 2 s |
| GST worksheet (1 month, 5k invoices) | — | 8 s | 15 s | async beyond 30 s |
| Invoice PDF | 1.5 s | 4 s | 8 s | 15 s |
| Bulk import 5k rows | async | job done ≤ 3 min | — | progress visible |
| Web: LCP on 4G mid-Android | — | ≤ 3 s | — | — |

- **Throughput:** 25 concurrent users per tenant × 20 tenants (500 req/min mixed read/write) without p95 regression > 20 %.
- **Resources:** API container ≤ 70 % CPU / ≤ 512 MB RSS at target load; DB connections ≤ 60 % of pool (pgbouncer in place, V file).
- **Capacity:** 100k invoices/tenant, 1M stock movements/tenant, 5-year retention, without index-only degradation (needs `EXPLAIN` review of top 20 queries).
- **Frontend (V):** main entry chunk 901 KB raw / ~250 KB gzip (measured with gzip); 139 lazy routes — acceptable; budget: entry ≤ 300 KB gzip, enforced in CI (NI).
- **Batch:** Celery tasks soft/hard limit 600/660 s (V) — any task nearing that needs chunking.

**Amendment 2026-10-02 (uplift plan D2/D13/D14).** The p95 columns above are the *target SLOs*. The bar that blocks an ISO score of 3 is no endpoint p95 above 8 s at 25 users for 30 minutes. Requests between 2 s and 8 s are flagged. "512 MB / 70 % CPU" is an evaluation target, applied after the soak as 1.5 × measured peak, not a limit set beforehand. The frontend budget is a CI ratchet at the measured initial-load gzip size plus 10 %, not a fixed 300 KB cap. See the uplift plan.

---

## 7. Reliability & Recovery

| Item | Proposed target | Current evidence |
|---|---|---|
| Availability | 99.5 % monthly (pilot, business hours 8–22 IST ≥ 99.9 %) | Single-host compose (V); no HA; U |
| RTO | ≤ 60 min | 4m6s on demo data (C); **U at pilot volume** |
| RPO | ≤ 15 min with PITR, else ≤ 24 h explicitly accepted | daily `pg_dump`, local only (V) → effective RPO = 24 h *if the host survives* |
| Backups | Encrypted, offsite, ≥ 30 days + 12 monthly, age alert | Not met (F-REL-01) |
| Recovery tests | Monthly restore from offsite + `check_invariants` | Weekly CI drill on fresh dump (V) — good, wrong source |

Failure-scenario matrix (what I could and could not confirm):

| Scenario | Expected | Evidence |
|---|---|---|
| Redis down | Throttle/cache degrade, `/health/` doesn't 500, tasks queue fails fast | Settings: broker timeout 2 s, retry 1 (V); health `throttle_classes=[]` (V); Redis required for dev (memory) |
| Postgres down | `/health/` → 503; no data loss | V code; chaos drill C |
| Worker/beat crash | Tasks retried; beat not duplicated | Single beat (V); duplicate-beat guard U |
| Third-party outage (LLM/GSP/WhatsApp) | Circuit breaker, user-visible degraded state | `circuit_breaker.py` exists (V); per-provider behaviour U |
| Duplicate POST | Idempotent | Durable `IdempotencyRecord` (V); coverage across all money POSTs U |
| Mid-transaction browser refresh | Server state consistent | Invariant sweep (C); POS fix (C) |

---

## 8. UX & Usability Findings

All from backlog/docs (C) unless noted — I did not use the UI.
1. **Cognitive load:** invoice/purchase editors expose too many controls at first sight (QOS-0095).
2. **Learnability:** no unaided-operator observation (QOS-0029); `docs/UX_AUDIT_2026-09-30.md` exists and is the right input.
3. **Accessibility:** axe smoke on selected routes only (V); keyboard/touch-target/heading gaps (QOS-0096); loading/error/empty states missing on some pages (QOS-0098).
4. **Localisation:** Hindi shows English text in places; `hi.ts` modified but uncommitted (V).
5. **Error protection:** unsaved-changes guard (C); destructive-action confirmation consistency U.
6. **Mobile:** Android shell, sideloaded APK only (accepted, QOS-0073); mobile-viewport clipping guard (C).
7. **Dense data tables:** `@tanstack/react-virtual` present (V) — good for large lists.

Highest-risk friction: first invoice, POS on a phone-width device, and reading dashboard vs report numbers (F-FUNC-01).

---

## 9. Maintainability & Architecture Debt

- **Pattern:** modular monolith, Django apps per domain, DRF with a tenant base class, event/invariant layer, Celery. Sound for the scale.
- **Debt hotspots (V sizes):** `config/settings.py` 1,102 lines of mixed policy; `accounts/tenant_backup.py` ≥ 1,867 lines; 80 viewsets + 112 APIViews = two parallel patterns for tenant scoping (the root of F-SEC-01).
- **Dark modules** (Manufacturing/Payroll/CRM) are code that ships but is feature-flagged off; they still carry migrations, tests, and attack surface (`dark_module` marker).
- **Document sprawl:** root has 3 UX plan docs, 4 task-register spreadsheets/CSVs, `test.xlsx`, `raw_user_input.csv`, `REPOSITORY_AUDIT.md` etc. Signal-to-noise cost for new engineers; a staged archive move is already in progress (V git status).
- **Doc drift risk:** backlog marks many items `verified`/`fixed` on "heuristic" evidence; QOS-0057 shows prior stale-OPEN labels. Treat lifecycle labels as claims.
- **No static typing gate** (NI in CI list); money/tax/stock modules are the best candidates.
- **Observability:** `/metrics` (Prometheus text, token-protected) + Sentry + request-id logs; no scraper/alert rules shipped, no tracing exporter.
- **Architectural debt not yet producing bugs:** (a) sync request-path integrations (LLM/PDF); (b) RLS off + two scoping patterns; (c) audit mutability; (d) single Redis for broker + cache + throttle + results (V `CELERY_RESULT_BACKEND = CELERY_BROKER_URL`) — a broker flush also clears throttle/idempotency caches (idempotency itself is DB-durable, V).

---

## 10. Missing Tests — prioritised inventory

| Pri | Test | Layer | Why |
|---|---|---|---|
| P1 | Auto-generated route × method cross-tenant matrix incl. all `APIView`s | L2 | F-SEC-01 |
| P1 | k6 SLO run on 50k tenant + 30 min soak with dated artefact | L7 | F-PERF-01 |
| P1 | Smoke + `check --deploy` inside the built prod image (3.14/Node 26 or aligned) | L2 | F-PORT-01 |
| P1 | Restore from *offsite* backup at pilot volume + `check_invariants` | L7 | F-REL-01 |
| P1 | Real-backend Playwright golden for QOS-0097 claims (dashboard, POS, editors) | L6 | UX fixes unverified |
| P1 | Axe over **every** route + role in CI; manual screen-reader pass on POS/invoice | L6 | WCAG |
| P2 | Postgres-by-default concurrent tests: double Complete, double allocate, concurrent period close vs post | L3 | F-REL-02 |
| P2 | Idempotency replay for *every* money-moving POST (auto-discovered) | L2 | duplicate submit |
| P2 | Third-party chaos: LLM timeout/malformed JSON/schema drift; webhook replay & reordering | L2 | interoperability |
| P2 | Migration rehearsal on production-shaped data (QOS-0014 in progress) | L7 | upgrade safety |
| P2 | Audit-log tamper-detection test | L2 | F-SEC-03 |
| P2 | Projection identity: dashboard AP/AR = aging under returns/partials | L10 | F-FUNC-01 |
| P3 | Mutation testing on `sales/services.py`, tax, stock valuation | L1 | assertion strength |
| P3 | WebKit/Firefox + low-end Android emulation | L6 | compatibility |
| P3 | Hindi completeness test (no raw English keys) | L6 | QOS-0098 |
| P3 | Long-running job tests: import 50k rows, report 1 yr data, time-limit behaviour | L7 | capacity |

False-positive/weak-test risks to inspect: tests that assert on mocked Celery eager mode (hides broker ordering, QOS-0012); `test_wf_extended_stubs.py` skipped workflow stubs counted as coverage; coverage % as a proxy (floor 83 %) — line coverage ≠ behaviour (QOS-0019's own title).

---

## 11. Quality Improvement Backlog

| ID | Finding | ISO area | Pri | Action | Acceptance | Validation |
|---|---|---|---|---|---|---|
| QI-01 | F-GOV-01 | Maintainability | P1 | Commit slices, cut RC SHA, protect main | clean tree; RC green | CI on RC |
| QI-02 | F-PORT-01 | Portability | P1 | Align Python/Node CI↔images | guard passes; in-image smoke | CI job |
| QI-03 | F-REL-01 | Reliability | P1 | Offsite, encrypted, fail-closed backups, age alert | restore from offsite ≤ 60 min | Drill |
| QI-04 | F-PERF-01 | Performance | P1 | Execute X-01 at 10k and 50k; size workers | Gate met for ISO 3; target SLOs close the finding | k6 artefact |
| QI-05 | F-SEC-01 | Security | P1 | Generated cross-tenant matrix; evaluate RLS in staging | 100 % routes classified | CI gate |
| QI-06 | F-SEC-04 | Security | P1 | Build TLS edge on pilot host | `edge_tls_smoke.sh` PASS | pasted output |
| QI-07 | F-SEC-02 | Security | P1 | TOTP MFA for OWNER/ACCOUNTANT | enforced + tests | e2e + unit |
| QI-08 | F-UX-01 | Usability | P1 | 5-user unaided study; Sev-1s fixed before RC1 | Study + Sev-1s for ISO 3; SUS ≥ 70 and ≥ 4/5 are the 3→4 bar | study notes |
| QI-09 | A11y | Usability | P1 | Axe on all routes; SR pass | 0 serious/critical | CI + manual |
| QI-10 | Governance | Quality in use | P1 | Sign/waive GO_NO_GO rows with named owners | all rows decided | doc |
| QI-11 | F-OBS-01 | Maintainability | P2 | Alerts + on-call drill; Sentry live | alert reaches phone ≤ 5 min | drill |
| QI-12 | F-SEC-03 | Security | P2 | Revoke UPDATE/DELETE; hash chain | tamper detected | test |
| QI-13 | F-REL-02 | Reliability | P2 | Postgres default for dev/test | PG tests run locally | CI/local |
| QI-14 | F-FUNC-01 | Functionality | P2 | Resolve QOS-0053 + L10 test | numbers agree | test |
| QI-15 | Async | Performance | P2 | Audit remaining sync long-running requests; index or async when p95 > 8 s; flag 2–8 s | no sync endpoint p95 > 8 s | k6 |
| QI-16 | Typing | Maintainability | P2 | mypy on money/tax/stock | 0 errors in scope | CI |
| QI-17 | Dashboard budget | Performance | P2 | QOS-0016 with 12 months data | ≤ 500 ms p95 | test |
| QI-18 | Pen-test | Security | P2 | External test | no High open | report |
| QI-19 | Redis split | Reliability | P3 | Separate broker from cache | independent failure | chaos |
| QI-20 | Repo hygiene | Maintainability | P3 | Archive stray spreadsheets/CSVs | root clean | review |

---

## 12. Release Readiness

| Target | Verdict | Why |
|---|---|---|
| Internal / founder-supervised demo | ✅ Ready | Works to the level docs claim; no confirmed Critical |
| **Controlled pilot (≤ 5 friendly tenants, founder on call)** | **⚠️ Conditional** | Needs QI-01..06, QI-10 at minimum; explicit RPO acceptance |
| Paid GA / self-serve | ❌ Blocked | Unmeasured performance, no MFA/offsite DR/TLS edge, unsigned compliance, unobserved usability |
| Scale (100s of tenants) | ❌ Blocked | Single-host compose, no capacity data, RLS off |

I did not find an unresolved *confirmed* P0 **defect**. P0 conditions are environmental (internet exposure without TLS edge).

---

## 13. Top 20 Actions (Customer impact × Risk × Frequency × Criticality × Dependency)

1. Commit/slice the 228-file working tree; cut an RC SHA (unblocks every other claim).
2. Align CI and image runtimes; add in-image smoke.
3. Build the TLS edge on the real pilot host; paste `edge_tls_smoke.sh` PASS.
4. Offsite + encrypted + fail-closed backups; backup-age alert; state RPO.
5. Execute the 50k-tenant k6 SLO + soak; commit result.
6. Exhaustive cross-tenant route matrix (all APIViews) as a CI gate.
7. Restore-from-offsite drill at pilot data volume (re-measure RTO).
8. Sentry + on-call live; define the 6 core alerts.
9. 5-user unaided usability study on the core invoice→payment loop.
10. Axe on all routes/roles + manual screen-reader pass on POS/invoice.
11. TOTP MFA for OWNER/ACCOUNTANT + step-up for exports.
12. Resolve AR/AP aging truth models (QOS-0053) + projection-identity test.
13. Verify QOS-0097 fixes on a real backend (golden e2e).
14. Audit remaining long-running sync requests; right-size workers from measurement.
15. Postgres as default dev/test DB so concurrency tests run for everyone.
16. CA review of GST worksheets (H-05) — the single strongest credibility artefact.
17. Audit log tamper-resistance (revoke mutate, hash chain).
18. Close QOS-0095/96/98 (editor density, touch/keyboard, empty/error/Hindi).
19. Sign or explicitly waive DPDP checklist and ENV_CHECKLIST with named owners.
20. mypy gate on money/tax/stock; enable mutation testing on the same modules.

---

## 14. Final Quality Gate

**Gates (0–9)**

| Gate | Status | Evidence | Blocking | Exit criteria |
|---|---|---|---|---|
| 0 Architecture | ✅/⚠️ | Modular monolith, tenant base, invariants (V) | Two scoping patterns; single-host | Isolation matrix; HA decision |
| 1 Feature completeness | ⚠️ | Scope frozen, WF-01..60 (C); QOS-0028 etc. | Known limitations must be sold as such | Freeze scope in sales collateral |
| 2 Functional correctness | ⚠️ | Decimal/invariants (V); QOS-0053 | AR/AP truth split | L10 identity green |
| 3 UX readiness | ❌ | QOS-0029/95/96/98 open | Unobserved users; a11y gaps | Study + Sev-1s for ISO 3; SUS ≥ 70 is the 3→4 bar |
| 4 Security readiness | ⚠️ | Strong config (V) | Isolation proof, MFA, TLS, pen-test | QI-05/06/07/18 |
| 5 Performance readiness | ❌ | No measurements (V) | F-PERF-01 | 8 s gate for ISO 3; target SLOs close the finding |
| 6 Reliability readiness | ⚠️ | Weekly drill (V) | Offsite/PITR, on-call | QI-03/11 |
| 7 Production readiness | ❌ | GO_NO_GO mostly unchecked (V) | Host, TLS, Sentry, SMTP, digests | All Final Gates |
| 8 Pilot/customer readiness | ⚠️ | 0 Critical (C) | Signatures, CA worksheet review, ≥5-company UAT unless waived to 3 | GO_NO_GO signed |
| 9 Scale readiness | ❌ | — | HA, capacity, RLS | Post-pilot |

**What can be released:** a supervised pilot to ≤ 5 businesses within frozen scope (sales/purchase/inventory/GST worksheets), once QI-01–06 and QI-10 are done.
**What should not be released:** anything internet-exposed without TLS edge; any claim of "audited", "SOC-ready", "GST-filing-ready", or performance numbers; dark modules (manufacturing/payroll/CRM) beyond what the freeze says.
**Must fix first:** F-GOV-01, F-PORT-01, F-SEC-04, F-REL-01.
**Requires evidence before release:** F-SEC-01 (isolation), F-PERF-01 (target SLOs passing at the 10k tier for a pilot Go; the 8 s gate is the ISO-3 bar), F-UX-01 (usability), H-05 (CA worksheet review; filing is not required for the score), restore-from-offsite RTO.
**Safe to defer:** MFA for non-money roles, CSP `unsafe-inline` removal, WebKit/Firefox matrix, mutation testing rollout, Redis split, RLS (provided the isolation matrix exists), repo hygiene.
**Monitor continuously post-release:** 5xx rate and p95 per endpoint; Celery queue depth and task failures; backup age and last-restore result; invariant failures per tenant (`check_invariants` nightly); webhook failure/retry counts; login failure/throttle spikes; cross-tenant 403/404 anomalies; time-to-first-invoice and weekly active users (H-01..H-05); dashboard-vs-report mismatch reports from support.

---

## 15. ISO/IEC 25010 Scorecard

Scores reflect *evidence*, not features. "Conf." = evidence confidence.

| Characteristic | Score | Conf. | Major gaps | Blocking risks | Next action |
|---|---|---|---|---|---|
| Functional suitability | **3** | Medium | AR/AP truth split; scope narrow by design; editor complexity | QOS-0053 | L10 identity test; CA review |
| Performance efficiency | **1** | Low | Zero measured data; 2 sync workers | F-PERF-01 (P1) | X-01 execution |
| Compatibility | **3** | Medium | Provider chaos/schema-drift untested; GSP/WhatsApp pending | — | contract tests |
| Usability | **2** | Low | No real-user observation; a11y subset; Hindi gaps | F-UX-01 (P1) | 5-user study |
| Reliability | **3** | Medium | Offsite/PITR; HA; chaos only claimed | F-REL-01 (P1) | offsite + drill |
| Security | **3** | Medium | Isolation proof; MFA; TLS edge; audit tamper; pen-test | F-SEC-01/02/04 (P1) | isolation matrix |
| Maintainability | **4** | Medium-High | No typing gate; big files; doc sprawl; uncommitted tree | F-GOV-01 (P1, process) | commit + mypy |
| Portability | **3** | Medium | Runtime skew; SQLite-vs-PG dev | F-PORT-01 (P1) | align versions |
| Quality in use | **2** | Low | No field data; unsigned compliance | Gate 8 | pilot metrics |

No numerical score above should be read as hiding a P0/P1: Maintainability's **4** coexists with F-GOV-01; Security's **3** coexists with three P1s.

### Evidence from tests I ran in this session (working tree, SQLite, Python 3.13 venv)
- `tsc -b` on `web/`: **exit 0** (type-check clean on the working tree).
- `tests/tenancy` + `tests/errors/test_webhook_and_async_contracts.py`: **28 passed**, 0 failed (includes billing-webhook bad-signature + replay dedup).
- Full backend suite (2,389 test functions): **not completed** — too slow on SQLite here. A first subset run showed one `database is locked` failure; that was **my own artefact** (an earlier full-suite process I had started was still holding the SQLite test DB). It disappeared after stopping that process. It is *not* a product finding, but it does illustrate F-REL-02: SQLite as the default local DB gives misleading concurrency signals.
- Not run: web vitest, Playwright, k6, Postgres-marked tests, invariant sweep, `check --deploy`.
- Minor observation: `RuntimeWarning: DateTimeField SalesInvoice.ack_date received a naive datetime` in a test — a test-fixture hygiene issue (P3), not evidence of a production defect.

---

## 16. Unknowns (explicit EVIDENCE REQUIRED list)

1. Cross-tenant behaviour of every `APIView`/generic view (F-SEC-01).
2. Any measured latency, throughput, or resource number.
3. Whether any CI job executes tests inside the shipped image (F-PORT-01).
4. Real-backend behaviour of 2026-09-30/10-01 UX fixes (QOS-0097).
5. Idempotency coverage across all money-moving endpoints.
6. Third-party failure behaviour (LLM malformed output, webhook replay/order) beyond forgery tests.
7. Accessibility with a real screen reader; behaviour at 200 % text scale.
8. Migration safety on production-shaped data.
9. Whether anything scrapes `/metrics` on the pilot host and whether alert rules exist (the endpoint does; no scraper or rules are in the repo).
10. Whether the 8 or so "verified" backlog items marked on `heuristic` evidence hold on the RC SHA.
