# DR cadence calendar (13.6)

Put these on a real calendar. Dates below are placeholders.

| Drill | Cadence | Last run | Next | Evidence |
|---|---|---|---|---|
| Backup restore + `check_invariants` | Monthly | | | Restore log + company=ok |
| Secret rotation dry-run | Quarterly | | | `secret_rotation_drill` output |
| Failover (managed PG) | Semi-annual | | | RTO minutes |
| Incident tabletop (scenarios A–C) | Quarterly; first one before the first paying pilot | | | Record in `TABLETOP_EXERCISES.md` |
| Razorpay down tabletop | Annual | | | Scenario D in `TABLETOP_EXERCISES.md`; notes in `docs/ops/BCP.md` |
| SMS/OTP down | Annual | | | Password-login fallback |

G13 is Human-signed after a dated restore against **hosted** backups, not this template.
