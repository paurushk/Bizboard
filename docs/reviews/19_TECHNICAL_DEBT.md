# Technical Debt

## Wave 22 (2026-08-06)

NewInvoicePage 1680LOC (751); inventory↔sales import (757); OpenAPI theater (750); weak PWA gate test (758).

## Wave 21 (2026-08-05)

**Superseded 2026-08-06:** FY close / recurring / TDS / SaaS shipped (BB-000664/669–671). Remaining debt: PhasePages splits, FIFO+WO load evidence, mega FE typing — see KNOWN_LIMITATIONS.

## Wave 20 (2026-08-05)

Number allocator still defensive full-scan (BB-000646). Dual file ingest (BB-000644).

## Wave 19 missed (2026-08-05)

PhasePages still the accounting app (BB-000630). Idempotency cache (BB-000610). Dead CORS env (BB-000625).

## Wave 19 (2026-08-05)

New debt: dual flag systems, SALE enum overload, untyped money clients, stale honesty docs, RLS design that cannot be enabled. See `BB-000550`–`BB-000598`.


**Date:** 2026-08-02

## Debt themes

1. **Docs drift** — root reports July 24; phase §0 ❌ vs Implemented; README understates; ONBOARDING honesty vs nav.
2. **FE god-modules** — `resources.ts` ~2.2k; `PhasePages.tsx` ~1.6k; mega invoice pages.
3. **Optional GL incompleteness** — dual truth when accounting on.
4. **Stub communications** — SMS/email/WhatsApp.
5. **Sandbox statutory paths** exposed in UI.
6. **Coarse RBAC** vs MSME multi-employee reality.
7. **Unpinned Python deps** + non-blocking pip-audit.
8. **Child rows without company_id**.
9. **Test debt** on FE pages and adversarial payments.
10. **Process debt** — Phase 1–7 before Phase 0 Go.

## Quantified (this register)

- Low/tech-debt category issues: see MASTER (~31 Technical Debt + many Medium maintainability).
- Historical `bugs/INDEX.md`: ~202 findings (many fixed in Wave0 — verify before rework).

## Pay-down order

See [REMEDIATION_ROADMAP.md](./REMEDIATION_ROADMAP.md).


## Wave 8 (2026-08-03)

Process debt: false Resolved closure (BB-000254). Doc drift: 12_DEVOPS_REVIEW stale claims (BB-000239); root MVP/PERF/UX stale (BB-000240). God modules unchanged.

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
