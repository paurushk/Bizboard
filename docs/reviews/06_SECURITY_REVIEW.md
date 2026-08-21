# Security Review

## Wave 22 (2026-08-06)

PWA `/api` cache + status 0 (738); compose RLS forced off (710); Celery RLS prerun residual (709); company switch header race (745); Android allowBackup (746); GSTIN sandbox trust (734).

## Wave 21 (2026-08-05)

BB-000672 cross-tenant ERP FKs; BB-000658 company-switch race; BB-000675–677 invite RBAC; BB-000691 VIEWER payments; BB-000680 AA flag; BB-000693 AI settings fail-open.

## Wave 20 (2026-08-05)

BB-000643 FileAsset path escape; BB-000644 store_bytes bypasses validation.

## Wave 19 missed (2026-08-05)

BB-000602/603 prod cookie+CSRF/Bearer; BB-000604 RLS order; BB-000616/617 invite+login tokens; BB-000618 read ACL; BB-000625 CORS; BB-000626 health; BB-000631/632 ClamAV/Cashfree.

## Wave 19 (2026-08-05)

Critical: ALLOWED_HOSTS `*` local bypass (BB-000550); RLS theater (BB-000551/552); VIEWER ERP ACL (BB-000553); WhatsApp global token (BB-000571); plaintext outbox (BB-000572); GSP creds on company PATCH (BB-000573); nginx IP Host rewrite (BB-000559).


**Date:** 2026-08-02 · **Score: 5.0 / 10**

## Positive controls

- JWT + rotate/blacklist refresh.
- Default `IsAuthenticated`; company-scoped querysets; cross-tenant → 404.
- Password validators enabled.
- Auth endpoint throttling (Wave0).
- Upload MIME/size allowlist (Wave0).
- nginx `media` internal; CSP/nosniff/frame/referrer headers present.
- No raw SQL / no `csrf_exempt` found in app code.

## Critical

| ID | Finding |
|----|---------|
| BB-000001 | DEBUG/SECRET fail-open |
| BB-000002 | OTP plaintext at rest |
| BB-000003 | OTP in API body when echo on |
| BB-000004 | Webhook company/amount routing |
| BB-000006 | SMS stub |
| BB-000013 | Mock mode ship risk |
| BB-000015 | No TLS at edge |

## High

| ID | Finding |
|----|---------|
| BB-000023 | IntegrityError leak |
| BB-000024 | Media when DEBUG |
| BB-000027 | Fernet from SECRET_KEY |
| BB-000028 | Seed known passwords |
| BB-000029 | Lockout LocMem |
| BB-000031 | JWT localStorage |
| BB-000018 | Coarse RBAC |
| BB-000032 | FE accounting ungated |
| BB-000035 | Share URL allowlist |
| BB-000194 | OTP printed to stdout |

## Residual from prior SECURITY_REPORT

Many July Criticals (uploads, throttle, envelope, media) are **fixed**. Treat `SECURITY_REPORT.md` as Historical; this doc + register are current.

## Pen-test

Not performed — BB EXTRA. Required before GA.

## Recommendations (order)

1. Production boot lock + TLS.
2. OTP hash + disable until SMS real.
3. Webhook identity binding.
4. CSP + consider httpOnly cookies; sign JWT accept-risk for pilot.
5. Fine-grained write capabilities.
6. External pen-test.


## Wave 8 (2026-08-03)

**Security score revised to 3.5/10.** Critical: sandbox webhook forgery (BB-000196), PayU unsigned accept (BB-000197), Razorpay stub links (BB-000198), journal posting by any member (BB-000200). High: IDOR logo/bank line, FE route gaps, open payment URLs, Fernet residual outside prod, DEBUG-on-public-host residual, Redis lockout bypass.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

### Wave 13 security residuals (verified)

| ID | Finding |
|----|---------|
| BB-000379 | `create_payment_link` + webhook still settle `provider=sandbox` in prod (PATCH-only ban) |
| BB-000387 | `prepare_einvoice` / `prepare_eway` HasCompany fallthrough |
| BB-000388 | `WarehouseViewSet` CRUD HasCompany — VIEWER mutates warehouses |
| BB-000389 | Register Set-Cookie email enumeration |
| BB-000403 | Access JWT still in login/OTP/refresh JSON bodies |
| BB-000404 | Users settings `canViewFinancialReports !== false` |
| BB-000407 | `settings.py` fail-open DEBUG/SECRET outside explicit prod/staging |
| BB-000413–418 | PaymentHealth, CSRF cookie JWT, FileAsset, masters/valuation READ ACL |

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.

---

## Wave 14 missed-findings (2026-08-04)

Appended `BB-000544`…`BB-000549` (6). Open **94**. See MASTER_ISSUE_REGISTER.md.
