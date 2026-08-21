## Sprint 6 remaining Dark / Defer (2026-08-05)

## Wave 22 limitations (2026-08-06)

| Area | Limitation |
|------|------------|
| Sales RCM | GSTR excludes; GL still posts Output GST |
| Multi-GSTIN 3B | Stamp resolved from empty list |
| FIFO cancels | Challan/PI/transfer/return peel wrong layers |
| SaaS billing | ACTIVE without pay; no-sub never blocked |
| PWA | Caches authenticated /api |
| Payroll | Employer PF/ESI not in GL |
| GRN | Not implemented |

| Area | Status | IDs |
|------|--------|-----|
| Tenant backup / restore API | **Shipped** — Owner encrypted export + sandbox restore. Nightly dumps (`scripts/backup.sh`) remain distinct | BB-000668 |
| Recurring invoices | **Shipped** — DRAFT-only beat; never auto-Complete | BB-000669 |
| SaaS entitlements | **Shipped MVP** — plans/subscriptions/Razorpay webhook + write gate | BB-000671 |
| FY close IS→RE | **Shipped** — zeros 4xxx/5xxx to 3100; does not close 3200 | BB-000664 |
| Live NIC / IRP protocol | **Protocol layer + Final Gate** — fail-closed until `GSP_CERTIFIED=1` + `GSP_LIVE_ENABLED=1` (Sprint E) | BB-000624 |
| Native store apps | **Android shell** — Play internal testing README; no iOS App Store binary | BB-000575 |
| PWA offline install | **SW + offline.html** — no iOS background-sync guarantee | BB-000580 |
| Outbox encryption | **Honesty** — plaintext + logout wipe + warning | BB-000572 |
| PhasePages remainder | **Tech-debt** — split into Banking / Inventory / AccountingExtra; invoice/purchase editors still large | BB-000630 |
| FIFO+WO load evidence | **Unproven** | BB-000592 |
| Mega FE typing | **Docs** — sales/purchases still untyped vs manufacturing typedClient | BB-000579 |

# Known Limitations and Tech Debt

## Remediation close-out (2026-08-05)

Open BB-000550–BB-000694 closed as Fix, Dark (flag+404+unclaim), or product-shipped former L-items (TDS/recurring/SaaS/DR/FY close). Live NIC stays fail-closed pending certified GSP. ERP preview modules stay dark unless `ENABLE_*` env + company `feature_flags` JSON (+ plan entitlements when subscribed). Capacitor Android is a WebView shell, not a store listing. RLS remains off.

## Sprint 4–5 Dark / Defer honesty (2026-08-05)

| Area | Status |
|------|--------|
| Manufacturing | Preview: ISSUE/RECEIPT + BOM snapshot on release + FG FIFO/issue cost + WIP GL 1450 when accounting on. Flag off + 404 outside tests. Not a full MES. |
| Payroll | Preview: PF/ESI/PT on complete + GL liabilities when flag on. TDS MVP under `ENABLE_TDS` (BB-000670). Not a full HRMS. |
| CRM | Preview: convert + LeadActivity timeline when `ENABLE_CRM`. Flag off + 404. |
| RLS | **Stay off** (`POSTGRES_RLS_ENABLED=0`). SET SESSION ready; compose role is superuser. |
| WhatsApp | Per-tenant Owner CRUD; no global token; approved templates else `wa.me`. |
| Tally | One-shot **export dump** — not live sync. Full incremental **Defer**. |
| OCR / AI reports | No invented gst_rate/qty; net sales; outstanding AP aging; layer valuation; WH/GSTIN filters. |
| Live NIC | **Defer** — prod submit blocked. |

## Wave 21 limitations (2026-08-05)

| Area | Limitation |
|------|------------|
| Multi-company | Consent join for existing users in Sprint 3; X-Company-Id must match active |
| Multi-branch | CompanyGstin CRUD in Sprint 3; filing still stamp-scoped |
| Invite | Password optional; invite_token omitted in prod/staging JSON (out-of-band); OWNER invite blocked |
| TDS/TCS / recurring / SaaS billing | **Shipped MVP** — see Sprint 6 table (BB-000669/670/671) |
| FY close | **Shipped** IS→RE 3100 (BB-000664); CA Final Gate still required for 10/10 |

## Wave 20 limitations (2026-08-05)

| Area | Limitation |
|------|------------|
| Multi-GSTIN IRP | Protocol adapter + Final Gate; fail-closed until `GSP_CERTIFIED` (BB-000624) |
| e-Way challan | Distance required (`transport_distance_km`); fail-closed if missing |
| Credit notes | Note IRN actions + UI panel; still blocked when invoice paid where applicable |
| File storage | Magic MIME fail-closed; download filename sanitized |

## Wave 19 missed limitations (2026-08-05)

| Area | Limitation |
|------|------------|
| accounting_enabled | GST Complete broken (BB-000599) until field-name fix |
| Cess | Documents only — not GL/IRP lines/inclusive/RCM |
| FIFO | Cancel/transfer/COGS peel unsafe |
| Prod auth | Cookie mode unshippable without CSRF+SPA change |
| AA | Empty ingest injects mock bank data |
| SOFT_CLOSED | Does not block or warn on Complete |

## Wave 19 living limitations (2026-08-05)

| Limitation | Honest status now |
|------------|-------------------|
| Manufacturing | **Preview** — ISSUE/RECEIPT + BOM snapshot + FG issue cost + WIP GL; flag-gated |
| Payroll | **Salary voucher MVP** — immutable completed runs; no PF/ESI/PT/TDS |
| CRM | **Dark** — lead notebook; no convert/activities; flag off |
| Multi-GSTIN | **Stamp-scoped** GSTR-1/3B + series-per-GSTIN + CompanyGstin CRUD. IRP uses stamp. Live NIC still Deferred |
| RLS | **Stay off** — SET SESSION ready; superuser compose role; do not enable |
| Mobile | **Capacitor config + manifest** — no store binary, no SW |
| WhatsApp Cloud | **Optional per-tenant** — no global token; approved templates or wa.me |
| OCR | **Assistive** — unknown rate/qty excluded (not invented) |
| GSTR-9 | **Worksheet aid** — tables 6/7 from claimable books ITC / purchase CN; not a full annual engine |
| FIFO | **Code path exists** — load-unproven with WO+POS |
| Final Gates | **Ops/CA unsigned** — blocks any 10/10 claim |


**Date:** 2026-08-02

## Product limitations (by design or incomplete)

| Limitation | Notes |
|------------|-------|
| No Manufacturing / BOM / WO | Not in codebase |
| No Payroll | Not in codebase |
| No CRM pipeline | Customer master only |
| No multi-company / multi-GSTIN branch | One active membership; warehouses ≠ legal branches |
| No native mobile app | Responsive web |
| WhatsApp = `wa.me` link | Not Business API |
| E-invoice/e-way = sandbox | No NIC HTTP |
| GSTR = offline aids | Not GSTN upload; `gst-filing-sandbox` 404 in prod/staging without `GSP_CERTIFIED` (no live filing adapter) |
| No GSTR-2A/2B match | ITC provisional at best |
| Composition returns absent | CMP-08/GSTR-4 missing |
| No cess / export / SEZ modes | Domestic B2B/B2C focus |
| GL optional & incomplete | Return COGS reverse missing (BB-000380); openings/advances dual-ledger (BB-000381/382) |
| Challan may move stock | When `stock_on_delivery_challan`; serial path incomplete (BB-000403); cancel/invoice bridge gaps (BB-000404) |
| SO may reserve stock | FEFO reserve exists; rebuild_balance corrupts lot reserved (BB-000402) |
| FIFO valuation incomplete | Setting does not drive COGS — blended cost used (BB-000401) |
| AI is assistive | Tax-refusal regex bypassable (BB-000405); default-on risk (BB-000420) |
| Live e-Invoice/e-Way | Production adapters always raise not-enabled (BB-000384) |
| Sandbox payments | Settings PATCH banned in prod; create/webhook paths still settle (BB-000379) |

## Technical debt (active)

See [19_TECHNICAL_DEBT.md](./19_TECHNICAL_DEBT.md) and Low/Medium issues in MASTER_ISSUE_REGISTER.

## Historical catalogs

- `bugs/INDEX.md` — 202 findings (2026-07-25); many Wave0-fixed — re-verify before work.
- Root `BUG_REPORT.md` / `SECURITY_REPORT.md` / etc. (2026-07-24) — **Historical**.

## Positive invariants to preserve

- Decimal money; CGST/SGST residual split.
- Append-only stock; company-scoped queries.
- Document-derived AR/AP.
- Postgres concurrency tests in CI.

---

## Wave 9 additions (2026-08-03)

| Limitation | Issue |
|------------|-------|
| Sandbox webhook signature still `ok` | BB-000258 |
| Company PATCH can re-enable gateway test_mode | BB-000259 |
| Cancel sales return orphans auto CN | BB-000260 |
| Sales DN / purchase notes / purchase returns missing GL | BB-000261–263 |
| Spoofable `notes=TALLY_OPENING` | BB-000264 |
| Access JWT still localStorage | BB-000266 |
| CoA/periods HasCompany-only | BB-000267 |
| B2CL threshold still ₹2.5L (law ₹1L) | BB-000274 |
| Challan-origin invoices skip COGS | BB-000270 |
| FE assume-local tax preview mismatch | BB-000277 |
| FIFO setting does not drive sale COGS | BB-000281 / BB-000062 |

Stock reservation and challan stock movement exist in code; prior table rows above that say otherwise are **historical** — prefer Wave 9 register.
- No raw SQL / no csrf_exempt in app code.


## Wave 8 (2026-08-03)

Added known limitations: payment adapters may stub/sandbox; purchase H9 incomplete; journals not SoD-gated; celery health ≠ worker liveness.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.

---

## Wave 14 P0 closure (2026-08-04)

Resolved BB-000456–462, BB-000544, BB-000548. Beat epoch+Redis key; refund REFUNDED+link reopen; disposal 5600/5700; return COGS SALE cost; SQLite prod refuse; `_wave14_assert_gates.py`. Open residual P1+ remain.

### Still Open (P1+ examples — not closed in P0 wave)

| Limitation | Register |
|------------|----------|
| `fetchAllPages` still wired for money lists | BB-000463 |
| `web/nginx.conf` still `unsafe-inline` CSP | BB-000464 |
| Live GSP / 2B / Manufacturing / Payroll / CRM / native mobile | BB-000384 / 406 / 035 (Deferred) |
| Purchase return cancel lot asymmetry | BB-000545 |
| Dual JWT auth stack outside prod cookie-only | BB-000547 |

