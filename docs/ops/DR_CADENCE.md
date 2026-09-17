# DR cadence calendar (13.6)

Put these on a real calendar. Dates below are placeholders.

| Drill | Cadence | Last run | Next | Evidence |
|---|---|---|---|---|
| Backup restore + `check_invariants` | Monthly | | | Restore log + company=ok |
| Secret rotation dry-run | Quarterly | | | `secret_rotation_drill` output |
| Failover (managed PG) | Semi-annual | | | RTO minutes |
| Razorpay down tabletop | Annual | | | Notes in `docs/ops/BCP.md` |
| SMS/OTP down | Annual | | | Password-login fallback |

G13 is Human-signed after a dated restore against **hosted** backups, not this template.
