# DevOps Review

## Wave 22 (2026-08-06)

Compose RLS=0 pin (710); migrate-on-start base (714); CD .env fixture missing (749); Dependabot skips mobile (747); nginx SW cache headers (755).

## Wave 21 (2026-08-05)

**Superseded 2026-08-06:** Tenant export/restore product path shipped (BB-000668); nightly `scripts/backup.sh` remains distinct. date.today() on UTC hosts (BB-000666) still open.

## Wave 20 (2026-08-05)

Shared MEDIA_ROOT tenant keys unsafe (BB-000643) — object storage required before multi-tenant prod.

## Wave 19 missed (2026-08-05)

BB-000605 CSP; BB-000626 health disclosure; BB-000636 beat duplicate snapshots.

## Wave 19 (2026-08-05)

Compose DB superuser (BB-000552); nginx Host rewrite (BB-000559); base compose still migrates on api start (BB-000585). Final Gates ops IDs remain Deferred.


**Date:** 2026-08-02 · **Updated:** 2026-08-03 (Open-closure wave) · **Score: 6.0 / 10**

## Present

- Docker compose: api, worker, beat, postgres, redis (password required), nginx, web; optional `backup` profile.
- Backend Dockerfile: non-root USER, HEALTHCHECK, multi-worker gunicorn.
- CI: ruff, makemigrations check, pytest on Postgres, blocking pip-audit, vitest, lint, build, npm audit high, Playwright smoke (non-gating) + golden e2e (merge gate), compose config/build.
- CD: GHCR image push on `main` (`.github/workflows/cd.yml`).
- Dependabot + CodeQL workflows.
- `.env.production.example` covers payments/GSP/LLM/Celery/OTP_PEPPER/Redis password.
- nginx security headers on edge and `web/nginx.conf`.
- Optional `SENTRY_DSN` wiring in Django settings.

## Remaining gaps (Deferred / ops)

| ID | Finding | Status |
|----|---------|--------|
| BB-000015 | HTTP-only edge / TLS at LB | Deferred — ops owner |
| BB-000014 | Go gates unsigned | Deferred — ops owner |
| BB-000045 | Host-level backup cadence + restore drill | Deferred — ops (script exists) |

## Wave 8 / Open-closure notes

Stale claims (pip-audit `|| true`, no beat) are **obsolete**. See MASTER_ISSUE_REGISTER for current statuses.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

### DevOps residuals

| ID | Finding |
|----|---------|
| BB-000385 | `docker-compose.prod.yml` beat healthcheck `assert … or True` — always healthy |
| BB-000406 | Root `PRODUCTION_READINESS.md` stale vs shipped product |
| BB-000407 | settings fail-open outside explicit prod/staging |
| BB-000434–437 | Thin prod overlay (no TLS), CSP unsafe-inline, CD without provenance, thin observability |

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.

---

## Wave 14 missed-findings (2026-08-04)

Appended `BB-000544`…`BB-000549` (6). Open **94**. See MASTER_ISSUE_REGISTER.md.
