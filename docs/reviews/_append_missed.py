#!/usr/bin/env python3
"""Append missed-findings issues BB-000192..195 to MASTER_ISSUE_REGISTER.md"""
from pathlib import Path

p = Path(__file__).resolve().parent / "MASTER_ISSUE_REGISTER.md"
text = p.read_text(encoding="utf-8")
text = text.replace("| **Total issues** | 191 |", "| **Total issues** | 195 |")
text = text.replace("| Medium | 93 |", "| Medium | 97 |", 1)
text = text.replace("| P2 | 93 |", "| P2 | 97 |", 1)
text = text.replace("| Performance | 7 |", "| Performance | 9 |", 1)
text = text.replace("| DevOps | 12 |", "| DevOps | 13 |", 1)
text = text.replace("| Security | 34 |", "| Security | 35 |", 1)

append = r'''

---

## BB-000192 — No explicit Django CACHES / Redis cache backend configured

| Field | Value |
|-------|-------|
| **Issue ID** | BB-000192 |
| **Title** | No explicit Django CACHES / Redis cache backend configured |
| **Category** | Performance |
| **Subcategory** | Caching |
| **Severity** | Medium |
| **Priority** | P2 |
| **Module** | Core |
| **Feature** | Cache |
| **Affected Files** | backend/config/settings.py |
| **Status** | Open |
| **Owner** | Unassigned |
| **Review Date** | 2026-08-02 |
| **Estimated Effort** | 1d |
| **Cross References** | BB-000029; Missed Findings Pass (Caching) |

### Problem Description
settings.py defines Celery Redis broker but no `CACHES` setting. Django defaults to local-memory cache per process. Login lockout and any cache usage will not share state across gunicorn workers.

### Evidence
Grep of `settings.py`: no `CACHES` / RedisCache configuration. CELERY broker uses Redis separately.

### Root Cause
MVP omitted shared cache backend while adding multi-worker deploy.

### Business Impact
Security controls (lockout) ineffective under multi-worker load.

### Technical Impact
Per-process cache islands.

### Customer Impact
Weaker brute-force resilience than designed.

### Security Impact
Medium — lockout bypass across workers.

### Performance Impact
No reliable shared response/query caching.

### Scalability Impact
Worsens with worker count.

### Compliance Impact
N/A

### Risk if ignored
False sense of rate-limit/lockout protection.

### Steps to reproduce
1. Run multiple gunicorn workers.
2. Exhaust login failures on worker A.
3. Continue attempts on worker B — counter not shared.

### Recommended Fix
Configure `CACHES` to Redis pointing at the same Redis; require in production.

### Immediate Fix
Add Redis `CACHES` when `REDIS_URL` present; fail prod if missing.

### Short-term Fix
Same + document ops requirement.

### Long-term Refactor
Cache key versioning for company-scoped entries.

### Required Tests
Documented multi-worker lockout check.

### Acceptance Criteria
Production uses shared Redis cache; lockout counters shared across workers.

---

## BB-000193 — No structured LOGGING configuration (JSON / correlation IDs)

| Field | Value |
|-------|-------|
| **Issue ID** | BB-000193 |
| **Title** | No structured LOGGING configuration |
| **Category** | DevOps |
| **Subcategory** | Observability |
| **Severity** | Medium |
| **Priority** | P2 |
| **Module** | Core |
| **Feature** | Logging |
| **Affected Files** | backend/config/settings.py |
| **Status** | Open |
| **Review Date** | 2026-08-02 |
| **Estimated Effort** | 2d |
| **Cross References** | Observability gaps; Missed Findings Pass (Logging) |

### Problem Description
No `LOGGING` dict in settings. Default Django logging is unstructured; no request-id / company_id correlation for SaaS incident response.

### Evidence
Grep settings: no `LOGGING`. Tasks use `logging.getLogger` but handlers/format unspecified for prod aggregation.

### Root Cause
MVP default logging.

### Business Impact
Slow incident diagnosis for paid pilot.

### Technical Impact
Hard to ship logs to aggregators with queryable fields.

### Customer Impact
Longer downtime during failures.

### Security Impact
Harder to detect auth abuse patterns in logs.

### Performance Impact
N/A

### Scalability Impact
Ops cost rises with tenants.

### Compliance Impact
Ops audit trail weak (app `AuditEvent` is separate).

### Risk if ignored
Blind SRE.

### Steps to reproduce
1. Inspect settings for `LOGGING` — absent.
2. Run API — default console text logs only.

### Recommended Fix
Add JSON logging with request_id middleware; include company_id when authenticated.

### Immediate Fix
Basic `LOGGING` dict with verbose console.

### Short-term Fix
JSON + correlation IDs.

### Long-term Refactor
OpenTelemetry traces + log correlation.

### Required Tests
Middleware sets request_id.

### Acceptance Criteria
Prod logs are structured JSON with request_id.

---

## BB-000194 — SMS OTP printed via print() to stdout

| Field | Value |
|-------|-------|
| **Issue ID** | BB-000194 |
| **Title** | SMS OTP printed via print() to stdout |
| **Category** | Security |
| **Subcategory** | Logging |
| **Severity** | Medium |
| **Priority** | P2 |
| **Module** | Accounts |
| **Feature** | SMS |
| **Affected Files** | backend/core/services/sms.py |
| **Status** | Open |
| **Review Date** | 2026-08-02 |
| **Estimated Effort** | 0.5d |
| **Cross References** | BB-000002; BB-000003; BB-000006 |

### Problem Description
Console SMS provider prints OTP to stdout, which lands in container logs and aggregators.

### Evidence
`sms.py` uses `print(...)` for OTP delivery stub.

### Root Cause
Dev stub convenience.

### Business Impact
OTP leakage via log access.

### Technical Impact
Secrets in stdout.

### Customer Impact
Account takeover if logs shared.

### Security Impact
Medium-High in shared log systems.

### Performance Impact
N/A

### Scalability Impact
N/A

### Compliance Impact
Credential-in-logs hygiene failure.

### Risk if ignored
OTP harvest from log platforms.

### Steps to reproduce
1. Enable console SMS path.
2. Request OTP.
3. Observe OTP in process stdout.

### Recommended Fix
Never print OTP; gate debug echo behind `OTP_DEBUG_ECHO` with `logger.debug` only when `DEBUG`.

### Immediate Fix
Remove `print`; use gated debug logger.

### Short-term Fix
Secret redaction filter in logging.

### Long-term Refactor
Real SMS provider; no local echo.

### Required Tests
Assert logs do not contain OTP in non-debug configs.

### Acceptance Criteria
No OTP plaintext in default logs.

---

## BB-000195 — No application-level caching strategy for masters/reports

| Field | Value |
|-------|-------|
| **Issue ID** | BB-000195 |
| **Title** | No application-level caching strategy for masters/reports |
| **Category** | Performance |
| **Subcategory** | Caching |
| **Severity** | Medium |
| **Priority** | P2 |
| **Module** | Reporting |
| **Feature** | Caching |
| **Affected Files** | backend/reporting/; backend/masters/ |
| **Status** | Open |
| **Review Date** | 2026-08-02 |
| **Estimated Effort** | 5d |
| **Cross References** | BB-000192; Performance review |

### Problem Description
Hot-path read models (tax rates, units, products, dashboard aggregates, GSTR packs) have no explicit cache/invalidation strategy. FE compounds load via `fetchAllPages`.

### Evidence
No company-scoped cache get/set patterns in reporting/masters services; no `CACHES` backend (BB-000192).

### Root Cause
Correctness-first MVP without read-model cache layer.

### Business Impact
Latency under concurrent users.

### Technical Impact
DB load amplification.

### Customer Impact
Slow dashboard/GSTR.

### Security Impact
N/A (must be company-scoped if added).

### Performance Impact
Medium — grows with tenants.

### Scalability Impact
High at 10k tenants without cache.

### Compliance Impact
Cached GSTR must invalidate on Complete/H9 (ties to dirty flags).

### Risk if ignored
Premature scale failure.

### Steps to reproduce
1. Load dashboard repeatedly for a large company.
2. Observe repeated heavy queries.

### Recommended Fix
After Redis `CACHES`: short TTL for masters; snapshot cache for GSTR periods; invalidate on document Complete/Amend.

### Immediate Fix
Document limitation for small pilots.

### Short-term Fix
Masters short TTL cache.

### Long-term Refactor
Materialized dashboard / snapshot store.

### Required Tests
Cache hit/miss + invalidation on invoice complete.

### Acceptance Criteria
Company-scoped cache keys; invalidation on writes.
'''

p.write_text(text + append, encoding="utf-8")
print("OK: register now 195 issues")
