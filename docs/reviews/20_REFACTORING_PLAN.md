# Refactoring Plan

## Wave 22 (2026-08-06)

Insert: (0l) sales RCM posting branch; (0m) period gate in money services; (0n) FIFO reverse-by-layer; (0o) PWA NetworkOnly /api; (0p) SaaS fail-closed writes.

## Wave 21 (2026-08-05)

Insert: (0h) money-doc void not delete; (0i) CompanyPrimaryKeyRelatedField on all ERP; (0j) invite consent + token UX; (0k) GSTR note classifier.

## Wave 20 (2026-08-05)

Insert: (0e) seller identity helper for IRP/e-way/GSTR; (0f) note amendment engine + IRN; (0g) UUID file keys.

## Wave 19 missed (2026-08-05)

Insert before ERP work: (0) prod auth+CSRF, (0b) post_sales_invoice field names+cess CoA, (0c) FIFO cancel/COGS peel, (0d) durable idempotency.

## Wave 19 (2026-08-05)

Priority refactors: (1) inventory business-event types, (2) filing GSTIN aggregate + series, (3) RLS session GUC + app role, (4) ERP capability matrix, (5) kill legacy fetch-all + typed money client. Do not add more ERP surface until P0s close.


**Date:** 2026-08-02

## Principles

- No big-bang rewrite.
- Prefer feature flags + posting matrix completion over new frameworks.
- Keep document-derived AR/AP invariant.

## Waves

### R1 — Safety (1–2 weeks)

- Production settings lock; strip mocks from prod builds.
- OTP hash; disable OTP UI until SMS.
- Webhook identity binding.
- TLS + backup automation.
- Hide/flag sandbox GSTR/e-invoice/accounting/AI.

### R2 — Correctness (3–6 weeks)

- Returns → CN or GSTR+GL path.
- RCM posting matrix; split tax accounts.
- Composition/unregistered enforcement.
- H9 + period hard gates + GL reverse/repost.
- E-invoice ValDtls schema.
- Document number uniqueness everywhere.
- Allocation CheckConstraints.

### R3 — Structure (4–8 weeks)

- Split `resources.ts` / `PhasePages` / invoice editors.
- Denormalize `company_id` on children.
- OpenAPI-generated client.
- Fine-grained RBAC capabilities.
- Soft-delete masters.

### R4 — Scale & compliance GA (ongoing)

- GSTR-2B match; live GSP.
- Pagination everywhere; load tests.
- RLS optional; observability stack.
- Roles Accountant/Viewer.
- POS mode; PWA offline.

### Explicit non-goals (until funded)

- Manufacturing MRP, Payroll, CRM pipeline, multi-GSTIN, WhatsApp Business — separate programs.


## Wave 8 (2026-08-03) priority refactors

1. Payment adapter fail-closed module + adversarial tests
2. Shared H9 amend service (sales+purchase)
3. Accounting permission mixin
4. Split resources.ts / invoice-purchase editors
5. Server-driven party/product pickers (kill fetchAll for docs)

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
