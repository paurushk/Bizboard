# Risk register draft (1.4)

Engineering draft. Founder owns residuals and accept-risk signatures.

| ID | Risk | Likelihood | Impact | Mitigation in repo | Residual (Human) |
|---|---|---|---|---|---|
| R001 | Cross-tenant read/write | M | Sev-1 | `company_id` on tenant tables, IDOR tests, no impersonation guard | Prod RLS soak still off |
| R002 | Double-complete / stock oversell | M | High | `select_for_update` + status machines; Postgres CI | SQLite local is not the lock proof |
| R003 | Webhook replay / forged capture | M | High | HMAC, `ProcessedWebhookEvent`, DLQ | Live gateway keys |
| R004 | SaaS vs AR money mix-up | M | High | Separate dunning/recon modules + tests | Chargeback finance policy |
| R005 | PDF/worker silent hang | H | Med | 409 + FAILED visible; beat dry-run | On-call names |
| R006 | Backup never restored | M | Sev-1 | `restore_drill.sh` | Off-host bucket + dated drill |
| R007 | Table B UI ships in prod image | M | High | freeze-table-B guard; CD GSTR default false | Image rebuild after this PR |
| R008 | Superuser DB bypasses RLS | H if RLS on | Sev-1 | Prod RLS default 0; STRIDE draft | Non-superuser role on hosted PG |
| R009 | Secret in git | M | High | gitleaks advisory | Rotate if a real secret lands |
| R010 | Unsigned Go/No-Go | H | Launch block | Checklists exist | Human signatures |
