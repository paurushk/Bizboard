# verify_fixed — 2026-10-24

Commit `0d829a1c` (plus working tree) · backend DB: **postgresql** · apply: True

Summary: manual 17, passed 4
Promoted to verified: 4 (QOS-0012, QOS-0154, QOS-0155, QOS-0156)

| Item | Kind | Result | Detail | Guard |
|---|---|---|---|---|
| QOS-0006 | manual | manual | not a backend/vitest guard | `scripts/test_concurrency_local.sh` |
| QOS-0007 | manual | manual | not a backend/vitest guard | `web/e2e/a11y.spec.ts::J-A11Y-P2-KEYBOARD POS scan field is keyboard-operable without a mouse` |
| QOS-0010 | manual | manual | not a backend/vitest guard | `web/e2e/route-smoke.spec.ts` |
| QOS-0013 | manual | manual | not a backend/vitest guard | `web/playwright.config.ts::webkit` |
| QOS-0016 | manual | manual | not a backend/vitest guard | `web/e2e-golden/v95-dashboard-p95.spec.ts::dashboard p95 stays within budget on twelve months of invoices` |
| QOS-0017 | manual | manual | not a backend/vitest guard | `web/e2e/pos-friction.spec.ts::opens with the scan field focused and no blocking dialog` |
| QOS-0019 | manual | manual | not a backend/vitest guard | `.github/workflows/ci.yml` |
| QOS-0023 | manual | manual | not a backend/vitest guard | `.github/workflows/ci.yml` |
| QOS-0025 | manual | manual | not a backend/vitest guard | `web/e2e/personas/role-boundaries.spec.ts` |
| QOS-0026 | manual | manual | not a backend/vitest guard | `web/e2e/mobile-layout.spec.ts` |
| QOS-0040 | manual | manual | not a backend/vitest guard | `web/e2e/pos-friction.spec.ts::exactly one tender button is emphasised as the remembered default (QOS-0040)` |
| QOS-0057 | manual | manual | not a backend/vitest guard | `docs/reviews/CR_090_104_RESTATUS_2026-09-11.md` |
| QOS-0058 | manual | manual | not a backend/vitest guard | `docs/reviews/MASTER_ISSUE_REGISTER.md` |
| QOS-0096 | manual | manual | not a backend/vitest guard | `web/e2e/route-smoke.spec.ts` |
| QOS-0099 | manual | manual | not a backend/vitest guard | `web/package.json::lint` |
| QOS-0105 | manual | manual | not a backend/vitest guard | `scripts/ci_gates/guards/guard_runtime_alignment.py` |
| QOS-0106 | manual | manual | not a backend/vitest guard | `scripts/ci_gates/guards/guard_config_consistency.py` |
| QOS-0012 | backend | passed | 2 passed | `backend/tests/broker/test_real_broker_einvoice.py` |
| QOS-0154 | web | passed | 1 passed | `web/src/pages/sales/VoidReceiptDialog.test.tsx::phone bottom sheet` |
| QOS-0155 | web | passed | 1 passed | `web/src/components/LocaleSwitcher.test.tsx::on a phone shows one button that offers the other language, and switches back` |
| QOS-0156 | backend | passed | 1 passed | `backend/tests/test_user_sessions_id3.py::test_a_reload_that_lost_the_rotated_cookie_keeps_the_user_signed_in` |

## Verified by direct check (guard is not a pytest/vitest test)

| Item | Evidence |
|---|---|
| QOS-0006 | scripts/test_concurrency_local.sh exists and CONTRIBUTING.md documents the Postgres row-lock lane (lines 9, 11). |
| QOS-0023 | .github/workflows/cd.yml 'Pin image digests' step (scripts/pin_image_digests.sh) and ci.yml 'Prod compose overlay pins image digests' check present. |
| QOS-0057 | docs/reviews/CR_090_104_RESTATUS_2026-09-11.md carries a verdict for CR-090..CR-104 (20 references). |
| QOS-0058 | docs/reviews/MASTER_ISSUE_REGISTER.md records 'R scheme reconciliation - SUPERSEDED (2026-09-11)'. |
| QOS-0099 | npm run lint: 0 errors (25 warnings); tsc -b exit 0 on 2026-10-24. |
| QOS-0105 | python scripts/ci_gates/guards/guard_runtime_alignment.py: GUARD OK on 2026-10-24. |
| QOS-0106 | python scripts/ci_gates/guards/guard_config_consistency.py: GUARD OK on 2026-10-24. |
