# On-call roster template (11.6)

Fill names. An empty row means nobody will be paged.
Do not invent names in git. OG1-H3 closes when the weekday IST 09–21
primary is a real person and “Page via” says how they get the Sentry alert.

How to close the Human Sentry steps: `docs/ops/OGATE_HUMAN.md`.

| Window | Primary | Backup | Phone | Page via |
|---|---|---|---|---|
| Weekdays IST 09–21 | | | | Sentry -> Telegram (OG1-H3b) |
| Nights / weekend | | | | |
| Billing / Razorpay | | | | |
| GST / CA questions | | | | Do not page Eng |

"Sentry -> Telegram" = Sentry alert rule fires an Internal Integration
webhook at `POST /api/v1/ops/alert/`, which relays into a private Telegram
group everyone on this roster is a member of — set up per `docs/ops/OGATE_HUMAN.md`
OG1-H3b. It's a free stand-in for a paid on-call product (PagerDuty/Grafana
OnCall); swap the "Page via" cell if/when you outgrow it.

Severity: `docs/ops/INCIDENT_RESPONSE.md`. Status copy: `docs/ops/STATUS_COMMS.md`.
A test page (`manage.py sentry_test_event`) is not a roster. After it
succeeds, paste the event id on `docs/ops/HYPERCARE.md` day-0.
