# Pilot onboarding (Phase 0)

1. Create Owner account / use seeded pilot user (`seed_pilot_fixtures`).
2. Set Company + GST settings (state, GSTIN). **Save errors are shown — do not leave GSTIN blank if GST-registered.**
3. Import CSV (products/customers/suppliers) via Settings → Import — review preview errors before commit.
4. Record opening stock.
5. Create first purchase → Complete → verify stock.
6. Create multi-line quotation → convert → Complete invoice → wait for PDF (download may 409 while generating — retry).
7. Partial receipt + allocate.
8. Invite Staff with least privilege; verify export/cancel flags.

## Privacy (DPDP one-liner)

BizBoard stores customer/supplier names, phones, and GSTINs for your company only. Data is used to issue invoices and reports. Contact support for export/deletion requests during the pilot. See `ENV_CHECKLIST.md` for operator controls.

## Completed invoice corrections (H9-A)

Owners may amend prices/discounts/charges on completed invoices with confirmation (audited). Quantities, products, and GST rates stay locked. Do **not** use returns to fix prices. Full Credit Notes arrive in Phase 1.

## Scope honesty

Pilot is **billing + inventory + derived ledgers**. Not claimed: GSTR filing, e-Invoice, full accounting, Tally sync.
