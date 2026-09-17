# BCP / DR scenarios (13.5)

Draft. Human approves.

| Scenario | User impact | Action | RPO/RTO |
|---|---|---|---|
| Single AZ / VM loss | All writes down | Restore latest dump on a new VM; previous image digest | Dump age / restore_drill duration |
| Ransomware on VM | Untrusted disk | Do not pay-restore in place; new VM + off-host dump | Dump age |
| Razorpay down | SaaS checkout + collections | Circuit open fail-closed; DLQ after HMAC; recon later | Events retry |
| SMS provider down | OTP login | Password login; disable OTP tab if unconfigured | None |
| Redis down | Completes may 503 on `.delay()` | Fix broker; eager mode forbidden in prod | Minutes |
| Postgres primary failover | Brief 5xx | `docs/ops/DB_FAILOVER.md` | Vendor RTO |

Do not run `erase_company` during DR.
