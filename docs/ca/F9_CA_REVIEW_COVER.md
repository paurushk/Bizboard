# F9 — CA Tax Invoice Review Cover Sheet

**What this is:** a short cover note for sending
[`CA_SIGN_OFF_CHECKLIST.md`](CA_SIGN_OFF_CHECKLIST.md) to an independent practising CA for
review. That checklist covers 9 GST tax-invoice scenarios (F1–F8, F12) from Bizboard's frozen
Tax Invoice PDF template. This is **Go/No-Go**'s F9 gate in
[`../pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) ("CA letter stored (F9) + F12 additional-charges
scope").

## What's already done (so the CA's job is narrow)

Every row in the checklist already has automated evidence — a real, currently-passing test that
renders the actual PDF and computes the actual DB totals for that exact scenario (see the
"guard reference" named in each row, dated 2026-09-12). This is **not** asking the CA to
re-derive the tax math from scratch; it is asking them to:

1. Look at the actual rendered staging PDFs for the 9 scenarios (attach or link them here — regenerate
   from staging with the frozen template, see Phase 0 plan §7.2) and confirm the layout, wording, and
   numbers are what a real GST tax invoice needs.
2. Confirm the **F12 decision is acceptable to state to a pilot customer**: additional charges
   (freight/packing) are treated as **non-taxable** for the pilot rather than taxed per rule. This is
   a business/compliance call, not a code question — flag if this needs to change before real invoices
   go out.
3. Sign the checklist (name, date, F9 sign-off) and initial the F12 decision line.

## The ask

> **Does this Tax Invoice template, with the 9 attached sample scenarios, satisfy GST invoice
> requirements as you understand them for a business issuing these documents to real customers?**

Please answer, in writing, on the checklist itself:

1. Is CGST+SGST vs IGST split correct on the intra-/inter-state samples (F1, F2)?
2. Is odd-paise rounding (F3) presented in a way you're comfortable with?
3. Do the BEFORE_TAX / AFTER_TAX discount samples (F5, F6) show the discount and tax correctly?
4. Is the NON_GST sample (F4) unambiguous that no tax applies?
5. Is the multi-rate sample (F8) itemised clearly enough to audit?
6. Is the F12 non-taxable-charges treatment acceptable, or does it need a compliance caveat on the
   invoice itself?
7. Overall: **sign-off / sign-off with conditions / cannot sign — say what's missing.**

## Scope notes (state to the CA)

This reviews the **Tax Invoice PDF template and its GST math**, not GST return filing (that's a
separate exercise — see [`H05_CA_REVIEW_COVER.md`](H05_CA_REVIEW_COVER.md)) and not live
e-invoice/IRN generation (out of pilot scope per `docs/FREEZE_SCOPE.md`).

## Record

| Field | Value |
|---|---|
| CA name / firm | |
| Membership no. | |
| Staging build / commit SHA | |
| PDF template freeze date | 2026-08-01 |
| Date reviewed | |
| Verdict | SIGN-OFF / SIGN-OFF WITH CONDITIONS / CANNOT SIGN |
| Conditions / blocking issues | |
| Signature | |
