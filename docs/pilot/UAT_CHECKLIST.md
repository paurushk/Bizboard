# Phase 0 Pilot UAT checklist

**DoD:** G1–G12 in [`PHASE_0_DOD.md`](./PHASE_0_DOD.md)  
**Plan tickets:** P0-600 (this matrix), P0-605 (fixtures), P0-606 (execution), P0-607 (import robustness)  
**Environment:** Staging, real API (not `VITE_USE_MOCKS`)  
**Companies:** ≥5 — use seed from P0-605; document reset between passes  

## Companies under test

| Code | Profile | Seed/reset notes | Owner |
|------|---------|------------------|-------|
| C1 | Pilot Retail GST | `seed_pilot_fixtures` → pilot-c1@bizboard.local / PilotPass123! | |
| C2 | Pilot Inter-State | pilot-c2@… | |
| C3 | Pilot Non-GST Shop | pilot-c3@… | |
| C4 | Pilot Multi-Rate | pilot-c4@… | |
| C5 | Pilot Multi-User | pilot-c5@… + pilot-c5-staff@… | |

Reset: `python manage.py seed_pilot_fixtures --reset`  
Perf seed (optional): `python manage.py seed_pilot_fixtures --perf-invoices 5000`

## Matrix (mark Pass / Fail / Blocked + date)

| ID | Flow | C1 | C2 | C3 | C4 | C5 | Notes |
|----|------|----|----|----|----|----|-------|
| G1 | Register → company GST setup | | | | | | |
| G2 | CSV import masters (preview → validate → commit; error report usable; no silent poison) | | | | | | P0-607 |
| G3 | Opening stock → balances correct | | | | | | |
| G4 | Purchase → complete → stock up | | | | | | |
| G5 | Quotation multi-line → convert → invoice | | | | | | |
| G6 | Invoice complete → PDF → download/share | | | | | | Download must not hang if PDF not READY |
| G7 | Partial receipt + allocation → outstanding | | | | | | |
| G8 | Sales return **non-first** line → stock + outstanding | | | | | | |
| G9 | Supplier payment + allocation | | | | | | |
| G10 | Ledgers + sales/purchase/inventory reports + CSV export | | | | | | |
| G11 | Staff: cancel/export/inventory/financials flags enforced | | | | | | C5 primary |
| G12 | Negatives: blocked customer; POS gate; stock BLOCK | | | | | | |

## Smoke (quick path — still required once per build)

1. Register company (or use demo) — Owner has all capability flags.  
2. Import products / create product with HSN + GST.  
3. Create supplier with state → purchase → Complete → stock increases.  
4. Create customer with state → sales invoice odd-paise price → UI totals match saved invoice.  
5. Partial receipt + allocation → ledger outstanding drops.  
6. Sales return → stock restored; outstanding adjusts.  
7. Cancel draft OK; staff without `can_cancel_documents` gets 403 on cancel.  
8. Blank party state blocks GST Complete (unless assume-local enabled).  
9. BEFORE_TAX vs AFTER_TAX discount labels visible on PDF/UI.  
10. Dashboard loads; receivables aging present; export requires `can_export`.  
11. Completed invoice lines not freely editable (DoD B6 allowlist).  
12. Unauthenticated `/media/` URL does not serve PDFs.

## Sign-off / SHA lock (DoD exit #6)

UAT build SHA: ________  Date: ________  QA: ________  Eng: ________  
Result: Pass / Fail / Conditional (list waivers): ________  

**Go build SHA:** ________  
- [ ] Go SHA **equals** UAT SHA, **or**  
- [ ] 12-row smoke re-run on Go SHA and re-signed below  

Smoke re-sign (if SHA differs): Date: ________  QA: ________  Eng: ________
