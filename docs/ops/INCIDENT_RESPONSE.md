# Incident response (11.8)

**Not a legal hold policy.** Founder / Human declares severity and customer comms.

## Severity

| Sev | Meaning | Example | Page |
|---|---|---|---|
| 1 | Tenant isolation or money integrity | Cross-tenant read, double-complete stock, lost receipts | Immediately |
| 2 | Writes down for all tenants | API 5xx, DB down, webhook HMAC broken | 15m |
| 3 | Degraded single feature | PDF worker, SMTP, one gateway | Next business hour IST |
| 4 | Cosmetic / single tenant | One PDF FAILED | Ticket |

## First hour

1. Declare sev in the on-call channel. Assign **incident lead** (Human).
2. Stop deploy / freeze migrations if schema is in doubt.
3. Preserve: image tag, migration head, last backup time, `X-Request-ID`s.
4. For money/isolation: stop writers (`api` `worker` `beat`) rather than “quick fix in prod”.
5. Customer message: what they should **not** do (do not re-complete; do not pay twice). No GST legal claims.
6. Fix or rollback per `docs/pilot/RUNBOOKS.md` (image tag first; restore if data may be wrong).
7. Open a postmortem using `POSTMORTEM.md` within 3 business days.

## Do not

- Disable tenant isolation tests or RLS checks “just to recover”.
- Replay webhooks without HMAC + `ProcessedWebhookEvent` dedup.
- Run `erase_company` during an incident.
- Enable `POSTGRES_RLS_ENABLED=1` in prod as an incident response.
