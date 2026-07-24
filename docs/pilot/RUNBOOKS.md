# Support runbooks (Phase 1)

## PDF worker down
- Symptom: invoice Complete succeeds but `pdf_status=QUEUED/FAILED`.
- Check: `docker compose ps worker`, Celery logs.
- Fix: restart worker; use Regenerate PDF on invoice detail.
- Customer workaround: download after regenerate.

## OTP / SMS failure
- Symptom: OTP request errors “not configured”.
- Phase 1: use email/password login; set `SMS_PROVIDER` + provider credentials for phone OTP.
- Never enable `OTP_DEBUG_ECHO` in production.

## SMTP / email share failure
- Symptom: Share email queued but not delivered.
- Set `EMAIL_HOST` / user / password; verify `DEFAULT_FROM_EMAIL`.
- WhatsApp share opens a link only (Business API later).

## Discount mode questions
- **Cash discount (after tax)**: reduces amount payable; GST unchanged.
- **Discount (reduces GST)**: lowers taxable value then GST — use when commercial discount should reduce tax.

## Place of supply blocked
- Add customer/supplier state or GSTIN, or Owner enables “Assume local state for blank party” in GST settings (use sparingly).
