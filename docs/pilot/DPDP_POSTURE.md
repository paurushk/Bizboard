# DPDP / app-sec posture (X-02)

This is an **honest product posture note**, not a certified DPDP audit, not a GDPR-grade erasure program, and not legal advice.

## What we store (pilot categories)

| Category | Examples | Where |
|---|---|---|
| Identity | owner email/phone, staff accounts | `accounts.User` |
| Party PII | customer/supplier name, phone, GSTIN, address | `masters` |
| Money documents | invoices, challans, receipts, GSTR JSON | `sales` / `purchases` / `reporting` |
| Files | invoice PDFs, import CSVs, bill photos | `core.FileAsset` |
| Comms | WhatsApp send status, dunning reminders | `sales` / `payments` |
| Telemetry | shop-floor events **without** GSTIN/phone | `insights.ShopFloorEvent` |

## Consent / opt-in (already product gates)

- **WhatsApp Cloud** send requires `Customer.whatsapp_opt_in=True` (default False). `wa.me` open-in-app is user-initiated and is not Cloud API.
- **AR dunning** requires company `dunning_enabled` (Owner, default off) and does not message customers with `dunning_opt_out=True`.
- LLM / bill-import remains Owner-gated (`ai_features_enabled`). Do not send Cloud WhatsApp or SMS dunning without those fields.

## Subprocessors (typical pilot)

Razorpay (payments), GSP (e-invoice / returns when live), Meta Cloud WhatsApp (only if Cloud send is enabled). Exact processors for a host are ops-owned.

## Retention

Pilot: retain operational data for the life of the company record unless a deletion request is processed by support. GST returns and invoice PDFs are statutory; do not silently purge a filed month.

## Access

Invoice PDFs and GSTR files are served only through authenticated, company-scoped API routes. PDF download writes an `AuditEvent` (`SalesInvoicePdf`). Cross-tenant IDs 404.

## Export / delete requests

Full erasure is a later charter. During pilot, export/deletion is a **support ticket**: see onboarding privacy line and `ENV_CHECKLIST.md` E10. Do not claim automated GDPR delete.

## Privacy notice

Operator publishes a privacy notice URL for the pilot host (settings / onboarding). Unsigned legal copy must not be invented here.

## What this is not

- Not a DPDP certification
- Not a DPIA
- Not consent for every subprocessors' own policies — operators must complete KYC/Meta/GSP paperwork
