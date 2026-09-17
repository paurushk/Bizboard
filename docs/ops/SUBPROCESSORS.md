# Subprocessors (10.8)

Inventory is derived from `backend/core/integration_inventory.py`. Counsel
fills DPAs. This list is **not** a legal DPA.

| Code name | Typical vendor | Money path | Freeze |
|---|---|---|---|
| razorpay_subscriptions | Razorpay | yes | SaaS billing |
| razorpay_collections | Razorpay | yes | A25 sandbox |
| cashfree_collections | Cashfree | yes | A25 sandbox |
| payu_collections | PayU | yes | A25 sandbox |
| smtp_email | Resend (SMTP relay) | no | password reset |
| sms_otp | MSG91 / Twilio | no | A26; off if unset |
| sentry | Sentry | no | errors |
| gsp_einvoice | GSP / NIC | yes | live submit dark (`GSP_LIVE_ENABLED=0`) |
| tally | Tally | no | Table B dark |
| whatsapp_cloud | Meta Cloud | no | Table B dark; `wa.me` share-link stays |

Region / residency commitments are Human. Flip a dark flag only via
`docs/ops/FREEZE_EXCEPTION.md`.
