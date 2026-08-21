# Frontend Review

## Wave 22 (2026-08-06)

PWA API cache (738); navigateFallback lie (737); feature-flag asymmetry (741); AI settings ON (756); NewInvoicePage god module (751); company switch persist (745).

## Wave 21 (2026-08-05)

Invite UI broken for prod (BB-000676/675/677/694). AI settings !== false (BB-000693).

## Wave 20 (2026-08-05)

No UI for e-way subSupplyType/transMode (BB-000642); no CN IRN actions.

## Wave 19 missed (2026-08-05)

BB-000605 CSP; BB-000612 flags; BB-000613 money truncate; BB-000630 PhasePages; BB-000635 virtualization theater.

## Wave 19 (2026-08-05)

No invoice GSTIN picker; outbox schema incomplete; fetch-all masters remain; typedClient only on manufacturing; ERP a11y/i18n gaps. Issues: BB-000556, BB-000572, BB-000577–580, BB-000588–589, BB-000597.


**Date:** 2026-08-02  
**Stack:** React 18, Vite 6, TS 5.6, MUI 6, TanStack Query 5, RHF, Axios, RR7

## Route surface

Full suite: sales (invoice, quotation, CN/DN, SO, challan), purchases parity, inventory (warehouses/transfers/serials), payments (links/recon), reports (GSTR1/3B/9, TB/P&L/BS), accounting CRUD, insights/AI, settings (Tally, gateway, GST).

Many Phase 3–5 screens are thin wrappers over `PhasePages.tsx` (~1.6k LOC).

## Critical / High

| ID | Topic |
|----|-------|
| BB-000013 | `VITE_USE_MOCKS` hazard |
| BB-000031 | JWT in localStorage |
| BB-000032 | Accounting routes ungated |
| BB-000033 | POS-unknown → intra preview |
| BB-000034 | `fetchAllPages` memory cliff |
| BB-000035 | Share URL allowlist |
| BB-* | Zod unused; mega invoice pages; a11y; Hindi |

## Strengths

- Route-level `lazy()` + manualChunks.
- Money/tax unit tests exist.
- ForbiddenPage for denied routes (Wave0).
- `posKnown` gates on sales/purchases Complete.

## Weaknesses

- UI gating ≠ security (must rely on API).
- Staff can deep-link into money/accounting flows.
- Client tax preview can disagree with server until rebound.
- English-only; ID-entry dialogs for MSME owners.

## Score: 5.8 / 10


## Wave 8 (2026-08-03)

Confirmed: VITE_USE_MOCKS prod hard-stop, `/auth/me` boot refresh, RoleRoute→Forbidden. Still open/new: localStorage JWT (BB-000257), RoleRoute gaps on quotations/returns/payments/inventory (BB-000209), payment href allowlist (BB-000210), fetchAllPages silent cap + invoice loads all customers (BB-000245/246), Zod absent (BB-000256), e-Way submit ungated (BB-000224), mobile drawer/a11y (BB-000242/243).

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
