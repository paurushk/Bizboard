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

**SR-40 signed 2026-09-10 — anonymised tombstone, 8-year retention.** The endpoint's default `mode` is
`tombstone`: every operational row is deleted, but the **statutory tax documents** (sales/purchase
invoices, credit/debit notes, returns, Bill of Entry, GST return snapshots + periods) are kept with all
party PII scrubbed — `Customer`/`Supplier` names → `[erased]`, phone/email/GSTIN/address blanked; the
`Company` row survives as a scrubbed placeholder with `erased_at` set. `manage.py
purge_tombstoned_companies` (daily) hard-deletes a tombstone once `erased_at` is older than the 8-year GST
retention window. `mode=hard` (CLI / purge job) keeps nothing.

`ENABLE_TENANT_ERASURE` stays **OFF by default** — flip it per deployment when erasure requests are handled
in-product; the CLI command works regardless for a support-ticket-driven erasure.

## Privacy notice

Operator publishes a privacy notice URL for the pilot host (settings / onboarding). Unsigned legal copy must not be invented here.

## What this is not

- Not a DPDP certification
- Not a DPIA
- Not consent for every subprocessors' own policies — operators must complete KYC/Meta/GSP paperwork
