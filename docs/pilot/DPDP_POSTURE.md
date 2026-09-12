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

---

## Control review record (QOS-0049)

Each control below was re-verified against the current tree on **2026-09-11**.
This records that the review happened; the data-protection owner still signs off.

| Control | Verified against | State |
|---|---|---|
| Party PII / files / GSTR served only via authenticated, company-scoped routes; cross-tenant IDs 404 | `tests/tenancy/`, `test_freeze_gate_contracts.py` (tenant-scoped download), `personas-golden.spec.ts` (live IDOR 404) | ✅ tested |
| PDF download writes an `AuditEvent` | `SalesInvoicePdf` audit event, `audit.statutory_events_present` | ✅ tested |
| Audit log is append-only (no update/delete path) | `test_freeze_gate_contracts.py` — audit viewsets have no Create/Update/Destroy mixin | ✅ tested |
| Request-log PII masking (no query string / doc number / body) | `test_freeze_gate_contracts.py::test_request_log_masks_ids_and_carries_no_body` | ✅ tested |
| WhatsApp Cloud send gated on `Customer.whatsapp_opt_in` (default False) | `payments` / `sales` send path; flag `ENABLE_WHATSAPP_CLOUD=0` in pilot | ✅ code + flag-off |
| AR dunning gated on `dunning_enabled` + `dunning_opt_out` | `test_wf42_dunning_schedule`, `payments/dunning.py` | ✅ tested |
| Automated right-to-erasure — cascade over every `company` FK; statutory carve-out; immutable `TenantErasureLog` | `accounts/erasure.py`, `test_erasure.py`, `tenancy.no_orphans_after_erasure`, `assert_erasure_model_coverage` drift guard | ✅ tested |
| Tombstone mode scrubs party PII, keeps statutory docs, `purge_tombstoned_companies` after the 8-yr window | `test_erasure.py` (tombstone path), `QOS-0074` (accepted behaviour) | ✅ tested |
| Data-subject export = exactly one company's data | tenancy assertion on the export payload (`tests/tenancy/`) | ✅ tested |
| Statutory retention — a filed month is not silently purged | closed-period gate (`A21`), erasure statutory carve-out | ✅ tested |
| Subprocessor list / privacy-notice URL / KYC paperwork | ops-owned per host | ⬜ ops action, not code |
| Boot-time secret validation (`DJANGO_FAIL_FAST_SECRETS`) | `test_freeze_gate_contracts.py::test_fail_fast_secrets_rejects_weak_secret_key` | ✅ tested |

**Sign-off:** ____________________  Date: __________  (data-protection owner)
