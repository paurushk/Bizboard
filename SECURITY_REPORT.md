> **Historical (2026-07-24).** Superseded for decision-making by `docs/reviews/` (2026-08-02 Scope C audit). Do not treat Criticals here as current without re-verification.

# BizBoard — SECURITY REPORT

**Date:** 2026-07-24  
**Scope:** AuthN/Z, tenancy, uploads, API abuse, XSS/SQLi probes, secrets, transport  

---

## Executive security verdict

**Not hardened for public SaaS at scale.** Core tenancy and auth basics are present and tested; several high-likelihood misconfiguration and XSS-adjacent risks remain.

**Security score: 5.5 / 10**

---

## Findings

| ID | Severity | Finding | Evidence | Recommendation |
|----|----------|---------|----------|----------------|
| S-01 | Critical | DEBUG/OTP echo/default secret if env wrong | `settings.py` DEBUG default `1`, `OTP_DEBUG_ECHO`, insecure SECRET_KEY fallback | Prod fail-fast; secrets from vault |
| S-02 | High | JWT in localStorage | `web/src/auth/session.ts` | httpOnly cookies or strict CSP |
| S-03 | High | Unvalidated generic uploads | `FileService.store_upload` | MIME/size allowlist; scan |
| S-04 | High | No DRF throttling observed | `REST_FRAMEWORK` settings | Login/OTP/register rate limits |
| S-05 | High | OTP SMS stub | `RequestOtpView` | Provider + no echo in prod |
| S-06 | Medium | Manual 400 as success:true | OTP empty body probe | Fix envelope |
| S-07 | Medium | OpenAPI docs instability / exposure | `/docs/` → 500 in probe | Auth-gate or disable in prod |
| S-08 | Medium | HTTP only (no TLS at nginx) | `nginx/default.conf` listen 80 | Terminate TLS; HSTS |
| S-09 | Medium | Limited security headers | Media `nosniff` only | CSP, Referrer-Policy, Permissions-Policy |
| S-10 | Medium | Coarse RBAC | OWNER/STAFF | Least privilege roles |
| S-11 | Low | Cross-tenant 404 | Isolation probe | OK; keep consistent |
| S-12 | Low | CSRF with Bearer JWT | Typical for SPA JWT | If moving to cookies, add CSRF |

---

## Tests performed

| Test | Result |
|------|--------|
| Unauthenticated `GET /sales/invoices/` | **401** |
| Cross-tenant `GET /sales/invoices/1/` | **404** (no leak of other tenant payload) |
| Weak password register | **Rejected** (length/common/numeric) |
| Search `q=<script>alert(1)</script>` | **200** empty results; no reflected execution in API JSON |
| Search SQLi-like `' OR 1=1 --` | Handled as search text (ORM) — no crash in prior suite; tenant tests exist |
| Password validators | Django four validators enabled |
| Logout refresh blacklist | Supported (`token_blacklist` app; ROTATE false) |
| Tenant isolation suite | Present in `test_tenant_isolation.py` |

---

## Auth details

| Item | Value |
|------|-------|
| Access token TTL | 60 minutes |
| Refresh TTL | 7 days |
| Storage | localStorage (`bizboard.access` / `refresh`) |
| CORS | Allowlist from env |
| Default permission | `IsAuthenticated` |
| Company scope | `CompanyScopedViewSet` + `HasCompany` |

---

## Sensitive data exposure

- Demo credentials documented in README (acceptable for demo; rotate for shared staging).  
- LLM API keys via env for bill import — ensure not logged.  
- Media path 403 on directory listing attempt — good.

---

## Broken access control notes

- Frontend route gates mirror OWNER / inventory / import flags.  
- Backend enforces Owner for company PATCH, users, audit; inventory adjust; import commit.  
- **Gap:** Sales staff can still cancel invoices, record payments, export reports — confirm product intent.

---

## Recommendations (priority order)

1. Prod configuration lock (DEBUG off, no OTP echo, strong secret).  
2. Upload allowlist + virus scan path.  
3. Rate-limit auth endpoints.  
4. TLS + security headers at edge.  
5. Move tokens out of localStorage or ship strict CSP.  
6. Expand role model before multi-employee customers.  
7. Penetration test before 10k-tenant launch.
