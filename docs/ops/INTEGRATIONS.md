# Outbound integrations (9.1)

Operator page for `backend/core/integration_inventory.py`. Secrets never
appear here. Counsel DPA names live in `SUBPROCESSORS.md`.

| Code name | Fallback when vendor is down | Money path | Freeze |
|---|---|---|---|
| razorpay_subscriptions | Stub checkout in non-prod; write-block via subscription status | yes | SaaS billing |
| razorpay_collections | Disable online collect; take cash/UPI offline | yes | A25 sandbox |
| cashfree_collections | Disable online collect; take cash/UPI offline | yes | A25 sandbox |
| payu_collections | Disable online collect; take cash/UPI offline | yes | A25 sandbox |
| smtp_email | Log send failure; password-reset still returns uniform 200 | no | required in prod |
| sms_otp | Password login; OTP unavailable when SMS_PROVIDER unset | no | A26 |
| sentry | Structured logs only | no | optional |
| gsp_einvoice | Preview only; GSP_LIVE_ENABLED=0 in freeze | yes | live submit dark |
| tally | Export dump; live sync dark in freeze | no | Table B |
| whatsapp_cloud | wa.me share-link; Cloud send dark in freeze | no | Table B |

Owner API: `GET /api/v1/integrations/inventory/` returns `settings_present`
booleans, not values. Staff is 403.

Circuit breakers + dead-letter: `core.circuit_breaker.call` fail-closed;
`DeadLetterEvent` for billing webhook poison. Do not Complete a money document
when a money-path adapter is open-circuit.
