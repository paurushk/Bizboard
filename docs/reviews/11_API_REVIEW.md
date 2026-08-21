# API Review

## Wave 22 (2026-08-06)

Idempotency TOCTOU (730); recon GET side effects (754); OpenAPI drift ungated (750); feature_flags no Owner API (715).

## Wave 21 (2026-08-05)

No CompanyGstin API (BB-000674); no WA connection API (BB-000678); AA unguarded (BB-000680).

## Wave 20 (2026-08-05)

No CN/DN einvoice/eway actions on note viewsets (BB-000647).

## Wave 19 missed (2026-08-05)

BB-000610 durable idempotency required.

## Wave 19 (2026-08-05)

OpenAPI description denies installed apps (BB-000584); typedClient not on money APIs (BB-000579); feature_flags JSON not in Company API (BB-000563).


**Date:** 2026-08-02

## Surface

Public versioned under `/api/v1/` — auth, company, masters, inventory, sales, purchases, payments, public pay, webhooks, accounting, ledgers, reporting, search, imports, insights, integrations/tally, files, notifications, audit, schema/docs.

## Strengths

- Envelope renderer + exception handler.
- OpenAPI gated to Owner when enabled.
- Company stamped on create; queryset scoped.

## Issues

| ID | Topic |
|----|-------|
| BB-000004 | Webhook AllowAny + company query |
| BB-000023 | IntegrityError details leak |
| BB-000043 | ENABLE_API_DOCS default 1 |
| BB-* | No Idempotency-Key on create invoice |
| BB-* | No OpenAPI-generated FE client |
| BB-* | Mass assignment audit residual |
| BB-* | Custom ViewSets must not skip company filter |
| F70 | No v2 strategy |

## Recommendations

1. Harden webhooks; never amount-only match.
2. Default docs off in prod.
3. Idempotency-Key for creates.
4. Contract tests / generated client.
5. Generic DB error messages.

## Score: 6.0 / 10


## Wave 8 (2026-08-03)

Payment webhook probe uses sandbox parser (BB-000205); public pay metadata disclosure (BB-000237); idempotency still roadmap (BB-000189).

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
