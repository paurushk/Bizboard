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

**Scope revision 2026-09-09b (v1 shipped 2026-09-10):** automated right-to-erasure (D13) is built —
`accounts.erasure.erase_company` runs an export first, then an owner-initiated cascade that removes the
company and **every** row it owns (all 114 `company` FK relations; the three PROTECT audit tables are
deleted, not orphaned), and writes an immutable `TenantErasureLog` (numeric id + name + requester +
export checksum only — no party PII). A drift guard (`assert_erasure_model_coverage`) fails CI if a new
model gains an un-erasable `company` FK. Surfaces: `POST /company/erase/` (owner, echo the exact company
name) and `manage.py erase_company`.

**v1 keeps nothing.** The statutory-retention *tombstone* carve-out (retain anonymised tax documents for
N years, then purge) is **founder decision SR-40** and is NOT implemented. Until it is signed off the HTTP
endpoint stays behind `ENABLE_TENANT_ERASURE` (default OFF / 404) — the CLI command and the service are
available for a support-ticket-driven erasure in the meantime.

## Privacy notice

Operator publishes a privacy notice URL for the pilot host (settings / onboarding). Unsigned legal copy must not be invented here.

## What this is not

- Not a DPDP certification
- Not a DPIA
- Not consent for every subprocessors' own policies — operators must complete KYC/Meta/GSP paperwork
