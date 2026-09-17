# Pilot environment checklist (P0-506 / E6)

Sign before any host receives real pilot PII / GSTINs. Copy rows into the go-meeting notes with signer + date.

**Related:** DoD E1/E6/E10, A11; `.env.production.example`; `docs/pilot/RUNBOOKS.md`.

---

## Hard gates (Must — not Conditional-waivable)

| # | Check | Expected | OK | Notes |
|---|--------|----------|----|-------|
| 1 | **TLS (P0-501 / E1)** | HTTPS at the edge for every host with real PII/GSTINs. `USE_TLS=1` when Django sits behind TLS-terminating proxy so secure cookies / `SECURE_*` apply. Plain HTTP is a **hard no-go**. | ☐ | Terminating proxy (Caddy/nginx/cloud LB) counts if end-user traffic is HTTPS. QOS-0020: run `scripts/edge_tls_smoke.sh https://<pilot-host>` and paste its PASS line here — don't check this box on a claim alone. |
| 2 | `DJANGO_ENV` | `production` | ☐ | |
| 3 | `DJANGO_DEBUG` / `DEBUG` | `0` / false | ☐ | Must not run DEBUG under production env. |
| 4 | `DJANGO_SECRET_KEY` | Unique, ≥40 chars, not a placeholder from examples | ☐ | App refuses weak keys when `DJANGO_ENV=production`. |
| 5 | `DATABASE_URL` | Managed Postgres (or compose Postgres with durable volume + off-host backups) | ☐ | Prefer managed; never point pilot at shared/dev DB. |
| 6 | Redis | `REDIS_URL` reachable; Celery broker/result backend healthy | ☐ | |
| 7 | `OTP_DEBUG_ECHO` | `0` (and impossible outside DEBUG) | ☐ | Never echo OTP codes in pilot/prod responses or UI. |
| 8 | `CORS_ALLOWED_ORIGINS` | Exact pilot HTTPS origin(s) only | ☐ | No `*` / localhost leftovers. |
| 9 | `DJANGO_ALLOWED_HOSTS` | Pilot hostname(s) only | ☐ | |
| 10 | `ENABLE_API_DOCS` | `0` unless intentionally on for staging | ☐ | |

---

## Freeze Table B / known-limitation flags (must stay 0 on freeze hosts)

| # | Check | Expected | OK | Notes |
|---|--------|----------|----|-------|
| 10a | `ENABLE_GSTR` / `ENABLE_GSTN_JSON` / `ENABLE_TALLY` | `0` | ☐ | Worksheets stay C1; live filing is Table B. |
| 10b | `ENABLE_MANUFACTURING` / `ENABLE_PAYROLL` / `ENABLE_CRM` | `0` | ☐ | Paid plans must not grant these (`freeze_safe_modules`). |
| 10c | `ENABLE_FIXED_ASSETS` / `ENABLE_BOE` | `0` | ☐ | D6/D10 known limitations; Django default is now OFF. |
| 10d | `GSP_LIVE_ENABLED` / `ENABLE_WHATSAPP_CLOUD` / `ENABLE_ACCOUNT_AGGREGATOR` | `0` | ☐ | Preview / `wa.me` fallbacks only. |
| 10e | `VITE_ENABLE_GSTR` / `VITE_ENABLE_EINVOICE_SUBMIT` (image bake) | `false` | ☐ | CD and compose default false. |
| 10f | `ENABLE_POS` / `ENABLE_TDS` / `ENABLE_SETUP_WIZARD` | `1` | ☐ | Freeze-supported (A23 / A24 / A19). |

---

## Email / SMS

| # | Check | Expected | OK | Notes |
|---|--------|----------|----|-------|
| 11 | `EMAIL_HOST` / `EMAIL_PORT` / user / password | Working SMTP; `DEFAULT_FROM_EMAIL` set | ☐ | Run `python manage.py sendtestemail <you@company>` (Django built-in) with real SMTP env vars set and paste confirmation of receipt here — don't check this box on a claim alone. |
| 12 | `EMAIL_USE_TLS` | True for submission port (587) | ☐ | |
| 13 | `SMS_PROVIDER` + credentials | Configured **or** OTP login disabled in UI (`VITE_ENABLE_OTP` unset) | ☐ | Password login is the pilot default if SMS is not live. |

---

## Ops floor

| # | Check | Expected | OK | Notes |
|---|--------|----------|----|-------|
| 14 | Backup cron | Daily `pg_dump` (or managed snapshot) copied **off-host** | ☐ | See RUNBOOKS — volume alone ≠ backup. |
| 15 | Uptime URL | External checker on `GET /api/v1/health/` + alert | ☐ | |
| 16 | Celery worker | Running; queue depth watched during PDF bursts | ☐ | Prefer inspect/active over flaky celery ping healthchecks. |
| 17 | Image / deploy tags | Immutable tags recorded per release | ☐ | Needed for rollback (P0-508). |
| 18 | `SENTRY_DSN` + on-call routing | Errors reach Sentry; a real alert fires to on-call | ☐ | Playbook: `docs/ops/OGATE_HUMAN.md`. Set `SENTRY_DSN`, run `python manage.py sentry_test_event`, confirm the event lands in the Sentry project and pages on-call — paste the event id here, don't check this box on a claim alone. |

---

## DPDP minimum (P0-509 / E10)

| # | Check | Expected | OK | Notes |
|---|--------|----------|----|-------|
| 19 | Prod DB access list | Named people/roles with access; no shared “root” Slack password | ☐ | Attach list or link. |
| 20 | PII in logs | No OTP codes, full phone dumps, or document payloads in app/access logs | ☐ | Scrub before raising log level. |
| 21 | Backup encryption / location | Encrypted at rest (provider or `gpg`/KMS); location documented (region/bucket) | ☐ | |
| 22 | Retention | Backup retention window written (e.g. 30 days); media retention noted | ☐ | |
| 23 | Onboarding privacy line | Pilot onboarding / ToS mentions processing of GSTIN, contact, invoice data | ☐ | One sentence minimum. |

---

## A11 accept-risk — JWT in `localStorage` (pilot)

| Item | Decision |
|------|----------|
| Storage | Access + refresh JWTs remain in browser `localStorage` for Phase 0 pilot (BUG-402). |
| Risk | Any XSS can read tokens for up to refresh lifetime (`JWT_REFRESH_DAYS`, prefer ≤2 in prod template). |
| Mitigations for pilot | Strict CSP where feasible; no third-party scripts on app origin; short refresh lifetime; logout clears keys; regenerate secrets on suspected compromise. |
| Session invalidation (BUG-407) | On definitive refresh reject, FE must clear session and force login (implement or track as follow-up hardening). |
| Post-pilot | Revisit httpOnly secure cookie / BFF session. |

**Accept-risk signer (PM/Eng):** ____________________  **Date:** __________

---

## Sign-off

| Role | Name | Date | Signature / initials |
|------|------|------|----------------------|
| Eng | | | |
| Ops | | | |
| PM | | | |
