# Phase 0 CA validation checklist — invoice / GST samples

Fill after generating PDFs from **staging** with the **frozen** Tax Invoice template (see Phase 0 plan §7.2). Sign and store under `docs/ca/` or the company vault.

Scenarios align with DoD **F1–F8** in [`docs/pilot/PHASE_0_DOD.md`](../pilot/PHASE_0_DOD.md). Automated parity fixture must cover the same set (`tax_parity_cases.json` + FE/BE tests).

| # | DoD | Scenario | Expected | PDF OK | DB OK | FE preview OK | Initials |
|---|-----|----------|----------|--------|-------|---------------|----------|
| 1 | F1 | Intra-state ₹200 @ 18% | CGST 18 + SGST 18 = 236 | | | | |
| 2 | F2 | Inter-state ₹100 @ 12% | IGST 12 = 112 | | | | |
| 3 | F3 | Odd paise ₹10.05 @ 18% | CGST 0.90 + SGST 0.91; line 11.86 | | | | |
| 4 | F4 | NON_GST | Tax 0 | | | | |
| 5 | F5 | AFTER_TAX discount ₹10 on ₹100@18% | Tax 18; grand 108 | | | | |
| 6 | F6 | BEFORE_TAX discount ₹10 on ₹100@18% | Taxable 90; tax 16.20 | | | | |
| 7 | F7 | Round-off on / off | Matches matrix | | | | |
| 8 | F8 | Multi-rate 5% + 28% | Accumulates | | | | |
| 9 | F12 | Additional charges (freight/packing) GST | Per B11 decision: taxed per rule **or** documented non-taxable / out-of-scope for pilot | | | | |

**Prerequisite:** BUG-204 fixed (PDF honors `invoice_discount_mode`) before F6 can pass. Automated PDF assert (F11) covers at least F1/F3/F6.

CA name: ________________  Date: ________  Sign-off (F9): ________

B11 / F12 decision (tax additional charges / scope out): ________________  Initials: ________

Staging build / commit SHA: ________________  PDF template freeze date: ________
