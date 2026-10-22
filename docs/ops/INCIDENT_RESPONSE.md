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

## Reporting clocks (WP-CP1, WP-CP2)

Start these clocks at **detection**, not at confirmation. Counsel owns the wording and confirms
which incidents are in scope; the incident lead owns sending.

| Report | Deadline | To | What to have ready |
|---|---|---|---|
| CERT-In cyber incident report | **6 hours** from noticing it, for the incident types in the CERT-In Directions (e.g. data breach or leak, unauthorised access, ransomware, compromise of systems or accounts) | CERT-In (incident@cert-in.org.in or their reporting form) | Time noticed, systems affected, what was seen, X-Request-IDs, image tag, logs (kept 180 days: `LOG_RETENTION.md`), contact person |
| DPDP personal data breach | Without delay, as the DPDP Rules require — to the Data Protection Board and to each affected person | Data Protection Board; affected users (through the tenant where Bizboard is their processor — follow the DPA) | Nature and extent, likely impact, what was done to limit it, what people should do, contact |
| Customer notice | Same day for Sev 1 | Affected tenants' owners | What happened, what they should not do, next update time |

Template fields for the breach notice are in `docs/ops/DPDP_REQUESTS.md` (WP-CP2). Log every
notice sent (who, when, channel) in the postmortem.

## Do not

- Disable tenant isolation tests or RLS checks “just to recover”.
- Replay webhooks without HMAC + `ProcessedWebhookEvent` dedup.
- Run `erase_company` during an incident.
- Enable `POSTGRES_RLS_ENABLED=1` in prod as an incident response.
