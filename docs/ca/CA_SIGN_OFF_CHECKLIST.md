"""Phase 1 CA validation checklist — invoice / GST samples.

Fill after generating PDFs from staging. Sign and store under docs/ca/.

| # | Scenario | Expected | PDF OK | Initials |
|---|----------|----------|--------|----------|
| 1 | Intra-state ₹200 @ 18% | CGST 18 + SGST 18 = 236 | | |
| 2 | Inter-state ₹100 @ 12% | IGST 12 = 112 | | |
| 3 | Odd paise ₹10.05 @ 18% | CGST 0.90 + SGST 0.91; line 11.86 | | |
| 4 | NON_GST | Tax 0 | | |
| 5 | AFTER_TAX discount ₹10 on ₹100@18% | Tax 18; grand 108 | | |
| 6 | BEFORE_TAX discount ₹10 on ₹100@18% | Taxable 90; tax 16.20 | | |
| 7 | Round-off on / off | Matches matrix | | |
| 8 | Multi-rate 5% + 28% | Accumulates | | |

CA name: ________________  Date: ________  Sign-off: ________
"""
