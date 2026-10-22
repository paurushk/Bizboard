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
3. Data-at-rest keys — see **Encryption keys** below. Never drop an old key before the re-encrypt.
4. `RAZORPAY_KEY_SECRET` + `RAZORPAY_WEBHOOK_SECRET` — Razorpay dashboard first, then env, then restart api/worker.
5. `SANDBOX_WEBHOOK_SECRET` / Cashfree / PayU collection secrets — same: provider console, then env.
6. `POSTGRES_PASSWORD` (owner) and `APP_DB_PASSWORD` (the RLS-bound app role) — `ALTER ROLE ... PASSWORD`,
   update `.env`, re-run `scripts/db-app-role.sh`, bounce api/worker/beat. PgBouncer `userlist.txt` if used.
8. `METRICS_TOKEN` — update the collector's `metrics_token` file and `.env` together.
7. `REDIS_PASSWORD` — broker + cache together or Celery will flap.

## Encryption keys (WP-B3)

Every key that protects stored data takes a list, **newest first**. The first key encrypts; every
listed key decrypts. `python manage.py rotate_encrypted_fields` finds every stored encrypted
value (all text columns, Fernet tokens and `gcm1.` blobs) and re-encrypts it with the newest key.

| Key | Format | Protects |
|---|---|---|
| `MFA_ENCRYPTION_KEY` | `new,old` (Fernet) | TOTP secrets |
| `GSP_FERNET_KEY` | `new,old` (Fernet) | GSP, gateway, integration, FIU credentials |
| `TENANT_EXPORT_FERNET_KEY` (falls back to `GSP_FERNET_KEY`) | `new,old` (Fernet) | Tenant backup files |
| `PLANWAVE_DATA_KEY` + `PLANWAVE_DATA_KEY_ID`, old ones in `PLANWAVE_RETIRED_KEYS=id:key,...` | AES-256-GCM, 32-byte url-safe base64 | Bank account numbers, portal secrets |

Steps (one key family at a time):

1. Generate the new key. Fernet: `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`.
   Planwave: `python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
   and pick a new id (`k2` after `k1`).
2. Deploy with the new key first and the old one still listed (Planwave: new key in
   `PLANWAVE_DATA_KEY`, new id in `PLANWAVE_DATA_KEY_ID`, `k1:<old key>` in `PLANWAVE_RETIRED_KEYS`).
3. `python manage.py rotate_encrypted_fields` (dry run) — note the counts.
4. `python manage.py rotate_encrypted_fields --apply`, then the dry run again: it must report
   `0 value(s) in total` and no unreadable values.
5. Remove the old key and deploy. Exception: keep the old **tenant export** key listed until every
   backup file made with it is older than the backup retention (`BACKUP_RETENTION_DAYS`), because
   stored backup files are not rewritten.
6. Record the date, key family and counts below.

`OTP_PEPPER` must be set on its own (it defaults to `SECRET_KEY`); rotating it only invalidates OTPs
in flight.

## Drill (monthly)

1. Run `--check-env` on staging. Missing/placeholder names must fail closed.
2. Rotate **one** non-prod webhook secret. Confirm a test webhook still 200s.
3. Confirm `gitleaks` advisory still allowlists `*example*` files only.
4. Date the drill next to the backup restore drill in `docs/pilot/GO_NO_GO.md` (Human).

Never commit live secrets. `.env.example` values are placeholders by design.

## Drill log

| Date | Secret / key family | Downtime | Values re-encrypted | By |
|---|---|---|---|---|
| | | | | |
