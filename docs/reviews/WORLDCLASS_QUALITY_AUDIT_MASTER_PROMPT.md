# Master Prompt — World-Class Product Quality Audit (UI · UX · API · Data)

> Paste everything below into a fresh agent session that has **browser
> automation**, **shell**, and **workspace write** access. Do **not** wait for
> confirmation when URL, credentials, and report path are already given.

---

## Why this exists

Bizboard is a GST billing / inventory / payments product for Indian SMEs.
A world-class product in this domain is not "screens that look fine." It is:

1. A shopkeeper can complete every money-moving task without confusion or data loss.
2. Every rupee, tax split, and stock unit on screen matches the API and the database.
3. Invalid, abusive, and concurrent actions fail safely with a human-readable reason.
4. Privilege, tenancy, and feature flags are consistent in nav, URL, and API.
5. Reports, PDFs, ledgers, and exports agree with the documents that created them.

This audit finds **every gap, bug, and improvement** that prevents that bar.
Completeness beats speed. A flow that "looks OK" but was not actually submitted
is **not tested**, not passed.

## Dual role (do both; do not collapse them)

### Layer A — Ordinary user (rendered app)

Behave as a first-time shopkeeper/accountant. Prefer the **screen** over source
to judge labels, empty states, copy, and discoverability. If the screen is
confusing, that **is** a finding even if the code is "correct."

### Layer B — System integrity (API + data)

After every successful mutation, **corroborate** through:

- The UI (list, detail, related module, report).
- The HTTP response (status, body totals, tax split, ids).
- A follow-up GET of the same resource.
- Downstream effects (stock, party ledger, dashboard KPI, PDF/export if present).

You **may** read `web/src/App.tsx` routes, `web/src/navigation/menu.ts`, and
OpenAPI at `/api/v1/docs/` as a **coverage checklist**, not as an excuse for
what a screen "should" do. You may hit the API with the session (same-origin
`fetch`) to compare numbers. You may query the DB **read-only** if a shell is
available — never write SQL except through the app UI/API under the `WCAUDIT-`
prefix.

Do **not** fix code. Report only.

## Environment (fill once, then go)

- Frontend candidates (try in this order; use the first that serves **Bizboard**):
  1. `http://localhost` (Docker/nginx)
  2. `http://localhost:5173` (Vite) — **verify title is Bizboard**; on mixed-dev
     machines 5173 may be a different project.
- Backend: same-origin `/api/v1/` or `http://localhost:8000/api/v1/` **only if
  that port is Bizboard**. Docker often publishes the API only behind nginx.
- Owner login: `[OWNER_EMAIL]` / `[OWNER_PASSWORD]`
- Lower-privilege login: `seed_demo` currently creates **Owner only**. Create
  Sales Staff via Settings → Users if missing.
- Test-data prefix: `WCAUDIT-` (do not reuse `UXAUDIT-` / `UXWAVE2-` / `FRAUDIT-`).
- Feature flags may hide GSTR, AI, Tally, e-invoice, POS, Accounting,
  Manufacturing, Payroll. Test what is reachable. A nav/URL/API mismatch is a finding.
- Celery worker/beat may be down — if a flow depends on async (PDF, SMS, import,
  daily summary), log the user-visible failure **and** note worker health.
- Do **not** trigger live payments, SMS, WhatsApp, or e-invoice sandbox submits.
  Stop, mark `not-tested (external side effect)`, continue.

If credentials and URL are already in the user message, **skip the confirmation
gate** and start after a 30-second environment probe.

## Ground rules

1. **Real interactions.** Type, click Save, create records. Looking is not testing.
2. **Happy path + abuse path** on every form that can move money or stock:
   empty submit, whitespace-only, invalid GSTIN/phone/email, negative qty/rate,
   qty 0, huge amounts, emoji/HTML in names, double-click Save, refresh mid-form,
   back/forward mid-form, two tabs racing the same document.
3. **Console + network after every load and submit.** A 4xx/5xx or console error
   with no user-facing message is a bug even if the UI looks fine.
4. **Viewports:** desktop `1280×800` and mobile `375×812` (PWA). Reload after resize.
   At least the golden chain and new invoice must run at both.
5. **Write incrementally.** After each stage, append findings. A coverage row
   still `pending` at session end is itself a finding (`audit-gap`).
6. **Do not read prior UX/FR reports until your own pass is done.** Cross-check last.
7. **Never skip a reachable route.** If time runs out, list untested routes
   explicitly — do not imply they passed.

## What counts as a finding

Broken flow, functional bug, data integrity (UI ≠ GET ≠ related screen), API
contract (500, HTML error, UI-only validation), validation, AuthZ/tenancy,
feature-flag mismatch, usability, accessibility, responsiveness, copy,
performance, observability (failure with no toast).

## Severity

- **Critical** — cannot complete a core money/stock/tax task; data loss; **wrong
  money or tax**; tenancy leak.
- **High** — painful workaround; wrong data displayed; whole viewport broken; API 500.
- **Medium** — inconsistent/unclear; doesn't block the task.
- **Low** — cosmetic, copy, minor polish.

If money/tax/stock disagrees across UI vs API vs report vs PDF, it is **Critical**
even if each screen looks reasonable in isolation.

## Mandatory numeric assertions

For every GST document: qty × rate = taxable; intra-state CGST=SGST=rate/2 IGST=0;
inter-state IGST=full rate; taxable+tax+cess±round_off = grand_total within ₹0.01;
editor == detail == list == GET == report.

For stock: purchase increases, sale decreases, BLOCK policy rejects oversell.
For payments: receipt changes outstanding and ledger by the same amount.

## Coverage matrix

Every `web/src/App.tsx` route: `pass` | `fail` | `blocked` | `not-tested`.
Include unauthenticated `/login` `/register` `/invite` `/pay/:token` and 404.

## Stage 0 — Environment probe (≤ 2 minutes)

Hit both frontends; confirm Bizboard; login; GET `/api/v1/auth/me/` and
`/api/v1/feature-flags/`; note docker worker/beat; write coverage skeleton.

## Stage 1 — Golden business chain (first, continuous)

Masters (WCAUDIT- supplier/customer/product, GSTIN abuse) → purchase qty 10
known rate 18% GST → stock +10 → sales invoice qty 3 (crown jewel, intra then
inter-state) → stock −3 → oversell vs BLOCK → partial receipt → reports show
the same numbers without a mystery refresh.

## Remaining stages

Unauthenticated; dashboard KPIs you can explain; rest of sales loop; purchases;
payment links as logged-out user; inventory; every report + export; POS;
settings + create Sales Staff; accounting/insights/manufacturing/payroll/CRM if
reachable; **RBAC at UI and API**; theme/logout/stale token/back-forward/404.

## Report format

Write to `docs/reviews/WORLDCLASS_QUALITY_AUDIT_FINDINGS.md`.
IDs: `WC-001`, `WC-002`, … (do not collide with `UX-` / `UXW2-` / `FR-` / `BB-`).

Per finding: ID, Module/Page, Severity, Category, Layers A/B, Steps, Expected,
Actual, Evidence (screenshot, HTTP, GET-after-POST numbers), Viewport/role,
one-sentence suggested fix.

End with Top 10 fix-first and an explicit **not-tested** list. Then cross-check
prior registers for duplicates and false "fixed" claims.

## Execution contract

- Do not ask which URL/path/staff account to use if the user already supplied them.
- Proceed module-by-module without pausing for approval.
- Stop only for real external side effects or a hard environment outage.
- Screenshot every finding, not only criticals.
