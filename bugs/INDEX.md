# Bizboard — Bugs Repository (Full Codebase Review)

**Date:** 2026-07-25
**Method:** Independent, line-by-line re-review of the entire codebase (backend Django/DRF + frontend React/TS), split across 7 parallel deep-dive passes, each of which re-verified every claim in the prior day's `BUG_REPORT.md` / `SECURITY_REPORT.md` / `PERFORMANCE_REPORT.md` / `UX_REVIEW.md` against the actual current code (not assumed), then hunted independently for anything else: bugs, gaps, broken flows, UI/feature/performance issues, and missing automated test coverage. Several claims were reproduced with live API calls, executed reproduction scripts (Python/Decimal and Node cross-checks of the tax engine), and actual test-suite/build runs — not just static reading.

This supersedes and absorbs the prior single-pass reports at the repo root; those are kept for historical reference but several of their claims are now marked fixed or inaccurate below, with evidence.

## How this is organized

Each area file contains full bug entries (severity, category, location, description, evidence, impact, remediation, suggested test, and status vs. the prior report). IDs are namespaced by area (100s, 200s, ... 700s) so they never collide.

| # | Area | File | Scope |
|---|------|------|-------|
| 01 | Backend core, auth, tenancy, config | [01-backend-core-auth-config.md](01-backend-core-auth-config.md) | accounts, config, core (permissions/viewsets/renderers/services) |
| 02 | Backend sales & purchases (GST money engine) | [02-backend-sales-purchases.md](02-backend-sales-purchases.md) | billing.py, sales/, purchases/, PDF generation |
| 03 | Backend inventory, payments, ledgers, reports, imports | [03-backend-inventory-payments-reporting.md](03-backend-inventory-payments-reporting.md) | inventory/, payments/, ledgers/, masters/, reporting/, search/, imports/ |
| 04 | Frontend core (API client, auth, utils, shared components) | [04-frontend-core-utils-auth.md](04-frontend-core-utils-auth.md) | api/, auth/, utils/, components/, hooks/, App.tsx |
| 05 | Frontend sales & purchases pages | [05-frontend-sales-purchases-pages.md](05-frontend-sales-purchases-pages.md) | New Invoice/Purchase, Returns, Receipts, Payments, Quotations |
| 06 | Frontend inventory, reports, settings, dashboard, auth pages | [06-frontend-inventory-reports-settings-pages.md](06-frontend-inventory-reports-settings-pages.md) | Products, Stock, Reports, Settings, Dashboard, Login/Register |
| 07 | Tests, CI, infra, migrations, docs-vs-reality | [07-tests-ci-infra-migrations.md](07-tests-ci-infra-migrations.md) | pytest/vitest/e2e suites, CI, Docker/nginx, migrations |

---

## Severity counts (live findings — excludes entries that only verify a prior claim as already-fixed or inaccurate)

| Severity | 01 | 02 | 03 | 04 | 05 | 06 | 07 | **Total** |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Critical | 3 | 1 | 0 | 0 | 7 | 0 | 2 | **13** |
| High | 3 | 9 | 5 | 3 | 8 | 13 | 5 | **46** |
| Medium | 13 | 8 | 13 | 10 | 16 | 18 | 16 | **94** |
| Low | 6 | 2 | 4 | 10 | 6 | 3 | 11 | **42** |
| Cosmetic | 1 | 1 | 0 | 2 | 0 | 2 | 1 | **7** |
| **Area total** | **26** | **21** | **22** | **25** | **37** | **36** | **35** | **202** |

Plus **15 entries** across all areas that re-verified a specific prior-report claim and found it either **already fixed** or **inaccurate as originally stated** (each documented with evidence in its area file) — these are not counted above since they're not live bugs, but they matter: several of the "Critical" items in the original `BUG_REPORT.md` (the CGST/SGST rounding split, the invoice-number editability, the discount label on Sales) turned out to have already been fixed since that report was written, which is worth knowing before re-fixing something that's already done.

**202 live findings** (201 from the original review pass, plus BUG-224 found afterward via live Playwright E2E testing and fixed the same day), of which roughly 10–12 clusters were independently discovered by two different review passes from different angles (see "Cross-cutting themes" below) — meaning the true count of distinct root causes is closer to **~189–191**, with the overlaps serving as extra confirmation rather than double-counting the same defect.

---

## The 15 most severe items — fix these first

1. **[BUG-703](07-tests-ci-infra-migrations.md#bug-703--media-is-served-by-nginx-with-zero-authentication-and-pdf-filenames-are-fully-predictablenumerable)** — `/media/` is served by nginx with **zero authentication** and fully predictable, sequential file paths. Anyone can download any tenant's GST invoice PDFs (customer names, GSTINs, amounts) by guessing URLs, completely bypassing the API's otherwise-correct tenant isolation. **Likely the single most severe finding in the whole review.**
2. **[BUG-109 / BUG-701](01-backend-core-auth-config.md#bug-109--companyuserviewset-allows-attaching-an-existing-unconsenting-user-to-your-company)** — Any company Owner can silently attach an existing, unconsenting user (from any other tenant) to their own company at any role, including OWNER — a genuine cross-tenant boundary violation. Independently rediscovered by two separate review passes.
3. **[BUG-108](01-backend-core-auth-config.md#bug-108--duplicate-phone-numbers-crash-otp-verification-with-a-500)** — Two active users sharing a phone number (common for families/small shops) permanently 500s OTP login for that number. Reproduced live.
4. **[BUG-102](01-backend-core-auth-config.md#bug-102--otp-sms-provider-never-sends-a-real-sms-in-any-configuration-but-reports-success)** — OTP SMS is never actually sent in any provider configuration; the API reports "OTP sent." success regardless. OTP login is non-functional out of the box.
5. **[BUG-222 / BUG-309](02-backend-sales-purchases.md#bug-222--race-condition-negative-stock-block-policy-can-be-bypassed-by-concurrent-completions)** — The negative-stock `BLOCK` policy is not race-safe: two concurrent sales completions for the same product can both pass validation and both post, overselling past zero. Independently found by two passes.
6. **[BUG-500 / BUG-501](05-frontend-sales-purchases-pages.md#bug-500--save--new-silently-discards-the-success-message-it-just-set)** — "Save & New" on both Invoice and Purchase forms silently wipes the success message *and* any payment-allocation error via a React state-batching bug — a cashier can believe a payment recorded when it actually failed.
7. **[BUG-506](05-frontend-sales-purchases-pages.md#bug-506--completedfinalized-invoices-and-purchases-remain-fully-line-item-editable-with-no-warning)** — Completed, GST-filed invoices/purchases remain fully line-item-editable with zero warning or confirmation before silently rewriting an issued document.
8. **[BUG-502](05-frontend-sales-purchases-pages.md#bug-502--purchase-number-prefixnext-number-fully-editable-and-mutates-the-shared-numbering-series)** — The Purchase form's invoice-number field is live-editable and, if touched, permanently reassigns the company's entire purchase-numbering sequence.
9. **[BUG-523](05-frontend-sales-purchases-pages.md#bug-523--quotations-limited-to-exactly-one-line-item)** — Quotations can only ever contain exactly one line item — a fundamental feature gap for any multi-product quote.
10. **[BUG-531](05-frontend-sales-purchases-pages.md#bug-531--salespurchase-returns-restricted-to-the-first-line-item-only)** — Sales/Purchase returns are hardcoded to the invoice's first line item only — there is no way to return item #2+ of a multi-item invoice.
11. **[BUG-521 / BUG-606–609](05-frontend-sales-purchases-pages.md#bug-521--systemic-customersupplierinvoice-list-fetchers-silently-drop-pagination-beyond-page-1)** — A shared `asList()` helper silently drops all pagination beyond page 1 across ~9 different list/picker call sites (customers, suppliers, products, stock, ledgers) — any shop past ~50 records loses access to data through the UI with no error shown.
12. **[BUG-208](02-backend-sales-purchases.md#bug-208--invoicepurchase-numbers-are-burned-at-draft-creation-not-at-complete)** — Invoice/purchase numbers are burned at draft creation (not at Complete as the code comments and validation docs claim), and drafts are freely deletable — producing silent, unexplained gaps in the GST-sequential numbering series.
13. **[BUG-308](03-backend-inventory-payments-reporting.md#bug-308--payment-allocation-race-condition-no-row-locking-allows-over-allocation)** — Payment allocation has the same unlocked-read race as stock (#5) — concurrent allocation requests can over-allocate a single receipt/payment past its actual amount.
14. **[BUG-704](07-tests-ci-infra-migrations.md#bug-704--shipped-placeholder-secret-key-is-long-enough-to-bypass-the-production-strong-secret-guard)** — The repo's own `.env.example` placeholder secret key is exactly long enough to satisfy the production "strong secret" fail-fast guard, meaning a pilot deploy that forgets to change it silently ships with a publicly-known JWT signing key.
15. **[BUG-101](01-backend-core-auth-config.md#bug-101--debugsecret_key-defaults-still-fail-open-not-closed)** — `DEBUG`/`SECRET_KEY`/`DJANGO_ENV` configuration fails **open**, not closed: an operator who simply forgets to set `DJANGO_DEBUG=0` gets no error and no warning, and the app boots in "production" with debug stack traces and the insecure default key.

---

## Cross-cutting themes

A few root causes surface repeatedly across areas — fixing the underlying pattern is more valuable than patching each symptom individually:

- **Unlocked read-then-write races around money and stock.** The stock-oversell race (#5) and the payment-allocation race (#13) are the same shape: an authorization decision is made from an unlocked snapshot read, and the row lock only appears later, around the write. `DocumentNumberService` shows the codebase already knows how to do this correctly with `select_for_update()` — the pattern simply wasn't applied to payments or inventory.
- **A pagination helper (`asList()`) silently drops everything past page 1.** This single frontend function is the root cause of data becoming unreachable in at least 9 different places (customers, suppliers, products, stock balances, ledger pickers) once a shop's data exceeds ~50 rows. One fix (switch these call sites to the existing, tested `listPage`/`fetchNextPage` pattern) resolves BUG-521 and BUG-606 through BUG-609 simultaneously.
- **Sales and Purchases pages are ~1,700 lines of duplicated code** (`NewInvoicePage.tsx` / `NewPurchasePage.tsx`), and fixes visibly land in one twin without being ported to the other — this is the direct root cause of BUG-502/504/508/517 (numbering, discount UI, place-of-supply gating all differ between the two forms despite the underlying business logic being identical).
- **Tenant isolation is a property of individually-tested code paths, not a structural guarantee.** The Django API layer correctly 404s cross-tenant access, but this is bypassed entirely one layer down at the static-file server (BUG-703) and undermined at the account-membership layer (BUG-109/701, BUG-110/702) — areas the existing `test_tenant_isolation.py` doesn't reach.
- **Backend features exist with no frontend to use them, and vice versa.** `receivables_aging`, `is_advance`/`unallocated` on receipts, and the `canExport`/`canCancelDocuments` permission flags are all fully implemented on one side and never read/enforced on the other — five-plus instances of this exact pattern across areas 03, 04, and 06.
- **Configuration and permission checks fail open by default**, requiring an operator to actively opt into safety (explicit `DJANGO_ENV=production`, remembering to change the example secret key, remembering to set throttle scopes on every view) rather than failing closed when something is left unset.
- **Test coverage is thinnest exactly where the money/security risk is highest.** Zero page-level tests exist for any of the 31 reviewed frontend pages; the e2e suite is 5 mock-only route-smoke tests with no real backend integration; CI runs against SQLite while production runs Postgres, so the `select_for_update()` locking this review flagged as broken would not be verified even if a concurrency test were written today.

---

## What was already fixed since the prior review (2026-07-24 reports)

Genuinely good news, confirmed with evidence rather than assumed:
- The CGST/SGST rounding-residual algorithm now matches exactly between frontend and backend (verified with cross-language reproduction scripts) — the original BUG-001 does not reproduce.
- The manual-400-as-`success:true` envelope bug is fixed; error responses now correctly wrap as `success:false` (verified live).
- A `BEFORE_TAX` invoice-discount mode was added on the backend and wired into the Sales UI (though not the Purchases UI — see BUG-203/504).
- The Sales invoice-number field is now correctly read-only in the UI and read-only in the API serializer (though the Purchases UI never got the same fix — see BUG-502).
- `RoleRoute` now renders a real `ForbiddenPage` with a message instead of silently redirecting home (though several individual settings pages still have their own, older, silent-redirect logic — see BUG-404/600).
- Granular capability flags (`can_manage_inventory`, `can_import`, `can_cancel_documents`, `can_export`) were added to the permission model — real progress on RBAC granularity, even though several are not yet enforced end-to-end (see BUG-405/406/612).
- DRF throttling is now implemented for login/OTP/register endpoints with sensible rates.

## What was found to be inaccurate in the prior reports

- The "dashboard receivables loops all customers" performance claim was misattributed — the dashboard itself uses SQL aggregation; the real per-customer N+1 lives in the ledger *list* views instead (BUG-301).
- The "purchase vs sales outstanding inconsistency" is not a calculation bug — both formulas are symmetric; the underlying difference is that `PurchaseInvoice` simply has no `RETURNED` status value (BUG-212/223).
- "Unallocated receipts have no Advance label" is fixed on the backend (the data exists and is correct) — the gap is purely that the frontend never renders it (BUG-304/527).
- The claimed "hardcoded Bengaluru jurisdiction" text does not exist in any editable frontend field — it only appears in a Django demo-seed script, and the real terms field is already fully owner-editable (BUG-603).
- "Report tables use a good PAGE_SIZE 50 default" is false for three of the report pages, which render their full result set with no pagination or virtualization at all (BUG-605).

---

## Suggested remediation order

1. **Stop the bleeding (security/data-integrity, ship this week):** BUG-703 (media auth), BUG-109/701 (unconsented tenant attach), BUG-108 (duplicate-phone 500), BUG-101/704 (secret-key fail-open), BUG-102 (OTP SMS stub).
2. **Concurrency correctness (before any real multi-user pilot):** BUG-222/309 (stock oversell race), BUG-308 (payment allocation race), BUG-712 (get Postgres into CI so these are actually verified).
3. **Money-critical UX (before trusting the counter-billing flow):** BUG-500/501 (silent message wipe), BUG-506 (unrestricted completed-invoice edits), BUG-502 (purchase numbering mutation), BUG-208 (draft numbering gaps).
4. **Feature completeness gaps that block real usage:** BUG-523 (quotations, one line only), BUG-531 (returns, first line only), BUG-521/606-609 (pagination cliff past ~50 records).
5. **Everything else**, roughly in the severity order within each area file, with the duplicated Sales/Purchases page logic (BUG-518) as a high-leverage refactor that prevents future re-occurrence of an entire class of these bugs.
