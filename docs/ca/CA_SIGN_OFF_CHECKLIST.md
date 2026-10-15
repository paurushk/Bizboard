# Phase 0 CA validation checklist — invoice / GST samples

Fill after generating PDFs from **staging** with the **frozen** Tax Invoice template (see Phase 0 plan §7.2). Sign and store under `docs/ca/` or the company vault.

Send this alongside [`F9_CA_REVIEW_COVER.md`](F9_CA_REVIEW_COVER.md) — the cover sheet explains what's
already automated-evidenced below and exactly what's left for the CA to review and sign.

Scenarios align with DoD **F1–F8** in [`docs/pilot/PHASE_0_DOD.md`](../pilot/PHASE_0_DOD.md). Automated parity fixture must cover the same set (`tax_parity_cases.json` + FE/BE tests).

**2026-09-12 — automated evidence pre-filled below** so the CA's job is to *review and sign*, not to
re-derive the numbers. Every "PDF OK" / "DB OK" cell is backed by a real, currently-passing automated
test that renders the actual PDF and/or computes the actual DB totals for that exact scenario — see the
guard reference under each row. "FE preview OK" is backed by the same fixture shared with the frontend
(`web/src/utils/tax.test.ts`), not a manual screenshot check; a human should still eyeball the live
preview once before signing. **CA name/date/sign-off and the B11/F12 business decision remain the two
cells only a human can fill** — nothing below substitutes for that.

| # | DoD | Scenario | Expected | PDF OK | DB OK | FE preview OK | Initials |
|---|-----|----------|----------|--------|-------|---------------|----------|
| 1 | F1 | Intra-state ₹200 @ 18% | CGST 18 + SGST 18 = 236 | ✅ auto (`test_pdf_totals_match_db_ca_signoff_f1_f2_f4_f5_f7_f8[f1_even_200_18]`) | ✅ auto (`test_billing_totals.py::test_line_tax_matches_frontend_fixture[f1_even_200_18]`) | ✅ auto (`web/src/utils/tax.test.ts`, same fixture) | |
| 2 | F2 | Inter-state ₹100 @ 12% | IGST 12 = 112 | ✅ auto (same PDF test, `[f2_inter_100_12]`) | ✅ auto (`test_line_tax_matches_frontend_fixture[f2_inter_100_12]`) | ✅ auto (shared fixture) | |
| 3 | F3 | Odd paise ₹10.05 @ 18% | **CGST 0.90 + SGST 0.90; line 11.85** (corrected 2026-09-12 — this row previously said 11.86; the actual computed and PDF-rendered value, matching the tested fixture, is 11.85) | ✅ auto (`test_pdf_totals_match_db_odd_paise_and_before_tax[f3_odd_paise]` — render→extract→assert vs DB) | ✅ auto (`test_line_tax_matches_frontend_fixture[f3_odd_paise_10_05_18]`) | ✅ auto (shared fixture) | |
| 4 | F4 | NON_GST | Tax 0 | ✅ auto (PDF test `[f4_non_gst]`) | ✅ auto (`test_line_tax_matches_frontend_fixture[f4_non_gst_line_zero_rate]`) | ✅ auto (shared fixture) | |
| 5 | F5 | AFTER_TAX discount ₹10 on ₹100@18% | Tax 18; grand 108 | ✅ auto (PDF test `[f5_after_tax_discount]`) | ✅ auto (`test_document_tax_parity_fixture[f5_after_tax_discount]`) | ✅ auto (shared fixture) | |
| 6 | F6 | BEFORE_TAX discount ₹10 on ₹100@18% | Taxable 90; tax 16.20 | ✅ auto (`test_pdf_totals_match_db_odd_paise_and_before_tax[f6_before_tax]` — render→extract→assert vs DB) | ✅ auto (`test_document_tax_parity_fixture[f6_before_tax_discount]` + `test_before_tax_invoice_discount_reduces_gst`) | ✅ auto (shared fixture) | |
| 7 | F7 | Round-off on / off | Matches matrix | ✅ auto (PDF test `[f7_round_off_on]` / `[f7_round_off_off]`) | ✅ auto (`test_document_tax_parity_fixture[f7_round_off_on/off]` + `test_auto_round_off_can_be_disabled`) | ✅ auto (shared fixture) | |
| 8 | F8 | Multi-rate 5% + 28% | Accumulates | ✅ auto (PDF test `[f8_multi_rate_5_28]`) | ✅ auto (`test_document_tax_parity_fixture[f8_multi_rate_5_28]`) | ✅ auto (shared fixture) | |
| 9 | F12 | Additional charges (freight/packing) GST | **Resolved 2026-09-09 (Scope revision, D9b/B11): non-taxable for the pilot** — charges add to `grand_total` without GST | ✅ auto (`test_additional_charges_are_non_taxable_for_pilot`, `test_additional_charges_untaxed_when_tax_disabled`) | ✅ same tests (DB-level, `compute_document_totals`) | n/a — labelled non-taxable in the FE line item, no separate FE fixture | still needs: is "documented non-taxable" acceptable to state to a pilot customer, or must the invoice UI say so explicitly? |

**Prerequisite:** BUG-204 fixed (PDF honors `invoice_discount_mode`) — **done**, all discount-mode rows above pass. Automated PDF assert (F11) now covers **all of F1–F8** (`backend/tests/test_pdf_and_share.py::test_pdf_totals_match_db_odd_paise_and_before_tax` for F3/F6, `::test_pdf_totals_match_db_ca_signoff_f1_f2_f4_f5_f7_f8` for the rest — all pass as of 2026-09-12).

**PDF template freeze:** declared 2026-08-01 on `wip/phase0` after P0-204b/P0-209 — do not change tax presentation without re-CA.

**What still needs a human:** the CA reviewing the live staging PDFs once (not just trusting the automated extraction) and signing; the F12 business-facing wording decision above; nothing else on this page.

CA name: ________________  Date: ________  Sign-off (F9): ________

B11 / F12 decision (tax additional charges / scope out): ________________  Initials: ________

Staging build / commit SHA: ________________  PDF template freeze date: ________

## Money In, Phase 2 (2026-10-11): items for the CA before they are switched on

Each setting is **off or warn by default** and changes nothing until the owner turns it on (Payments settings). The plan is `docs/plans/MONEY_IN_PHASE2_IMPLEMENTATION_PLAN.md`.

| # | Setting | What the CA confirms | Initials |
|---|---|---|---|
| 1 | Customer TDS on receipts (account **1270** "TDS Receivable (deducted by customers)") | The account head suits how the firm claims TDS (Form 26AS / certificates); the register at Reports, TDS receivable matches the 26AS entries | |
| 2 | **Advance GST** (`advance_gst_treatment = services`) | Services advances are taxable at receipt (Table 11A), adjusted at invoice (11B) including across months, and a refund of an advance needs a refund voucher (CGST s.31(3)(e)); the default rate; that the tax is **reported in GSTR-1 but not posted to the ledger** (the return page shows the difference) or that it should also be posted | |
| 3 | **Cash limit** (`cash_269st_mode`): off / warn / block | Whether Rs 2,00,000 or more from one person in a day should only warn (default) or be refused (s.269ST) | |
| 4 | Cheques held as advances until they clear (`cheque_allocation_on_clearance`) | The firm's practice on when a cheque counts as received | |
| 5 | Settlement discount | The discount is cleared against the bill when money is applied and posts to 5150 Settlement Discounts, split to the paisa across partial allocations | |

CA name: ________________  Date: ________  Sign-off: ________

## Money hub (2026-10-14) — items for the CA

Plan: [`../plans/MONEY_HUB_PLAN.md`](../plans/MONEY_HUB_PLAN.md). Nothing below posts to the ledger.

| # | Item | What the CA confirms | Sign-off |
|---|------|----------------------|----------|
| M1 | Tax dues wording (Money page, "Tax dues") | "TDS deducted on supplier bills" is the right label for the supplier-bill TDS worksheet total, due the 7th of the next month; "GST for the month (estimate)" is the GSTR-3B net-payable hint, due the 20th, and is clearly an estimate. Bizboard records no tax payment, so the page never says "unpaid". | |
| M2 | Cash and bank "now" counts cleared money only | A cheque received, or issued, is outside cash until it clears. The dashboard cash and the Cash Book now use the same rule. | |
| M3 | Advances paid to suppliers are shown beside payables, not netted off them | Netting would change supplier balances on the ledger, statements and credit checks; confirm whether it should, before it is built. | |
| M4 | TDS certificate received (Form 16A) | Recording it only marks the receipt as no longer awaiting its certificate; the 1270 balance is unchanged until the CA decides how the tax is claimed. Confirm that is the right split. | |
| M5 | Customers-owe-you basis | With books on and the GL basis ready, the figure follows accounts 1200 and 2300; otherwise it follows the bills. The page says which (badge) and shows the difference against the control accounts. Payables follow the same rule for the total, but each supplier's own balance is always from bills. | |

## Purchase review (2026-10-15) — items for the CA

Plan: [`../plans/PURCHASE_REVIEW_FIX_PLAN.md`](../plans/PURCHASE_REVIEW_FIX_PLAN.md). Review of the other
screens: [`../reviews/PURCHASE_OTHER_SCREENS_REVIEW_2026-10-15.md`](../reviews/PURCHASE_OTHER_SCREENS_REVIEW_2026-10-15.md).

| # | Item | What the CA confirms | Sign-off |
|---|------|----------------------|----------|
| P1 | Cancelling a paid purchase bill keeps the payment as a supplier advance | The bill's allocations are reversed on the cancel date and the payment (cash/bank entry) is left as it was, shown as an unallocated advance to that supplier. Confirm this is the treatment wanted, and that voiding the payment is a separate, deliberate step. | |
| P2 | Payment taken with the bill, when TDS is also set on the bill | The payment is allocated in full to the bill, and the existing rule still applies: a payment that carries its own TDS cannot be allocated to a bill that already has TDS. Confirm the editor should not offer both. | |
| P3 | Bill of entry with a zero assessable value | The server refuses a BoE with no BCD/IGST/cess but does not check the assessable value. Confirm whether a zero assessable value can ever be correct. (PB-01) | |
| P4 | Owner approval of a 3-way match difference on a purchase bill | The app now lets an Owner or Manager complete a bill that differs from its order or receipt, after writing a reason; the reason and the differences are stored in the audit log. Confirm that a written reason is enough for your audit trail. | |
| P5 | Releasing a cancelled-GSTIN hold (bill or payment) | An Owner or Accountant can complete a bill from, or pay, a supplier whose GSTIN is cancelled, after writing a reason. The system does **not** decide whether the ITC on such a bill is claimable. Confirm that claim is still reviewed separately (GSTR-2B / ITC eligibility). | |
