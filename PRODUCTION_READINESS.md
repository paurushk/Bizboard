# BizBoard — PRODUCTION READINESS

**Date:** 2026-07-24  
**Decision framework:** Can we take money from thousands of Indian SMBs without causing GST/accounting harm?

---

## Recommendation

| Audience | Deploy? |
|----------|---------|
| Internal dogfood | **Yes** |
| Paid pilot 20–50 (with CA + monitoring) | **Yes, after Critical fixes** |
| General availability / 10,000 businesses | **No — not today** |

**Overall score: 5.8 / 10**

---

## Would you confidently deploy BizBoard to 10,000 paying businesses today?

### **No.**

### Justification

1. **Money must be identical on screen, in DB, and on PDF.** Live probes prove FE CGST/SGST preview can diverge from backend by paise on ordinary amounts (₹10.05 @ 18%). At 10k tenants that becomes systematic disputes and CA rejection.  
2. **GST semantics are incomplete for unsupervised compliance.** No credit/debit notes, GSTR extracts, reverse charge, tax-inclusive mode, or explicit place-of-supply. Document discount after tax can mislead taxable value. MVP plan admits this; mass market will not read the plan.  
3. **Operational services are stubs.** OTP SMS echoed in DEBUG, console email, WhatsApp-as-link — not SaaS-grade communication.  
4. **Security baseline insufficient for public multi-tenant SaaS at scale.** localStorage JWT, unvalidated uploads, no rate limits, HTTP edge, DEBUG-friendly defaults.  
5. **RBAC is binary.** Cashiers effectively get accountant powers; silent redirect on denied routes.  
6. **Scale unproven.** Dashboard receivables are O(customers); no 10k-invoice load evidence.  
7. **Own docs require CA sign-off before pilot** (`README.md`, `MVP_IMPLEMENTATION_PLAN.md`). That gate is still open.

The codebase **is** a strong foundation: tenant isolation works, 120 backend tests pass, inventory/ledger design is accountant-aware for a billing MVP. That supports a **controlled pilot**, not a 10k blast radius.

---

## Go / No-Go checklist

### Must-fix before any paid pilot (P0)

<!-- BUG-729/731: this checklist had drifted from reality in both directions
     — some items were already done and still shown unchecked, others were
     checked as done in the old TEST_REPORT.md/PERFORMANCE_REPORT.md while a
     regression sat unfixed. `bugs/INDEX.md` is now the authoritative,
     re-verified source; this list is updated to match it as of the pass
     that closed most of these out. -->
- [x] Align FE tax math with BE residual split + add parity tests (verified matching via cross-language reproduction; `roundMoney` further hardened against float-representation edge cases)
- [x] Fix API error envelope (`success: false` on all non-2xx)
- [x] Label / split before-tax vs after-tax discounts (Sales was already done; Purchases UI now matches)
- [x] Force `DEBUG=0`, strong secrets, disable OTP echo in prod compose (placeholder-secret denylist added; see `bugs/01-backend-core-auth-config.md` BUG-101 for the one residual, documented gap that can't be closed without either an explicit `DJANGO_ENV` in every deploy target or changing the zero-config local-dev default)
- [ ] CA review & sign-off of Tax Invoice PDF + sample GST scenarios
- [ ] SMTP (or provider) for invoice email; document WhatsApp limitation
- [x] File upload allowlist + size limits (already implemented in `FileService.validate_upload`)
- [x] Auth rate limiting (already implemented; OTP verify's own throttle scope added)
- [ ] TLS termination + basic security headers (headers present at nginx; TLS termination is an infra/ops task for the upstream load balancer)

### Should-fix before expanding pilot (P1)

- [x] Access-denied UX (`ForbiddenPage` now used consistently instead of silent redirects)
- [x] Receivables aging (dashboard now renders the aging buckets the backend already computed)
- [x] Dashboard outstanding SQL aggregation (customer/supplier ledger list views and receivables aging now use bulk aggregation instead of N+1 loops)
- [x] Staff permission matrix UAT (cancel / export / financials) — `canCancelDocuments`/`canExport` are now actually enforced in the UI, not just defined
- [ ] Expand Playwright golden-path E2E (still the single biggest test-coverage gap — see `bugs/07-tests-ci-infra-migrations.md` BUG-725)
- [x] Warn when party state missing (don't silently assume intra) — Purchases now has the same `posKnown` gate Sales already had

### Before claiming GA / 10k (P2)

- [ ] Credit/Debit notes  
- [ ] GSTR-1/3B export aids  
- [ ] Hardened session storage / CSP  
- [ ] Load test + capacity plan  
- [ ] Broader roles (Accountant, Viewer)  
- [ ] External pen-test  
- [ ] Support/runbooks, backups, RPO/RTO drills  

---

## Module scores (repeat)

| Module | /10 |
|--------|----:|
| Auth | 6.5 |
| Sales | 7.0 |
| Purchases | 7.0 |
| Inventory | 8.0 |
| Payments | 7.5 |
| Ledgers | 7.0 |
| Reports | 5.5 |
| GST compliance | 4.0 |
| Accounting depth | 3.5 |
| PDF/Share | 7.0 |
| Imports | 6.5 |
| RBAC | 5.5 |
| Security | 5.5 |
| UX | 7.0 |
| Performance | 6.0 |
| **Overall** | **5.8** |

---

## Residual risk statement

Even after P0, BizBoard remains a **billing + inventory + derived ledger** product, not a full books or GST-return product. Marketing and sales must not claim Tally/Vyapar feature parity on GSTR, e-invoice, or accounting statements until those land.

---

## Suggested pilot success criteria

1. ≥5 real businesses complete weekly purchase→sale→pay→return cycles with zero total mismatches.  
2. Zero Critical defects open for 14 days.  
3. CA sign-off letter on PDF + tax samples.  
4. PDF success rate ≥99%; worker alerts wired.  
5. Support playbook for cancel/return/discount questions.

---

## Artifacts in this audit pack

| File | Purpose |
|------|---------|
| `TEST_REPORT.md` | Executive summary & coverage |
| `BUG_REPORT.md` | Defect catalog |
| `CALCULATION_VALIDATION.md` | GST/tax/totals |
| `ACCOUNTING_VALIDATION.md` | CA lens |
| `SECURITY_REPORT.md` | Security |
| `UX_REVIEW.md` | Usability |
| `PERFORMANCE_REPORT.md` | Latency/scale |
| `PRODUCTION_READINESS.md` | This decision record |
