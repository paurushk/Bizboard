# Pilot FAQs (17.2)

Answers match freeze A1–A26 / Table B / C1–C8. Not tax advice, not a contract.

## What BizBoard does in the freeze

Sales invoices (intra/inter/non-GST), quotations → invoice, sales returns /
credit notes, purchases and purchase returns, product lookup, stock movements,
receipts and supplier payments with allocation, ledgers, core reports, A4 PDF,
Excel/CSV imports (idempotent), exports, Owner/Admin vs Sales Staff RBAC,
tenant isolation, setup wizard, login (password + OTP when SMS is configured),
period close + H9 price correction, decimal money, counter POS, TDS/TCS on
documents, sandbox online collection (Cashfree or PayU).

## What it does not do (Table B)

GSTR **screens / GSTN filing**, live NIC e-invoice, manufacturing, payroll, CRM,
Tally live sync, WhatsApp Cloud API, Account Aggregator, native app-store apps,
multi-GSTIN, full perpetual FIFO COGS. Paid plans must not turn those on.

## GST returns

GSTR-1 / 3B in product are **offline worksheets**. File on the GST portal
yourself (C1). e-invoice preview is **not** a filed IRN (C2).

## Stock costing

Running weighted cost, not FIFO layers (C3).

## Books

Accounting is opt-in per company (`accounting_enabled`) (C4).

## Offline drafts

Plaintext on the device; sign-out wipes them (C5).

## OTP

Needs `SMS_PROVIDER=msg91` or `twilio` on the host. Otherwise use password (C6).

## Online payments

Sandbox only during pilot (C8). Webhook replay is a no-op.

## Support will not

Log in as you. There is no impersonation. They can look at logs and ask you to
reproduce. Erasure / DPDP deletes follow the operator playbook, default off.

## Money errors

Do not complete the same invoice twice. PDF 409 means “still generating” — wait
or Regenerate PDF. Closed period rejects back-dated posts; H9 amends price, not qty.
