# STRIDE draft (10.1)

This is an **engineering threat-model draft**, not a pentest report and not a
legal opinion. Human signs Go/No-Go after a real review. Postgres RLS is
**off** in production (`POSTGRES_RLS_ENABLED=0`); app-layer `company_id` is
the isolation guarantee until RLS is soaked.

| Surface | S | T | R | I | D | E | Control in tree |
|---|---|---|---|---|---|---|---|
| JWT access + refresh cookie | Stolen token used as the user | Refresh cookie rewritten | Owner denies a login they did | Staff token reads another company | Logout-all not called | Token issued without auth | Short access TTL, SameSite, logout-all, company_id on every queryset |
| Media / invoice PDF | Guess `/media/company_N/` | Swap file bytes | “I never downloaded that” | Cross-tenant PDF | Delete object store | Serve without JWT | Django `FileResponse` after JWT + tenant check; nginx `/media/` is `internal` |
| Django admin | Superuser session hijack | Privilege flag toggle | Admin action unsigned | Staff browses all tenants | Drop a company | Enable admin on the internet | `ADMIN_ENABLED` default off outside DEBUG; `SuperuserOnlyAdminMixin` |
| Webhooks (Razorpay SaaS, Cashfree/PayU collections) | Replay captured HMAC | Tamper payload after verify | Provider says event was not sent | Map capture onto tenant B | Drop after verify | Unsigned webhook in prod | HMAC required when secret set; `ProcessedWebhookEvent`; DLQ park; `rls_bypass` only inside the view |
| Support impersonation | N/A (no feature) | N/A | N/A | Act-as-user becomes tenant Owner | N/A | Hidden sudo route | Guard `no_impersonation` + 404 tests. `switch-company` is membership, not impersonation |
| RLS (staging flag only) | Superuser DB role bypasses FORCE RLS | SET `app.company_id` to victim | “RLS was on” when it was not | Read all rows via bypass GUC leaked on the pool | — | Enable prod RLS without soak | Default 0 in prod example; staging example 1; never claim prod RLS |

Spoofing / Tampering / Repudiation / Information disclosure / Denial of service / Elevation.

## Residual (Human)

- TLS terminator, HSTS preload, WAF, and pentest are not this document.
- ToS / DPA / DPIA are legal, not STRIDE.
- Turning `POSTGRES_RLS_ENABLED=1` in production is a founder call after soak.
