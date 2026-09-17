# Log retention / PII (11.10)

| Store | Retention in code | PII rule |
|---|---|---|
| JSON request logs | Host log rotate (not Django) | Path redacts INV-/UUID; hashed user/company ids; **no body** (`test_request_log_masks_ids_and_carries_no_body`) |
| `HelpEvent` | 180 days — `prune_help_events_task` weekly | Search text stays in Bizboard |
| `AuditEvent` | Kept (PROTECT on company) | Erasure playbook, not silent CASCADE |
| Sentry | Vendor default until Human sets | Do not send PAN/GSTIN in extras |
| Invoice PDF / media | Until erasure | JWT + tenant check |

Legal retention window (GST 8y tombstones) is Human. Do not shorten AuditEvent in an LLM session.
