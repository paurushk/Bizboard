# Product behaviours for counsel (16.1 / 16.2)

Facts the product already implements. **Do not treat this as Terms of Service,
privacy policy, DPA, or DPIA.** Lawyer drafts those from this list.

## Accounts and access

- Shared-schema multi-tenancy via `company_id`. RLS exists; `POSTGRES_RLS_ENABLED` defaults off until Human soak.
- Invite roles: Owner, Manager, Sales staff, Inventory staff, Accountant, Auditor, Viewer. Owner-only for users/billing.
- Passwords hashed; OTP hashed at rest; lockout and throttles on auth.
- No impersonation API (`guard_no_impersonation`).
- MFA/SSO: decision in `docs/ops/MFA_SSO.md` — not a TOTP product in freeze.

## Money and GST

- Freeze SUPPORTED: A1–A26 (POS on, GSTR **screens** off, live NIC e-invoice submit off).
- Worksheets / JSON are aids. Product does **not** file GSTR-1/3B at a GSTN portal in freeze (C1).
- Excel imports; do not treat CSV IDs as source of truth.

## Data

- Categories: `docs/pilot/DPDP_POSTURE.md`.
- Erasure: `erase_company` (flag off by default). Tombstone vs hard is documented there.
- Request logs redact query strings and document numbers (`test_request_log_masks_ids_and_carries_no_body`).

## Billing

- Razorpay subscriptions; SaaS dunning is not AR collections dunning.
- Cancelled subscription keeps writes until the paid period ends (B9-007).
- Chargeback payloads without a subscription entity are ignored.

## What this file will not do

Invent refund copy, GST opinions, or processor contract terms.
