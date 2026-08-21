# Backend Review

## Wave 22 (2026-08-06)

Sales RCM GL missing (695); period except-pass (699); service-layer period bypass (700); idempotency TOCTOU (730); recon GET mutates (754).

## Wave 21 (2026-08-05)

Money-doc destroy (BB-000650/651); ERP serializer tenant gap (BB-000672); payroll races (BB-000685).

## Wave 20 (2026-08-05)

File ingest split-brain (BB-000643/644); document number scan (BB-000646); notes IRP gap (BB-000647).

## Wave 19 missed (2026-08-05)

BB-000599–601, BB-000607–610 posting/FIFO/model/idempotency residuals.

## Wave 19 (2026-08-05)

New P0/P1 in manufacturing/payroll/crm services, feature-flag asserts, idempotency shadowing, Celery RLS bootstrap. Issues: BB-000553–555, BB-000561, BB-000563–567, BB-000586.


**Date:** 2026-08-02

## Apps inventory

`accounts`, `masters`, `inventory`, `sales`, `purchases`, `payments`, `ledgers`, `accounting`, `reporting`, `imports`, `insights`, `integrations`, `search`, `core`, `config`

## Strengths

- Service-layer complete/cancel paths with `transaction.atomic`.
- Document number allocation with row locks (PG).
- Payment allocation locking; stock oversell tests on Postgres CI.
- Phase 1 notes, Phase 2 GSTR builders, Phase 3 gateways, Phase 4 warehouses, Phase 5 CoA, Phase 6 insights, Phase 7 Tally present in code.

## Critical / High issues (register)

| ID | Topic |
|----|-------|
| BB-000001 | Settings fail-open |
| BB-000002–000006 | OTP / SMS |
| BB-000004 | Webhooks |
| BB-000005, BB-000012 | GSP sandbox + payload |
| BB-000007–000011 | GST/accounting correctness |
| BB-000018–000030 | RBAC, credit race, doc uniqueness, Fernet, IntegrityError leak, media, WhatsApp, seeds, lockout |

## Code smells

- Dual paths for note GL posting (service vs view) — BB medium notes.
- Magic `TALLY_OPENING` string — BB medium.
- `DocumentLineModel` without company — BB-000017.
- Coarse permissions on money writes — BB-000018.

## Services quality

| Service | Quality |
|---------|---------|
| `billing.py` | High (tax math) |
| `InventoryService` | High |
| `LedgerService` | High with edge cases |
| `PostingService` | Medium — incomplete matrix |
| `gst_returns.py` | Medium — aid not filer |
| `gsp_adapters.py` | Sandbox only |
| `sms.py` / notifications | Stub |
| `llm.py` | Functional; privacy risk |

## Score: 6.2 / 10 (engine) · 4.0 / 10 (production completeness)


## Wave 8 (2026-08-03)

New backend findings BB-000196–BB-000257 focus on **payment gateway authenticity**, **purchase H9 GL gap**, **journal RBAC**, **FileAsset/bank-line IDOR**, **OTP verify race**, **missing `requests` dependency**, **ADMIN_ENABLED default**, and **celery false-positive health**. Scope C OTP hash / ValDtls / RCM GL / composition gates verified still present.

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
