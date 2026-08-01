# Phase 0 — Definition of Done

**Status:** Canonical Phase 0 exit criteria (rev 3)  
**Audience:** Eng, PM, QA, Ops, CA  
**Related plan:** [`PHASE_0_IMPLEMENTATION_PLAN.md`](./PHASE_0_IMPLEMENTATION_PLAN.md)  
**Related bugs:** [`bugs/INDEX.md`](../../bugs/INDEX.md)

This file is the **source of truth** for Phase 0 go/no-go. Ticket IDs in the implementation plan and the scoreboard key to the IDs below. Do not treat chat history as DoD.

**Operative schedule:** Until PM fills a higher headcount, **solo (7–8 weeks)** is the schedule — see plan §0 / §4.3.

---

## Goal

Controlled paid pilot (20–50 businesses) can run:

**purchase → sale → partial pay → return → ledger/report**

with correct money, tenant isolation, no silent data loss, operable production ops, and CA-approved tax/PDF.

Phase 0 does **not** add full Credit Notes / GSTR / e-Invoice / GL / payment gateway / multi-warehouse / AI BI — except where a **named pilot correction-path decision** explicitly allows a minimal adjustment mechanism (see B6 / H9).

---

## Legend

| Tag | Meaning |
|-----|---------|
| **Must** | Blocks pilot Go |
| **Should** | Blocks only if no written PM waiver |

---

## A. Security & tenancy

| ID | Requirement | Must/Should | Bug refs (primary) |
|----|-------------|-------------|--------------------|
| **A1** | Invoice PDFs and uploads are not anonymously enumerable via `/media/`; authenticated, tenant-scoped download works | Must | BUG-703 |
| **A2** | Owners cannot silently attach another tenant’s existing user; invite is create-only or consent-based | Must | BUG-109, BUG-701 |
| **A3** | Active company resolution is deterministic; ambiguous multi-membership does not silently pick wrong tenant (and UI can recover) | Must | BUG-110, BUG-702 |
| **A4** | Production refuses weak/placeholder `SECRET_KEY` and cannot silently run with `DEBUG` on when `DJANGO_ENV=production` | Must | BUG-101, BUG-704 |
| **A5** | Secrets and local artifacts are not baked into images; `.dockerignore` present; `.env` not committed | Must | BUG-705, BUG-706, BUG-707 |
| **A6** | Login, register, OTP request, and OTP verify are throttled; lockout after max OTP attempts is tested | Must | BUG-105, BUG-728 |
| **A7** | Duplicate phone numbers do not 500 OTP verification | Must | BUG-108 |
| **A8** | OTP never reports success without a real send in pilot/prod; OTP UI hidden or password-only when SMS not live; **FE must not display OTP debug codes outside DEBUG** | Must | BUG-102, BUG-628 |
| **A9** | Automated tests cover cross-tenant **writes**; assertion-free debug tests removed or completed | Must | BUG-721, BUG-700 |
| **A10** | Cancelling an invoice with payment allocations cannot leave orphan allocations / wrong outstanding (block or reverse atomically) | Must | BUG-722 |
| **A11** | Token storage + session invalidation: documented decision for JWT in `localStorage` and forced logout when refresh is rejected (implement hardenings or signed accept-risk) | Must | BUG-402, BUG-407 |

---

## B. Money & concurrency integrity

| ID | Requirement | Must/Should | Bug refs |
|----|-------------|-------------|----------|
| **B1** | Concurrent sales completes under negative-stock `BLOCK` cannot oversell; lock-before-check proven on Postgres | Must | BUG-222, BUG-309 |
| **B2** | Concurrent payment allocations cannot over-allocate a receipt/payment; proven on Postgres | Must | BUG-308 |
| **B3** | Screen preview, DB totals, **and PDF** match for the CA sample set. Math fixture alone is insufficient — at least F1/F3/F6 have automated render→extract→assert vs DB | Must | tax/CA, BUG-204 |
| **B4** | BEFORE_TAX / AFTER_TAX discounts correct on Sales **and** Purchases **and** PDF renderer (`invoice_discount_mode` honored; no self-contradictory PDF math) | Must | BUG-203, BUG-204, BUG-504 |
| **B5** | Document numbers assigned at Complete (or gaps explained + non-burn on draft); purchase number UI cannot mutate series | Must | BUG-208, BUG-502 |
| **B6** | Completed invoices/purchases are not freely line-editable; **named correction path** for paid+wrong-price exists (see H9) — not “return as price fix” | Must | BUG-506, BUG-213, BUG-220 |
| **B7** | Destructive actions (cancel/delete) require explicit confirmation | Should | BUG-520 |
| **B8** | Concurrency/locking tests run in CI against **PostgreSQL**; pytest markers registered | Must | BUG-712 |
| **B9** | Payment allocation / receipt delete is authorized, audited, and cannot silently cascade away money trails without guard | Must | BUG-310, BUG-311 |
| **B10** | Line `gst_rate`, `unit_price`, `discount_percent`, `additional_charges` have bounds validation on documents | Must | BUG-210, BUG-211 |
| **B11** | **Additional charges / GST scope decision:** either charge GST on freight/packing per CA-agreed rule and implement, **or** written CA+PM scope that additional charges are out-of-scope / non-taxable for pilot (checklist row added) — silence not allowed | Must | BUG-205 |

---

## C. Counter-billing UX blockers

| ID | Requirement | Must/Should | Bug refs |
|----|-------------|-------------|----------|
| **C1** | Save & New does not wipe success or payment-error messages (Sales + Purchases) | Must | BUG-500, BUG-501 |
| **C2** | Save draft vs Complete are explicit; primary Save does not silently Complete | Must | BUG-507 |
| **C3** | Purchases has the same place-of-supply / party-state gate as Sales | Must | BUG-508 |
| **C4** | Quotations support multiple lines; qty > 0; convert double-submit guarded; dialog resets | Must | BUG-523–526 |
| **C5** | Returns can target any invoice line; qty clamped to original sold/purchased | Must | BUG-531, BUG-532 |
| **C6** | Lists/pickers past page 1 work — no silent drop at ~50 | Must | BUG-521, BUG-606–609, BUG-533 |
| **C7** | Large register reports paginate/virtualize and meet performance floor (E8) | Should | BUG-605 |
| **C8** | UI surfaces backend/business errors on saves and forms — **including Company and GST settings** (no silent failed save); not only Axios string parsing | Must | BUG-522, BUG-617, BUG-618 |
| **C9** | Unallocated receipts show Advance / unallocated clearly | Should | BUG-527, BUG-304 |
| **C10** | Allocation UX: exclude fully paid; default = remaining balance; amount > 0; dialog reset | Must | BUG-528–530 |
| **C11** | Product form wires HSN/GST validators already unit-tested in utils | Must | BUG-621 |
| **C12** | Dashboard renders backend receivables aging (and related dashboard fields UAT asserts); export actions enforce `can_export` | Must | BUG-601, BUG-602, BUG-612 |

---

## D. Communications & PDF ops

| ID | Requirement | Must/Should | Bug refs |
|----|-------------|-------------|---------|
| **D1** | Staging/prod SMTP delivers invoice email; failures visible | Must | runbooks |
| **D2** | WhatsApp is link-share only; no Business API claim | Must | — |
| **D3** | OTP policy documented; `OTP_DEBUG_ECHO` impossible outside DEBUG **backend and frontend** (no unconditional OTP debug display) | Must | BUG-102, BUG-628 |
| **D4** | Complete does not hang on broker; download does not sync-hang generating PDF; regenerate works | Must | BUG-224 + download sync |
| **D5** | `/api/v1/docs/` loads, or intentionally disabled | Should | BUG-104 |

---

## E. Deploy, reliability & pilot ops floor

| ID | Requirement | Must/Should | Bug refs |
|----|-------------|-------------|----------|
| **E1** | HTTPS at edge for any host with real pilot PII/GSTINs | Must | — |
| **E2** | Restart policies; healthchecks where cost-effective; documented skips | Should | BUG-708, BUG-709 |
| **E3** | CI green on protected main **after** WIP lands | Must | BUG-712, BUG-713 |
| **E4** | Daily DB backup off-host; restore drill dated | Must | BUG-733 / RUNBOOKS |
| **E5** | Uptime on `/api/v1/health/` + alert; Celery backlog notes | Must | RUNBOOKS |
| **E6** | Env checklist signed | Must | — |
| **E7** | High/critical CVEs fixed or waived in writing | Should | BUG-714, BUG-715 |
| **E8** | Performance floor: invoice list **and** ledger list/CSV paths (known N+1) — see plan §10.1; seed must be able to produce the load | Should | PERFORMANCE_REPORT, BUG-301 |
| **E9** | Deploy rollback: image tags + migration reverse vs restore decision tree | Must | migrations WIP |
| **E10** | DPDP minimum: access list, PII-in-logs policy, backup encryption/location, retention, onboarding privacy line | Must | DPDP / pilot |

---

## F. CA, tax & PDF sign-off

| ID | Requirement | Must/Should |
|----|-------------|-------------|
| **F1** | Intra-state ₹200 @ 18% — PDF + DB match | Must |
| **F2** | Inter-state IGST sample — match | Must |
| **F3** | Odd paise ₹10.05 @ 18% — match | Must |
| **F4** | NON_GST — tax 0 | Must |
| **F5** | AFTER_TAX discount — match | Must |
| **F6** | BEFORE_TAX discount — match (**blocked by BUG-204 until PDF fixed**) | Must |
| **F7** | Round-off on/off — match | Must |
| **F8** | Multi-rate lines — match | Must |
| **F9** | Named CA signs; artifact stored | Must |
| **F10** | Math parity fixture covers F1–F8 in BE + FE CI | Must |
| **F11** | Automated PDF totals check for at least F1, F3, F6 (render → extract → assert vs DB) | Must |
| **F12** | Additional-charges GST decision recorded with CA (ties to B11) | Must |

---

## G. Pilot UAT (golden path)

Staging, **real API**, ≥5 companies:

| ID | Flow | Must/Should |
|----|------|-------------|
| **G1** | Register → company GST setup (**save errors visible**) | Must |
| **G2** | CSV import with usable error report | Must |
| **G3** | Opening stock → balances correct | Must |
| **G4** | Purchase → complete → stock up | Must |
| **G5** | Quotation multi-line → convert → invoice | Must |
| **G6** | Invoice complete → PDF → download/share | Must |
| **G7** | Partial receipt + allocation | Must |
| **G8** | Sales return non-first line | Must |
| **G9** | Supplier payment + allocation | Must |
| **G10** | Ledgers + reports + CSV export (`can_export` enforced) | Must |
| **G11** | Staff capability flags enforced (cancel / **export** / inventory / financials) | Must |
| **G12** | Negatives: blocked customer; POS gate; stock BLOCK | Must |

Automation: golden e2e against real backend (BUG-725). Matrix: [`UAT_CHECKLIST.md`](./UAT_CHECKLIST.md).

---

## H. Support, docs, pilot governance

| ID | Requirement | Must/Should |
|----|-------------|-------------|
| **H1** | Runbooks accurate (incl. deploy rollback, on-call) | Must |
| **H2** | Support playbook: cancel / return / discount / immutability allowlist / **paid-invoice correction path (H9)** | Must |
| **H3** | Onboarding + privacy one-liner + **explicit statement of paid-invoice correction policy** | Must |
| **H4** | Scope honesty: no GSTR / e-Invoice / full books claims | Must |
| **H5** | Ops metrics instrumented | Should |
| **H6** | Critical quiet gate (exit criteria) | Must |
| **H7** | Support SLA / on-call documented | Must |
| **H8** | Kill criteria and Phase 1 graduation criteria agreed | Must |
| **H9** | **Paid completed invoice correction-path decision** signed before go-live (Options in plan §7.1) — not FAQ-only | Must |

---

## Explicitly out of Phase 0

Full Credit Notes product, SO/PO, challans, POS, recurring · GSTR / e-Invoice / e-Way · Double-entry / P&L / BS · Payment gateway / bank recon · Multi-company/branch/warehouse · Tally/Busy/Zoho · WhatsApp Business API · AI BI · Full pen-test / 10k load — **unless** H9 explicitly ships a *minimal* credit-note-as-adjustment for pilot only.

---

## Exit criteria (all required for Go)

1. Scoreboard shows every **Must** Done or Waived (PM signed).  
2. Every Critical and High in `bugs/INDEX.md` mapped to a ticket or written waiver.  
3. Critical quiet gate: no *new* Critical since UAT sign-off; zero open Criticals at go meeting.  
4. CA sign-off (F9) including F12 / B11 decision.  
5. UAT matrix ≥5 companies (G1–G12).  
6. **Go build SHA == UAT build SHA** (recorded on UAT checklist), **or** 12-row smoke re-run and re-signed on the Go SHA.  
7. TLS (E1), backups (E4), monitoring (E5), env (E6), DPDP (E10).  
8. H7–H9 signed; H4 honesty.  

### Sign-off

| Role | Name | Date | Go / No-Go / Conditional |
|------|------|------|--------------------------|
| PM | | | |
| Eng | | | |
| QA | | | |
| CA (tax/PDF) | | | |
| Ops | | | |

UAT build SHA: ________________  
Go build SHA: ________________ (must match, or smoke re-signed)

**Conditional Go** may waive only **Should** items. **Must not** waive: open Critical money/tenancy, missing CA letter, missing TLS on real-PII hosts, unmapped Criticals, unsigned H9, SHA mismatch without re-smoke.
