# Hypercare checklist (17.4)

First 7 days after paid beta. Named owner per row.

| Day | Check | Owner | Done |
|---|---|---|---|
| 0 | Image digest + migrate head recorded | Eng | |
| 0 | Sentry test event id pasted | Ops | |
| 1–7 | `check_invariants` nightly green | Eng | |
| 1–7 | No P0 money defects open | QA | |
| 1–7 | Razorpay recon mismatches = 0 or DLQ parked | Ops | |
| 1–7 | Backup job succeeded (vendor console) | Ops | |
| 30 | Post-launch review (`docs/ops/POSTMORTEM.md` if incidents) | Founder | |

Paste the `manage.py sentry_test_event` id into the day-0 Sentry row (OG1-H4).
Playbook: `docs/ops/OGATE_HUMAN.md`.

Do not enable Table B flags during hypercare to “help” a paid tenant.
