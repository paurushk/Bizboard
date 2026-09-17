# Expand / contract migrations (7.7)

Guard: `scripts/ci_gates/guards/guard_zdt_migrations.py`. A `RemoveField`,
`RenameField`, `DeleteModel`, or `RenameModel` without the token
`EXPAND_CONTRACT_OK` in the migration file fails CI.

Rolling deploys run mixed app versions against one schema. Dropping a column in
the same release that old workers still SELECT/INSERT will 500.

## Expand (this release)

- Add nullable columns, new tables, new indexes concurrently in Postgres.
- Dual-write if a column is replacing another. Readers still use the old name.
- Example: `billing.0006_subscription_saas_dunning` only `AddField`s.

## Contract (a later release)

1. Ship code that no longer reads/writes the old column.
2. Wait until every api/worker replica is on that image.
3. Add a new migration that drops/renames **and** contains `EXPAND_CONTRACT_OK`
   plus a comment pointing at the expand migration / release tag.
4. Rollback plan: restore from backup if the drop was wrong; do not reverse a
   data-lossy contract unless `reverse` is tested.

## SOP checklist

- [ ] `makemigrations` is expand-only, or the contract file has `EXPAND_CONTRACT_OK`.
- [ ] `python scripts/ci_gates/run_guards.py` passes.
- [ ] Image tag + migration head recorded (see `docs/pilot/RUNBOOKS.md` rollback).
- [ ] Money / statutory tables: prefer restore over clever `migrate` backwards.
