# Competitor Analysis

## Wave 22 (2026-08-06)

No GRN vs Zoho/Tally (735); SaaS seat/entitlement non-enforcing vs Zoho Billing (725–727); multi-GSTIN 3B bug vs Tally multi-firm (697).

## Sprint 6 honesty (2026-08-05)

BizBoard is **not** racing Zoho Books / TallyPrime / ERPNext on manufacturing, statutory payroll, multi-branch GSTIN, live NIC, recurring invoices, or SaaS entitlements (BB-000591 / BB-000519). Positioning remains GST billing + inventory for Indian MSMEs, with optional books and preview/dark ERP modules. CN IRN + paid-invoice credit notes are in Sprint 2; live NIC remains fail-closed.

## Sprint 2 honesty (2026-08-05)

CN IRN (CRN/DBN + PrecDocDtls) and paid-invoice credit notes (invoiced − prior notes cap) are now in product. Live NIC/IRP remains fail-closed vs Zoho/TallyPrime certified GSP (BB-000519 / BB-000624). Multi-company / statutory payroll / manufacturing still trail competitors.

## Wave 21 (2026-08-05)

Zoho/Tally allow multi-firm login and branch GSTIN CRUD in-product. BizBoard invite hard-fails existing emails (BB-000673) and has no CompanyGstin UI (BB-000674). No TDS vs Tally/Zoho.

## Wave 20 (2026-08-05)

TallyPrime / Zoho Books / ERPNext all IRN credit notes and allow CN after receipt. BizBoard cannot (BB-000647/648). Multi-GSTIN e-way is table stakes vs Zoho/TallyPrime — BB-000639 fails that bar.

## Wave 19 (2026-08-05)

Checkbox ERP modules do not create Zoho/TallyPrime/ERPNext parity (BB-000591). Positioning must stay “GST billing + inventory (+ preview modules)”.


**Date:** 2026-08-02

## Positioning

BizBoard aims at Indian MSME cloud GST billing. Competitors: **TallyPrime**, **Zoho Books**, **Vyapar**, **Busy**, **ERPNext**, **Marg**, **ClearTax** (compliance).

## Comparison (honest)

| Capability | BizBoard | TallyPrime | Zoho Books | Vyapar | ERPNext |
|------------|----------|------------|------------|--------|---------|
| GST tax invoice | Strong math | Mature | Mature | Strong UX | Strong |
| GSTR filing | Aids/sandbox | Ecosystem | Strong | Aids | Apps |
| E-invoice live | No | Yes/ecosystem | Yes | Yes | Apps |
| Full books | Opt-in incomplete | Core | Core | Light | Core |
| Inventory | Strong append-only | Strong | Good | Strong | Strong |
| Manufacturing | No | Yes | Limited | Limited | Yes |
| Payroll | No | Add-on | Yes | No | Yes |
| Multi-company | No | Yes | Yes | Limited | Yes |
| Offline | No | Yes (local) | Limited | Yes | Limited |
| WhatsApp Business | No | Partners | Yes | Yes | Apps |
| Tally migration | CSV | N/A | Import | Import | Tools |
| Price / cloud | TBD | License | SaaS | Freemium | Open+host |

## Gaps that block win themes

1. **Compliance completeness** (2B, live e-invoice, composition) vs ClearTax/Zoho.
2. **Voucher speed / offline** vs Tally/Vyapar.
3. **Manufacturing** vs ERPNext — do not compete here yet.
4. **Trust** — sandbox UI that looks live destroys CA trust faster than missing features.

## Strategic recommendation

Win on: **clean cloud billing + stock + honest GST aids + easy Tally import** for small traders.  
Do not win on: full ERP claims until modules exist.

Register: competitor EXTRA issues.


## Wave 8 (2026-08-03)

No change to competitor gaps (Tally/Zoho/ERPNext). Payment integrity bugs make BizBoard weaker than Zoho Books on collections reliability until P0s close.

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
