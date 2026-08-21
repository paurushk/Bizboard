> **Historical (2026-07-24).** Superseded for decision-making by `docs/reviews/` (2026-08-02 Scope C audit). Do not treat Criticals here as current without re-verification.

# BizBoard Production Readiness — TEST REPORT

> **Stale-numbers notice (BUG-729):** a follow-up pass on 2026-07-25 found
> the test counts/timings below no longer match reality (actual: 149
> backend tests, ~30 frontend tests as of that pass, both smaller/faster
> suites than claimed here). Rather than re-editing this snapshot every
> time the suite changes, treat `bugs/INDEX.md` and a fresh
> `cd backend && pytest` / `cd web && npm test -- --run` as the
> authoritative current numbers — this file is a point-in-time snapshot, not
> a live source of truth.

**Date:** 2026-07-24  
**Environment:** Docker stack (`localhost`) — Postgres 17, Redis, API, Celery worker, Nginx, Web  
**Roles exercised:** Demo OWNER (`demo@bizboard.local`)  
**Auditor personas:** Senior QA, Product, CA (GST), Security, UX, End User  

---

## Executive Summary

BizBoard is a **credible MVP** for Indian SMB GST billing: multi-tenant isolation works, document status machines are tested, inventory is append-only, ledgers are derived from documents, and automated backend coverage is strong (**120/120 pytest passed**).

It is **not production-ready for mass commercial deployment**. Critical calculation parity gaps (frontend preview vs backend persisted GST), incomplete GST compliance surface (no GSTR / credit notes / reverse charge / tax-inclusive), coarse permissions, stubbed SMS/email/WhatsApp, and weak file-upload hardening remain blockers for “10,000 paying businesses.”

**Verdict:** Fit for a **controlled paid pilot (20–50 businesses)** after Critical/High fixes and **CA sign-off** on invoice PDF + GST math. Not fit for broad launch today.

---

## Coverage

| Area | Coverage | Notes |
|------|----------|-------|
| Automated backend tests | **High** | 120 passed — tax, status, stock, ledger, payments, tenant, PDF, imports |
| Automated frontend unit tests | **Medium** | 26 passed — tax/money/permissions/PDF poller; not full page coverage |
| E2E Playwright smoke | **Low** | Route/smoke only; not full semantic workflows |
| Live UI walkthrough | **Medium** | Dashboard, New Invoice, New Purchase, Products, nav structure |
| Live API probes | **High** | Auth, tax edge, discount, OTP envelope, tenant isolation, latency |
| Manual every-control matrix (all screens × all states) | **Partial** | Not exhaustively clicked; risk residual on secondary screens |
| Load / 10k invoices | **Not run** | Scalability inferred from code (dashboard O(n) receivables) |
| Multi-browser / zoom / dark mode | **Not run** | MUI light theme; no dark mode observed |
| Full permission matrix (all staff flag combos) | **Partial** | Code + route gates reviewed; live staff UAT incomplete |

**Estimated semantic coverage of MVP in-scope flows:** **~68%**  
**Estimated coverage of CA-grade GST/accounting expectations:** **~35%** (many features Phase 2 by design)

---

## Pass / Fail Snapshot

| Suite | Result |
|-------|--------|
| Backend `pytest` | **120 passed** |
| Frontend Vitest | **26 passed** |
| Live health `/api/v1/health/` | **Pass** |
| Unauthenticated invoice list | **401 Pass** |
| Cross-tenant invoice read | **404 Pass** (scoped queryset) |
| Weak password rejected | **Pass** |
| FE↔BE CGST residual parity | **FAIL** |
| API error envelope on manual 400 | **FAIL** (`success: true`) |
| Invoice discount vs taxable base clarity | **FAIL** (post-tax discount) |
| OTP / SMS production readiness | **FAIL** (stub + DEBUG echo) |
| File upload hardening | **FAIL** |
| GSTR / Credit Note / Reverse charge | **N/A / Missing** (Phase 2) |

**Passed (automated + core probes):** ~150  
**Failed / blocked findings:** 28 catalogued (see `BUG_REPORT.md`)  
**Critical:** 4 · **High:** 9 · **Medium:** 10 · **Low/Cosmetic:** 5  

---

## Screens Tested

| Screen | Path | Status | Notes |
|--------|------|--------|-------|
| Login | `/login` | Partial | Redirected when session present |
| Dashboard | `/` | Pass w/ notes | KPIs render; empty-state OK |
| New Sales Invoice | `/sales/new` | Pass w/ Critical calc risk | Rich form; Save disabled until valid; shortcuts present |
| Sales History | `/sales/history` | Visited | List/nav OK |
| New Purchase | `/purchases/new` | Pass w/ notes | Parity with sales form; Upload Bill link |
| Products | `/inventory/products` | Pass | Table, Edit, Bulk Actions, GST% |
| Customer Ledger | `/reports/customer-ledger` | Visited | Route resolves |
| Remaining 25 pages | various | Code/route audited | Not every control exercised live |

---

## Module Scores (out of 10)

| Module | Score | Rationale |
|--------|------:|-----------|
| Authentication & session | 6.5 | JWT + blacklist logout; tokens in localStorage; OTP stub |
| Sales invoicing | 7.0 | Strong workflow; FE preview can disagree with BE by ₹0.01+ |
| Purchases | 7.0 | Feature parity; bill LLM import depends on provider keys |
| Inventory | 8.0 | Append-only movements; complete/cancel stock rules tested |
| Payments & allocations | 7.5 | Caps/party match tested; advances unlabeled in UX |
| Derived ledgers | 7.0 | Correct architecture; aging/advance UX thin |
| Reports / dashboard | 5.5 | Useful basics; no GSTR/HSN/aging/P&L; O(n) receivables |
| GST compliance | 4.0 | Intra/IGST/NON_GST OK; missing CA-critical filings & notes |
| Accounting depth | 3.5 | Intentionally MVP; no TB/P&L/BS/journals |
| PDF / share | 7.0 | Async PDF + regenerate; WhatsApp is link-only |
| Imports / exports | 6.5 | CSV + bill upload; LLM/config dependent |
| Permissions / RBAC | 5.5 | Only OWNER vs STAFF + 2 flags; staff can run finance |
| Security hardening | 5.5 | Tenant isolation good; upload/rate-limit/OTP gaps |
| UX / accessibility | 7.0 | Clear billing UX; some labels confusing; a11y partial |
| Performance / scale | 6.0 | Fast on demo data; unproven at 10k invoices |
| **Overall production readiness** | **5.8** | Pilot-capable after Critical/High remediation |

---

## Business Logic Issues (summary)

1. Frontend CGST/SGST equal-half split ≠ backend residual split → preview/saved mismatch.  
2. Document-level `invoice_discount` reduces grand total **after** tax — does not reduce taxable value / output tax.  
3. Missing party state defaults to **intra-state** — can misclassify IGST.  
4. Sales staff can create/cancel invoices, payments, and view all financial reports.  
5. No credit/debit notes — returns only; CA workflows incomplete.  
6. Purchase outstanding ignores `RETURNED` status while sales includes it — inconsistency risk.

---

## Calculation Issues (summary)

See `CALCULATION_VALIDATION.md`. Key live probe:

| Case | Backend | Frontend sim |
|------|---------|--------------|
| ₹10.05 @ 18% intra | CGST **0.90** + SGST **0.91** = 1.81; line 11.86; grand 12.00 | CGST **0.91** + SGST **0.91** = **1.82** |

---

## Accounting / GST / UX / Security / Performance

Detailed in companion reports:

- `BUG_REPORT.md`
- `CALCULATION_VALIDATION.md`
- `ACCOUNTING_VALIDATION.md`
- `SECURITY_REPORT.md`
- `UX_REVIEW.md`
- `PERFORMANCE_REPORT.md`
- `PRODUCTION_READINESS.md`

---

## Improvement Suggestions (top)

1. **Single source of truth for tax** — call BE preview endpoint or port residual split + Decimal rules to FE.  
2. **CA pack** — HSN summary, GSTR-1 export, credit/debit notes, place of supply, tax-inclusive toggle.  
3. **Clarify invoice discount** — “cash/commercial discount (after tax)” vs “taxable discount (before tax).”  
4. **RBAC** — Accountant / Manager / Viewer; separate “view financials” / “cancel documents.”  
5. **Harden uploads** — MIME allowlist, size limits, malware scan path.  
6. **Production notifications** — real SMS/SMTP/WhatsApp; disable OTP echo.  
7. **Aging & advances** — receivables aging buckets; label unallocated receipts as advances.  
8. **Expand E2E** — full purchase→sale→partial pay→return→cancel golden path.

---

## Production Readiness Score

**5.8 / 10**

| Question | Answer |
|----------|--------|
| Deploy to 20–50 pilot SMBs after Critical fixes + CA sign-off? | **Conditional Yes** |
| Deploy to **10,000 paying businesses today**? | **No** |

### Would you confidently deploy BizBoard to 10,000 paying businesses today?

**No.**

**Justification:** The product has solid architectural bones (tenant scoping, document-as-truth ledgers, append-only stock, strong pytest suite). However, a mass-market GST billing product cannot ship with (a) UI totals that can disagree with stored tax by paise, (b) post-tax discounts that can mislead GST liability understanding, (c) stubbed OTP/SMS and console email, (d) coarse RBAC where every staff user is effectively a full cashier-accountant, (e) no GSTR/credit-note/e-invoice path that Indian GST-registered traders eventually need, and (f) unproven performance of dashboard receivables aggregation and large registers. README and MVP plan correctly require **CA approval before production pilot**; that gate is not yet passed for scale.

Ship a **paid pilot** with monitoring, CA-reviewed invoice PDF, and Critical/High fixes first. Re-score after those close.
