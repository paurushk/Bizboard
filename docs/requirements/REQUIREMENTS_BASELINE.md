# Bizboard requirements baseline, release 1 (BB-004)

One signable statement of what release 1 is. It does not repeat the detail: each section names
the document that holds it, and that document stays the source of truth. Status as of
2026-10-23; the freeze scope (`docs/FREEZE_SCOPE.md`, ratified decisions D1–D17) is the base, and
§3 lists what was added after it.

## 1. Who it is for

Indian B2B traders first (ARCH-03 semi-wholesaler, ₹1–5 Cr, one GSTIN), then counter retail with
POS (ARCH-01) and multi-godown traders (ARCH-04). Users: owner, booker / counter staff,
in-house accountant, and the firm's practising CA. Personas and guardrails:
`docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md`; segments and channels: `SIGNOFF_PACK_2026-10-23.md` §B-12.

## 2. Supported workflows (release 1)

The 26 end-to-end workflows A1–A26 in `docs/FREEZE_SCOPE.md` §A, each mapped to passing tests in
`docs/FREEZE_SCOPE_COVERAGE.md`: GST sales (intra, inter-state, nil-rated), quotations, returns and
credit notes, purchases and debit notes, product lookup, stock movements and balances, receipts and
supplier payments with allocation, party ledgers, core reports, PDF invoices, imports and exports,
roles, tenant isolation, onboarding, sign-in, period close with corrections, money as fixed-scale
decimals, counter POS (D1), TDS/TCS (D2), sandbox online collection (D3) and OTP sign-in (D4).
Screen-by-screen flows: `docs/FLOW_CATALOG.md`; journeys: `docs/USER_JOURNEY_MAP_AND_IMPLEMENTATION_PLAN.md`.

## 3. Added since the freeze (supported, with their own plans and tests)

| Area | What | Plan / record |
|---|---|---|
| Sales | Sales orders, delivery challans, quick order entry, credit/debit notes, sales returns rework | `docs/QUICK_ORDER_ENTRY_*`, `CREDIT_NOTES_IMPLEMENTATION_PLAN.md`, `SALES_RETURNS_FIX_PLAN.md`, `docs/plans/QUOTATIONS_*` |
| Money | Money hub (receipts, payments, TDS certificates), cheque lifecycle | `docs/plans/MONEY_HUB_PLAN.md` |
| Purchases | Bill upload with extraction to a draft (D14 guards) | Bill upload review v2 |
| Inventory | Godowns, batches/expiry, serials, transfers, valuation (weighted average) | Inventory review plans |
| Accounting | Books per company, shadow books (ledger in the background), period close, GL parity checks | `docs/accounting/`, accounting screens plan |
| Home | Dashboard and Needs attention | Dashboard + attention programme |
| SaaS account | Plans, trial, quotas, plan changes with proration, UPI Autopay, Bizboard GST invoices, TDS credit, support tickets and read-only support access, ownership transfer and owner recovery, signed-in devices, Google sign-in, readable export, onboarding checklist, Busy/Vyapar/Marg import | `docs/roadmap/SAAS_FULL_PRODUCT_*`, handover |
| Operations | Error tracking (GlitchTip), alerts, uptime probes, backups incl. the tracker, staff pages in Django admin | `docs/ops/GLITCHTIP.md`, `ALERTS.md` |

Plan limits are enforced by the billing module (this supersedes D11's "not enforced in the pilot").

## 4. Built but off by default (switched on per company or per environment)

Manufacturing (`ENABLE_MANUFACTURING`), payroll, CRM, contracts, workshop/job cards, business
agents, AI insights, Tally import (per pilot, by support), Busy/Vyapar/Marg import (per company, by
support), fixed assets (D6), Bill of Entry (D10), WhatsApp Cloud API, extended GSTR screens. They
are not release-1 commitments; turning one on goes through `docs/ops/FREEZE_EXCEPTION.md`.

## 5. Not in release 1

GST portal filing and GSTN JSON, live e-invoice / e-way generation, GSTR-2B and IMS matching,
account-aggregator banking, native app-store builds, multiple GSTINs per company, FIFO cost layers
(`docs/FREEZE_SCOPE.md` §B). Composition dealers and material reverse-charge businesses are
screened out of the pilot (D8, D9).

## 6. Known limitations told to users

`docs/FREEZE_SCOPE.md` §C and the in-app **What this pilot does not do** page (`/limits`):
worksheets are not filing; e-invoice is preview only; stock cost is a running weighted average;
offline drafts are plaintext on the device; online collection is sandbox until a live gateway;
WhatsApp is a share link; Tally import has no live sync.

## 7. Business rules that must hold (where they are enforced)

| Rule | Enforced by |
|---|---|
| CGST/SGST vs IGST from place of supply; cess; TDS/TCS | Sales/purchase services; `FG-2c`; `docs/architecture/DECIMAL_ROUNDING.md` |
| Unique, sequential document numbers per company (per GSTIN and financial year where set) | `core/services/document_numbers.py`; unique (company, number) on every money document (`SCHEMA_REVIEW_2026-10-23.md`) |
| Stock balance = sum of movements, never negative where the company blocks it | `FG-2a/inventory`; inventory services |
| Every posting balanced; closed periods refuse back-dated money changes | `FG-2a/gl`; accounting services; GST period gate |
| One company never sees another's data | App-level scoping + Postgres row-level security (`tests/test_rls_coverage.py`) |
| Money is a fixed-scale decimal end to end | `FG-2a/money`; no float money field (schema review) |
| Owners, accountants and journal posters use two-step sign-in | `accounts/mfa_service.py` |

## 8. Non-functional requirements

| Area | Requirement | Where |
|---|---|---|
| Performance and availability | p95 targets and 99.5% availability | `docs/ops/SLO.md`, sign-off pack B-6 |
| Capacity | Scale thresholds | Sign-off pack B-7 |
| Backups and recovery | Nightly encrypted off-host, retention, RPO 15 min / RTO 4 h | Sign-off pack B-8, B-9; `scripts/backup.sh` |
| Security | Row-level security, MFA, rate limits on the real client address, no secrets in logs, CodeQL/Trivy in CI, independent pentest before launch | `docs/ops/STRIDE.md`, `core/log_redaction.py`, BB-144 |
| Privacy (DPDP) | Readable export, erasure with statutory retention (8 years), breach clocks | `docs/ops/DPDP_REQUESTS.md`, `INCIDENT_RESPONSE.md` |
| Language and devices | English and Hindi; desktop first; phone layouts; Android shell for pilots | i18n parity tests; `docs/ops/MOBILE_VERSION_POLICY.md` |
| Support | Severity targets | Sign-off pack B-10 |

## 9. Changing this baseline

New scope enters only through `docs/ops/FREEZE_EXCEPTION.md` with the founder's name and date; this
file is then updated in the same change.

## Sign-off

The founder confirms §2–§6 are what release 1 commits to, and the open ratification lines in
`docs/FREEZE_SCOPE.md` (sections A, B, C, G, H) are accepted as stated there.

Founder: ____________________  Date: __________
