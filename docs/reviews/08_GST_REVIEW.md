# GST Review

## Wave 22 (2026-08-06)

GSTR-3B empty stamp (697); GSTR-9 unscoped (698); RCM note liability (696); SUPECOM totals (707); silent primary stamp (708); export ignores GSTIN (740); 2B first-match (716); GSTR live filing stub (742).

## Code-max (2026-08-05)

**Score: 9.3 / 10** (compliance engineering ceiling). Live NIC/IRP (BB-000624) stays fail-closed until `GSP_CERTIFIED` + Final Gate — blocks true 10/10.

Closed this pass: sales RCM confirm + `rchrg`; SUPECOM when `ecommerce_operator_gstin` set; CN/DN IRN UI; note filing stamps; stamp-address fail-closed; GSTR-1 DOC/AT GSTIN scope; 2B UNREVIEWED + CLAIMABLE gate; `company_gstin` on GSTR pages; TDS/TCS MVP worksheets (not IT portal).

Offline CA aids only — not GSTN portal upload schema.

## Wave 21 (2026-08-05)

BB-000652 CDNUR vs B2CS; BB-000653 e-way cancel leaves bill no; BB-000663 auto-CN discount; BB-000674 CompanyGstin no CRUD.

## Wave 20 (2026-08-05)

BB-000639 seller GSTIN stamp ignored on IRP/e-way; BB-000640–642 e-way challan/URP/taxonomy; BB-000647 no CN IRN; BB-000649 CN POS drift.

## Wave 19 missed (2026-08-05)

BB-000607 is_gst_registered; BB-000608 SOFT_CLOSED; BB-000611 inclusive cess; BB-000614 ITC; BB-000619–624 returns/RCM/GSTR-1/SEZ/CMP/IRP; BB-000637 2B match; BB-000638 POS fallback.

## Wave 19 (2026-08-05)

P0: multi-GSTIN blended GSTR + interstate from primary GSTIN (BB-000556); OCR rate default 18 (BB-000557); series not per GSTIN (BB-000569); GSTR-9 tables 6/7 stubs (BB-000568); outbox drops cess (BB-000577); SUPECOM still unguarded (BB-000596).


**Date:** 2026-08-02 · **Score: 3.5 / 10**

## What is correct

- Decimal + `ROUND_HALF_UP`; CGST/SGST residual split.
- Tax-inclusive extract with stash to avoid double-extract.
- Place-of-supply gate on Complete (when configured).
- RCM memo fields for 3B; GSTR honesty disclaimers; composition blocked from regular GSTR packs at export.
- Invoice value mismatch detection excludes bad B2B rows.
- Allowed rates include 0.25% / 3%.

## Critical gaps

| ID | Finding |
|----|---------|
| BB-000005 | Sandbox IRP/e-way only |
| BB-000007 | Composition/unregistered can tax-invoice |
| BB-000008 | Sales returns missing CDNR |
| BB-000009 | ITC without 2B / eligibility |
| BB-000011 | H9 vs period close |
| BB-000012 | E-invoice ValDtls / float |

## High gaps

| Topic | IDs |
|-------|-----|
| Untaxed additional charges | BB related G1 |
| AFTER_TAX discount vs GSTR identity | G2/G16 |
| No cess / SEZ / export | G8/G9 |
| Incomplete GSTR-1 tables | G13 |
| GSTR-9 aid only | G20 |
| No CMP-08/GSTR-4 | G21 |
| No live GSTN portal upload | product |

## CA guidance

Treat all GSTR screens as **offline aids** until CA sign-off and portal schema validation. Do not market “GST Portal Integration” as live filing.

## Score: 3.5 / 10 (compliance) · 7.5 / 10 (billing tax math only)


## Wave 8 (2026-08-03)

New/residual: GSTR-3B `net_payable_hint` still subtracts provisional ITC (BB-000212); manual mark-IRN (BB-000214); client-writable einvoice/AATO (BB-000215); Null GSTIN provider (BB-000225); e-Way FE submit ungated (BB-000224); blank company POS→intra in FE (BB-000233). Live GSP still Deferred (BB-000005).

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

### Wave 13 GST residuals (verified)

| ID | Finding |
|----|---------|
| BB-000384 | Live IRP/E-Way adapters always raise not-enabled in production |
| BB-000391 | FE `placeOfSupplyKnown` treats any state text as known |
| BB-000396 | SOFT_CLOSED behaves as hard CLOSED |
| BB-000397 | `assume_local_state_for_blank_party` does not stamp POS on Complete |
| BB-000398 | GSTR-1 CDNR includes notes against opening invoices |
| BB-000400 | Composition challan convert → uncompletable GST draft |
| BB-000405 | No GSTR-2B — ITC always provisional |
| BB-000419 / 422 | POS string fallback invents inter/intra; dual maps lack CI parity |

**Verdict:** Offline GSTR aids only. Fail-closed e-invoice flags in prod until live GSP ships.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
