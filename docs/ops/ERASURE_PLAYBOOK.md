# Tenant erasure playbook (3.9 / 16.6)

Matches `accounts/erasure.py` and `python manage.py erase_company`.

**HTTP Owner self-serve is gated on `ENABLE_TENANT_ERASURE` (default 0).** Do not
flip that in production without a Human DPDP decision. The CLI is for operators
who already made the call.

## Modes

| Mode | What remains | When |
|---|---|---|
| `tombstone` (default) | Scrubbed statutory tax docs + Company row with `erased_at`; operational rows gone | GST retention (8 years + 2 days) — SR-40 |
| `hard` | Nothing | CLI / sandbox sweep / purge after retention |

Every run writes `TenantErasureLog` with **no party PII**. Idempotent.

## CLI

```
python manage.py erase_company --company-id 42 --confirm "Exact Company Name" \
  --reason "DPDP request #…" --requested-by "ops@…"
```

- `--confirm` must equal `Company.name` exactly.
- Refuses outside a non-prod shell unless `--force`.
- `--mode tombstone|hard`
- `--skip-export` only if a prior export is already stored.

Coverage drift: `assert_erasure_model_coverage` fails CI if a new `company` FK
is neither cascaded, handled, nor in the retained set.

## Operator steps

1. Export (unless skip) and store the SHA256 from the command output off-host.
2. Run tombstone unless legal has signed hard-delete (Human / counsel — not LLM).
3. Confirm the Owner login no longer sees the company; health still 200 for others.
4. Do **not** erase during a Sev-1 incident.
5. Purge of expired tombstones is a scheduled job after the retention window — not a manual SQL delete.
