> **Historical (2026-07-24).** Superseded for decision-making by `docs/reviews/` (2026-08-02 Scope C audit). Do not treat Criticals here as current without re-verification.

# BizBoard — BUG REPORT

**Date:** 2026-07-24  
**Source:** Automated tests + live API/UI audit + code review  

Severity key: **Critical** (money/GST wrong or security breach) · **High** (data integrity / major workflow) · **Medium** · **Low** · **Cosmetic**

---

## Critical

### BUG-001 — Frontend vs backend CGST/SGST split mismatch
- **Category:** Calculation / Business Logic  
- **Evidence:** Live API `POST /sales/invoices/` for qty 1 × ₹10.05 @ 18% → CGST `0.90`, SGST `0.91` (sum `1.81`). FE `calculateLineTax` uses equal halves → `0.91`+`0.91`=`1.82`.  
- **Code:** `backend/core/services/billing.py` (residual on SGST); `web/src/utils/tax.ts` (equal halves; outdated comment).  
- **Impact:** Invoice **preview can disagree with saved/PDF totals** by ₹0.01+ per line; trust and GST filing risk.  
- **Fix:** Align FE to BE residual algorithm (or server-side preview). Add parity tests for odd paise.

### BUG-002 — Manual HTTP 400 responses wrapped as `success: true`
- **Category:** API / UX  
- **Evidence:** `POST /auth/otp/request/` with `{}` → HTTP 400 body `{"success": true, "data": {"detail": "phone is required"}}`.  
- **Code:** Views return `Response(..., status=400)` without raising; `EnvelopeJSONRenderer` only skips wrap when `response.exception`.  
- **Impact:** Clients treating `success` flag as truth will mis-handle errors (OTP, possibly other views).  
- **Fix:** Raise ValidationError / use exception handler; or wrap non-2xx as `success: false` in renderer.

### BUG-003 — Document-level discount applied after tax without clear GST semantics
- **Category:** GST / Business Logic / Calculation  
- **Evidence:** Invoice ₹100 @ 18% + `invoiceDiscount=10` → taxable `100`, CGST/SGST `9`+`9`, grand `108`. Tax unchanged.  
- **Code:** `billing.py` `raw_total = taxable + tax + charges - inv_discount`. UI label “+ Discount”.  
- **Impact:** Shop owners may believe GST reduced; **output tax overstated** vs commercial intent; GSTR mismatch risk.  
- **Fix:** Offer before-tax vs after-tax discount modes; relabel UI; document CA policy.

### BUG-004 — Production defaults favor DEBUG / insecure secrets if misconfigured
- **Category:** Security  
- **Evidence:** `DJANGO_DEBUG` defaults `"1"`; hardcoded insecure `SECRET_KEY` fallback; `OTP_DEBUG_ECHO = DEBUG`.  
- **Code:** `backend/config/settings.py`.  
- **Impact:** Accidental prod deploy leaks OTP codes, stack traces, weak crypto.  
- **Fix:** Fail-fast if `DEBUG` or default secret in non-dev; require env in compose prod profile.

---

## High

### BUG-005 — Generic file upload has no MIME/size validation
- **Category:** Security  
- **Evidence:** `FileService.store_upload` stores whatever is uploaded; only nginx `client_max_body_size 20m`. Bill import has MIME checks; `/files/` does not.  
- **Impact:** Malware hosting, disk abuse, XSS via served content if content-type wrong.  
- **Fix:** Allowlist, max size, content sniffing, authenticated download only.

### BUG-006 — JWT access/refresh stored in `localStorage`
- **Category:** Security  
- **Evidence:** `web/src/auth/session.ts`.  
- **Impact:** Any XSS steals session for up to refresh lifetime (7d).  
- **Fix:** Prefer httpOnly secure cookies + CSRF; or strict CSP + XSS hardening.

### BUG-007 — OTP SMS provider stubbed; DEBUG echoes code
- **Category:** Security / Product  
- **Evidence:** `RequestOtpView` docstring; `debug_code` when `OTP_DEBUG_ECHO`.  
- **Impact:** Cannot ship phone login to production; code leakage if DEBUG left on.  

### BUG-008 — Email / WhatsApp notifications not production-ready
- **Category:** Product / UX  
- **Evidence:** Console email backend unless SMTP; WhatsApp share is link (MVP plan).  
- **Impact:** “Share invoice” promises incomplete for paying customers.

### BUG-009 — RBAC too coarse for multi-user shops
- **Category:** Permissions / Business Logic  
- **Evidence:** Roles = OWNER | SALES_STAFF; staff can invoice, pay, cancel, see ledgers/reports unless separate flags. No Viewer/Accountant.  
- **Impact:** Accidental deletes/cancels; financial data exposure to cashiers.

### BUG-010 — Missing party state defaults to intra-state GST
- **Category:** GST  
- **Evidence:** `is_intra_state` / FE `isIntraState` return true when party state blank.  
- **Impact:** Interstate sale billed as CGST+SGST → **wrong tax type** for GST returns.

### BUG-011 — No credit/debit notes (Phase 2)
- **Category:** Accounting / GST  
- **Impact:** Common post-invoice corrections forced through returns or edits; CA rejection for many traders.

### BUG-012 — Role denial silently redirects to dashboard
- **Category:** UX / Permissions  
- **Evidence:** `App.tsx` `RoleRoute` → `<Navigate to="/" />` with no message.  
- **Impact:** Staff think feature is broken.

### BUG-013 — Dashboard receivables loops all customers
- **Category:** Performance  
- **Evidence:** `ReportService.dashboard` sums `customer_outstanding` per customer.  
- **Impact:** Degrades as party master grows (thousands of customers).

---

## Medium

### BUG-014 — FE `tax.ts` comment contradicts backend behavior
- Claims both halves use `q2(tax/2)` leaving 0.01 unallocated; BE uses residual on SGST.

### BUG-015 — FE `roundMoney` uses binary float + EPSILON; BE uses Decimal ROUND_HALF_UP
- Edge-case divergence beyond half-split.

### BUG-016 — FE `isIntraState` prefers GSTIN state codes; BE compares state name strings
- Possible intra/inter mismatch when one side has GSTIN and other has name only.

### BUG-017 — Purchase outstanding excludes RETURNED; sales includes RETURNED
- Ledger inconsistency across modules (`ledgers/services.py`).

### BUG-018 — Unallocated receipts credit customer ledger with no “Advance” label
- Accounting clarity issue for owners.

### BUG-019 — OpenAPI `/api/v1/docs/` returned 500 in live probe
- Developer/support friction; confirm Spectacular config behind auth in prod.

### BUG-020 — Invoice number fields editable in UI before complete
- Risk of user confusion vs server-assigned series on Complete.

### BUG-021 — No API rate limiting / throttling observed
- Brute-force login/OTP risk (OTP has attempt cap per challenge only).

### BUG-022 — Media served via nginx with limited security headers
- Only `nosniff` on `/media/`; no CSP/HSTS at edge (HTTP listen 80).

### BUG-023 — E2E coverage thin vs product surface
- Smoke tests only; regression risk on billing parity screens.

---

## Low / Cosmetic

### BUG-024 — UI label “+ Discount” with “- ₹” adornment
- Confusing sign semantics on invoice totals panel.

### BUG-025 — Icon-only buttons without visible text (toolbar)
- Some rely on aria-label only; verify all have names.

### BUG-026 — Customer autocomplete showed only Walk-in in empty query
- May need type-to-search affordance clearer for multi-customer demos.

### BUG-027 — Terms default mentions Bengaluru jurisdiction
- Hard-coded geography may confuse non-KA companies.

### BUG-028 — Cross-tenant access returns 404 not 403
- Acceptable pattern; document as intentional.

---

## Passed / Non-bugs (keep)

- Unauthenticated API → 401.  
- Cross-tenant invoice → not readable.  
- Weak passwords rejected by Django validators.  
- Status machines, stock append-only, payment allocation caps covered by tests.  
- Save actions disabled until invoice has required party/lines (good guardrail).

---

## Counts

| Severity | Count |
|----------|------:|
| Critical | 4 |
| High | 9 |
| Medium | 10 |
| Low/Cosmetic | 5 |
| **Total** | **28** |
