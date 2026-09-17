# Vendor SLA / dependency sheet (9.6)

Template only. Contracts and named contacts are Human.

| Integration | Vendor | Sandbox account | Prod contract | Status page | Fallback in product |
|---|---|---|---|---|---|
| SaaS billing | Razorpay | | | | Stub checkout + trial; write-block on unpaid |
| Collections | Razorpay / Cashfree / PayU | | | | Cash/UPI offline |
| Email | Resend (SMTP relay) | | | | Uniform password-reset 200 |
| SMS OTP | MSG91 / Twilio | | | | Password login |
| Errors | Sentry | | | | JSON logs |
| GSP | (named GSP) | | | | Preview only while `GSP_LIVE_ENABLED=0` |

See `docs/ops/SUBPROCESSORS.md` for the code inventory. DLT entity ID is not in-repo.
