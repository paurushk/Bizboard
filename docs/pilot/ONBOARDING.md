# Pilot onboarding (Phase 0)

Product setup wizard design: [`docs/onboarding/NEW_USER_ONBOARDING_PLAN.md`](../onboarding/NEW_USER_ONBOARDING_PLAN.md).
When `ENABLE_SETUP_WIZARD=1`, the product path is Register → Login → `/setup`;
when off, onboarding remains checklist-only.

1. Create Owner account / use seeded pilot user (`seed_pilot_fixtures`).
2. Set Company + GST settings (state, GSTIN). **Save errors are shown — do not leave GSTIN blank if GST-registered.**
3. Import CSV (products/customers/suppliers) via Settings → Import — review preview errors before commit.
4. Record opening stock.
5. Create first purchase → Complete → verify stock.
6. Create multi-line quotation → convert → Complete invoice → wait for PDF (download may 409 while generating — retry).
7. Partial receipt + allocate.
8. Invite Staff with least privilege; verify export/cancel flags.

## Privacy (DPDP one-liner)

BizBoard stores customer/supplier names, phones, and GSTINs for your company only. Data is used to issue invoices and reports. Contact support for export/deletion requests during the pilot. Operator posture: [`DPDP_POSTURE.md`](DPDP_POSTURE.md). See `ENV_CHECKLIST.md` for operator controls.

## Completed invoice corrections (H9-A)

Owners may amend prices/discounts/charges on completed invoices with confirmation (audited). Quantities, products, and GST rates stay locked. Do **not** use returns to fix prices. Full Credit Notes arrive in Phase 1.

## Scope honesty

Pilot is **billing + inventory + derived ledgers**.

**Feature flags** (`web/.env.example`): GSTR reports, AI insights, Tally,
e-invoice sandbox submit, and accounting UI are off unless
`VITE_ENABLE_*` or `VITE_PILOT_ADVANCED` is set. Accounting also needs
`company.accountingEnabled`.

**Do not claim:** live GST portal / NIC e-invoice filing (sandbox submit is
preview only — not filed to GSTN), WhatsApp beyond share-link, full
Manufacturing / Payroll / CRM, or multi-company.
