# Tenant model (3.1)

**Status:** Matches code. Founder still signs “company_id = tenant.”

- One `accounts.Company` per GSTIN in freeze (no multi-branch).
- Almost every money/master row has `company` FK. Isolation is app-layer `company_id` filters. `POSTGRES_RLS_ENABLED` defaults **0** in production.
- Global (not tenant): `Plan`, auth `User` (user can belong to companies via `CompanyUser`), some health/metrics.
- Erasure: `accounts.erasure` tombstone vs hard; HTTP gated `ENABLE_TENANT_ERASURE=0`. Playbook: `docs/ops/ERASURE_PLAYBOOK.md`.
- Coverage drift: `assert_erasure_model_coverage` fails CI when a new company FK is neither cascaded, handled, nor retained.

Do not add support impersonation. `switch-company` is membership, not act-as.
