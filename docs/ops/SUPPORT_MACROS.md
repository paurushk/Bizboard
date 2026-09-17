# Support reply macros (16.5)

Paste and fill the bracketed bits. Do not add GST filing claims, impersonation
offers, or legal language. Align with `docs/pilot/FAQS.md` and
`docs/ops/PRODUCT_BEHAVIORS_FOR_COUNSEL.md`.

## money-wrong

We will not ask you to Complete the same invoice twice. Send the invoice
number, the PDF total, and the ledger line that looks wrong. If the period is
closed we cannot back-date; H9 amends price, not quantity.

## cannot-complete

The Complete button shows a Help code when a freeze rule blocks the post
(stock, GSTIN, closed period, credit hold). Copy the code from the red
banner. Do not retry Complete until that code is gone.

## gst-worksheet

BizBoard GSTR-1 / GSTR-3B are **offline worksheets**. File on the GST portal
yourself. We do not submit returns or generate a live IRN in the freeze.
If you need the JSON, export from Reports → GST worksheets.

## freeze-exception (payroll / CRM / GSTR screens / Tally live)

Those modules stay dark on freeze hosts. Paid plans do not turn them on.
If this is a signed exception, Ops uses `docs/ops/FREEZE_EXCEPTION.md` —
support cannot flip the flag from chat.

## login-access

There is no staff login-as-you. Reset password or request a new OTP if SMS
is enabled on your host. If OTP is off, use email + password.

## billing-saas (subscription, not customer receipts)

SaaS billing (trial, seats, Razorpay subscription) is separate from customer
collections (AR). Send the company name and the Razorpay subscription id, not
a sales invoice number.

## import-cutover

Use the Excel templates (not CSV). Re-import of the same SKU / party is
rejected as a duplicate. Cutover counts: `python manage.py cutover_recon`.
