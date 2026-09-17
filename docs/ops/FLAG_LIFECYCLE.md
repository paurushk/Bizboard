# Feature-flag lifecycle (14.7)

How freeze flags turn on and off. This is operator documentation, not a
product changelog. Paid plans must not enable Table B dark modules.

## Layers

1. **Deployment env** (`ENABLE_*` on Django settings) is the ceiling for
   credential-backed and Table B flags.
2. **Plan modules** (`billing.Plan.modules`) can grant dark preview modules
   (`ENABLE_MANUFACTURING` / `PAYROLL` / `CRM`) only when the env ceiling is
   on. Seeded paid plans use `freeze_safe_modules()` so those keys stay false.
3. **Company JSON** (`Company.feature_flags`) can deny a flag, and can lift
   keys in `ROLLOUT_GRANTABLE_KEYS` (POS, GSTR, Tally, GSTN JSON, setup
   wizard, TDS) *if the env ceiling is already on*. Do not use JSON to
   smuggle Table B through a freeze host.
4. **Kill switch:** set the env var to `0` and bounce api/worker. There are
   no forever flags.

## Freeze Table B (must stay off on freeze hosts)

`ENABLE_GSTR`, `ENABLE_GSTN_JSON`, `ENABLE_TALLY`, `ENABLE_MANUFACTURING`,
`ENABLE_PAYROLL`, `ENABLE_CRM`, `VITE_ENABLE_*` counterparts, live
`GSP_LIVE_ENABLED`. Guard: `scripts/ci_gates/guards/guard_freeze_table_b_defaults.py`.

`ENABLE_POS`, `ENABLE_TDS`, and `ENABLE_SETUP_WIZARD` are freeze-supported
(A23 / A24 / A19). Production and staging env templates pin them `1`. They
are grantable, not dark modules.

## Known limitations (D6 / D10)

`ENABLE_FIXED_ASSETS` and `ENABLE_BOE` default **OFF** in Django. Tests opt
in via `backend/config/settings_test.py`. Production and staging env
templates pin `0`. Route guards 404 when the flag is missing or false
(fail-closed). They are **not** plan-grantable (`ROLLOUT_GRANTABLE_KEYS`).

## Adding a flag

1. Add to `ENV_FLAG_KEYS` and `settings.py` (`_env_bool`, default `"0"` unless
   freeze-supported).
2. If Table B: add the on-pattern to `guard_freeze_table_b_defaults` and pin
   `0`/`false` in `.env.production.example` and CD/compose.
3. If a paid dark module: add to `FREEZE_DARK_PLAN_MODULES` and keep seed
   plans false.
4. Mirror the mock default in `web/src/config/featureFlags.ts`.
5. Document the kill switch in this file.

Human still signs `docs/ops/FREEZE_EXCEPTION.md` before any freeze host
flips a Table B flag.
