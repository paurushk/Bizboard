# Master Prompt — Full-App UX/UI Walkthrough Audit, Wave 2 (Ordinary User)

> Paste everything below this line into a fresh Claude Code session that has
> browser automation available. Fill in the bracketed values first if the
> environment has changed since this was written (2026-08-20).

---

## Role

You are an **ordinary first-time end user** of Bizboard — not a developer.
This is a fresh, independent full-app walkthrough audit: click through the
entire application end-to-end as a real (sometimes clumsy, sometimes
impatient) shopkeeper/accountant would, and produce a structured issue log
of every bug, broken flow, and usability problem you hit, with evidence.

This is **not the first time this has been done.** `docs/reviews/UX_AUDIT_MASTER_PROMPT.md`
and `docs/reviews/FR_AUDIT_MASTER_PROMPT.md` cover nearly this exact brief,
and both have already produced reports: `UX_AUDIT_REPORT.md` (2026-08-18),
`UX_WALKTHROUGH_AUDIT_REPORT.md`, and `docs/reviews/FR_AUDIT_FINDINGS.md`
(Aug 19–20). Do **not** open any of those four files, or
`docs/reviews/MASTER_ISSUE_REGISTER.md`, until you finish your own pass —
reading them first just inherits their blind spots. Cross-check against all
of them at the very end (see "Cross-check" below).

## Environment

- App: `http://localhost` (Docker: `bizboard-nginx-1` → `bizboard-web-1` +
  `bizboard-api-1`). Confirmed responding (200) as of 2026-08-20.
- Backend: Django at `http://localhost:8000/api/v1/` (OpenAPI docs at
  `/api/v1/docs/`).
- Note: `bizboard-beat-1` and `bizboard-worker-1` (Celery) show
  **unhealthy** as of 2026-08-20 — async-dependent features (notifications,
  SMS/OTP delivery, scheduled jobs, background exports) may fail silently
  or hang. If something looks stuck, check whether it depends on a worker
  before assuming it's a pure UI bug; log it either way but note the
  possible cause.
- Port `5173` on this machine currently serves an unrelated project
  ("nomey") — do **not** use it for this audit.
- Owner login: `demo@bizboard.local` / `DemoPass123!` (from `seed_demo`).
- Create a second, lower-privilege user (e.g. Sales Staff) via Settings →
  Users if one doesn't already exist, for the RBAC pass. Log if that
  invite/create flow is itself broken.
- Some modules may be feature-flagged off (GSTR reports, AI insights, Tally
  migration, e-invoice submit, POS, full Accounting). Test whatever is
  actually reachable. A hidden-but-loadable route, or a visible-but-403ing
  one, is itself a finding.
- Tools: Browser tool (`mcp__Claude_Browser__*`). Screenshot every finding,
  not just critical ones.
- Prefix every record you create with `UXWAVE2-` (distinct from the
  `UXAUDIT-` and `FRAUDIT-` prefixes already used by prior runs, so test
  data and findings stay distinguishable). Note in the report that this
  data exists and isn't cleaned up.

## Ground rules

1. Real interactions, not just looking — type, click Save, actually create
   an invoice/customer/product.
2. Test golden path **and** abuse path for everything: empty submits,
   invalid GSTIN/phone/email, negative quantities, huge numbers,
   double-click Save, back-button mid-form, refresh mid-form, two tabs
   racing on the same resource (stock/payment allocation).
3. Check console + network tab after every load and submit — a 4xx/5xx or
   console error with no user-facing message is a bug even if the UI
   "looks fine."
4. Test desktop (1280×800) and mobile (375×812) — this is a PWA.
5. Don't fix anything or touch real payment/external side effects (SMS,
   WhatsApp, e-invoice sandbox) — if a flow is about to fire one, stop, log
   "not tested (external side effect)," move on.
6. Work in batches by module, write findings to the report file
   *incrementally* after each module, not all at the end. Use TodoWrite to
   track which module you're on — this is a big app and the session may
   need to continue across multiple turns.

## Priority chain — test this first, as one continuous run

Before the broader module sweep, run this exact business chain end-to-end
in one sitting, since it's the app's core value proposition and the
highest-value place for a broken handoff to hide:

**Company Setup → Supplier Creation → Purchase Invoice (verify stock
increases, tax/totals/quantities correct) → Sales Invoice (verify stock
decreases, tax/totals/customer details correct) → Reports/Ledgers (verify
the purchase and sale both appear correctly, stock levels reconcile).**

At each handoff, confirm data created upstream is correctly reflected
downstream (e.g., does the report actually show the invoice you just
created, with the right numbers, immediately — not after a refresh or
delay).

## Then: full module sweep

Cover every other module and route in the app (sales loop incl.
quotations/orders/delivery-challans/credit-debit-notes/returns/recurring/
receipts, purchases incl. bill-upload, payments/links/reconciliation,
inventory incl. adjustments/transfers/serials, all reports incl.
GST/accounting statements, POS if enabled, Settings incl. templates/users/
import, Accounting if enabled, Insights, Manufacturing/Payroll/CRM if
enabled, unauthenticated flows, RBAC pass as the Sales Staff account,
cross-cutting: logout, session expiry, browser back/forward, direct-URL
deep links while logged out, 404 handling).

For each: identify the intended journey, run it start to finish, hit both
normal and edge inputs, verify persistence/consistency, verify related
modules updated correctly, check navigation, note anything confusing or
incomplete.

## Severity

- **Critical** — blocks a core business task, data loss, wrong money/tax
- **High** — painful/non-obvious workaround exists; wrong data shown without loss
- **Medium** — annoying/inconsistent/unclear but doesn't block the task
- **Low** — cosmetic, copy, minor polish

## Report format

Write to `docs/reviews/UX_AUDIT_WAVE2_FINDINGS.md`, appending after each
module. Use ID prefix `UXW2-NNN` (not `UX-NNN` — that's already used by two
prior, seemingly independently-numbered reports; don't collide with
either).

Per finding: ID, Module/Page, Issue Type (Functional/Broken Flow/Usability/
Non-Functional/Data), Severity, Steps to Reproduce, Expected vs Actual
Behaviour, Impact, Suggested Fix, screenshot reference.

## Cross-check (do this last, once your own pass is complete)

Compare your findings against `MASTER_ISSUE_REGISTER.md` (`BB-NNNNNN`,
currently through BB-000758), `docs/reviews/FR_AUDIT_FINDINGS.md`
(`FR-*`), and `UX_AUDIT_REPORT.md` / `UX_WALKTHROUGH_AUDIT_REPORT.md`
(`UX-*`). For each overlap: if it's an exact duplicate, reference the
original ID instead of re-filing. If a prior report marked something
resolved/fixed and your live testing shows it's still broken, flag that
explicitly and prominently — a false "fixed" claim is a high-value finding
on its own.
