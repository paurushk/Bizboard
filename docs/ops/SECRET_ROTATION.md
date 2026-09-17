# Secret rotation (10.4)

Drill command (prints order, **does not rotate**):

```
docker compose exec api python manage.py secret_rotation_drill
docker compose exec api python manage.py secret_rotation_drill --check-env
python scripts/ops/secret_rotation_drill.py
```

Live rotation is Human. Dual-run old+new HMAC/JWT verifiers until every in-flight
token and webhook has drained.

## Order

1. `SECRET_KEY` — Django signing / fallback OTP pepper. Rotate with overlap.
2. `OTP_PEPPER` — existing hashed OTPs become unverifiable; users re-request OTP.
3. `GSP_FERNET_KEY` / `TENANT_EXPORT_FERNET_KEY` — re-wrap ciphertext before dropping the old key.
4. `RAZORPAY_KEY_SECRET` + `RAZORPAY_WEBHOOK_SECRET` — Razorpay dashboard first, then env, then restart api/worker.
5. `SANDBOX_WEBHOOK_SECRET` / Cashfree / PayU collection secrets — same: provider console, then env.
6. `POSTGRES_PASSWORD` — update role, then `DATABASE_URL`, then bounce api/worker/beat. PgBouncer `userlist.txt` if used.
7. `REDIS_PASSWORD` — broker + cache together or Celery will flap.

## Drill (monthly)

1. Run `--check-env` on staging. Missing/placeholder names must fail closed.
2. Rotate **one** non-prod webhook secret. Confirm a test webhook still 200s.
3. Confirm `gitleaks` advisory still allowlists `*example*` files only.
4. Date the drill next to the backup restore drill in `docs/pilot/GO_NO_GO.md` (Human).

Never commit live secrets. `.env.example` values are placeholders by design.
