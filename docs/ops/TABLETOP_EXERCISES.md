# Incident tabletop exercises

A tabletop is a talk-through: someone reads out what is happening, the team says what it would do,
and a scribe writes down every step that was slow, unclear or missing from a runbook. Nothing is
touched in production. It closes the readiness row "no DR/failover drill or incident tabletop
held" for the **tabletop** half; the failover half needs hosted Postgres (`DB_FAILOVER.md`).

## How to run one (about 2 hours)

| Role | Who | Job |
|---|---|---|
| Facilitator | Anyone not playing the lead (a friend, the CA, a contractor) | Reads the injects at the times below; answers "what do I see?" from the scenario notes; does not hint |
| Incident lead | On-call primary (`ONCALL_ROSTER.md`) | Declares severity, decides, says each action out loud |
| Scribe | A third person, or the facilitator if only two | Fills the record at the bottom as it happens |

Solo founder: still worth doing. Read each inject, set a 5-minute timer, write your actions before
reading the next. The point is finding the gaps, not the score.

Have open: `INCIDENT_RESPONSE.md`, `ALERTS.md`, `DB_FAILOVER.md`, `STATUS_COMMS.md`,
`POSTMORTEM.md`, `GLITCHTIP.md`, `ONCALL_ROSTER.md`, `docs/pilot/RUNBOOKS.md`.

Rules: say the real command or screen you would use; "I'd check the logs" is not an answer until it
names which logs and how. If a runbook is wrong or silent, the scribe writes it down and you move on.

## Scenario A: "I can see another company's invoices" (Sev 1, isolation)

| Time | Inject |
|---|---|
| 00:00 | A pilot owner phones: "On the Sales list I can see invoices with a customer I don't know." They send a screenshot showing a Support ID. |
| 00:05 | `/admin/ops/errors/` with that Support ID shows nothing. The API log has the request. |
| 00:15 | A second pilot reports the same within the last hour. A deploy went out 90 minutes ago. |
| 00:30 | You confirm rows from company 7 were returned to a user of company 3. |
| 00:45 | The pilot asks whether their data was also shown to someone else. |

Expected: Sev 1 at 00:00 (`INCIDENT_RESPONSE.md` → isolation). Stop writers (`api`, `worker`,
`beat`) instead of hot-fixing; preserve image tag, migration head, Support IDs. Roll back the image
(`deploy-staging.yml` → `rollback`) and check `POSTGRES_RLS_ENABLED` / the app DB role are what
`HOSTED_STAGING.md` §4 says. **Start the CERT-In 6-hour clock at 00:00**, not at 00:30. DPDP
breach notice to affected people without delay (Counsel words it). Same-day customer notice
(`STATUS_COMMS.md`). Postmortem within 3 business days.

Probe: who exactly do you notify, and from which address? Where is the CERT-In form? Can you tell
from the logs which other users saw company 7's rows?

## Scenario B: database down at month end (Sev 2, availability)

| Time | Inject |
|---|---|
| 00:00 | ntfy push: "GlitchTip: API ready is down". `/api/v1/health/` still answers; `?ready=1` is 503. |
| 00:05 | It is the 31st, 18:30 IST. Three pilots are closing the month. |
| 00:10 | The provider status page says the managed Postgres primary failed over 4 minutes ago. |
| 00:20 | `ready` is back, but the worker logs `server closed the connection unexpectedly` every few seconds. |
| 00:40 | A pilot says one invoice shows "Completed" but has no PDF and no ledger entry. |

Expected: Sev 2 (writes down for all tenants). `DB_FAILOVER.md`: confirm `DATABASE_URL` follows the
new primary, bounce `api` / `worker` / `beat` holding dead sockets. Measure RTO from 00:00. For the
invoice: do **not** tell them to complete again (`ALERTS.md` → PDF queue); run
`check_invariants` for that company and regenerate the PDF. Status-page update and "next update
at" time (`STATUS_COMMS.md`). If data may be lost: restore decision per `docs/pilot/RUNBOOKS.md`.

Probe: what is our real RPO with the current backup schedule? Who decides restore vs forward-fix?

## Scenario C: the alarms are silent (Sev 2, money path)

| Time | Inject |
|---|---|
| 00:00 | No alerts all day. A pilot emails at 16:00: "Receipts since lunch are not reducing customer balances." |
| 00:10 | `/admin/ops/errors/` shows "The tracker did not answer". No "Error tracker is not answering" page arrived. |
| 00:20 | The GlitchTip VM's disk is full; it stopped accepting events at 12:40. A deploy went out at 12:30. |
| 00:35 | Receipts are saved, but allocation fails with a 500 that nobody saw. |

Expected: Sev 2 (money integrity for some writes; escalate to 1 if balances are wrong, not just
late). Ask why the watcher did not page: `OPS_TELEGRAM_CHAT_ID` / `OPS_NTFY_URL` set? beat running
(`ALERTS.md` → Beat silent)? Roll back the 12:30 deploy; free the tracker's disk; replay nothing by
hand. List the affected receipts by Support ID / time window and re-run allocation per company.

Probe: what would have told us at 12:40? (Answer to record: the tracker-down watcher, if paging is
configured; an external check on the tracker itself, `GLITCHTIP.md` §5.)

## Scenario D: Razorpay is down on renewal day (Sev 3, annual drill in `DR_CADENCE.md`)

Short form: subscription renewals fail for 3 hours; dunning would email "payment failed" to every
renewing owner. Expected: `BCP.md` → Razorpay down (circuit fails closed, webhooks retry, recon
later), no write-gate for affected companies until the gateway is back, one honest status note.
Probe: how do we stop `billing.tasks.run_saas_dunning_task` alone? (Known gap, 2026-10-23: there is
no switch for it; stopping `beat` stops every scheduled job. Record the decision.)

## Record (copy one per session into the evidence pack)

| Field | Value |
|---|---|
| Date, start and end time | |
| Scenario(s) run | |
| People and roles | |
| Severity declared, and when | |
| Time to first correct action (minutes) | |
| Reporting clocks started at the right time? | |
| Runbook gaps found (each one becomes a ticket) | |
| Decisions nobody could make (each one gets an owner) | |
| Actions with owner and due date | |

Then add a row to `DR_CADENCE.md` ("Incident tabletop") with the date and a link to the record, and
fix the runbooks that were wrong or silent within two weeks.

## Appendix: run pack (WP-6, 2026-10-25)

Print this appendix. Cut out the inject cards; the facilitator hands them over one at a time at
the times shown (solo: turn one over, start a 5-minute timer, write your actions, then turn the
next). Then score the session with the sheet below and fill the record above.

### Inject cards

| Card | Scenario | Time | Says |
|---|---|---|---|
| A1 | A | 00:00 | "On the Sales list I can see invoices with a customer I don't know." Screenshot shows a Support ID. |
| A2 | A | 00:05 | The Support ID is not in `/admin/ops/errors/`. The API log has the request. |
| A3 | A | 00:15 | A second pilot reports the same. A deploy went out 90 minutes ago. |
| A4 | A | 00:30 | Confirmed: company 7's rows were returned to a company 3 user. |
| A5 | A | 00:45 | "Was our data shown to someone else as well?" |
| B1 | B | 00:00 | Phone push: "API ready is down". `/api/v1/health/` answers; `?ready=1` is 503. |
| B2 | B | 00:05 | It is the 31st, 18:30 IST. Three pilots are closing the month. |
| B3 | B | 00:10 | Provider status page: the Postgres primary failed over 4 minutes ago. |
| B4 | B | 00:20 | `ready` is back; the worker logs "server closed the connection unexpectedly". |
| B5 | B | 00:40 | One invoice is "Completed" with no PDF and no ledger entry. |
| C1 | C | 00:00 | 16:00 email: "Receipts since lunch are not reducing customer balances." No alerts all day. |
| C2 | C | 00:10 | `/admin/ops/errors/` says "The tracker did not answer". No tracker-down page arrived. |
| C3 | C | 00:20 | The tracker's disk is full since 12:40. A deploy went out at 12:30. |
| C4 | C | 00:35 | Receipts save; allocation fails with a 500 nobody saw. |

### Scoring sheet (one per scenario)

| # | Check | Points | Got |
|---|---|---|---|
| 1 | Severity declared at the first card, and the right one (A: Sev 1; B, C: Sev 2) | 2 | |
| 2 | Reporting clocks started at **detection**: CERT-In 6 hours (A), customer notice same day (A, B) | 2 | |
| 3 | The first action stops the harm before diagnosis (A: stop writers and roll back; B: bounce dead sockets; C: roll back the 12:30 deploy) | 2 | |
| 4 | Named the real command, screen or log for every action (not "check the logs") | 2 | |
| 5 | Used the right runbook (`INCIDENT_RESPONSE.md`, `DB_FAILOVER.md`, `ALERTS.md`, `STATUS_COMMS.md`) | 1 | |
| 6 | Customer message drafted with a "next update at" time (`STATUS_COMMS.md`) | 1 | |
| 7 | Evidence kept: image tag, migration head, Support IDs, time window | 1 | |
| 8 | Postmortem opened with an owner and a date (`POSTMORTEM.md`) | 1 | |
| 9 | Every runbook gap written down as it was found | 1 | |
| 10 | Time to first correct action, in minutes (record it; not scored) | — | |
| | **Total (out of 13)** | | |

10 or more: the runbooks carry you. 7 to 9: fix the gaps found within two weeks, then re-run that
scenario. Below 7: re-run within a month.

### Solo run, pre-filled record

| Field | Value |
|---|---|
| Date, start and end time | |
| Scenario(s) run | A, B, C (D optional) |
| People and roles | Founder: incident lead and scribe (solo mode). No backup on call yet (D-01): record that as a gap |
| Severity declared, and when | A: … B: … C: … |
| Time to first correct action (minutes) | A: … B: … C: … |
| Reporting clocks started at the right time? | |
| Runbook gaps found | |
| Decisions nobody could make | Who is the backup on call? Who approves a restore instead of a forward fix when the founder is unreachable? |
| Actions with owner and due date | |

The technical half (does each alert actually fire, and how fast) is the game day:
`scripts/drills/game_day.sh`, results in `docs/ops/DRILLS/`.
