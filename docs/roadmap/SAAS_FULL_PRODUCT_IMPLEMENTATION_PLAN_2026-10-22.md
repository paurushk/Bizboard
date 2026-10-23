# Full SaaS product — implementation plan: before paid beta and before public launch

**Date:** 2026-10-22 · **Revision:** 3.1 (review applied, see §0d; Q9 answered) · **Status:** Phase 1 and Phase 2 built and tested (see §8 and §9), deep review fixed (§10); what is left is people items only · **Branch at writing:** `feat/mfg-p0-foundations` (large uncommitted tree)

This plan covers the items from the 2026-10-22 checklist review and the "full-fledged SaaS"
review that must be done **before paid beta** (alongside Waves 1–3 of the scorecard) and
**before public launch**, and that can be built and tested in this repo (lane **LLM**) or built
here and then switched on by a person with an account or key (lane **Split**). Items for after
launch are listed in Appendix A only.

It sits after, not instead of:

- [SAAS_READINESS_IMPLEMENTATION_PLAN_2026-10-21.md](SAAS_READINESS_IMPLEMENTATION_PLAN_2026-10-21.md) — WP-A..L, built 2026-10-22
- [SAAS_READINESS_HANDOVER_2026-10-22.md](SAAS_READINESS_HANDOVER_2026-10-22.md) — the 20 people items
- [SAAS_READINESS_ALL_DIMENSIONS_AND_NFR_2026-10-21.md](SAAS_READINESS_ALL_DIMENSIONS_AND_NFR_2026-10-21.md) — scorecard and waves SR0–SR4

Each work package (WP) gives the goal, files, steps, tests, "done when", dependencies, size and
lane. Review IDs are in brackets: **N1–N9** from the checklist gap review; letter IDs (F-, B-,
I-, C-, D-, G-, R-, S-, P-, E-, L-, X-) from the full-SaaS review.

**Lanes:** **LLM** = can be built and tested in this repo · **Split** = built here, a person adds
a key/account or signs a number · **Human** = only a person (listed, not planned).

**Sizes:** S ≤ 1 day · M 2–4 days · L 1–2 weeks (one engineer or one agent session).

**Precondition:** WP-A1 of the 2026-10-21 plan (commit the tree, tag `v1.0.0-beta`). The founder
chose to commit later (handover §2 item 1), so **nothing in this plan starts until WP-A1 has
landed**. Every WP adds files; starting on top of the uncommitted tree makes that commit harder,
and WP-EN1's merge-size gate would block the WP-A1 chunks themselves.

---

## 0. Scope, code facts and review record

### 0a. Scope

| Phase | Review items | WPs here | People-only (not planned) |
|---|---|---|---|
| **P1 — before paid beta** (with Waves 1–3, weeks 2–16) | F-01, F-02, F-03, F-05, B-05, B-06, I-01, C-01, C-04, P-03, G-01 (Tally part), L-04, S-01, S-02, L-02, E-01, X-01, plus N1, N2, N4, N6, N9 | AB1–AB4, BL1, BL2, ID1, ID2, CM1, CM2, SC1, SC2, CP1, CP2, PO1, PO2, PO3, GR1a, EN1 (19) | X-01 Bizboard's own GST/books/TDS · S-01 named staff DB accounts and no direct container exec |
| **P2 — before public launch** (Wave 4) | B-01, B-04, G-01 (other sources), G-05, I-02, I-03, I-05, C-05, D-02, R-04, S-03, E-04 | BL3, BL4, ID3, ID4, ID5, CM3, DL1, GR1b, GR2, RS1, SC3 (11) | E-04 two people who can deploy, roll back and be on call |

- **L-02 (effective-dated GST rates) is already done** — `masters/models.py:477` `HsnRate` has `valid_from` / `valid_to`. No WP.
- **P-02 health score** sits in P1 with N9 (monthly business metrics): both read the same tables and the founder needs the numbers from the first paid customer.
- Revision 3 moved **CM2, PO3, GR1a (Tally XML) and CP2 (DPDP register)** into P1 — see §0d.

### 0b. What the code already has (found while planning and in review)

| Area | What the code shows | Effect on the plan |
|---|---|---|
| SMS limits | `DEFAULT_THROTTLE_RATES["otp"] = "5/min"` per client (`config/settings.py:372`); `SmsProvider.send_otp` / `send_text` in `core/services/sms.py` | No per-number, per-day or platform limit (AB1). |
| SMS DLT | `_send_msg91` uses one `MSG91_TEMPLATE_ID` (OTP only, required for Indian numbers in prod-like envs); `send_text` (dunning SMS) has **no** DLT template ID | Any non-OTP SMS would be dropped by Indian operators. Template registry is a P1 blocker (CM2). |
| Cache counters | `ai_spend._incr` does `cache.add(key, 0, ttl)` then `cache.incr` — if the key expires between the two calls, `incr` raises | New counters (AB1) use Redis `INCR` + `EXPIRE … NX` in one pipeline; fix `ai_spend._incr` the same way while there. |
| Company resolution | `get_company_user` (`core/permissions.py`) uses `X-Company-Id` when sent (409 if it differs from `User.active_company_id`), **else falls back to `active_company_id`** (per user, not per tab); it saves `active_company_id` on first use, even on GET | A request without the header — a download link, image, PDF tab or poll — runs against whatever company the user last switched to (ID2). The save-on-GET matters for ID4. |
| Company switch | `SwitchCompanyView` (`accounts/views.py:1018`) blacklists the refresh token; `useCompanySwitcher.ts` calls `qc.clear()`; outbox drafts keyed by `(companyId, userId)` | Switching itself is sound; the leaks are header-less requests and the outbox flush (ID2). |
| Merchant tickets | `support.Ticket` has a required `customer` FK to `masters.Customer`; it is a merchant-to-buyer helpdesk gated by `CareSalesAccess` and `ENABLE_SUPPORT_TICKETS`, which `TRIAL_HELD_FALSE` (`billing/services.py`) holds off for trials; `VendorTicketShare` lets a merchant share one of those tickets with the vendor | **Not** usable for tenant-to-Bizboard support. PO3 adds a separate platform model. |
| SaaS GST invoice | `billing/platform_gst.py` `_PROVIDERS = {"cashfree", "payu"}`; `PlatformGstInvoice` docstring: Razorpay subscriptions don't write here | **No Razorpay renewal produces a GST invoice today.** BL2 wires `subscription.charged`. |
| Razorpay webhook | `RazorpayWebhookView` dedupes on `(subscription id, status, X-Razorpay-Event-Id)` + `ProcessedWebhookEvent`, and ignores an event whose `created_at` is **strictly older** than the last one seen for that subscription | Same-second events are fine. But a `subscription.charged` delivered after a newer status event is dropped as `out_of_order` — charge events must bypass that check (BL2). |
| Plan switch | `start_or_update_subscription` creates a **new** Razorpay subscription (`_create_razorpay_subscription(..., start_at=...)`), parks it in `pending_razorpay_subscription_id`, and cancels the old one when the new one goes active; no `PATCH` update | Proration builds on this pattern, not on Razorpay's subscription update (BL3). |
| SaaS dunning | `Subscription` has no invoice balance or partial-payment state; `run_saas_dunning` filters `status=PAST_DUE` | There is no bank-transfer path to compute a TDS "shortfall" against. BL1 uses a refund/credit flow instead. |
| Tally import | `integrations/tally/adapter.py` imports masters (CSV/XLSX) with opening balances and a post-commit recon; `integrations/permissions.py` gates it on `ENABLE_TALLY`, which is OFF in the frozen profile and in `TRIAL_HELD_FALSE`. `ENABLE_TALLY` is in `ROLLOUT_GRANTABLE_KEYS`, and `build_feature_flags` applies the company's `feature_flags` value **last** for those keys, so a per-company grant wins even over a trial plan's held `False`; the web app (`config/features.ts` `isTallyEnabled`) follows the runtime flag once loaded. The only grant tool, `grant_rollout_flag`, refuses unless `E2E_GOLDEN_GRANT=1` and picks the user's first company. | Q9 answered: keep the gate; staff grant per pilot company. GR1a adds an audited admin grant action. |
| Export | `accounts/export_views.py` `TenantExportView` → `tenant_backup.build_export_payload` → `encrypt_export_zip` | Encrypted, for restore only; a departing customer can't open it (DL1). |
| Dependencies | `.github/dependabot.yml` covers pip, web npm, mobile npm | Only SBOM + image scan left (SC3). |
| Entrypoint | `backend/docker-entrypoint.sh` only wraps the container's main command; `docker exec` doesn't run it | A break-glass check there is bypassable (SC2). |

### 0c. Repo rules every WP follows

- A new tenant table is a `CompanyScopedModel` with an RLS migration; the RLS coverage test and `guard_module_readiness` stay green. Platform tables (not per tenant) say so in their docstring.
- A new beat job fans out per company or visits only companies with pending work; `guard_no_inline_company_loops` stays green.
- Founder/staff tooling goes in **Django admin**, never as a new page in the customer SPA.
- New UI strings go in `web/src/i18n/en.ts` **and** `hi.ts` and are listed for the Hindi review (handover item 17).
- New flags follow `docs/ops/FLAG_LIFECYCLE.md` (owner, default, removal date).
- After an API change: `manage.py spectacular` → `docs/openapi-snapshot.json` → `npm run gen:api-types` → `npx tsc -b` → `npm run lint`.
- Every new alert rule gets a runbook section and is covered by `tests/test_alert_rules.py`.

### 0d. Review revision 3 (2026-10-22)

An external review of revision 2 was checked against the code.

| # | Review point | Checked | Change |
|---|---|---|---|
| R1 | `support.Ticket` is the merchant-to-buyer helpdesk, not tenant-to-Bizboard support; trials can't use it | **Confirmed** (required `customer` FK; `ENABLE_SUPPORT_TICKETS` in `TRIAL_HELD_FALSE`) | PO3 adds `support.PlatformTicket`, open to every tenant; ID4 links to it. |
| R2 | Razorpay renewals never produce a `PlatformGstInvoice` | **Confirmed** (`_PROVIDERS`, docstring) | BL2 wires `subscription.charged` → `issue_platform_gst_invoice`; size S → M. |
| R3 | No bank-transfer flow, so "TDS shortfall" can't be computed | **Confirmed** | BL1 rewritten: pay 100% online, upload Form 16A, staff verify, credit or refund. |
| R4 | Plan switch creates a new subscription; no `PATCH` | **Confirmed** | BL3 builds on the existing pending-subscription pattern; UPI mandate re-approval in BL4. |
| R5 | SMS counters must count failed attempts; 6-digit range too narrow; `add`+`incr` race | **Taken** (race confirmed in `ai_spend._incr`) | AB1: count on attempt, prefix length configurable (default 4), atomic pipeline. |
| R6 | Header-less requests fall back to `active_company_id` | **Confirmed** | ID2 adds header-less cases and a server rule for multi-company users. |
| R7 | GET handlers can write; support access needs a DB-level read-only transaction | **Taken** | ID4: `SET TRANSACTION READ ONLY` for grant requests; staff path bypasses `get_company_user`'s save. |
| R8 | Break-glass check in the entrypoint is bypassed by `docker exec` | **Confirmed** | SC2: check in `manage.py`; real control is no direct exec + named DB roles + statement logging (people item). |
| R9 | EN1 would block the WP-A1 chunks | **Taken** | EN1 activates only after WP-A1 lands. |
| R10 | CM2 (DLT templates) is a P1 blocker | **Confirmed** (`send_text` has no template ID) | Moved to P1. |
| R11 | PO3 needed in Wave 2 (SR2-06 staffed support) | **Taken** | Moved to P1. |
| R12 | Tally XML needed for SR2-01 / SR2-04 | **Taken**, plus the `ENABLE_TALLY` gate found while checking | GR1 split: GR1a (Tally) in P1, GR1b (Busy/Vyapar/Marg) in P2. Q9 (founder, 2026-10-22): **keep import behind `ENABLE_TALLY`; staff grant it per pilot company** — no freeze exception. |
| R13 | DPDP request register needed from first real data | **Taken** | CP2 in P1 (from Appendix A). |
| R14 | Non-transactional email needs `List-Unsubscribe` | **Partly taken** — CM3 announcements are in-app, not email; but trial-nurture and digest emails exist or will | CM1 adds `List-Unsubscribe` + one-click opt-out per category; full preferences stay in Appendix A. |
| R15 | Same-second webhook events are dropped by the timestamp check | **Not as stated** — the check is strict `<`, and dedupe already uses the event ID. The real risk is a late `subscription.charged` older than the last status event | BL2: charge events bypass the ordering check; dedupe on event ID + payment ID. |
| R16 | Statutory pre-debit notice is sent by the bank/NPCI rail | **Taken** | BL4: Bizboard's own notice is email-only; set `customer_notify` per Razorpay docs. |
| R17 | Add nullable IRN fields to `PlatformGstInvoice` now | **Taken** (cheap) | BL2 adds `irn`, `ack_no`, `ack_date`, `signed_qr` (nullable, unused until Bizboard crosses the threshold). |

---

## 1. Workstreams at a glance

| WS | Theme | P1 — before paid beta | P2 — before public launch |
|---|---|---|---|
| AB | Abuse and fraud | AB1 SMS caps · AB2 bot check · AB3 one trial per business · AB4 public-link hardening | — |
| BL | Billing | BL2 Razorpay renewals → SaaS GST invoice · BL1 customer TDS (refund/credit flow) | BL3 proration on plan change · BL4 UPI Autopay |
| ID | Identity | ID1 ownership transfer + owner recovery · ID2 company-context isolation | ID3 sessions screen + new-device alert · ID4 customer-approved support access · ID5 Sign in with Google |
| CM | Communications | CM1 email bounce suppression + unsubscribe header · CM2 SMS/WhatsApp template registry (DLT) | CM3 What's new + announcements |
| DL | Data | — | DL1 readable, versioned customer export |
| GR | Growth | GR1a Tally XML + bill-wise outstanding import | GR1b Busy, Vyapar, Marg importers · GR2 onboarding checklist |
| RS | Scale | — | RS1 month-end load scenario |
| SC | Security | SC1 security.txt + disclosure · SC2 break-glass production access audit | SC3 SBOM + image scan |
| CP | Compliance | CP1 CERT-In log retention + incident clock · CP2 DPDP request register + breach notice | — |
| PO | Product ops | PO1 known-limitations page · PO2 tenant health + monthly metrics · PO3 tenant-to-Bizboard support ticket | — |
| EN | Engineering | EN1 small-merge gate (after WP-A1) | — |

**Counts:** P1 = 19 WPs (≈ 37 engineer-days), P2 = 11 WPs (≈ 29 engineer-days).

---

## 2. Phase 1 — before paid beta

Target: built and green in CI by the end of Wave 1 (week 6) where no host is needed, PO3 and
GR1a ready before the first closed-beta import (SR2-01), and everything proven on hosted staging
during Wave 2. Paid beta (Wave 3, SR3-01) doesn't start until every P1 "done when" is met or
waived in writing.

### WS-AB — Abuse and fraud

#### WP-AB1 SMS spend and per-number caps [F-02] — LLM, M

**Goal:** OTP fraud (SMS pumping) can't run up the SMS bill, even across rotating IPs. Built
first because the bill arrives on day one of a public sign-up page.

- **Files:** new `core/services/sms_guard.py`; `core/services/sms.py` (`SmsProvider.send_otp`, `send_text`); `core/services/ai_spend.py` (`_incr` fix); `config/settings.py`; `deploy/prometheus/` alert rules; `docs/ops/ALERTS.md`; superuser-only admin view in `core/admin.py`.
- **Steps:**
  1. `check_and_count_sms(phone, purpose)` runs before every send. Counters are Redis `INCR` + `EXPIRE … NX` in one pipeline (no `add`-then-`incr` race). Same fail-closed stance as `ai_spend.py`, but **no settle step**: an attempt counts against every limit whether the provider succeeds, fails or times out. Only a refusal by an earlier internal check (bad number format) is not counted.
  2. Limits (settings, defaults in brackets): per phone per hour [3] and per day [8]; per number range per hour [30], where the range is the first `SMS_RANGE_PREFIX_LEN` [4] digits after `+91` (operator series), configurable because the right width depends on observed attack traffic; non-Indian numbers blocked unless `SMS_ALLOW_INTERNATIONAL=1`; platform sends per day [`SMS_PLATFORM_DAILY_CAP=5000`]; kill switch `SMS_DISABLED=1`.
  3. With `SMS_DISABLED=1`, OTP screens offer email OTP when the account has a verified email; otherwise a translated "SMS is paused, try again later".
  4. A blocked send returns the same "code sent" response (no oracle), records the block and sends nothing.
  5. Metrics: `sms_sent_total{purpose}`, `sms_failed_total{purpose}`, `sms_blocked_total{reason}`, `sms_platform_used_ratio`. Alerts: blocked > 50/hour; platform use > 80% of the cap; provider failures > 20% over 15 min.
  6. Admin page: today's sends, failures, blocks by reason, top 20 number ranges, and a kill-switch toggle (settings override row, audited).
  7. Apply the same pipeline fix to `ai_spend._incr` and re-run `tests/test_ai_spend.py`.
- **Tests:** each limit trips exactly at its boundary; a provider failure still consumes the per-phone budget; threaded concurrency test can't overshoot the platform cap; expiry-between-calls case (key deleted between steps) doesn't raise; blocked send identical in the HTTP response; kill switch; international block; Redis down → OTP refused with a support code.
- **Done when:** tests green; alert rules in `test_alert_rules.py`; runbook section "SMS spend spike".
- **Decision:** §7 Q2 (defaults apply until answered).

#### WP-AB2 Bot check on sign-up, OTP and reset [F-01] — Split, M

**Goal:** a script can't create accounts or trigger OTP/reset sends at scale.

- **Files:** new `core/services/bot_check.py`; `accounts/views.py` (`RegisterView`, `RequestRegisterOtpView`, `RequestOtpView`, `RequestPasswordResetView`); `config/settings.py` (`BOT_CHECK_PROVIDER`, `TURNSTILE_SECRET_KEY`, `BOT_CHECK_ENFORCE`, `BOT_CHECK_ALLOW_NONE`); web `RegisterPage.tsx`, `LoginPage.tsx`, `ForgotPasswordPage.tsx`, new `web/src/components/BotCheck.tsx`; `.env.production.example`.
- **Steps:**
  1. `verify_bot_token(token, remote_ip) -> bool`. Provider `turnstile` posts to Cloudflare siteverify with a 5 s timeout. Provider `none` always passes (dev/test). Provider `stub` passes only the token `"ok"` (tests and e2e).
  2. Production: fail-closed when the provider is unreachable, only on these four endpoints, with stable error code `BOT_CHECK_FAILED` translated in the UI.
  3. `BOT_CHECK_ENFORCE=0` = shadow mode: log the would-block result, don't block. One week of shadow mode on staging first.
  4. The widget loads lazily on the four screens only.
  5. Boot check: production refuses to start with provider `none` unless `BOT_CHECK_ALLOW_NONE=1`.
  6. Mobile shell: confirm Turnstile loads in the Capacitor WebView (allow its domain in `mobile/capacitor.config.ts` if navigation is restricted).
- **Tests:** each endpoint refuses a missing or bad token; passes with the stub; shadow mode passes and logs; production boot check; web tests for loading / failed / retry.
- **Done when:** tests green; a curl without a token on staging gets `BOT_CHECK_FAILED`.
- **Person:** Turnstile site and keys.

#### WP-AB3 One trial per business [F-03] — LLM, M

**Goal:** a business can't restart the free trial by signing up again.

- **Files:** `billing/services.py` (`ensure_register_trial`); new `billing/trial_guard.py`; new platform model `billing.TrialFingerprint` (keyed HMAC hashes only); `accounts/onboarding.py`; `accounts/serializers.py` (register); new `core/data/disposable_email_domains.txt` + `scripts/refresh_disposable_domains.py`.
- **Steps:**
  1. On trial start, store keyed HMAC-SHA256 hashes (pepper from settings, a rotatable newest-first list like other keys) of: GSTIN, PAN (characters 3–12 of the GSTIN when only a GSTIN is given), owner phone (E.164 via `otp_utils.normalize_e164`), owner email (lower-cased).
  2. A sign-up whose GSTIN or PAN hash — or phone **and** email hash together — matches a trial used in the last 365 days gets **no trial**: the account works, the subscription page offers paid plans, support code `TRIAL_ALREADY_USED`.
  3. A GSTIN added later during setup runs the same check and ends a running trial early if it matches (email explains why).
  4. Disposable email domains are rejected at sign-up with a translated message.
  5. Staff override in Django admin ("allow a new trial") needs a reason; audit row.
- **Tests:** each match rule; 366-day expiry; late-GSTIN path; override audited; no raw value stored; disposable domain rejected; pepper rotation still matches old hashes.
- **Done when:** tests green; `docs/ops/DATA_CATEGORIES.md` notes fingerprints survive erasure because they hold no clear personal data (counsel to confirm).

#### WP-AB4 Public link hardening [F-05] — LLM, S

**Goal:** public invoice, quotation, receipt and pay links can't be guessed, scraped or indexed.

- **Files:** the public views exercised by `tests/tenancy/test_preauth_writes_rls_postgres.py`; `config/settings.py` (new `public_link` throttle); the document share UI.
- **Steps:**
  1. Audit each link type and fix gaps: token ≥ 128 bits from `secrets`, not derived from IDs; constant-time compare; expiry (default 180 days); owner revoke; `Cache-Control: no-store` and `X-Robots-Tag: noindex`.
  2. Throttle `public_link` 60/min per IP; per-token view counter; a token opened from more than 50 distinct IP prefixes in a day is flagged in admin.
  3. "Revoke link" and "Create new link" on the share menu if missing.
- **Tests:** per link type: entropy, expiry, revoke, headers, throttle.
- **Done when:** tests green; findings and fixes listed in the PR.

### WS-BL — Billing

#### WP-BL2 Razorpay renewals produce a SaaS GST invoice [B-06] — LLM, M

**Goal:** every Bizboard charge — including every Razorpay subscription renewal — produces a GST
invoice a registered customer can claim input tax credit on, and refunds produce a credit note.
Built before BL1 because BL1's credits and refunds need the credit note.

- **Files:** `billing/platform_gst.py` (`_PROVIDERS`, `issue_platform_gst_invoice`); `billing/models.py` (`PlatformGstInvoice` + docstring); `billing/views.py` (`RazorpayWebhookView`); `billing/services.py`; `billing/recon.py`; invoice PDF/email template; owner billing screen.
- **Steps:**
  1. **Wire Razorpay:** add `"razorpay"` to `_PROVIDERS`. In `RazorpayWebhookView`, handle `subscription.charged` (and `invoice.paid` if the account emits it): take `payment.entity.id` as `capture_id` and the charged amount, then call `issue_platform_gst_invoice`. Update the model docstring.
  2. **Ordering:** charge events **bypass** the `billing:wh:lastts:{rzp_id}` out-of-order check — that check only protects status transitions. A charge is deduped on the Razorpay payment ID (the existing one-invoice-per-capture rule) as well as the event ID.
  3. **Recon:** `reconcile_saas_subscriptions` also lists charges for each live subscription and issues any missing invoice (so a lost webhook is caught the next day).
  4. **Content:** buyer GSTIN and legal name from the verified company GSTIN (`gstin_legal_name`), address and state; place of supply from the buyer's state; IGST vs CGST + SGST against `platform_gstin` (reuse `core/services/place_of_supply.py`); SAC code (setting, default 998314 until the CA confirms); B2C path when there's no GSTIN.
  5. **Numbering:** sequential per financial year with no gaps (`core/services/sequences.py`).
  6. **Credit notes:** `kind = INVOICE | CREDIT_NOTE` + `original` FK, used by refunds (BL1, BL3).
  7. **Future e-invoicing:** nullable `irn`, `ack_no`, `ack_date`, `signed_qr` fields, unused until Bizboard crosses the e-invoice threshold (B-07).
  8. Owner screen lists invoices and credit notes with PDF download.
- **Tests:** a `subscription.charged` fixture issues one invoice; the same charge delivered twice → one invoice; a charge older than the last status event is still invoiced; recon issues a missed invoice; intra-/inter-state splits; B2C; credit note on refund; FY numbering without gaps under two concurrent captures (Postgres).
- **Done when:** tests green; a sandbox renewal on staging produces an invoice. **Person:** CA signs the format (handover item 18).

#### WP-BL1 Customer TDS on SaaS fees — refund/credit flow [B-05] — LLM, M

**Goal:** a customer who must deduct TDS on Bizboard's fees can recover it, without any
partial-payment state in subscriptions. The customer pays 100% online; after the quarter they
upload Form 16A; staff verify; the TDS amount is credited to the next renewal or refunded.

- **Files:** `billing/models.py` (new `SaasTdsClaim`: company, platform invoice(s), section, rate, amount, quarter, certificate file, status `SUBMITTED` / `VERIFIED` / `REJECTED` / `SETTLED`, settlement `CREDIT` or `REFUND`, staff user); `billing/services.py`; `billing/views.py` + serializer; web billing screen; Django admin review queue.
- **Steps:**
  1. Owner submits a claim: picks invoices from BL2's list, section/rate from a CA-maintained list (settings; defaults 194J 2%, 194J 10%, 194C 1%, 194C 2%), uploads the certificate (existing `FileAsset` + ClamAV path in `core/services/files.py`). The amount is computed from the invoices' taxable value; the owner can't type it.
  2. Staff verify the certificate against the TRACES details in admin (a person checks; the tool records who and when).
  3. Settlement: **credit** — the next renewal's amount is reduced via a one-time discount/addon on the Razorpay subscription; or **refund** — a Razorpay partial refund against the original payment. Either way BL2 issues a credit note.
  4. Reminder email after each quarter's Form 16A due date for companies that marked "we deduct TDS".
  5. Dunning is unchanged: subscriptions stay fully paid online, so there's nothing to skip.
  6. Admin list of verified claims by quarter (feeds Bizboard's own TDS receivable, X-01).
- **Tests:** claim amount computed from invoices; duplicate claim for the same invoice refused; credit applied once; refund path calls the gateway stub once and issues a credit note; rejected claim notifies the owner.
- **Done when:** tests green. **Person:** CA confirms sections and the credit-vs-refund choice (§7 Q5).

### WS-ID — Identity and account lifecycle

#### WP-ID1 Ownership transfer and owner recovery [I-01] — LLM, M

**Goal:** a company never gets stuck because its only owner left, lost their phone or died.

- **Files:** `accounts/models.py` (`CompanyUser`); new `accounts/ownership.py`; `accounts/views.py` + `accounts/urls_company.py` (`/companies/ownership/transfer/`, `/accept/`, `/cancel/`); web settings → users; Django admin action; new `docs/ops/OWNER_RECOVERY.md`.
- **Steps:**
  1. **Self-serve transfer:** an owner picks an active member; the target accepts by emailed single-use link (72 h, like `InviteJti`); the old owner becomes MANAGER or leaves. Needs current password + MFA (`sensitive_action` throttle). Both get an email; audit row.
  2. **Invariant:** a company always has ≥ 1 active OWNER. Demoting, deactivating or deleting the last owner is refused on every path (role change, deactivate, delete account, user erasure).
  3. **Staff-assisted recovery** (no owner can sign in): Django admin action needing a PO3 ticket, a reason and approval by a second staff user. It sends an owner invite to an address the business has proven (GST-registered email or signed letter — a person checks; the tool records what was checked). 72-hour delay with an email to all current owners, who can cancel.
- **Tests:** transfer happy path; last-owner protection on each write path; recovery needs two different staff users; owners can cancel during the delay; every step audited.
- **Done when:** tests green; runbook linked from `docs/ops/SUPPORT_MACROS.md`.

#### WP-ID2 Company-context isolation [N6] — LLM, M

**Goal:** a user in two companies can never read or write the wrong one, from any tab, device,
download link or background sync.

- **Files:** new `tests/tenancy/test_company_switch.py`; `core/permissions.py` (`get_company_user`); `web/src/api/client.ts`; `web/src/hooks/useCompanySwitcher.test.ts`; `web/src/offline/flushPosCheckout.ts` + test; every place the web app builds a URL opened outside `apiClient` (download links, PDF tabs, `<img src>` for attachments).
- **Server rule:** for a user with **more than one** active membership, an authenticated tenant endpoint without `X-Company-Id` is refused with 409 `COMPANY_HEADER_REQUIRED`, except a short allow-list (`/auth/me/`, `/auth/memberships/`, `/auth/switch-company/`, logout). Single-company users keep today's fallback.
- **Header-less URLs:** downloads, PDF tabs and attachment images either go through `apiClient` as blobs (header attached), or use a short-lived signed URL that carries the company ID inside the signature. List each one found and which way it was fixed.
- **Cases:**
  1. Switch in tab 1; tab 2 still sends company A's `X-Company-Id` and writes → 409, nothing written to B.
  2. Multi-company user, request with no header → 409 `COMPANY_HEADER_REQUIRED` (GET included).
  3. A PDF/export/attachment URL created under A, opened after switching to B → serves A's file only if the signature says A, otherwise refused; never B's data under A's link or vice versa.
  4. After a switch, no cached data from A renders (`qc.clear()` before the first B render).
  5. An outbox draft created under A and flushed while B is active → sent with A's header, or held until A is active; never posted to B.
  6. A Celery task started by a request under A runs with A's tenant GUC (`tests/rls_helpers.py app_role()`).
  7. Mobile: case 5 in the Capacitor build (one e2e in `mobile/e2e`).
- **Done when:** all cases pass; a guard test greps the web source for `window.open(`/`href=` to `/api/` outside the approved helpers.

### WS-CM — Communications

#### WP-CM1 Email bounce suppression and unsubscribe header [C-01] — Split, M

**Goal:** sending reputation stays good, so OTP and invoice emails keep reaching inboxes.

- **Files:** new platform model `core.EmailSuppression` (hashed address, reason, source, expires_at); new provider webhook endpoint (HMAC-verified like the payment webhooks, DLQ via `billing.DeadLetterEvent` on failure); `core/tasks.py` `send_email_notification`; Django admin list with an audited "remove" action.
- **Steps:**
  1. Hard bounce or spam complaint → suppress permanently; three soft bounces in 7 days → 30 days.
  2. Sign-up verification, OTP and reset emails to a suppressed address show "we can't email this address" with a way to change it.
  3. Owner sees a warning on a customer record whose email is suppressed.
  4. Every email carries a category (`security`, `billing`, `transactional`, `product`, `marketing`). Non-transactional categories (`product`, `marketing`, digests, trial nurture) get `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers and a footer link; the link sets a per-user, per-category opt-out (tokenised, no login). Full preference screens stay in Appendix A.
  5. Metric `email_suppressed_total{reason}`; alert when bounces exceed 5% of a day's sends.
- **Tests:** webhook signature, replay, duplicate; each suppression rule; expiry; OTP path message; headers present only on non-transactional categories; one-click opt-out works without login and only for that category.
- **Done when:** tests green. **Person:** pick the provider and set the webhook secret (§7 Q7); SPF/DKIM is handover item 6.

#### WP-CM2 SMS/WhatsApp template registry (DLT) [C-04] — LLM, M

**Goal:** every SMS has a registered DLT template, so non-OTP SMS (dunning, payment reminders)
isn't silently dropped by Indian operators. Today only OTP has a template (`MSG91_TEMPLATE_ID`);
`send_text` has none.

- **Files:** new `core/message_templates.py` (key, channel, DLT template ID, DLT header/sender, WhatsApp template name + language, variables, version, approved flag); `core/services/sms.py` (`_send_msg91`, `_send_twilio`, `send_otp`, `send_text`); `core/services/whatsapp.py`; `config/settings.py` (template IDs from env, one per key); new guard `scripts/ci_gates/guards/guard_message_templates.py`.
- **Steps:**
  1. Replace `send_text(phone, body)` with `send_template(phone, key, **vars)`; move every current SMS/WhatsApp body (OTP, dunning A-07, payment reminders) into the registry.
  2. MSG91: send each key through its own flow/template ID. Twilio: same registry, body rendered from it.
  3. Production and staging refuse to send a key whose template isn't approved or has no DLT ID for an Indian number (same rule `_send_msg91` already applies to OTP).
  4. The guard fails when code calls a provider send with a raw string body.
  5. Every send goes through AB1's `check_and_count_sms`.
- **Tests:** each registered template renders with its variables and stays within DLT length; unapproved key refused under production settings; guard fires on a raw-body fixture; AB1 counters consulted.
- **Done when:** guard green and required. **Person:** fill DLT IDs once registration is done (handover item 6).

### WS-SC — Security

#### WP-SC1 security.txt and disclosure page [S-02] — LLM, S

- **Files:** `web/public/.well-known/security.txt` (contact, expiry, policy URL, languages en/hi); new `docs/help/SECURITY_DISCLOSURE.md` (scope, out of scope, how to report, response times) with the safe-harbour paragraph marked **for counsel**; check the prod web image serves `/.well-known/`.
- **Tests:** web build test that the file is in the output and its `Expires` is in the future.
- **Done when:** served at `/.well-known/security.txt` from the prod image.

#### WP-SC2 Break-glass production access audit [S-01, code side] — LLM, M

**Goal:** every staff session that can read or change production data is named, justified and
reviewable. App code can't stop someone with `docker exec` from running `python -c …`, so the
code side makes the approved path easy and logged, and the people side removes the other paths.

- **Files:** `backend/manage.py` (refuse `shell`, `shell_plus`, `dbshell` and any command in a configurable "interactive" list when `DJANGO_ENV=production` unless `BREAKGLASS_SESSION_ID` is set to a live session); new command `breakglass_session --reason --ticket` that creates the session row, posts to the ops channel (`core/services/telegram.py`) and prints the ID; platform audit model `core.BreakGlassSession` (staff, reason, PO3 ticket, started, ended); `docs/ops/ACCESS_REVIEW.md` (quarterly review); `docs/ops/POSTGRES.md` (statement logging for staff DB roles, e.g. `log_statement = 'mod'` or pgaudit on those roles).
- **People side (§6):** no direct `docker exec` into production containers outside break-glass; one named DB role per staff member, no shared password; statement logging on for those roles.
- **Tests:** `manage.py shell` refused in production mode without a session; allowed with a live one; session expires after 2 h; session row and ops message written.
- **Done when:** tests green; runbook updated.

### WS-CP — Compliance, code side

#### WP-CP1 CERT-In log retention and incident clock [N1] — Split, M

**Goal:** logs needed for an incident report are kept 180 days in India, and the incident runbook
has the 6-hour reporting step.

- **Files:** `docs/ops/LOG_RETENTION.md`; `docs/ops/INCIDENT_RESPONSE.md`; `core/services/retention.py`; `config/settings.py`; a log-shipping example under `deploy/`.
- **Steps:**
  1. Inventory the logs that count: web/API access logs, sign-in and MFA events, admin and break-glass actions (SC2), worker logs, payment webhooks. For each: store, retention, region.
  2. Retention ≥ 180 days in an India-region store; no prune job in `retention.py` deletes these earlier.
  3. A "CERT-In report" step in `INCIDENT_RESPONSE.md`: 6-hour clock from detection, fields to collect, who sends it, template location (wording from counsel).
  4. Time sync: document NTP on every host; a startup check warns when the app and DB clocks differ by more than 2 s.
- **Tests:** retention settings test; clock check.
- **Done when:** tests green; docs updated. **Person:** counsel confirms scope; hosting keeps logs in India (handover item 2).

#### WP-CP2 DPDP request register and breach notice [L-04, N2] — LLM, S

**Goal:** from the first real customer, every privacy request has a record, a due date and an
outcome, and a breach has a notification template ready.

- **Files:** new platform model `support.DataPrivacyRequest` (type `ACCESS` / `CORRECTION` / `ERASURE` / `GRIEVANCE` / `CONSENT_WITHDRAWAL`; requester; company; received, due, closed; outcome; staff); Django admin views; hooks in the self-serve export (`TenantExportView`) and erasure flows so each one creates a row; `docs/ops/INCIDENT_RESPONSE.md` breach-notice section with fields for the Board and for affected people (text from counsel).
- **Tests:** self-serve export and erasure create rows; overdue requests flagged in admin; a manual request can be logged by staff.
- **Done when:** tests green; template section in the runbook.

### WS-PO — Product operations

#### WP-PO1 Customer-facing known-limitations page [N4] — LLM, S

**Goal:** customers and sales know exactly what Bizboard doesn't do.

- **Files:** new `docs/help/LIMITATIONS.md` (source of truth) and a public help route in the web app (en + hi); links from the help menu and sign-up.
- **Content** (from `docs/FREEZE_SCOPE.md` C1–C3 and the deferred list): GSTR-1/3B are worksheets for your CA, not portal filing; no live IRN / e-way bill — record the number from your current tool; no GSTR-2B / IMS matching; stock cost is weighted average, not FIFO; Tally: import of masters, opening balances and outstanding bills, switched on by support on request (GR1a), no live sync; WhatsApp is a share link, not automatic sending.
- **Guard:** extend an existing flag guard so turning on `GSP_LIVE_ENABLED`, `ENABLE_TALLY` or `ENABLE_WHATSAPP_CLOUD` in the frozen profile fails CI unless `LIMITATIONS.md` changes in the same commit.
- **Done when:** page in the web build; guard green.

#### WP-PO2 Tenant health score and monthly business metrics [P-02, N9] — LLM, M

**Goal:** the founder sees which tenants are healthy, which are at risk, and the month's SaaS
numbers, without running SQL.

- **Files:** new `support/health.py`; Django admin views (tenant list sortable by score; monthly metrics table); weekly snapshot task fanned out per company; new platform model `support.TenantHealthSnapshot` (company, week, score, inputs JSON).
- **Score inputs (0–100):** setup finished and first invoice (`TenantActivation`); documents per week, last 4 weeks vs previous 4; days since any user's last login; seats used vs limit (`VendorTenantSnapshot`); open P0/P1 platform tickets (PO3); subscription in `PAST_DUE`; last books check (`core.TenantSweepResult`). Weights in settings; first version even weights.
- **Monthly table:** sign-ups, activated (first invoice within 14 days), trial → paid, paid churn, net revenue retention (from BL2 invoices), tickets per 100 tenants, median time to first invoice.
- **Rules:** staff-only (admin); practice/demo companies excluded.
- **Tests:** score on seeded tenants (healthy, stalled, at-risk); monthly table on a fixed fixture; snapshot task passes `guard_no_inline_company_loops`.
- **Done when:** both views show seeded data. GR2 adds activation steps later; the score reads them when present.

#### WP-PO3 Tenant-to-Bizboard support ticket [P-03] — LLM, M

**Goal:** any user of any tenant — trial included — can ask Bizboard for help from inside the
app, and support works a queue with severity and SLA timers. Needed for SR2-06 (staffed support
in closed beta).

- **Files:** new platform model `support.PlatformTicket` (company, raised_by, subject, description, severity P0–P3, taxonomy tag from `docs/ops/TICKET_TAXONOMY.md`, status, assignee, SLA due, Support ID, route, app version, recent error codes) and `support.PlatformTicketMessage` (+ attachments through `FileAsset`); tenant endpoints `/support/platform-tickets/`; Django admin queue with filters and SLA timers; web "Contact support" form in the help menu and a "My requests" list.
- **Rules:**
  - Separate from `support.Ticket` (merchant-to-buyer helpdesk, `masters.Customer` FK, `CareSalesAccess`, held off in trials) — don't touch that model, its views or `VendorTicketShare`.
  - Not gated by `ENABLE_SUPPORT_TICKETS` or any plan flag; available to every active member. Members see tickets they raised; owners see all of their company's.
  - The form attaches the Support ID, route, app version and the last 5 error codes — never request bodies or form data.
  - Email on staff reply goes through CM1's suppression check.
- **Tests:** a trial tenant can file; a VIEWER can file; RLS app-role test that one company can't see another's tickets; attachments carry no request bodies; SLA due set per severity; overdue shows in admin.
- **Done when:** tests green. **Person:** staffed channel and SLA targets (SR2-06).

### WS-GR — Growth

#### WP-GR1a Tally XML and bill-wise outstanding import [G-01, Tally part] — LLM, M

**Goal:** a closed-beta business on Tally, once staff have granted it the Tally module, brings
masters, opening balances and outstanding bills without engineering help, in time for SR2-01
(import real books) and SR2-04 (parallel month).

**Gating (Q9, founder, 2026-10-22):** the importer stays behind `ENABLE_TALLY`. It remains OFF
in the frozen profile and held off for trials; staff turn it on for each named pilot company. No
new flag, no freeze exception, no change to `integrations/permissions.py`, `TRIAL_HELD_FALSE`
or the env profile.

- **Files:** `integrations/tally/adapter.py` (extend); new Django admin action in `accounts/admin.py` (company admin) + `accounts/rollout_grants.py`; `imports/views.py` source picker; web imports screen; `docs/help/IMPORT_FROM_TALLY.md` with export steps in Tally; `docs/ops/DARK_MODULE_GRANT.md` (new "Rollout flag grant per pilot" section).
- **Steps:**
  1. **Staff grant tool:** the existing `grant_rollout_flag` command is test-only (refuses without `E2E_GOLDEN_GRANT=1`, picks the user's first company), so add a superuser-only Django admin action "Grant / revoke rollout flag" on the company: pick a key from `ROLLOUT_GRANTABLE_KEYS`, enter a reason and a PO3 ticket, then set `feature_flags[key] = True` (or remove it to revoke). Each grant writes an audit row (staff user, company, key, reason, ticket) and clears the memoised flags for that company. Only `ROLLOUT_GRANTABLE_KEYS` are offered, so dark modules (`DARK_MODULE_KEYS`) can't be lifted this way.
  2. **Pilot list:** the admin company list shows a "Tally granted" column and a filter, so ops can see which pilots have it. Revoke after cutover if the pilot shouldn't keep the export.
  3. Tally XML masters export (ledgers with groups, GSTIN, state; stock items with HSN, unit, GST rate, opening stock) next to the existing CSV/XLSX.
  4. Bill-wise outstanding (Tally "Bills Receivable/Payable" with bill reference, date, due date, amount) → opening receivables/payables, so ageing and collections work from day one.
  5. Dry-run preview with row errors; idempotent re-run; `_post_commit_recon` totals vs the file (party count, opening balance totals, outstanding totals) and a downloadable error file.
  6. **Ungranted companies:** the setup wizard and imports screen show "Moving from Tally? Ask support to switch on Tally import" with a link that opens a PO3 ticket tagged `tally-import-request`, instead of hiding the option silently.
- **Tests:** anonymised Tally XML fixtures (collected from the first pilots; synthetic ones until then); idempotent re-run; recon totals; malformed XML → translated errors. Gating: a company without the grant gets 403 from the import endpoints; a **trial** company with the staff grant can import (company value beats the plan's held `False`); revoking removes access on the next request; the admin action refuses a key outside `ROLLOUT_GRANTABLE_KEYS` and a non-superuser; every grant and revoke is audited.
- **Done when:** a real pilot's Tally export imports with zero unexplained recon difference after a staff grant, and the grant is visible in the admin pilot list.

### WS-EN — Engineering

#### WP-EN1 Small-merge gate [E-01] — LLM, S — after WP-A1

**Goal:** no more months-long uncommitted trees.

- **Files:** new PR check in `.github/workflows/ci.yml`; `docs/ops/RELEASE_HYGIENE.md`; `scripts/ci_gates/GATE_INVENTORY.md`.
- **Steps:** count changed lines on a PR excluding generated files (`docs/openapi-snapshot.json`, `web/src/api/openapi-types.ts`, lockfiles, `docs/accounting/LEDGER_COVERAGE_MAP.md`); warn above 1,500, fail above 4,000 unless the PR carries `large-change-approved`.
- **Order:** merge the check only **after** the WP-A1 chunks are on `main`, or the chunks would trip it.
- **Done when:** the check runs on PRs and is listed in the gate inventory.

### P1 people items (not planned here)

| Item | Who |
|---|---|
| X-01 Bizboard's own GST registration, books, deferred revenue and TDS receivable | Founder + CA |
| S-01 named DB role per staff member, no shared password, statement logging on those roles, no direct `docker exec` into prod outside break-glass | Ops |
| Turnstile keys (AB2); email provider + webhook secret (CM1); DLT template IDs (CM2) | Founder |
| CA: TDS sections and credit-vs-refund (BL1); SaaS invoice format and SAC (BL2) | CA |
| Counsel: disclosure safe harbour (SC1), CERT-In scope and template (CP1), breach and request wording (CP2), fingerprint retention (AB3) | Counsel |
| Support channel staffed with SLA targets (PO3, SR2-06) | Founder |
| Tally export files from the first pilots (GR1a) | Founder / beta businesses |
| Grant `ENABLE_TALLY` to each named Tally pilot with GR1a's admin action, and revoke it after cutover where needed | Ops / support |

---

## 3. Phase 2 — before public launch

Target: built during the closed and paid beta (weeks 6–16) and proven on hosted staging before
the Wave 4 launch gate.

### WS-BL — Billing

#### WP-BL3 Proration on plan change [B-04] — Split, M

**Goal:** upgrades take effect at once and the customer pays only the difference; downgrades take
effect at period end. Built on today's pattern — a new Razorpay subscription parked in
`pending_razorpay_subscription_id`, old one cancelled when the new one is active — not on
Razorpay's subscription update call.

- **Files:** `billing/services.py` (`start_or_update_subscription`, `_create_razorpay_subscription`, `_cancel_razorpay_subscription`); `billing/views.py` (`SubscriptionDetailView`, `CheckoutView`); web plan screen.
- **Steps:**
  1. **Upgrade:** new modules and limits apply immediately; the prorated difference for the rest of the current period (days left × daily price difference) is charged once via a Razorpay order/payment link; BL2 invoices it. The new plan's subscription is created with `start_at` = current period end (existing path), so the next renewal is at the new price.
  2. **UPI Autopay subscriptions:** a higher amount needs a new mandate, so the upgrade flow asks the user to approve the new subscription's mandate (BL4); until approved, the old mandate stays and the upgrade's modules stay on through the current period.
  3. **Downgrade:** at period end (current `pending_plan` behaviour); the screen lists modules and limits that will change. A downgrade below current use (`billing/quotas.py` `usage_snapshot`) is refused with what to remove first.
  4. Failed proration payment → upgrade modules revert at the end of a 3-day grace.
- **Tests:** proration amount on fixed dates; one-time charge invoiced once; pending subscription starts at period end; downgrade refused over quota; failed proration reverts after grace; out-of-order webhook variants (extend existing).
- **Done when:** tests green. **Person:** sandbox run of upgrade, downgrade and UPI re-mandate.

#### WP-BL4 UPI Autopay renewals [B-01] — Split, M

- **Files:** `billing/services.py` (`_create_razorpay_subscription`: allow UPI, set `customer_notify` as Razorpay recommends for mandates); `billing/views.py` (`CheckoutView`, `RazorpayWebhookView`); web checkout and billing screen.
- **Steps:**
  1. Offer UPI Autopay next to card at checkout.
  2. Handle mandate events: `subscription.authenticated`, `subscription.charged` (invoiced by BL2), `subscription.paused`, `subscription.resumed`, `subscription.cancelled`, `subscription.halted` (through `_map_razorpay_status`; unknown events go to the DLQ).
  3. **Pre-debit notice:** the statutory notice and pause/opt-out link are sent on the bank/NPCI rail. Bizboard's own reminder is **email only** (CM1 category `billing`), 3 days before renewal — no SMS, so it doesn't duplicate the statutory SMS or spend AB1 budget.
  4. Billing screen: mandate status, next debit date, "cancel mandate" link; upgrade re-mandate prompt (BL3 step 2).
- **Tests:** webhook fixtures per event; replay and duplicate; Bizboard reminder email once per cycle and never SMS; halted mandate enters dunning.
- **Needs:** BL2. **Person:** enable UPI Autopay on the Razorpay account; sandbox run.

### WS-ID — Identity

#### WP-ID3 Active sessions screen and new-device alert [I-03] — LLM, M

- **Files:** new `accounts.UserSession` (refresh-token family id, device label from user agent, IP prefix /24, created, last used, revoked_at) written by `LoginView`, `VerifyOtpView`, `MfaLoginVerifyView` (`accounts/mfa_views.py`) and `CookieTokenRefreshView`; list/revoke endpoints next to `LogoutAllView`; web settings → security.
- **Steps:** list the user's sessions; revoke one (blacklist that family's refresh token); email on sign-in from a device label + IP prefix not seen in 90 days; owners see members' session counts (not details).
- **Tests:** only own sessions listed; revoke blocks refresh; new-device email once; full IPs never stored.
- **Done when:** tests green.

#### WP-ID4 Customer-approved support access [I-05] — LLM, L — **blocked on §7 Q4**

**Goal:** support can look at a tenant's data to fix an issue without screen-sharing, only with
the owner's approval, read-only, time-limited and fully audited. Replaces the screen-share-only
decision (execution plan 4.6) and the guard `tests/test_no_impersonation.py`.

- **Files:** new `support.SupportAccessGrant` (company, granted_by, staff user or "any support staff", scope `READ_ONLY`, expires_at ≤ 72 h, `PlatformTicket` FK, revoked_at); `core/middleware.py` / `core/rls.py`; a permission class for grant requests; web settings → "Allow Bizboard support to view your data"; in-app banner while a grant is live; Django admin "open tenant read-only" link.
- **Steps:**
  1. Owner creates a grant (MFA required) tied to a PO3 ticket.
  2. A staff request under a live grant: sets the tenant GUC for that company only; runs inside a transaction opened with `SET TRANSACTION READ ONLY`, so the database refuses any write — including side effects of GET handlers (audit rows, caches written to the DB, `active_company_id` saves); refuses non-safe HTTP methods with `SUPPORT_READ_ONLY` before the view runs; resolves the company from the grant, **not** through `get_company_user` (the staff user has no membership, and its save-on-GET must not run).
  3. Each request is audited in a separate, writable connection or after the read-only transaction ends (the audit write must not be inside it).
  4. Owner sees what support viewed and can revoke at once; a beat task that visits only live grants revokes expired ones.
- **Tests:** no grant → nothing visible; grant → reads work; non-safe methods 403; a GET handler that writes fails with the DB read-only error and is reported, not swallowed; audit row written outside the read-only transaction; expiry; revoke; app-role RLS test that the staff path can't reach a second company; `test_no_impersonation.py` becomes "no access without a live grant".
- **Done when:** tests green; `docs/ops/SUPPORT_MACROS.md` updated. **Person:** counsel approves consent wording.

#### WP-ID5 Sign in with Google [I-02] — Split, M

- **Files:** new `accounts/google_signin.py` (verify the Google ID token: audience, issuer, expiry, `email_verified`); endpoint `/auth/google/` in `accounts/urls_auth.py`; `LoginPage.tsx`, `RegisterPage.tsx`; `requirements.txt` + `constraints.txt` (`google-auth`, pinned).
- **Steps:** existing user with that verified email → sign in, then the normal `mfa_challenge_response` for money roles; new email → normal sign-up with email pre-verified, legal acceptance recorded (`LegalAcceptance`), AB2 and AB3 still apply. No linking by an unverified email.
- **Tests:** bad audience / issuer / expired token refused; MFA still challenged; unverified email refused; acceptance recorded; trial dedupe applies.
- **Done when:** tests green. **Person:** Google OAuth client IDs for staging and prod.

### WS-CM — Communications

#### WP-CM3 What's new and announcements [C-05] — LLM, S

- **Files:** `docs/help/WHATS_NEW.md` (source, en + hi per entry); web `WhatsNewPanel` from the help menu with an unread dot stored server-side per user; staff-only admin model `core.Announcement` (text en/hi, start, end, target all / plan / company, severity) for maintenance and incident banners. In-app only — no email, so no unsubscribe needed.
- **Tests:** unread logic; banner window and targeting; guard that every entry has Hindi text.
- **Done when:** panel and banner work on seeded data.

### WS-DL — Data

#### WP-DL1 Readable, versioned customer export [D-02] — LLM, M

**Goal:** a customer who leaves can open their data in Excel or another system, not only restore it into Bizboard.

- **Files:** `accounts/export_views.py` (`TenantExportView`: add `format=readable`); `accounts/tenant_backup.py` (reuse `build_export_payload` and `_csv_bytes`); new `docs/help/DATA_EXPORT_FORMAT.md`.
- **Steps:**
  1. Keep the encrypted export for restore.
  2. Readable ZIP: `manifest.json` (format version, company, generated at, files with row counts and SHA-256); one CSV per entity with documented, stable column names (UTF-8 with BOM so Excel shows Hindi correctly); PDFs of statutory documents; a README in en + hi.
  3. Large tenants: built in a Celery task on the `reports` queue; owner gets a time-limited download link (MFA required). Each export creates a CP2 `ACCESS` row.
  4. Version rules: adding a column is a minor bump; renaming or removing one is a major bump with notice.
- **Tests:** manifest counts equal DB counts on a seeded company; checksums verify; column snapshot test; only OWNER can request; link expires; CP2 row created.
- **Done when:** tests green; format doc published in help.

### WS-GR — Growth

#### WP-GR1b Busy, Vyapar and Marg importers [G-01, other sources] — LLM, M–L

- **Files:** new `integrations/busy/`, `integrations/vyapar/`, `integrations/marg/` with the Tally adapter's shape (`parse_*_rows` → preview → commit → `_post_commit_recon`); `imports/views.py` source picker; one help guide per source.
- **Steps:** map each tool's standard Excel exports for parties, items, opening stock and outstanding bills. Build from 2–3 real anonymised files per source from pilots (§7 Q8), not from guesses; one source at a time by pilot demand. Same gating model as GR1a: each source sits behind a rollout-grantable flag that is off by default and granted per pilot company with GR1a's admin action (one new key, `ENABLE_LEGACY_IMPORT`, added to `ROLLOUT_GRANTABLE_KEYS` and to `TRIAL_HELD_FALSE`).
- **Tests:** fixture per source; idempotent re-run; recon totals; malformed file errors translated.
- **Done when:** each built source imports its fixture with zero unexplained recon difference.

#### WP-GR2 Onboarding checklist and time to first invoice [G-05] — LLM, M

- **Files:** `billing/models.py` (`TenantActivation`: add GSTIN verified, first item, first party, first purchase, first payment, invited a user, imported from old software); the code paths that perform those actions set the timestamps; web home-screen checklist card (dismissible, en + hi); events in the Journey Health schema (`insights/event_schema.py`).
- **Tests:** each step completes from the real action only; card hides at 100% or on dismiss; event schema test updated.
- **Done when:** PO2's monthly table shows median time to first invoice by sign-up week.

### WS-RS — Scale

#### WP-RS1 Month-end and GST-deadline load scenario [R-04] — Split, S

- **Files:** new `load/month_end.js` (k6): 70% of tenants open GSTR-1/3B worksheets and export ZIPs/PDFs within 2 hours while normal invoicing continues; a row in `docs/ops/LOAD_RESULTS_TEMPLATE.md`; a `docs/ops/WORKER_SCALE.md` section on pre-scaling workers before the 10th, 11th and 20th.
- **Done when:** scenario runs locally against the large-tenant seed. **Person:** run on hosted staging (handover item 11).

### WS-SC — Security

#### WP-SC3 SBOM and image scanning [S-03] — LLM, S

- **Files:** `.github/workflows/ci.yml` or `cd.yml`: CycloneDX SBOM for backend, web and mobile per build, attached to the release; Trivy scan of built images failing on new CRITICAL; reviewed allow-list `security/trivy-allowlist.yaml` (reason + expiry per entry).
- **Done when:** job green and required; allow-list empty or every entry justified.

### P2 people items (not planned here)

| Item | Who |
|---|---|
| E-04 two people who can deploy, roll back and be on call | Founder |
| Razorpay sandbox runs: proration, UPI Autopay, re-mandate on upgrade (BL3, BL4) | Founder / Eng |
| Google OAuth client IDs (ID5) | Founder |
| Support-access consent wording (ID4) | Counsel |
| Busy/Vyapar/Marg sample files from pilots (GR1b) | Founder / beta businesses |
| Month-end scenario run on hosted staging (RS1) | Eng on hosted infra |

---

## 4. Order and dependencies

```
WP-A1 commit/tag (previous plan) — nothing below starts before it
 │
 ├─ P1, weeks 1–6 (three lanes in parallel)
 │    Lane 1 — abuse/comms/compliance: AB1 → CM2 → AB2 → AB3 → AB4 · CP1 · CP2 · SC1
 │    Lane 2 — billing/identity:        BL2 → BL1 · ID2 → ID1
 │    Lane 3 — ops/product/growth:      EN1 · PO1 · CM1 → PO3 → SC2 · PO2 · GR1a (as pilot files arrive)
 │    then: hosted-staging proof during Wave 2 (Turnstile shadow → enforce, CM1 webhook,
 │          CP1 log store, sandbox renewal invoiced by BL2)
 │
 └─ P2, weeks 6–16
      Lane 1 — billing:   BL3 → BL4
      Lane 2 — identity:  ID3 · ID5 · ID4 (after Q4)
      Lane 3 — growth:    GR2 · GR1b (as pilot files arrive) · DL1
      Lane 4 — ops:       CM3 · SC3 · RS1
```

| WP | Needs first | Shares files with (one writer at a time) |
|---|---|---|
| AB1 | Redis in every environment (already required) | CM2 (`core/services/sms.py`), AB2 (`accounts/views.py`) |
| CM2 | AB1 | AB1 |
| AB2 | — | AB3, ID1, ID3, ID5 (`accounts/views.py`) |
| AB3 | — | BL1, BL2 (`billing/`) |
| BL2 | — | BL1, BL3, BL4 (`billing/views.py`, `billing/services.py`) |
| BL1 | BL2 (credit notes, invoice list) | BL2 |
| ID2 | — | ID4 (`core/permissions.py`) |
| ID1 | PO3 (recovery needs a ticket) | ID3 (`accounts/views.py`) |
| PO3 | CM1 (reply emails) | — |
| SC2 | PO3 (session names a ticket) | — |
| PO2 | PO3, BL2 (ticket and revenue inputs) | — |
| GR1a | PO3 (grant reason names a ticket; "ask support" link); pilot Tally files for the done-when | `accounts/admin.py` |
| EN1 | WP-A1 merged | `.github/workflows/ci.yml` |
| BL3 | BL2 | BL4 |
| BL4 | BL2 | BL3 |
| ID4 | §7 Q4, PO3, ID2 | `core/middleware.py`, `core/rls.py`, `core/permissions.py` |
| ID5 | AB2, AB3 | `LoginPage.tsx`, `RegisterPage.tsx` with AB2 |
| GR1b | GR1a, sample files (§7 Q8) | `imports/views.py` with GR1a |
| GR2 | PO2 | `billing/models.py` |
| DL1 | CP2 | `accounts/export_views.py` |

**Sizes:** P1 ≈ 37 engineer-days (about 2.5 weeks with three lanes). P2 ≈ 29 engineer-days (about 2 weeks with four lanes), plus waiting time for pilot files and sandbox runs.

---

## 5. How to test (recipes)

- Backend: `pytest` from `backend/`. `settings_test` drops `DATABASE_URL` unless `PYTEST_KEEP_DATABASE_URL=1`; Postgres-marked tests need it. Don't edit models or migrations while a long run is going.
- RLS: every new tenant table gets a test under the non-superuser role (`tests/rls_helpers.py app_role()`), plus the existing RLS coverage test.
- Concurrency (AB1 counters, BL2 numbering) and the read-only transaction (ID4): Postgres tests (`pytest.mark.postgres`); they must run, not skip, in CI (`check_postgres_skips.py`).
- Webhooks: fixtures from Razorpay's documented payloads under `tests/fixtures/razorpay/`; every new event type also gets replay, duplicate and out-of-order tests.
- Web: `npx tsc -b` (not `tsc -p .`), `npm run lint` (0 errors, CI-gated), `npx vitest run <files>`.
- After API changes: `manage.py spectacular` → `docs/openapi-snapshot.json` → `npm run gen:api-types`.
- Guards: `python scripts/ci_gates/guards/<guard>.py` from the repo root; add new guards to the runner and `scripts/ci_gates/GATE_INVENTORY.md`.
- Write test scripts with the Write tool, not shell heredocs (apostrophes and backslashes get mangled).

---

## 6. Definition of done

| Phase | Done when |
|---|---|
| **P1 — before paid beta** | All 19 P1 WPs green in CI. On hosted staging: a sandbox Razorpay renewal produces one GST invoice; Turnstile enforcing after a shadow week with no false blocks; an SMS cap test send blocked and alerted; a dunning SMS delivered through a registered DLT template; bounce webhook received and suppressing; logs in the India-region store with 180-day retention; a trial tenant files a platform ticket and staff answer it; a pilot's Tally export imported with zero unexplained recon difference; limitations page live; health view showing the beta tenants. P1 people items closed or waived in writing. |
| **P2 — before public launch** | All 11 P2 WPs green in CI (ID4 built, or Q4 answered "no" and the WP dropped in writing). Sandbox runs of proration, UPI Autopay and re-mandate logged; at least one of Busy/Vyapar/Marg importing anonymised pilot files with zero unexplained recon difference; month-end scenario run on hosted staging with results against `SLO.md`; SBOM + image scan required in CI; P2 people items closed. |

---

## 7. Decisions needed before starting

| # | Question | Default if no answer (lets the build start) | Blocks |
|---|---|---|---|
| Q1 | Bot check provider? | Cloudflare Turnstile | — |
| Q2 | SMS caps? | 3/hour and 8/day per number; 30/hour per 4-digit range; 5,000/day platform; international off | — |
| Q3 | Trial dedupe keys and window? | GSTIN/PAN, or phone + email together; 365 days | — |
| Q4 | Allow customer-approved, read-only support access (replaces screen-share-only, plan 4.6)? | **Answered 2026-10-22 (founder): yes** — read-only, ≤ 72 h, owner approves per request | — |
| Q5 | Which TDS sections/rates do customers apply to Bizboard fees; settle by credit on next renewal or refund? | **Answered 2026-10-22 (founder): credit by default, refund on request.** Section list stays a CA-maintained setting | BL1 CA sign-off |
| Q6 | Plan change rule? | Upgrade now with a one-time prorated charge; downgrade at period end | — |
| Q7 | Email provider for bounce webhooks? | Amazon SES, India region | CM1 on staging |
| Q8 | Which non-Tally importers first? | Busy, then Vyapar, then Marg, by pilot demand | GR1b order |
| Q9 | One-time Tally import is behind `ENABLE_TALLY` (OFF in the freeze and for trials). Split it into its own flag? | **Answered 2026-10-22 (founder): no.** Keep it behind `ENABLE_TALLY`; staff grant it per pilot company (GR1a step 1). No freeze exception. | — |

---

## Appendix A — after public launch (not planned in detail)

| Item | Review ID | Size |
|---|---|---|
| Notification preference screens per user/channel (CM1 covers one-click opt-out only) | C-02 | M |
| Push notification sender (FCM) + per-device tokens (today one `User.push_token`) | C-03 | M |
| GST rule-change kit (`apply_hsn_rate_change`, runbook, notice template) | L-01 | M |
| API / mobile compatibility test against the last release's schema | E-03 | M |
| Flag expiry guard | P-05 | S |
| Consented product analytics on the Journey Health pipeline | P-01 | M |
| NPS / CSAT survey | P-04 | S |
| Audit log screen and export for owners | I-04 | M |
| Annual plans + deferred-revenue schedule | B-02 | M |
| Add-ons (users, SMS packs, storage, AI credits) | B-03 | M |
| E-invoicing (IRN) on Bizboard's own invoices once over the threshold — fields added in BL2 | B-07 | M |
| Accountant (CA) multi-client console | G-02 | L |
| Referral programme | G-03 | M |
| Practice company with demo data | G-04 | M |
| Storage lifecycle rules and per-tenant storage view | D-04 | S |
| One-tenant point-in-time restore into a staff-only copy | D-05 | M |
| Copy masters into a new company | D-03 | M |
| Old-year report performance (indexes, closed-year summaries) | D-01 | L |
| Read-replica router for reports | R-01 | M |
| Dedicated PDF worker pool | R-03 | S |
| Sharding trigger ADR | R-06 | S |
| Fake-invoice signals for staff | F-04 | M |

---

## 8. Implementation record — Phase 1 (2026-10-22)

**State:** all 19 P1 work packages built and tested in the working tree, **not committed** (WP-A1
from the 2026-10-21 plan is still open; the founder asked to proceed anyway). Nothing is on a host.
P2 has not started.

### What was built

| WP | What exists now | Proof |
|---|---|---|
| AB1 | `core/services/sms_guard.py` caps every SMS (per phone hour/day, per 4-digit range, platform/day, international off, kill switch, fail-closed); attempts count even when the provider fails; `manage.py sms_guard status/kill`; 3 alert rules + runbook `ALERTS.md#sms-spend`; `core/services/counters.py` fixes the `add`+`incr` expiry race, also used by `ai_spend` | `tests/test_sms_guard.py` (13) |
| CM2 | `core/message_templates.py` registry; `SmsProvider.send_template` is the only SMS path; MSG91 sends non-OTP SMS by DLT template id (flow API); production refuses a template with no DLT id; dunning uses the `payment_reminder` template on every channel; WhatsApp names come from the registry; `guard_message_templates` | `tests/test_message_templates.py` (7) |
| ID2 | Server: a user in 2+ companies must send `X-Company-Id` on tenant API calls (409 `COMPANY_REQUIRED`, `REQUIRE_COMPANY_HEADER_FOR_MULTI`, off in test settings). Web: other tabs reload on a company switch (`api/companyContext.ts`); every outbox flush stops if the company changed; care attachments load through `apiClient`; a source scan forbids direct API links | `tests/tenancy/test_company_switch.py` (6), web `companyContext.test.ts`, `noDirectApiLinks.test.ts`, `attachments.test.tsx` |
| PO1 | The existing in-app page gained 2B/IMS, Tally and WhatsApp lines (en + hi); public route `/limits`; source `docs/help/LIMITATIONS.md`; `guard_limitations_page` keeps doc, page and both languages in step | web `PilotLimitsPage.test.tsx` |
| SC1 | `web/public/.well-known/security.txt` (served as text by nginx), `docs/help/SECURITY_DISCLOSURE.md` (safe harbour marked for counsel) | web `securityTxt.test.ts` |
| BL2 | Razorpay `subscription.charged` issues the GST invoice (a late charge is still invoiced but never moves status back); daily recon issues missed ones; buyer GSTIN/legal name/state, SAC, Bizboard-wide gap-free FY numbers (`BB2627-000001`, `PlatformInvoiceSequence`), credit notes, empty IRN fields; owner list `GET /billing/invoices/` and a panel on Billing | `tests/test_platform_gst_bl2.py` (7 + 1 Postgres) |
| BL1 | `billing/tds_claims.py`: owner claims TDS on chosen invoices with Form 16A; amount computed from taxable value; staff verify in admin → Razorpay partial refund per invoice (retry-safe); reject with reason; panel on Billing | `tests/test_tds_claims_trial_guard.py` |
| AB3 | `billing/trial_guard.py`: hashed GSTIN/PAN/phone/email fingerprints; a repeat business gets its trial already ended; a GSTIN added later ends a running repeat trial; disposable email domains refused at sign-up; staff can delete fingerprints in admin | same file |
| AB4 | `PublicLinkMiddleware`: `no-store` + `noindex` on every public share link (errors too); a token opened from more than 50 networks a day is logged and counted | `tests/test_public_link_hardening.py` (9) |
| AB2 | `core/services/bot_check.py` (Turnstile / none / stub, shadow mode); the four pre-login endpoints call it; web `BotCheck` widget (lazy, only with a site key) + `X-Bot-Token` on those four calls; CSP allows Cloudflare's script and frame; production refuses to boot without Turnstile unless `BOT_CHECK_ALLOW_NONE=1` | `tests/test_bot_check.py` (12), web `botCheck.test.ts` |
| PO3 | `support.PlatformTicket` + messages (separate from the merchant helpdesk); any member, any plan; owners see all, others their own; SLA due per severity; P0/P1 ping ops; admin queue where a typed reply is emailed; web `/help/contact` (+ "My requests"), linked from Help; Support ID, route and last 5 error codes attached | `tests/test_saas_phase1_ops.py`, web `ContactSupportPage.test.tsx` |
| ID1 | `accounts/ownership.py` + API (`/company/ownership/…`): owner offers ownership (password + MFA), member accepts from an emailed link, roles swap in one transaction; staff recovery = `manage.py owner_recovery request` + second-staff approval in admin + 72-hour wait + owner invite (hourly beat task); web "Make owner" on Users + `/ownership/accept`; runbook `docs/ops/OWNER_RECOVERY.md` | `tests/test_saas_phase1_ops.py`, web test |
| CM1 | `core/mail.py`: one `send()` for all email; hard bounce/complaint suppress, 3 soft bounces in 7 days suppress for 30; non-transactional categories get `List-Unsubscribe` + one-click; `/email/events/` webhook (SES via SNS, Postmark; HTTP Basic); `/email/unsubscribe/`; all six `send_mail` sites moved; `guard_no_direct_send_mail`; sign-up says plainly when an address bounced before | `tests/test_saas_phase1_ops.py` |
| SC2 | `manage.py` refuses `shell`/`shell_plus`/`dbshell` on production without a live `BREAKGLASS_SESSION_ID`; `manage.py breakglass_session open/end/list` (ops ping, 2-hour sessions, commands recorded); admin list for the access review | `tests/test_saas_phase1_ops.py` |
| CP1 | `LOG_RETENTION.md` CERT-In section (what, where, 180 days, India), `INCIDENT_RESPONSE.md` reporting clocks; `bizboard_clock_skew_seconds` + `BizBoardClockSkew` alert | `tests/test_alert_rules.py` |
| CP2 | `support.DataPrivacyRequest` register (admin, overdue flag); self-serve export and company erasure create closed rows; `docs/ops/DPDP_REQUESTS.md` (steps + breach-notice fields for counsel) | `tests/test_saas_phase1_ops.py` |
| PO2 | `support/health.py` score (setup, first invoice, invoicing trend, last sign-in, seats; minus P0/P1 tickets, past due, failed books check); weekly fan-out task; admin list worst first; `manage.py saas_metrics --month` (sign-ups, activated, trial→paid, churn, NRR, tickets/100, median days to first invoice) | `tests/test_saas_phase1_ops.py` |
| GR1a | `integrations/tally/xml_import.py` reads Tally XML (UTF-16, DOCTYPE/ENTITY refused) incl. bill-wise outstanding; one opening document per bill with its due date, plus on-account remainder, so totals still tie; XML allowed for import uploads; admin action "Grant or revoke a rollout flag" (superuser, reason, ticket, audited; only grantable keys) with a "Tally" column and filter; ungranted Tally page links to a prefilled support request | `tests/test_tally_xml_import.py` (5) + existing Tally tests |
| EN1 | `scripts/ci_gates/check_merge_size.py` + advisory `merge-size` CI job (warn 1,500 / fail 4,000 changed lines, generated files excluded); docs | logic self-test |

Migrations: `billing/0014`, `0015`; `core/0069`, `0070` (RLS for the five new tenant tables);
`accounts/0070`, `0071`; `support/0006`. OpenAPI snapshot and web types regenerated (additions only).

### Bugs found while building

| Bug | Effect | Fix |
|---|---|---|
| The SMS guard treated customer phones stored as 10 digits (no +91) as international | Dunning SMS to most stored customers would have been refused | 10-digit numbers starting 6–9 (and 0-prefixed) are normalised to +91 |
| Import uploads refused `application/xml` | A Tally XML export could not be uploaded at all | `.xml` sniffed from content and allowed for the import kind only |
| `ai_spend._incr` used `add` then `incr` | A key expiring between the calls raised and refused a model call | Shared `core/services/counters.incr` |
| The ownership email named no link | The member could not find the offer | Email carries `FRONTEND_URL/ownership/accept?token=…` |
| Two tabs share the active company (localStorage) | After a switch in tab 1, tab 2 kept showing company A while sending company B's header | Other tabs reload on switch |

### Where it differs from the plan

- **AB1** defaults: 5/hour per phone (matches the OTP view's existing limit) and 10/day, not 3/8. Kill switch and status: `manage.py sms_guard` and (second pass) the admin page `/admin/ops/sms-guard/` (superuser flips, audited).
- **AB2** boot refusal applies to `DJANGO_ENV=production` only, so the local staging stack keeps booting; staging must set Turnstile before the hosted run.
- **AB3** a repeat business gets its trial row already ended (read-only until it pays), rather than no subscription row.
- **AB4** done once in middleware rather than per view; existing revoke/expiry were already in place.
- **BL1** (second pass, Q5) credit by default: a verified claim comes off the next renewal by refunding that much of the renewal's own payment the moment it is charged (webhook, with a daily retry); the owner can switch to a refund while credit is left. Quarterly Form 16A reminder on the 16th of Aug/Nov/Feb/Jun.
- **BL2** (second pass) PDF of each invoice and credit note: `GET /billing/invoices/<id>/pdf/`, linked from the Billing panel; seller block from `PLATFORM_LEGAL_NAME` / `PLATFORM_ADDRESS`.
- **CM1** a send helper + guard instead of an email-backend wrapper (a contract test pins `EMAIL_BACKEND`). (Second pass) the customer page warns when the customer's email is suppressed (`emailSuppressed` on the customer read and the 360 view).
- **PO1** guard checks doc/page/language parity; turning a deferred feature on is already blocked by `guard_freeze_table_b_defaults`.
- **PO2** monthly numbers: `manage.py saas_metrics` and (second pass) the admin page `/admin/ops/saas-metrics/`, which also shows median days to first invoice by sign-up week (GR2).

### Phase 1 proof (second pass, 2026-10-22)

- Postgres (throwaway container): the BL2 numbering race, RLS coverage and every new suite pass.
  The first Postgres run found a real bug: `accept_transfer` locked with `select_for_update()`
  across a nullable join, which Postgres refuses (`FOR UPDATE cannot be applied to the nullable
  side of an outer join`) — ownership transfers could never be accepted on Postgres. Fixed with
  `select_for_update(of=("self",))`.
- AB1 counters on a real Redis: `tests/test_counters_redis.py` (exact under 8 concurrent workers,
  expiry kept, per-phone cap holds across 12 concurrent senders).
- Full backend suite: see §9 results.

---

## 9. Implementation record — Phase 2 (2026-10-22)

All 11 P2 work packages are built and tested in the working tree. Q4 and Q5 answered by the
founder the same day (yes / credit by default).

| WP | What exists now | Proof |
|---|---|---|
| BL3 | `billing/plan_change.py`: upgrade applies at once (`effective_plan` used for modules, quotas and seat limit), prorated difference (seconds left × price difference / 30 days) charged once by Razorpay payment link, `payment_link.paid` webhook invoices it (BL2); the new plan's subscription still starts at period end; unpaid after 3 days → upgrade reverted and pending subscription cancelled (daily task); downgrade at period end, refused over seat/storage use; Billing shows the change, the pay-the-difference and approve-mandate buttons | `tests/test_plan_change_autopay.py` |
| BL4 | `billing/autopay.py`: mandate state and payment method recorded from webhook events (authenticated, activated, charged, pending, halted → PAST_DUE → dunning, paused, resumed, cancelled); other `subscription.*` events parked on the DLQ; renewal reminder email 3 days ahead, once per cycle, never SMS; Billing shows method, mandate state and next debit | same file |
| ID3 | `accounts.UserSession` (device label, /24 or /48 prefix, never the full IP), recorded at every refresh-cookie issue; refresh moves the row, revoke blacklists its token; new-device email (90 days); Settings → Users "Signed-in devices"; owners get member session counts only | `tests/test_user_sessions_id3.py` |
| ID4 | `support.SupportAccessGrant` / `SupportAccessLog`: owner grants (password + two-step) for one open request, ≤ 72 h, any or a named staff member; staff read in `/admin/ops/support-view/<grant>/` (8 sections) inside a database READ ONLY transaction (SQLite: `query_only`), tenant GUC set transaction-locally and every query filtered on the grant's company; non-GET refused with `SUPPORT_READ_ONLY`; each look logged after the read-only block; owner sees every look and can end it; hourly expiry, resolving the request ends it; banner on every screen while live; `SUPPORT_MACROS.md` | `tests/test_support_access_id4.py` (+ Postgres app-role test) |
| ID5 | `accounts/google_signin.py` (PyJWT against Google's keys: audience, issuer, expiry, verified email; no new dependency); existing user → same membership and two-step checks as a password sign-in; new email → sign-up with company name and terms, bot check and trial dedupe still apply; shared `create_owner_account`; web button on Login and Register (only with `VITE_GOOGLE_CLIENT_ID`), CSP allows Google Identity Services | `tests/test_google_signin_id5.py`, contract in `tests/test_mfa.py` |
| CM3 | `web/src/help/whatsNew.ts` (en + hi) mirrored in `docs/help/WHATS_NEW.md`; "What's new" button with an unread dot stored per user; `core.Announcement` staff banners (all / plan / company, window, severity) shown on every screen; `guard_whats_new` | `tests/test_announcements_cm3.py`, guard self-test |
| DL1 | `accounts/readable_export.py`: ZIP with `manifest.json` (rows + SHA-256 per file), one CSV per section (UTF-8 BOM), invoice PDFs (first 500), README en + hi; built on the `reports` queue; owner-only after password; link 24 h then purged; privacy-register row; `docs/help/DATA_EXPORT_FORMAT.md` with version rules; column snapshot pins the main sections | `tests/test_readable_export_dl1.py` |
| GR1b | `integrations/legacy_import.py`: Busy / Vyapar / Marg party and item exports mapped onto the Tally importer's rows, same commit and recon; non-party ledgers skipped; wrong file refused with the expected columns; `ENABLE_LEGACY_IMPORT` grantable per company, held off for trials; Import page panel; `docs/help/LEGACY_IMPORT.md` | `tests/test_legacy_import_gr1b.py` |
| GR2 | `billing/onboarding.py`: 8 steps stamped once on `TenantActivation` from the real action (model signals; the timestamps are the record — a separate telemetry event would break the OG2-E8 no-dual-write gate); home-screen card (owner can hide; hides at 100%); PO2 admin page shows median days to first invoice by sign-up week | `tests/test_onboarding_gr2.py` |
| RS1 | `load/month_end.js` (k6): 70% of tenants open GSTR-1/3B and download both as Excel over the window while drafts are completed; gates in the header; row in `LOAD_RESULTS_TEMPLATE.md`; pre-scaling in `WORKER_SCALE.md` | script parses (`node --check`); see open items |
| SC3 | CI job `supply-chain` (merge blocker): Trivy on both built images (fixable CRITICAL fails), CycloneDX SBOMs for backend, web, mobile and both images kept with the run; CD attaches the release SBOMs; `security/trivy-allowlist.yaml` + `guard_trivy_allowlist` (reason + expiry, not expired) | guard + self-test, `guard_required_checks_match` |

Migrations: `accounts/0072`–`0074`, `billing/0016`–`0018`, `core/0071`, `core/0072` (RLS for
the three new tenant tables), `integrations/0004`, `support/0007`. OpenAPI snapshot and web
types regenerated (additions only).

### Bugs found while building (Phase 2 and second pass)

| Bug | Effect | Fix |
|---|---|---|
| `accept_transfer` used `select_for_update()` with `select_related` on nullable FKs | On Postgres every ownership acceptance failed | Lock only the transfer row (`of=("self",)`) |
| simplejwt refuses to parse a blacklisted token by default | Session tracking could never move a device row on refresh (new row each time) | Read the rotated token with `verify=False` |
| SQLite `query_only` was reset inside a broken transaction | After one refused write the connection stayed read-only for the rest of the process | Reset on the raw connection outside Django's transaction state |
| Postgres `SET TRANSACTION READ ONLY` inside an outer transaction outlives a released savepoint | The support log write after a look (and the rest of the request) would fail | The read-only block always rolls back, undoing READ ONLY and the GUCs |
| Local venv lacked `prometheus-client` (declared in requirements) | Two metrics tests failed locally only | Installed the declared version |

### Where Phase 2 differs from the plan

- **ID4** staff read through an admin viewer of eight sections rather than replaying the customer's own API as them; it needs no change to `get_company_user` and cannot reach a write path. `tests/test_no_impersonation.py` stays as is (there is still no act-as route); "no access without a live grant" is proved by the ID4 tests.
- **ID5** uses PyJWT (already installed with SimpleJWT) instead of adding `google-auth`.
- **GR1b** column names follow each tool's documented standard export; they are confirmed against real pilot files before a source is granted (people item below), and a mismatched file is refused, never guessed.
- **BL4** "offer UPI Autopay next to card" is Razorpay's hosted checkout (both methods shown when UPI Autopay is enabled on the account); Bizboard records the method the customer chose.
- **SC3** SBOMs are kept as workflow artifacts on every CI run and every CD release run (there is no GitHub Release step to attach them to).

### What is left (people only)

- Founder / ops: Turnstile keys; email provider + webhook credentials; DLT template ids; staffed
  support channel and SLAs; Google OAuth client ids (staging, prod); UPI Autopay enabled on the
  Razorpay account; two people who can deploy, roll back and be on call; grant `ENABLE_TALLY` /
  `ENABLE_LEGACY_IMPORT` per pilot.
- CA: TDS sections and the credit mechanism (BL1); SaaS invoice format and SAC (BL2); Bizboard's
  own books (X-01).
- Counsel: disclosure safe harbour (SC1), CERT-In scope (CP1), breach and request wording (CP2),
  fingerprint retention (AB3), support-access consent wording (ID4).
- Sandbox / hosted runs: Razorpay sandbox for upgrade, downgrade, UPI re-mandate and renewal
  (BL3, BL4); `load/month_end.js` on hosted staging (RS1; needs k6, not installed here).
- Pilot files: 2–3 anonymised Busy / Vyapar / Marg exports to confirm the column maps (GR1b) and
  Tally exports for GR1a.
- Hindi review of every new string: [`docs/SAAS_HINDI_REVIEW.csv`](../SAAS_HINDI_REVIEW.csv).

---

## 10. Deep review and fixes (2026-10-23)

A twelve-way review of the three Phase 1 + 2 commits (billing ×2, accounts ×2, support/ops, core,
integrations, web ×2, CI/deploy, tests, cleanup) found about 130 candidate issues. Every one was
checked against the code; the real ones are fixed in this pass and each fix has a test unless it
is CI or deploy configuration.

| Area | What was wrong | Fix |
|---|---|---|
| RLS (all staff admin) | `rls_bypass()` did not nest: an inner block switched the bypass off for the outer one; the TDS-claim and ownership admins wrapped only a lazy queryset, so on Postgres their lists were empty and staff could never verify a claim or approve a recovery | `rls_bypass` is a no-op inside an enclosing bypass; shared `core.admin.RlsBypassAdminMixin` renders list and change pages inside it (Postgres test) |
| BL1 TDS money | Concurrent refund requests (or verify + refund) refunded every invoice twice; credit refunds ran inside one transaction that rolled back the record of a refund already made, so the daily task refunded it again; switching to refund stranded a claim that could not be refunded | One short locked transaction per invoice / per claim, Razorpay idempotency key per (claim, invoice), refundability checked before switching (back to credit if nothing went out), verify/reject lock and re-read |
| BL2 GST | Nightly recon would invoice every historical Razorpay charge, dated today; one failure stopped the sweep; intra-state chosen by raw state strings; CGST and SGST a paisa apart | Charges only within 35 days and after `PLATFORM_GST_INVOICES_FROM`, `amount_paid` only, per-charge parking, one query for existing ids; `is_intra_state` on GST state codes, equal halves |
| BL3 plan change | The old subscription's renewal promoted a pending plan; repeating the upgrade re-charged and extended the free grace forever; a paid overlay never expired; trial "upgrades" got paid plans free; old and new subscriptions both charged at the renewal; seat limit ignored the upgrade; paid superseded links were dropped | Promote only on the new subscription's activation; one upgrade at a time (same plan returns the stored links, the old plan undoes an unpaid upgrade); a paid upgrade lasts to its period end + grace; upgrades need an ACTIVE paid period; the old subscription is set to end at cycle end once the new mandate is approved; `effective_plan` for invites and seat counts; unmatched paid links invoiced and parked; link status checked before reverting; checkout single-flight |
| BL4 autopay | Unknown events were applied then parked; the pending mandate overwrote the live one's state; reminder quoted the old plan and one SMTP error lost the day's cohort | Classify before applying (`subscription.updated` handled); mandate state from the live subscription only; reminder catches up, uses the plan that will be charged, per-subscription errors |
| ID3 sessions | `/auth/switch-company/` minted a fresh 14-day session from an access token, undoing "sign out this device"; revoked devices counted as known; logout/reset left rows; mapped IPv4 collapsed to `::/48`; the new-device email blocked sign-in on SMTP | A live, non-blacklisted refresh token is required; revoke/refresh race closed; logout, password reset and last-membership removal close rows; `core.netutil.ip_prefix`; email sent by a worker after commit; a Security page every user can open |
| ID1 ownership | An offer stayed valid after its owner was demoted or removed; accept failed on Postgres for multi-company members; 500s on bad input; recovery to an existing member switched their access off | Re-check the offering owner inside the lock; look up by token under the bypass, act under `company_scope`; clear errors; promote in place; recovery expiry enforced; runbook covers the lost-phone MFA reset; owners can see and cancel a pending transfer or recovery |
| ID5 Google | Any Google account with a matching email opened an existing account, even where Google is not the mail provider; sign-up skipped state, choice and phone checks; JWKS keys cached forever with a 30 s fetch | Link only Gmail or a Workspace `hd` matching the domain; the password sign-up's serializer rules; `cache_keys=False`, 5 s timeout, any verification error is a 401; MFA waiver audited as for passwords |
| ID4 support | Closing the request did not end access; a deleted named staff member widened the grant to all staff; bad `hours` became 72; SQLite dev viewer always errored; the ticket admin crashed on every save; PROTECT blocked company deletion; logs deletable | Resolve revokes at once and closed tickets never pass `usable_grant`; PROTECT on the named staff user; bad hours refused; PRAGMA set inside the transaction; `save_formset` fixed; CASCADE; no delete |
| DL1 export | A dead build stayed PENDING forever and blocked new exports; the whole ZIP (and base64 file blobs) built in memory; plaintext ZIPs outlived company erasure; list polling used the shared 10/min sensitive budget | Stale PENDING failed and ignored; streamed to a temp file, no file blobs in CSV; erasure and sandbox teardown delete the ZIPs; throttle only on POST; poll every 15 s; expired links shown as expired |
| GR1a/GR1b imports | Tally XML took the CGST rate (half), dropped parties under sub-groups, ignored the bill count in the row cap; legacy balances mis-parsed (signs, "Cr" suffix, "Rs."), advances silently dropped while recon expected them, payable ledgers became suppliers, positional item codes collided across files, GST cells concatenated digits | Integrated/Central+State rate from the latest GST details; group ancestry; bills counted; strict balance parser with Dr/Cr from column, suffix or sign; advances listed as notes and excluded from expected totals; party groups only; stable codes from names; one-rate GST validation; row numbers from the file; extra CSV cells and old .xls refused clearly |
| Core | Bounce webhook credentials were never defined in settings (every call refused); a bad body 500'd on Postgres; out-of-office replies suppressed addresses; a late soft bounce lifted a suppression; non-ASCII credentials 500'd; public-link spread and Turnstile used the proxy's address; dunning shared the OTP SMS budget; phones normalised three ways | Settings added; DLQ write under the bypass; Postmark type map; locked soft-bounce update; byte compares; `core.netutil.client_ip`; Turnstile hostname check; OTP and bulk texts have separate series budgets and bulk keeps 10% of the platform cap free; one `normalize_e164`; unknown `BOT_CHECK_PROVIDER` refused at boot |
| Web | Bot-check widget reset loop; multi-company first requests without `X-Company-Id`; stale tabs kept writing after a cleared company; legacy import could not import a second file; thumbnails broke on reopen; file opens blocked as pop-ups; Google button in the app shell | Reset only after a token is used; active company stored at sign-in; listener compares with the shown company; mutations reset; data-URL thumbnails; tab opened in the click; native shell hides it; PDF/download errors shown |
| CI / deploy | Turnstile site key and Google client id never reached the built web bundle (production would refuse every sign-up, OTP and reset); the supply-chain job lacked PyYAML; the backend SBOM listed no packages; the docker scan ignored the allow-list; the merge-size label needed a new push; guards missed aliases and private senders; month-end k6 script could not sign in on staging | Build args in the Dockerfile, CD (repository variables) and compose; tools installed; SBOM from a resolved environment (`cyclonedx-py`); `trivyignores` on both scans; labels read at run time; AST guards; cookie sessions paced under the login limit, arrivals spread over the window, CSP `frame-src 'self' blob:`, `noindex` on share links |

Tests that could not fail were made real: the OTP no-enumeration check, the SMS refusal rollback,
the import reconciliation checks (they read keys that never existed) and the readable-export column
snapshot (it pinned 2 of 12 sections; all 12 are now seeded and pinned).

New migrations: `billing/0019_plan_change_links`, `billing/0020_relax_protect_fks`,
`support/0008_relax_protect_fks`, `accounts/0075_relax_protect_fks`. New settings:
`EMAIL_WEBHOOK_USER`, `EMAIL_WEBHOOK_PASSWORD`, `PLATFORM_GST_INVOICES_FROM`,
`TURNSTILE_ALLOWED_HOSTNAMES`; build-time `VITE_TURNSTILE_SITE_KEY`, `VITE_GOOGLE_CLIENT_ID`
(CD repository variables).

Left on purpose (judgement, not bugs): the three owner-capability definitions are not merged
(no behaviour difference for an OWNER, whose role bypasses the flags); `NotificationService` still
has a fixed category (the two callers that need another one call `core.mail.send` directly and now
catch their errors); TDS credit and refund amounts stay in JSON lists on the claim (fixed for
races; a settlement table would be a larger change).
