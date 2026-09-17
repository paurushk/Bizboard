# Migration rollback / forward-fix (14.8)

Pair with `docs/ops/EXPAND_CONTRACT.md` and `docs/pilot/RUNBOOKS.md`.

## Prefer forward-fix

If a release is wrong but schema is expand-only: ship a follow-up image on the **same** migration head. Do not reverse.

## Unsafe to reverse (restore instead)

- Any data migration that rewrote money, GST, stock, or allocations
- `RemoveField` / `DeleteModel` (contract phase)
- Erasure / tombstone
- Number-series changes

## Safe to reverse only after expand readers are gone

- Additive `AddField` null/default
- New table unused by old workers

List the last-known-good migration per app with `showmigrations` **before** each prod deploy. Record it next to the image tag.
