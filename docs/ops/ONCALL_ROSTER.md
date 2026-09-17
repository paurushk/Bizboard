# On-call roster template (11.6)

Fill names. An empty row means nobody will be paged.
Do not invent names in git. OG1-H3 closes when the weekday IST 09–21
primary is a real person and “Page via” says how they get the Sentry alert.

How to close the Human Sentry steps: `docs/ops/OGATE_HUMAN.md`.

| Window | Primary | Backup | Phone | Page via |
|---|---|---|---|---|
| Weekdays IST 09–21 | | | | Sentry / SMS |
| Nights / weekend | | | | |
| Billing / Razorpay | | | | |
| GST / CA questions | | | | Do not page Eng |

Severity: `docs/ops/INCIDENT_RESPONSE.md`. Status copy: `docs/ops/STATUS_COMMS.md`.
A test page (`manage.py sentry_test_event`) is not a roster. After it
succeeds, paste the event id on `docs/ops/HYPERCARE.md` day-0.
