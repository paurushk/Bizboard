# BizBoard — Phase 7: Ecosystem & Scale

**Status:** Phase 7.0 Tally import/export implemented; CompanyGstin + switch-company exist (7.2 remaining is PM isolation UAT). PAN/UDYAM format + HTTP sandbox shipped. Thermal 80mm and FY GSTIN series are in product. 7.4+ live India Stack / ONDC remain demand-gated.  
**Canonical path:** [`docs/phase7/PHASE_7_ECOSYSTEM_SCALE.md`](./PHASE_7_ECOSYSTEM_SCALE.md)  
**Root pointer:** [`PHASE7_IMPLEMENTATION_PLAN.md`](../../PHASE7_IMPLEMENTATION_PLAN.md)  
**Stack:** Django 5 + DRF (`backend/`) · React 18 + MUI (`web/`) · Celery + Redis · adapter pattern already used for GSP/IRP (`core/services/gsp_adapters.py`) · notifications (`core/services/notifications.py`) · imports pipeline (`imports/`) · tenancy via `company_id` (**must evolve** for multi-company).

---

## Start gate — do not scale a leaky core

Phase 7 attaches **migration magnets, messaging, tenancy expansion, and India Stack**. It amplifies whatever money/GST/AI quality already exists.

| Prerequisite | Source of truth | Why |
|--------------|-----------------|-----|
| Phase 0 Go + pilot money Criticals | [`docs/pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) | Importing Tally into a broken tenant multiplies pain |
| Phase 1 + Phase 2.0 exit (documents + GSTR aids) | Phase 1 / 2 docs | Migration customers expect GST-capable billing |
| Phase 6.0 alerts live **or** explicit PM waiver | [`docs/phase6/PHASE_6_AI_DIFFERENTIATOR.md`](../phase6/PHASE_6_AI_DIFFERENTIATOR.md) | Digests + WA Business need an insights payload |
| Paid pilot demand signal for each integration | Sales / support | Busy/Zoho/ONDC are **demand-gated** — do not build speculatively |
| Legal/DPDP review for KYC verifications & WhatsApp templates | External | India Stack + WA templates are compliance-heavy |

**Sequencing principle:** **Tally import (migration)** and **WhatsApp Business (retention)** can start before multi-company. **Multi-company / multi-branch** is an architecture wave that unlocks multi-GSTIN (Phase 2 D13 debt). **Manufacturing BOM**, **ONDC**, **DigiLocker / Aadhaar eSign** stay Future until ICP expands.

### Plan map

| Document | Role |
|----------|------|
| Phases 0–2 | Core billing + GST readiness |
| Phase 6 | AI insights on transactions |
| **This file** | **Phase 7** — ecosystem & scale |
| MVP §19 historical backlog | Tally, multi-company, POS, manufacturing, WA Business |

### Headcount / calendar (solo senior full-stack — demand-gated)

| Wave | Duration | Gate |
|------|----------|------|
| Phase 7.0 — Tally import/export (migration magnet) | ~6–8 weeks | ≥ 5 pilots asking to leave Tally |
| Phase 7.1 — WhatsApp Business API | ~4–5 weeks | Meta Business verification ready |
| Phase 7.2 — Multi-company / multi-branch | ~8–10 weeks | Customer with 2+ GSTINs or branches blocked |
| Phase 7.3 — POS mode + recurring invoices | ~5–6 weeks | Retail counter pilots |
| Phase 7.4 — India Stack verifications (PAN, GSTIN, UDYAM) | ~3–4 weeks | Overlaps OK with 7.1 after provider pick |
| Phase 7.5 — Busy / Zoho adapters | ~4–6 weeks **each** | Only when demand appears |
| Phase 7.6 — ONDC / DigiLocker / Aadhaar eSign | TBD | Explicit Future |
| Phase 7.7 — Manufacturing BOM | TBD | PRD Future; ICP = manufacturers |
| **If all 7.0–7.4 sequential** | **~26–33 weeks** | Parallelize only with headcount &gt; 1 |

**Pragmatic first year:** 7.0 + 7.1 + 7.4 (+ start 7.2 design). Defer Busy/Zoho/ONDC/BOM until signals clear.

---

## 0. Current-state snapshot (as of 2026-08-02)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| CSV/Excel import pipeline | ✅ `imports/` | ✅ import UX | Masters + bills; not Tally XML |
| LLM purchase-bill extract | ✅ | ✅ | Unrelated to Tally |
| WhatsApp share | `wa.me` link only | Share buttons | **Not** Business API |
| SMS | Console stub | OTP | Not production SMS |
| GSTIN verify | Adapter + `NullGstinProvider` | Verify actions | Live provider Phase 2.1 track |
| Multi-company membership | Blocked by `uniq_active_membership_per_user` | Single company context | **Architectural lock** |
| Branches / warehouses | ❌ | ❌ | Single warehouse MVP lock |
| POS mode | Barcode/SKU search only | Fast billing partial | Full POS later (MVP §19) |
| Recurring invoices | ❌ | ❌ | Missing |
| Tally / Busy / Zoho | ❌ | ❌ | Deferred everywhere |
| PAN / UDYAM verify | ❌ | ❌ | Missing |
| ONDC / DigiLocker / eSign | ❌ | ❌ | No prior art |
| Manufacturing / BOM | ❌ | ❌ | MVP excludes manufacturers |
| Payment gateway / bank recon | ❌ | ❌ | Record-only payments |

**Patterns to extend:**

- Integrations = **Protocol adapters** (same shape as `gsp_adapters.py`) + encrypted company credentials
- Imports = reuse `ImportJob` status machine (Upload → Validate → Preview → Commit → Error report)
- Notifications = extend `NotificationService` channels; keep honesty when channel stubbed
- Tenancy changes = migrate carefully; every `CompanyScopedModel` assumes one company — branch may be nullable FK later
- Never claim Tally/Vyapar parity in onboarding until adapters certified

---

## 1. Locked product decisions

| # | Decision | Lock |
|---|----------|------|
| D1 | **Tally first** among desktop accounting migrations; Busy/Zoho only on written demand | Shared `AccountingMigration` interface; Tally is reference impl |
| D2 | Tally **import** = masters + opening outstanding + optional stock; **export** = voucher/daybook CSV/XML aid for CA — not live two-way sync in 7.0 | Bi-directional sync = later epic |
| D3 | WhatsApp Business = **template messages** for invoice link, payment reminder, daily summary | Free-form chat bot = out of 7.1 |
| D4 | Multi-company = user may have **multiple active memberships**; UI company switcher; JWT/session carries `active_company_id` | Drop/replace `uniq_active_membership_per_user` with careful migration |
| D5 | Multi-branch / warehouse = optional `Branch` under Company; documents gain nullable `branch`; stock balances become `(company, branch, product)` | Default branch auto-created for existing tenants |
| D6 | Multi-GSTIN = **one GSTIN per Company** still preferred; multi-GSTIN org = multiple Companies under an `Organization` | Avoid filing hell inside one Company (honors Phase 2 D13) |
| D7 | POS mode = dedicated fast UI + optional hardware barcode; same `SalesInvoice` documents underneath | No separate POS ledger |
| D8 | Recurring invoices = schedule creates **draft** invoices; Owner/Staff confirms Complete | Never auto-Complete money without human (pilot default) |
| D9 | India Stack 7.4 = **PAN + GSTIN + UDYAM** verify adapters; soft-fail allow save + Health/Insights alert | No Aadhaar eKYC storage of raw biometrics |
| D10 | ONDC / DigiLocker / Aadhaar eSign = **Future** — design hooks only (credential slots, event names) | No build until PM charter |
| D11 | Manufacturing BOM = **Future** — requires inventory multi-level + production orders | Out of trader ICP |
| D12 | All external credentials encrypted at rest (reuse GSP secrets pattern) | Owner-only manage |
| D13 | Adapter failures never block billing Complete | Degrade to manual / link share |
| D14 | Scale work in this phase = indexes, export pagination, Celery isolation, load test harness — not Kubernetes | Stay on Compose / Lightsail-class deploy |

---

## 2. Scope split — waves

### Phase 7.0 — Tally import/export (migration magnet)

**Why first:** Highest acquisition lever for shops already on Tally.

**Import (guided wizard):**

1. Upload Tally export (XML / Excel daybook — lock format in Q1)  
2. Map ledgers → Customers / Suppliers / Products  
3. Preview opening AR/AP and stock  
4. Commit via existing import job + document/opening services  
5. Error report download  

**Export:**

- Masters CSV  
- Sales/purchase register export already exists — add **Tally-friendly voucher CSV/XML** labeled “for CA import aid”  
- Disclaimer: not certified Tally sync  

**New:** `integrations` app or `imports/tally/` package + `TallyAdapter` protocol.

### Phase 7.1 — WhatsApp Business API

- Provider adapter (`WhatsAppProvider`: Meta Cloud API first)  
- Template catalog: `invoice_ready`, `payment_reminder`, `daily_summary`  
- Opt-in / opt-out fields on Customer + Company WABA config  
- Replace pure `wa.me` for **automated** sends; keep `wa.me` as fallback share  
- Webhook for delivery status → update `Notification.status`  
- FE: Settings → WhatsApp; document share “Send via WhatsApp Business”

### Phase 7.2 — Multi-company / multi-branch

**Architecture (hardest wave):**

1. Introduce `Organization` (billing account) optional; or allow multi membership without org in v1  
2. Remove single-active-membership constraint; add `User.active_company_id` / header `X-Company-Id`  
3. Company switcher in shell nav  
4. `Branch` model; migrate stock to branch-aware balances; default branch  
5. Reports filter by branch; Owner consolidated org report = 7.2b  
6. Audit + tenant isolation test matrix rewrite  

**Explicit non-goal in 7.2:** consolidating GSTR across GSTINs into one filing pack.

### Phase 7.3 — POS mode + recurring invoices

**POS:**

- `/pos` full-screen route: search, cart, pay, print  
- Tender shortcuts (Cash/UPI); still creates normal SalesInvoice + Receipt  
- Optional: second display / thermal (thermal may already exist as optional DOC-501)  
- Offline POS = **not** in 7.3 (MVP deferred offline)

**Recurring:**

- `RecurringInvoiceSchedule`: customer, lines template, cadence, next_run, active  
- Celery creates drafts; notify Owner  
- Insights can mention upcoming recurring (Phase 6 tools)

### Phase 7.4 — India Stack verifications (PAN, GSTIN, UDYAM first)

- Extend verify Protocol: `PanProvider`, harden `GstinProvider`, `UdyamProvider`  
- Company / Customer / Supplier fields: `pan`, `udyam_number` + verification status mirrors GSTIN  
- Cache payloads DPDP-aware (same as Phase 2 GSTIN verify)  
- Health / onboarding checklist: “verify identity”

### Phase 7.5 — Busy / Zoho (demand-gated)

- Implement same `AccountingMigration` interface  
- Separate tickets per product; do not start without ≥ N customer requests logged  

### Phase 7.6 — Future: ONDC / DigiLocker / Aadhaar eSign

- **ONDC:** catalog publish / order ingest — only if B2B commerce ICP appears  
- **DigiLocker:** document fetch for KYC — after 7.4 providers mature  
- **Aadhaar eSign:** PDF signing for agreements / e-invoices adjunct — legal review first  
- Deliverable now: ADR stub + credential placeholder table only

### Phase 7.7 — Future: Manufacturing BOM

- Models: `BillOfMaterials`, `BomLine`, `ProductionOrder`, component stock issue / FG receipt  
- Requires branch/warehouse maturity (after 7.2)  
- PRD marks Future — do not schedule until manufacturer pilots signed  

---

## 3. Data model sketches

### Integrations

| Model | Purpose |
|-------|---------|
| `IntegrationConnection` | company, provider (`TALLY`,`WHATSAPP`,`PAN_API`,…), status, encrypted secrets, metadata |
| `IntegrationSyncRun` | job log, counts, error file FK |
| `WhatsAppTemplateBinding` | template name, language, BizBoard event key |
| `Customer.whatsapp_opt_in` | bool + timestamp |

### Tenancy

| Model | Purpose |
|-------|---------|
| `Organization` (optional v1) | billing parent |
| `Branch` | company FK, name, code, is_default, address |
| `StockBalance` | add `branch` FK; unique `(company, branch, product)` |
| Documents | nullable `branch` FK; default = company default branch |
| `CompanyUser` | drop single-active unique; add last_selected_at |

### POS / Recurring

| Model | Purpose |
|-------|---------|
| `RecurringInvoiceSchedule` | cadence, template JSON / line FKs, next_run_at, is_active |
| `PosSession` (optional) | open/close cash drawer totals — only if retail pilots need z-report |

### India Stack

| Fields | On |
|--------|-----|
| `pan`, `pan_verification_status`, `pan_verified_at` | Company, Customer, Supplier |
| `udyam_number`, `udyam_*` status fields | Company (primary) |

---

## 4. Adapter protocols

```text
AccountingMigrationAdapter
  parse_masters(file) -> MappingPreview
  parse_openings(file) -> OpeningPreview
  commit(preview_id, company, user) -> SyncRun
  export_vouchers(company, date_from, date_to) -> FileAsset

WhatsAppProvider
  send_template(to, template, params) -> provider_message_id
  handle_webhook(payload) -> DeliveryUpdate

IdentityVerifyProvider
  verify_pan(pan) -> VerifyResult
  verify_gstin(gstin) -> VerifyResult   # may already exist
  verify_udyam(number) -> VerifyResult
```

Sandbox/null providers mandatory for CI (same as GSP).

---

## 5. API surface (incremental)

| Area | Paths |
|------|-------|
| Tally | `/api/v1/integrations/tally/upload/`, `.../preview/`, `.../commit/`, `.../export/` |
| WhatsApp | `/api/v1/integrations/whatsapp/settings/`, `.../send-invoice/`, webhook `/api/v1/webhooks/whatsapp/` |
| Company switch | `POST /api/v1/auth/select-company/`, `GET /api/v1/company/memberships/` |
| Branches | `/api/v1/branches/` CRUD; reports accept `?branch=` |
| POS | reuse sales invoice create + `/api/v1/pos/quick-sale/` convenience if needed |
| Recurring | `/api/v1/sales/recurring-schedules/` |
| Verify | `/api/v1/verify/pan/`, `/udyam/` (+ existing GSTIN) |

---

## 6. Frontend

| Area | UX |
|------|----|
| Tally | Settings → Migration wizard (4 steps) |
| WhatsApp | Settings → Messaging; share modal channel picker |
| Multi-company | Header company switcher; membership list |
| Branches | Settings → Branches; doc header branch select |
| POS | `/pos` distraction-free; large tap targets |
| Recurring | Sales → Recurring schedules |
| Verify | Buttons on Company/Customer/Supplier forms |

---

## 7. Ticket breakdown (high level)

### Wave 7.0 — Tally

| ID | Item | Pts |
|----|------|-----|
| ECO-000 | `integrations` app + Connection + SyncRun | 5 |
| ECO-001 | Tally parse masters + mapping UI | 13 |
| ECO-002 | Opening AR/AP + stock commit | 13 |
| ECO-003 | Export voucher aid + disclaimer | 8 |
| ECO-004 | Golden fixture from sample Tally export | 8 |
| ECO-005 | Onboarding honesty + support runbook | 3 |

### Wave 7.1 — WhatsApp Business

| ID | Item | Pts |
|----|------|-----|
| ECO-100 | Meta provider + secrets | 8 |
| ECO-101 | Templates + send invoice/reminder | 8 |
| ECO-102 | Webhook delivery status | 5 |
| ECO-103 | Opt-in UX + FE settings | 8 |
| ECO-104 | Fallback to wa.me when WABA down | 3 |

### Wave 7.2 — Multi-company / branch

| ID | Item | Pts |
|----|------|-----|
| ECO-200 | Membership constraint migration + select-company | 13 |
| ECO-201 | FE company switcher + context bugsweep | 13 |
| ECO-202 | Branch model + default backfill | 8 |
| ECO-203 | StockBalance branch migration | 13 |
| ECO-204 | Documents/reports branch filter | 8 |
| ECO-205 | Tenant isolation suite rewrite | 13 |

### Wave 7.3 — POS + recurring

| ID | Item | Pts |
|----|------|-----|
| ECO-300 | POS page + quick pay path | 13 |
| ECO-301 | Recurring schedules + Celery drafter | 8 |
| ECO-302 | Notify drafts ready | 3 |
| ECO-303 | POS UAT checklist | 3 |

### Wave 7.4 — India Stack verifications

| ID | Item | Pts |
|----|------|-----|
| ECO-400 | PAN/UDYAM fields + providers | 8 |
| ECO-401 | FE verify + cache | 5 |
| ECO-402 | Health/onboarding hooks | 3 |
| ECO-403 | DPDP retention note | 2 |

### Demand-gated / Future

| ID | Item | Pts |
|----|------|-----|
| ECO-500 | Busy adapter | 21 |
| ECO-501 | Zoho Books adapter | 21 |
| ECO-600 | ONDC spike ADR | 5 |
| ECO-601 | DigiLocker spike | 5 |
| ECO-602 | Aadhaar eSign spike | 5 |
| ECO-700 | BOM + production order epic | 40+ |

---

## 8. Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Tally XML dialect chaos | Failed migrations | Support 1–2 documented export recipes; paid onboarding help |
| Claiming “Tally sync” | Legal/support | D2 export = aid; copy review |
| WA template rejection / ban | Channel loss | Keep wa.me; compliance templates only |
| Multi-company auth bugs | Cross-tenant leak | ECO-205 mandatory; BUG-110 history |
| Branch stock migration downtime | Ops pain | Expand-contract migration; default branch |
| Auto recurring Complete | Wrong invoices | Drafts only (D8) |
| India Stack vendor lock-in | Cost | Protocol + null provider |
| Building ONDC/BOM early | Wasted months | Hard Future gate |
| Scope collision with Phase 6 | Bandwidth | Integrations after 6.0; assistant tools later call WA send |

---

## 9. Definition of Done

### Phase 7.0 exit

- [ ] At least one real Tally export recipe documented and green on golden fixture  
- [ ] Masters + openings commit with error report  
- [ ] Export aid downloadable with disclaimer  
- [ ] Support runbook for failed mappings  

### Phase 7.1 exit

- [ ] Template send for invoice + reminder in sandbox/prod WABA  
- [ ] Delivery status reflected on Notification  
- [ ] Opt-in enforced; wa.me fallback works  

### Phase 7.2 exit

- [ ] User with 2 companies can switch without logout; isolation tests pass  
- [ ] Default branch backfilled; stock unique per branch  
- [ ] Document create respects selected branch  

### Phase 7.3 exit

- [ ] POS path creates completed invoice + payment in &lt; N taps UAT  
- [ ] Recurring creates drafts on schedule; no auto-Complete  

### Phase 7.4 exit

- [ ] PAN + UDYAM verify soft-fail path live (GSTIN per Phase 2 provider)  
- [ ] Status fields visible on Company form  

### Future (not DoD)

- [ ] Busy / Zoho  
- [ ] ONDC commerce  
- [ ] DigiLocker / Aadhaar eSign  
- [ ] Manufacturing BOM  

---

## 10. Open questions

| # | Question | Default | Freeze before |
|---|----------|---------|---------------|
| Q1 | Tally format: XML vs Excel vs both? | **Excel/CSV first** if XML unstable; XML as 7.0b | 7.0 |
| Q2 | Organization entity in 7.2 v1? | **No** — multi membership only; Org when billing needs it | 7.2 |
| Q3 | Meta Cloud API vs BSP (Wati/Interakt)? | Prefer **BSP** for template ops speed unless cost blocks | 7.1 |
| Q4 | POS offline? | **Online-only** in 7.3 | 7.3 |
| Q5 | Recurring auto-Complete for trusted pilots? | **No** until explicit flag + audit | 7.3 |
| Q6 | PAN provider (NSDL / Karza / same GSP)? | Decide with GSTIN verify vendor | 7.4 |
| Q7 | When to start 7.2 vs more AI? | Start 7.2 design when first multi-GSTIN deal is real | PM |

---

## 11. First implementation slice

1. **ECO-000** — integrations skeleton + secrets  
2. **ECO-001 → ECO-005** — Tally migration magnet  
3. **ECO-100 → ECO-104** — WhatsApp Business (parallel paperwork Day 1)  
4. **ECO-400** — PAN/UDYAM while WA templates bake  
5. **ECO-200 design doc** early; implement when customer blocked  
6. POS/recurring when retail cohort lands  
7. Busy/Zoho/ONDC/BOM — backlog only  

---

## 12. Success metrics

| Metric | Target |
|--------|--------|
| Pilots migrated from Tally via wizard | ≥ 10 in first 2 cohorts after 7.0 |
| Migration time Owner self-serve | &lt; 1 day for ≤ 500 ledgers with support doc |
| WA reminder → payment within 7 days | Uplift vs wa.me-only baseline |
| Multi-company isolation incidents | 0 |
| POS sale time | &lt; 30 seconds happy path |
| Speculative Busy/Zoho builds without demand | 0 |

---

## 13. Relationship to Phases 3–6

| Phase | Interaction |
|-------|-------------|
| Phase 2.5 (2A/2B) | Independent GST compliance track; don’t block Tally |
| Phase 3–5 (payments / inventory / light books) | See `docs/phase3`–`phase5`; warehouse depth is Phase 4 (not 7.2) |
| Phase 6 AI | Daily summary / reminders become WA templates; assistant may call `send_reminder` propose→confirm after 7.1 |
| Phase 2 D13 multi-GSTIN | Solved via **multi-company** (7.2), not multi-GSTIN-per-Company |
| Scale (load, pen-test) | Run before GA marketing of “ecosystem” features |

---

## 14. Review changelog

- Initial plan (2026-08-02): Tally-first migration; WA Business; multi-company/branch architecture; POS + recurring; India Stack verify trio; ONDC/eSign/BOM explicitly Future and demand-gated.

---

*This plan implements product Phase 7 ecosystem & scale. It does not weaken Phase 0–2 money/GST gates or replace Phase 6 AI sequencing.*
