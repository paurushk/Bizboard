# For the CA: bills of supply from a regular-GST company in GSTR-1 and GSTR-3B

**Status:** options B + A are **built behind the company flag `GST_BILL_OF_SUPPLY_RETURNS`, off
for every company** (founder decision D-14, 2026-10-25). Nothing changes for anyone until the CA
agrees and the flag is turned on for a company. If the CA prefers another treatment, the flag
stays off and we change the code first. Found in the BB-100 walk-through (finding F2,
`docs/reviews/BB100_JOURNEY_WALKTHROUGH_2026-10-24.md`).

## What happens today

A company registered as a **regular** GST taxpayer can still issue an invoice of type
**"Non-GST invoice"** (a bill of supply, `invoice_type = NON_GST`). For example, a shop that also
sells exempt goods.

The GSTR-1 and GSTR-3B worksheets read only the invoice types GST, TAX and RETAIL
(`GST_INVOICE_TYPES`, `backend/reporting/gst_returns.py`). So a completed Non-GST invoice:

| Worksheet table | Included? |
| --- | --- |
| GSTR-1 B2B / B2CL / B2CS / HSN | No (correct: no tax on it) |
| GSTR-1 Table 8 (nil-rated, exempt, non-GST) | **No** |
| GSTR-1 Table 13 (documents issued) | **No**, neither in the count nor in the number ranges |
| GSTR-3B 3.1(c) nil-rated and exempt, 3.1(e) non-GST | **No** (built from the same Table 8 figures) |
| Sales register and the dashboard | Yes |

The worksheet notices the gap and shows: *"Worksheet totals do not tie to the sales register.
Difference: …"*. It does not say why.

**Seen on the load-test company, October 2026:** 207 completed Non-GST invoices worth ₹23,860
were missing from Tables 8 and 13. The worksheet showed outward value ₹160 against ₹24,020 in the
sales register.

Lines on a GST invoice already carry their own nature (TAXABLE, NIL, EXEMPT, NON_GST). Nil, exempt
and non-GST lines on a **GST** invoice do reach Table 8 and 3.1(c)/(e) today. Only whole
**Non-GST invoices** are left out.

## Questions for the CA

1. For a regular taxpayer, should a bill of supply's value appear in **GSTR-1 Table 8**? If yes,
   under which column: nil-rated, exempted or non-GST? Should it be decided per line (each line's
   nature) or per invoice?
2. Should those bills count in **Table 13**? If yes, on which document line, and as their own
   number series?
3. Should the same values reach **GSTR-3B 3.1(c)** (nil-rated and exempt) or **3.1(e)** (non-GST)?
4. Should a regular taxpayer be allowed a Non-GST invoice that contains a **taxable** item at all?
   Today it is allowed, and the tax on it is simply not charged.

## Options the product can take (pick one; each is a small change)

| Option | What changes | Effect |
| --- | --- | --- |
| **A. Report them** | Non-GST invoices of a regular company go to Table 8 by each line's nature, or as "exempt" when the line is TAXABLE. They count in Table 13 and flow to 3B 3.1(c)/(e). | The worksheet ties to the sales register |
| **B. Block taxable lines** | A regular company's Non-GST invoice may hold only nil, exempt or non-GST lines; then option A reports them | Stops tax being dropped by choosing the wrong invoice type |
| **C. Keep as is, explain** | Nothing is added to the return; the mismatch warning names the Non-GST invoices and their total | The CA adds them by hand |

Our suggestion, for the CA to confirm or overrule: **B, then A.** (Built, flag off.)

**What the flag does today:** completing a Non-GST invoice of a regular company is refused while any
line is still TAXABLE; Non-GST invoices (and their cancellations) are read by GSTR-1, so their lines
go to Table 8 by nature and they are counted in Table 13; GSTR-3B 3.1(c)/(e) follow. A line saved
as TAXABLE before the flag was on is reported as **exempt**. Credit and debit notes against Non-GST
invoices are still left out; tell us if they should be reported too. Past periods change only when their worksheet is
re-run with the flag on.

**CA decision:** _____________________ **Date:** __________ **Name:** __________________
