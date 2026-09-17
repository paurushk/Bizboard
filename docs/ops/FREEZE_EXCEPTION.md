# Freeze exception SOP (1.1)

The freeze is `docs/FREEZE_SCOPE.md`. Table B modules stay **off** in:

- `backend/.env.pilot.example` / `web/.env.pilot.example`
- `.env.production.example`
- `docker-compose.yml` web build-arg **defaults**
- `.github/workflows/cd.yml` web `--build-arg`

Guard: `scripts/ci_gates/guards/guard_freeze_table_b_defaults.py`.

## How to take a freeze exception

1. Open a PR titled `freeze-exception: <flag>`.
2. Put `FREEZE_EXCEPTION` plus the flag name in the **same** file that turns the flag on.
3. Human (founder) writes on the PR: why, which A-row is removed, which test will gate the new surface.
4. Do not enable GSTR screens, manufacturing, payroll, CRM, Tally live, or live NIC e-invoice to “help a paid plan.” Paid plans must not turn Table B on (`billing.entitlements.FREEZE_DARK_PLAN_MODULES`).

POS (`ENABLE_POS` / `VITE_ENABLE_POS`) is freeze **SUPPORTED** (A23), not an exception.
