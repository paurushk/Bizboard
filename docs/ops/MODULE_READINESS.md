# Module readiness (WP-M1)

Every backend app that owns tenant data (a model with a `company` key) is listed here with how it
meets the SaaS rules. `scripts/ci_gates/guards/guard_module_readiness.py` fails CI when an app with
tenant tables is missing from this table, so a new module cannot ship without someone filling in
its row.

Columns:
- **RLS** — every tenant table is in a `core/migrations/*rls*` list (enforced by `tests/test_rls_coverage.py`).
- **Ledger** — posts to the GL through `PostingService.post` with registered source types
  (`accounting/coverage.py`, enforced in tests), or `none` when it moves no money/stock value.
- **Checks** — invariant domains in `core/invariants/` that cover it, or `none`.
- **Jobs** — its beat tasks are classified in `tests/test_beat_tasks_rls_postgres.py`, or `none`.
- **Runbook** — where ops looks when it breaks.

| App | RLS | Ledger | Checks | Jobs | Runbook |
|---|---|---|---|---|---|
| `accounting` | yes | yes | gl, gl_parity, reports | depreciation fan-out | `docs/ops/LEDGER_REPAIR_RUNBOOK.md` |
| `accounts` | yes | none | tenancy | backups, settings alerts fan-out | `docs/ops/ERASURE_PLAYBOOK.md` |
| `agents` | yes | none | none | expire / cancel / purge fan-out | `docs/ops/AGENTS_RUNBOOK.md` |
| `banking` | yes | none | none | none | `docs/ops/INTEGRATIONS.md` |
| `billing` | yes | none | none | SaaS recon / dunning (bypass) | `docs/ops/ALERTS.md` |
| `complaints` | yes | none | none | none | `docs/ops/SUPPORT_MACROS.md` |
| `contracts` | yes | via sales invoices | money | status / reminders per company | `docs/ops/SUPPORT_MACROS.md` |
| `core` | yes | none | audit, numbering, tenancy | books check, seal, prunes | `docs/ops/ALERTS.md` |
| `crm` | yes | none | none | reminders / stale imports per company | `docs/ops/SUPPORT_MACROS.md` |
| `imports` | yes | opening balances, opening stock | money, inventory | none | `docs/ops/CUTOVER.md` |
| `insights` | yes | none | projection | summaries / attention fan-out | `docs/ops/ALERTS.md` |
| `insurance` | yes | none | roadmap | none | `docs/ops/SUPPORT_MACROS.md` |
| `integrations` | yes | none | none | none | `docs/ops/INTEGRATIONS.md` |
| `inventory` | yes | stock adjustments (flag) | inventory | reservations / expiry bands | `docs/ops/LEDGER_REPAIR_RUNBOOK.md` |
| `jobwork` | yes | yes | jobwork | none | `docs/MANUFACTURING_RUNBOOK.md` |
| `manufacturing` | yes | yes (flag `MFG_COSTING_GL`) | manufacturing | none | `docs/MANUFACTURING_RUNBOOK.md` |
| `masters` | yes | none | tenancy | customer audit per company | `docs/ops/SUPPORT_MACROS.md` |
| `payments` | yes | yes | money, gl, projection | gateway recon / refunds / dunning | `docs/ops/ALERTS.md` |
| `payroll` | yes | yes | gl | none | `docs/ops/LEDGER_REPAIR_RUNBOOK.md` |
| `planwave` | yes | none | none | none | `docs/ops/SECRET_ROTATION.md` |
| `projects` | yes | via sales invoices | roadmap | milestone reminders per company | `docs/ops/SUPPORT_MACROS.md` |
| `purchases` | yes | yes | gl, gst, money | none | `docs/ops/LEDGER_REPAIR_RUNBOOK.md` |
| `quality` | yes | none | none | none | `docs/MANUFACTURING_RUNBOOK.md` |
| `reporting` | yes | none | reports | ITC digests per company | `docs/ops/ALERTS.md` |
| `sales` | yes | yes | gl, gst, money, numbering | recurring, zips, PDFs, quote sweep | `docs/ops/LEDGER_REPAIR_RUNBOOK.md` |
| `support` | yes | none | none | none | `docs/ops/SUPPORT_MACROS.md` |
| `workshop` | yes | via sales invoices | roadmap | none | `docs/ops/SUPPORT_MACROS.md` |
