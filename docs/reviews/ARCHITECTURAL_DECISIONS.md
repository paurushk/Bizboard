# Architectural Decisions (Audit-derived ADRs)

## Wave 22 ADR notes (2026-08-06)

**ADR-A32:** Money create/allocate must period-gate in the service layer, not only HTTP views. **ADR-A33:** Authenticated `/api` must never be SW-cached. **ADR-A34:** FIFO reverse restores peels / retires source layers — never invent zero-cost layers. **ADR-A35:** SaaS writes fail closed when subscription required. **ADR-A36:** Sales RCM posting must not credit Output GST.

## Wave 21 ADR notes (2026-08-05)

**ADR-A28:** Money documents are voided, never hard-deleted. **ADR-A29:** All company-scoped FKs use CompanyPrimaryKeyRelatedField. **ADR-A30:** Invite is token+consent; passwords forbidden in prod. **ADR-A31:** GSTR note section follows original supply class (B2B/B2CL/B2CS), not party GSTIN alone.

## Wave 20 ADR notes (2026-08-05)

**ADR-A25:** Filing identity = CompanyGstin row, not Company.gstin. **ADR-A26:** Credit notes amend frozen supplies (POS/tax/GSTIN snapshot). **ADR-A27:** Object keys are server-generated UUIDs; client filenames are metadata only.

## Wave 19 missed ADR notes (2026-08-05)

**ADR-A22 (recommended):** Durable idempotency table, not cache. **ADR-A23:** CSRF bootstrap is part of cookie-auth or cookie-auth is forbidden. **ADR-A24:** `accounting_enabled` must not break Complete — posting guards tested with real lines.

## Wave 19 ADRs adopted (Sprint 6 / 2026-08-05)

### ADR-A19 — Do not enable Postgres RLS until session GUC + NOSUPERUSER app role land

**Status:** Accepted.  
**Decision:** `POSTGRES_RLS_ENABLED` remains 0 in all deployed envs until BB-000551/552/560/561/562 are proven in CI.  
**Rationale:** SET LOCAL + superuser design is theater or outage.

### ADR-A20 — Inventory movements are business events, not SALE/PURCHASE overloads

**Status:** Accepted.  
**Decision:** Manufacturing, transfers, challans, and invoices must not share `MovementType.SALE`/`PURCHASE`.  
**Rationale:** BB-000554/555/593.

### ADR-A21 — Filing GSTIN is an aggregate root for series, tax split, and returns

**Status:** Accepted.  
**Decision:** Either one active filing GSTIN per tenant or full per-GSTIN series+GSTR. Stamps without scoping are forbidden.  
**Rationale:** BB-000556/569.


**Date:** 2026-08-02  
**Status:** Recommendations from independent audit — adopt formally via eng RFC.

## ADR-A01 — Document-derived AR/AP (keep)

**Decision:** Party outstanding remains computed from documents + allocations; no stored ledger balance tables for AR/AP.  
**Rationale:** Prevents dual-write drift for billing MVP; matches current LedgerService.  
**Consequence:** Statements must handle opening balances and advances carefully (open medium issues).

## ADR-A02 — GL is a projection, not a second source of truth

**Decision:** When `accounting_enabled`, Complete/Cancel/Amend/Return/Note **must** succeed in posting or the document transition fails.  
**Rationale:** Optional incomplete GL creates false books (BB-000016).  
**Consequence:** Harder Complete path; requires full posting matrix (RCM, returns, H9).

## ADR-A03 — Postgres-only production

**Decision:** Refuse production boot without Postgres `DATABASE_URL`.  
**Rationale:** Document numbers, stock, payments rely on `select_for_update` (BB-000055).

## ADR-A04 — Sandbox statutory never looks live

**Decision:** E-invoice/e-way/GSTR UI must watermark and feature-flag; production GSTIN cannot obtain sandbox IRN presented as success.  
**Rationale:** BB-000005 / BB-000014 compliance risk.

## ADR-A05 — Registration type gates document types

**Decision:** COMPOSITION → Bill of Supply / CMP only; UNREGISTERED → no GST tax invoice.  
**Rationale:** BB-000007.

## ADR-A06 — Filed period immutability

**Decision:** SOFT_CLOSED/CLOSED GST (and accounting) periods block money H9; corrections via credit/debit notes or explicit reopen.  
**Rationale:** BB-000011.

## ADR-A07 — Feature flags per pilot tier

**Decision:** Company (or plan) flags for accounting, AI, Tally, e-invoice submit, GSTR packs.  
**Rationale:** UI over-claim vs validated surface.

## ADR-A08 — Child rows carry company_id

**Decision:** Denormalize tenant key on JournalLine, document lines, price list items.  
**Rationale:** BB-000017 defense-in-depth.

## ADR-A09 — OTP off until SMS real

**Decision:** Keep `VITE_ENABLE_OTP` unset in prod until provider + hashed storage.  
**Rationale:** BB-000002/000003/000006.

## ADR-A10 — Do not claim ERP modules not in tree

**Decision:** Marketing/README/nav must not list Manufacturing, Payroll, CRM, Multi-branch, WhatsApp Business, live GST Portal, native Mobile until implemented.  
**Rationale:** BB-000035 / BB-000014.


## Wave 8 (2026-08-03) ADR notes

- **ADR-W8-1:** Payment sandbox adapter must never activate for named providers without credentials in non-test env.
- **ADR-W8-2:** “Resolved” in register requires linked adversarial test; process gate BB-000254.

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

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues) + missed `BB-000544`…`BB-000549`. Open **94**. Wave 13 Open==0 invalidated. Production Readiness **3.3 / 10**.

### ADR enforcement gaps found in Wave 14

- **ADR-A03 violated in code:** Postgres-only production is documented but `DATABASES` still defaults to SQLite with no `DJANGO_ENV` engine refuse (BB-000544).
- **ADR-A02 residual:** Return COGS reverse amount ≠ original sale cost basis (BB-000460); disposal write-off misuses expense account (BB-000459); refund path breaks AR control (BB-000457).
- **ADR-W8-2 reaffirmed:** Checklist/string gates ≠ adversarial residual tests (BB-000461 / BB-000548).
