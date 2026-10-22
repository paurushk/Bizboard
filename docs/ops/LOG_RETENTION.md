# Log retention / PII (11.10)

| Store | Retention in code | PII rule |
|---|---|---|
| JSON request logs | Host log rotate (not Django) | Path redacts INV-/UUID; hashed user/company ids; **no body** (`test_request_log_masks_ids_and_carries_no_body`) |
| `HelpEvent` | 180 days — `prune_help_events_task` weekly | Search text stays in Bizboard |
| `AuditEvent` | Kept (PROTECT on company) | Erasure playbook, not silent CASCADE |
| Sentry | Vendor default until Human sets | Do not send PAN/GSTIN in extras |
| Invoice PDF / media | Until erasure | JWT + tenant check |

Legal retention window (GST 8y tombstones) is Human. Do not shorten AuditEvent in an LLM session.


## CERT-In: 180 days, in India (WP-CP1)

The CERT-In Directions of 28 April 2022 require ICT system logs to be **kept for 180 days, stored in
India**, and every log source to be **time-synced** (NTP). Counsel confirms scope (Human); this is
the engineering half. Constant: `core/services/retention.py` `CERT_IN_LOG_RETENTION_DAYS = 180`.

| Log | Where it is written | What keeps it 180 days | Region |
|---|---|---|---|
| Web/API access (JSON request logs, `bizboard.request`) | stdout of `api` | Ship container stdout to a log store with ≥ 180-day retention (see below); host rotation alone is not enough | India region store |
| Sign-in, OTP, MFA, password reset | `AuditEvent` + request logs | `AuditEvent` is never pruned (see table above) | Primary DB (India) |
| Admin and break-glass actions | Django admin log, `AuditEvent`, `BreakGlassSession` (WP-SC2) | Not pruned | Primary DB |
| Worker / beat logs | stdout of `worker`, `beat` | Same log store as access logs | India region store |
| Payment and billing webhooks | `ProcessedWebhookEvent`, `DeadLetterEvent`, request logs | Not pruned by the app | Primary DB |
| nginx edge access logs | `nginx` container | Same log store | India region store |

App prune jobs and why they are **not** CERT-In logs: `prune_help_events_task` (product search
telemetry), `prune_idempotency_records_task` (replay keys), `purge_steps` (AI agent traces, kept per
`AGENTS.STEP_RETENTION_DAYS`), `purge_old_invoice_zips_task` (generated exports),
`core.sweep.prune_old_results` (books-check results). Do not add a prune job for any row in the
table above without changing this page and getting counsel's OK.

**Log store (Human, hosting choice):** a managed log service or Loki/S3 bucket in an Indian region
with a 180-day (or longer) retention rule. Docker `json-file` rotation on the host is only a buffer.

**Time sync:** NTP (`chronyd` or `systemd-timesyncd`) on every app host. The app exports
`bizboard_clock_skew_seconds` (app vs database clock) and alerts above 2 s (`BizBoardClockSkew`).
