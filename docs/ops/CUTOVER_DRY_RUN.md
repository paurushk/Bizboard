# Cutover dry-run (6.4)

1. Staging company via `seed_staging` (refuses production).
2. Import Excel (not CSV IDs) through Settings → Import; re-run once (A15 idempotent).
3. `python manage.py cutover_recon --company-id <id>` — prints product/customer/supplier/invoice counts then `check_invariants`.
4. Variance vs `docs/ops/CUTOVER.md` field map must be 0 or explained (Human).

Do not reverse a money migration to undo a bad import — restore.
