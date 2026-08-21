# BizBoard — Phase 3: Payments & Cash Ops

**Status:** Implemented in code (2026-08-02; 2026-08-21: MDR posts to 5200 when books-on; HDFC/ICICI/SBI CSV fixtures). Razorpay primary + Cashfree/PayU adapters; sandbox webhooks for CI.  
**Canonical path:** [`docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md`](./PHASE_3_PAYMENTS_CASH_OPS.md)  
**Root pointer:** [`PHASE3_IMPLEMENTATION_PLAN.md`](../../PHASE3_IMPLEMENTATION_PLAN.md)  
**Stack:** Django 5 + DRF (`backend/payments/`, `backend/ledgers/`) · React 18 + MUI (`web/`) · Celery + Redis · existing `PaymentService` (record-only) · `Company.upi_id` / bank fields · invoice PDF QR toggle (`include_payment_qr`) · Phase 6 cashflow forecast is **prediction only** — this phase owns **actual cash tracking**.

---

## Start gate — money collection readiness (read first)

| Prerequisite | Source of truth | Why it matters |
|--------------|-----------------|----------------|
| Phase 0 Go / money Criticals closed | [`docs/pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) | Gateway money on broken tenants multiplies support |
| Phase 1 outstanding helper + CN/DN netting | [`docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md`](../phase1/PHASE_1_DOCUMENT_COMPLETENESS.md) | Auto-allocation from gateway must hit correct outstanding |
| Receipt / payment / allocation race locks green | `PaymentService` + BUG-308 tests | Concurrent gateway webhooks + manual allocate |
| `LedgerService` party outstanding trusted | `backend/ledgers/` | Payment Links that over-collect destroy trust |
| Gateway vendor shortlist + KYC started (PM) | §13 | 3.1 eng must not wait for Day-1 of wave |

**Do not start live gateway settlement before allocation + outstanding math is green.** A Payment Link that marks an invoice paid while outstanding math is wrong is worse than record-only UPI.

**Why this phase after GST polish (Phase 2):** Pilots collect cash/UPI today via record-only receipts. Collection *conversion* (links, auto-match bank credits) is the next founder ROI after filing aids — and is required input for Phase 5 bank reconciliation and honest Phase 6 cash baselines.

### Plan map (numbering clarification)

| Document | Role |
|----------|------|
| `MVP_IMPLEMENTATION_PLAN.md` §19 item 6 | Historical: “Payment gateway” deferred |
| [`docs/phase2/...`](../phase2/PHASE_2_GST_RETURNS_READINESS.md) DoD | Mentions “GSTR-2A/2B = Phase 3 candidate” — **renamed to Phase 2.5** |
| Phase 6 plan map | Said “Phase 3 = 2A/2B” — **superseded**; Phase 6 data gate means “transaction history”, not this doc’s number |
| **This file** | **Phase 3** — Payments & cash ops |
| [`docs/phase5/...`](../phase5/PHASE_5_LIGHT_ACCOUNTING.md) | Consumes bank statement lines + cash book from this phase |

### Headcount / calendar (solo senior full-stack)

| Wave | Duration | Same person? |
|------|----------|--------------|
| Phase 3.0 — UPI / instruments hardening | ~3–4 weeks | Yes |
| Phase 3.1 — Payment Links + gateway | ~4–5 weeks eng (**vendor KYC parallel from Day 1**) | Yes — after 3.0 |
| Phase 3.2 — Bank statement import + auto recon | ~4–5 weeks | Yes — after 3.1 receipt provenance |
| Phase 3.3 — Cashflow tracking report | ~2–3 weeks | Yes — after instruments + bank lines exist |
| **Calendar consequence** | **~14–18 weeks** sequential | Waves **cannot** overlap gateway + bank parsers at headcount 1 |

**3.0 + 3.1 (no bank feed): ~7–9 weeks** — highest collection-lift for pilots.  
Bank recon (3.2) can slip if gateway alone unblocks receivables; do not skip 3.0 UPI QR correctness.

**Non-engineering track (starts Day 1 of Wave 3.0):** Payment gateway merchant account (Razorpay / Cashfree / PayU — pick one primary), webhook URL + TLS, settlement bank account mapping, UPI collect VPA verification. Calendar-dominated (often 2–6 weeks).

---

## 0. Current-state snapshot (as of 2026-08-02)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Customer receipts / supplier payments | ✅ `CustomerReceipt` / `SupplierPayment` | ✅ `ReceiptsPage` + invoice partial pay | **Record-only** |
| Payment modes | `CASH` `UPI` `BANK` `CARD` `CREDIT` | ✅ | No instrument / bank account FK |
| Allocations | ✅ capped + row-locked | ✅ | Manual / on-invoice only |
| Company UPI ID + bank fields | ✅ on `Company` | ✅ settings | Static; no VPA verify |
| Invoice payment QR | PDF flag `include_payment_qr` | Toggle on editor | **Static UPI deep-link style** — no amount/txn id / status |
| Payment Links / gateway | ❌ | ❌ | Missing |
| Webhooks / settlement | ❌ | ❌ | Missing |
| Bank statement import | ❌ | ❌ | Missing |
| Auto reconciliation | ❌ | ❌ | Missing |
| Cash / bank book report | ❌ | ❌ | Missing — Phase 6 forecast ≠ cash book |
| Opening cash | `Company.opening_cash_balance` + `as_of` | Insights settings | Used by AI forecast only |

**Patterns to extend (do not invent parallel money truth):**

- Money in/out still creates **`CustomerReceipt` / `SupplierPayment`** (or a thin subtype) — gateway never bypasses `PaymentService`
- Outstanding only via `LedgerService` helpers
- Async: Celery for webhook finalize, statement parse, match suggestions — never block Complete
- Secrets: Fernet encrypt gateway credentials like GSP (`Company.gsp_credentials_encrypted` pattern)
- Events: emit `customer_receipt.created`, `payment_link.paid`, `bank_line.matched` via `core/events.py`
- Permissions: `can_view_financial_reports` for cash reports; Owner for gateway credentials + force-match

---

## 1. Locked product decisions

| # | Decision | Lock |
|---|----------|------|
| D1 | Gateway / Payment Links **create normal receipts** (then allocate) — never a second “paid” flag on invoices that skips `PaymentAllocation` | One outstanding formula forever |
| D2 | Primary Indian gateway adapter is **pluggable** (`PaymentGatewayAdapter`); ship **one** provider in 3.1; second provider = later | Sandbox fake adapter for CI |
| D3 | **Payment Link** = shareable URL / WhatsApp for one sales invoice (or open amount against customer); expiry + amount locked at create | Partial collect allowed if link `allow_partial=true` (default false for invoice links) |
| D4 | Webhook is source of **settlement truth**; UI “Mark paid” without gateway remains for cash/UPI offline | Idempotent webhook by `provider_payment_id` |
| D5 | Stronger UPI = **amount-locked UPI intent / QR** with `txn_note` = receipt/invoice number; optional collect-request status when provider supports it | Static company UPI string alone is insufficient for 3.0 DoD |
| D6 | Receipts gain optional `instrument` / `bank_account` / `gateway_payment` FKs; mode enum stays for UX filters | CREDIT mode never creates cash movement |
| D7 | Bank statement import = Upload → Validate → Preview → Commit (clone Import Service UX) | CSV/XLSX first; OFX/MT940 later |
| D8 | Auto recon = **suggestions first**, Owner confirms; auto-apply only for exact amount + unique invoice/receipt reference match when `auto_match_exact=true` | Never silent force-match of ambiguous lines |
| D9 | Cashflow **tracking** report = actual cash/bank movements from receipts, supplier payments, and matched bank lines — not Phase 6 prediction | Label UI “Cash book / Cashflow actuals” vs Insights “Forecast” |
| D10 | Refunds via gateway = create negative-style adjustment document path: **Sales CN allocation unwind or explicit `PaymentRefund`** that reverses allocation then posts gateway refund | No silent receipt delete (PROTECT allocations) |
| D11 | Multi-currency = **out** | INR only |
| D12 | Payout to suppliers via gateway = **out of 3.x** (record-only supplier payments remain) | Avoid dual disbursement complexity |
| D13 | Fees / MDR: store `gateway_fee` on settlement; optionally net vs gross receipt (Q3) | Default: record **gross** customer amount as receipt; fee as expense note until Phase 5 GL |
| D14 | Permissions: Staff may create links / record UPI if `can_manage_payments` (new flag, default true Owner+Staff like receipts today); credentials + recon force-match = Owner/Admin | Audit every credential change + force-match |

---

## 2. Scope split — waves

### Phase 3.0 — UPI collection hardening + payment instruments

- `BankAccount` master (company-scoped): name, account no (masked), IFSC, type (CURRENT/SAVINGS/CASH_BOX), `is_default`
- `PaymentInstrument` optional thin table **or** fields on receipt: `bank_account`, `upi_vpa`, `utr`, `card_last4`
- Amount-locked UPI QR payload builder for invoice PDF + share card (`pa`, `am`, `tn`, `cu=INR`)
- Receipt create UX: require UTR for UPI/BANK when company setting `require_payment_reference=true`
- Duplicate UTR warning (same company, 90-day window)
- Health-style alerts: `UPI_ID_MISSING`, `OPEN_INVOICE_NO_LINK_OR_UPI` (optional)

### Phase 3.1 — Payment Links + gateway

- Encrypted gateway credentials on Company (or `PaymentGatewayConfig`)
- `PaymentLink` model + public pay page (tokenized, no JWT) + WhatsApp/email share via Notification Service
- Adapter: create link / fetch status / refund stub
- Webhook endpoint (HMAC verify) → idempotent `PaymentService.create_receipt` + auto-allocate to source invoice
- Invoice detail: Link status panel (CREATED / SENT / PAID / EXPIRED / CANCELLED)
- FE settings: enable gateway, webhook URL copy, test mode toggle

### Phase 3.2 — Bank statement import + auto reconciliation

- `BankStatement` + `BankStatementLine` (append-only lines; void via status)
- Import pipeline + column mapping presets (HDFC/ICICI/SBI/generic)
- Matcher service: amount + date window + reference/UTR/invoice number heuristics → `MatchSuggestion`
- Confirm match → link line to receipt/payment **or** create receipt from unmatched credit (wizard)
- Unmatched aging report + alerts

### Phase 3.3 — Cashflow tracking report

- Cash/bank book by account + mode for date range
- Inflow / outflow / net; opening from `BankAccount.opening_balance` or company opening cash
- Export XLSX; deep links to documents
- Optional: daily cash position widget on Dashboard (not Phase 6 forecast)

### Phase 3.4 (explicitly later — not in core calendar)

- Second gateway provider
- UPI Autopay / mandates
- Payouts to suppliers
- Live bank API feed (Account Aggregator)
- GSTR-2A/2B purchase reconcile (**Phase 2.5**, compliance track)

**Rationale for order:** Static UPI QR + instruments fix today’s collection UX without vendor lock-in. Gateway builds on clean receipt provenance. Bank import needs receipt UTRs/link refs to match well. Cash book is reporting on top of instruments + bank lines.

---

## 3. Architecture

```text
┌─────────────────┐     ┌──────────────────────┐
│ Invoice / Cust  │────▶│ PaymentLink Service  │──▶ Gateway Adapter
└────────┬────────┘     └──────────┬───────────┘     (Razorpay/…)
         │                         │ webhook
         │                         ▼
         │              ┌──────────────────────┐
         └─────────────▶│ PaymentService       │──▶ CustomerReceipt
                        │ + Allocation         │      + PaymentAllocation
                        └──────────┬───────────┘
                                   │
┌─────────────────┐                │
│ Bank CSV/XLSX   │──▶ Import ────▶│ BankStatementLine
└─────────────────┘       │        │      │
                          │        │      ▼
                          │        │ MatchService ──▶ confirm ──▶ link / create receipt
                          ▼        ▼
                     Reporting: Cash book / recon status
```

### 3.1 New modules (proposed)

| Module | Responsibility |
|--------|----------------|
| `payments/models.py` (extend) | `BankAccount`, `PaymentLink`, `GatewayPayment`, `BankStatement`, `BankStatementLine`, `ReconMatch` |
| `payments/gateway.py` | Adapter Protocol + sandbox + one provider |
| `payments/upi.py` | UPI QR / intent payload helpers |
| `payments/recon.py` | Match scoring + suggest/confirm |
| `payments/webhooks.py` | HMAC verify + idempotent finalize |
| `web/.../PaymentLinksPage.tsx` | List + create + share |
| `web/.../BankReconPage.tsx` | Import + match UI |
| `web/.../CashBookPage.tsx` | Actuals report |

Prefer extending **`payments`** app; introduce `banking/` only if models exceed ~8 files.

### 3.2 Key models (sketch)

```text
BankAccount(company, name, account_number_masked, ifsc, account_type, opening_balance, opening_as_of, is_default)

PaymentLink(
  company, token, sales_invoice?, customer?,
  amount, allow_partial, status, expires_at,
  provider, provider_link_id, paid_receipt?,
  created_by
)

GatewayPayment(
  company, provider, provider_payment_id UNIQUE(company, provider, id),
  amount, fee, status, raw_payload (retention-bound),
  payment_link?, receipt?
)

BankStatement(company, bank_account, period_start, period_end, source_file, status)
BankStatementLine(statement, txn_date, value_date, amount signed, narration, utr, balance_after?, match_status)
ReconMatch(line, receipt?, supplier_payment?, confidence, matched_by, matched_at)
```

Extend `CustomerReceipt` / `SupplierPayment`:

| Field | Purpose |
|-------|---------|
| `bank_account` FK null | Instrument |
| `utr` / `reference` (existing) | Match key — enforce length/normalize |
| `gateway_payment` FK null | Provenance |
| `source` enum | `MANUAL` \| `GATEWAY` \| `BANK_IMPORT` \| `PAYMENT_LINK` |

### 3.3 Webhook / idempotency rules

1. Verify signature; reject 401 on failure (no body leak).
2. Upsert `GatewayPayment` on `(company, provider, provider_payment_id)`.
3. If already `CAPTURED` with receipt → return 200 no-op.
4. Else create receipt + allocate in **one** `transaction.atomic`.
5. Emit event; enqueue notification “Payment received”.

### 3.4 Match scoring (3.2)

| Signal | Weight |
|--------|--------|
| Exact amount | High |
| UTR equality | High |
| Invoice/receipt number in narration | High |
| Date within ±3 days | Medium |
| Customer name token overlap | Low |
| Multiple candidates | → suggest only, never auto |

---

## 4. API surface (draft)

| Method | Path | Notes |
|--------|------|-------|
| CRUD | `/api/v1/payments/bank-accounts/` | Owner write |
| POST | `/api/v1/payments/links/` | Body: invoice or customer+amount |
| POST | `/api/v1/payments/links/{id}/cancel/` | |
| GET | `/api/v1/payments/links/{id}/` | Auth |
| GET | `/api/v1/public/pay/{token}/` | Public, rate-limited |
| POST | `/api/v1/webhooks/payments/{provider}/` | CSRF exempt, HMAC |
| POST | `/api/v1/payments/statements/upload/` | Preview |
| POST | `/api/v1/payments/statements/{id}/commit/` | |
| GET | `/api/v1/payments/recon/suggestions/` | |
| POST | `/api/v1/payments/recon/confirm/` | |
| GET | `/api/v1/reports/cash-book/` | Query: account, from, to |

---

## 5. Frontend surfaces

| Route / area | Work |
|--------------|------|
| Settings → Bank accounts | New |
| Settings → Payment gateway | Credentials, test mode, webhook URL (Owner) |
| Sales → Payment Links | List, create from invoice, copy/share |
| Invoice detail | UPI QR preview (amount-locked); Link panel; gateway status |
| Receipts | UTR field; bank account; source badge |
| Banking → Statements | Import wizard |
| Banking → Reconciliation | Suggestion queue |
| Reports → Cash book | New actuals report |
| Dashboard | Optional cash position tile |

Reuse MUI patterns from `ReceiptsPage`, import wizards, GST Health alert lists. Wire via `resources.ts` + `domain.ts` + `menu.ts` + i18n.

---

## 6. Work breakdown (tickets)

Points ≈ solo senior full-stack hours/2 (same scale as Phase 1/2).

### Wave 3.0 — UPI + instruments (~28–34 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| PAY-000 | `BankAccount` model + API + settings FE | 5 | — |
| PAY-001 | Receipt/payment instrument fields + UTR normalize/dedupe warn | 5 | PAY-000 |
| PAY-002 | Amount-locked UPI QR builder + PDF/share integration | 5 | — |
| PAY-003 | Invoice detail “Pay via UPI” panel + copy intent link | 3 | PAY-002 |
| PAY-004 | Company setting `require_payment_reference` + FE | 2 | PAY-001 |
| PAY-005 | Alerts: missing UPI / duplicate UTR | 3 | PAY-001 |
| PAY-006 | Tests: QR payload; UTR uniqueness warn; migration | 5 | PAY-001..002 |

### Wave 3.1 — Gateway + Links (~40–50 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| PAY-100 | Gateway credentials encrypt + settings UI | 5 | vendor sandbox |
| PAY-101 | Adapter Protocol + sandbox fake + one provider | 8 | PAY-100 |
| PAY-102 | `PaymentLink` model + create/cancel/list API | 5 | PAY-101 |
| PAY-103 | Public pay page (minimal, branded, mobile-first) | 8 | PAY-102 |
| PAY-104 | Webhook idempotent finalize → receipt + allocate | 8 | PAY-101, Phase 1 outstanding |
| PAY-105 | Share link via WhatsApp/Email Notification Service | 3 | PAY-102 |
| PAY-106 | Invoice FE link panel + status | 5 | PAY-102 |
| PAY-107 | Refund path stub (provider + unwind allocation) | 5 | PAY-104 |
| PAY-108 | Security: rate limit public + webhook replay tests | 3 | PAY-104 |

### Wave 3.2 — Bank import + recon (~38–48 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| PAY-200 | Statement models + upload preview/commit | 8 | PAY-000 |
| PAY-201 | Bank CSV presets (3 banks + generic) | 5 | PAY-200 |
| PAY-202 | MatchService scoring + suggestions API | 8 | PAY-200, PAY-001 |
| PAY-203 | Confirm match + create-receipt-from-line wizard | 8 | PAY-202 |
| PAY-204 | Recon FE queue + unmatched aging | 8 | PAY-203 |
| PAY-205 | Auto-match exact policy flag + audit | 3 | PAY-202 |
| PAY-206 | Tests: golden CSV fixtures + ambiguous non-auto | 5 | PAY-202 |

### Wave 3.3 — Cashflow tracking (~18–24 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| PAY-300 | Cash book ReportService query (by account/mode) | 8 | PAY-000, receipts source |
| PAY-301 | FE Cash book + XLSX export | 5 | PAY-300 |
| PAY-302 | Dashboard cash position tile (optional) | 3 | PAY-300 |
| PAY-303 | Clarify Insights forecast disclaimer vs actuals | 2 | PAY-301 |

**Core exit (3.0+3.1):** ~68–84 pts ≈ **7–9 weeks**  
**Full Phase 3:** ~124–156 pts ≈ **14–18 weeks** (+ gateway KYC overlap)

---

## 7. Testing strategy

| Layer | Must cover |
|-------|------------|
| Unit | UPI QR fields; match scores; fee gross/net policy |
| API | Webhook replay idempotency; public token expiry; allocate caps unchanged |
| Integration | Link paid → receipt → invoice outstanding → 0 |
| Fixtures | Golden bank CSV → expected suggestions |
| FE | Mobile pay page; recon confirm/reject |
| Security | HMAC fail; webhook without signature; public enumeration of tokens |
| E2E | Complete invoice → create link → sandbox pay → receipt allocated → cash book shows inflow |

**Invariant (mandatory):** After gateway capture, `LedgerService.sales_invoice_outstanding(invoice)` equals pre-pay outstanding − captured amount (within paise rules).

---

## 8. Security & ops

| Topic | Rule |
|-------|------|
| Gateway secrets | Encrypted at rest; never in list serializers |
| Public pay tokens | High entropy; expiry; rate limit by IP + token |
| Webhooks | HMAC + timestamp skew window; store raw payload with DPDP retention |
| PCI | No card PAN storage — hosted checkout only |
| Audit | Link create/cancel, webhook capture, recon force-match, credential rotate |
| Failure UX | Gateway down → fall back to UPI QR / manual receipt; never block billing Complete |

---

## 9. Risk register

| Risk | Mitigation |
|------|------------|
| Double receipt from webhook + manual | Idempotency key; UI warns if link already PAID |
| Ambiguous bank match auto-applies wrong invoice | Suggestions default; exact-only auto |
| MDR confusion in ledgers | D13; Phase 5 posts fee expense later |
| Treating Phase 6 forecast as cash book | D9 labeling; PAY-303 |
| Vendor KYC delay | 3.0 ships without gateway; sandbox adapter for CI |
| Public pay page phishing lookalikes | Clear BizBoard + company legal name; HTTPS only |
| Scope into full GL | Journals stay Phase 5 |

---

## 10. Definition of Done

### Phase 3.0 exit

- [ ] ≥ 1 bank account / cash box per company; receipts can reference it
- [ ] Amount-locked UPI QR on invoice PDF/share when UPI ID present
- [ ] UTR capture + duplicate warning
- [ ] Tests green for QR payload + instrument fields

### Phase 3.1 exit

- [ ] Sandbox Payment Link → webhook → receipt + allocation for one invoice
- [ ] Public pay page works on mobile; expired links rejected
- [ ] Credentials encrypted; Owner-only settings
- [ ] Idempotent webhook test; outstanding invariant green
- [ ] Manual record-only path still works when gateway off

### Phase 3.2 exit

- [ ] CSV import preview/commit for ≥ 1 bank preset + generic
- [ ] Suggestion queue; confirm links line ↔ receipt
- [ ] Exact auto-match optional; ambiguous never auto
- [ ] Unmatched aging visible

### Phase 3.3 exit

- [ ] Cash book by account/date with export
- [ ] UI distinguishes actuals vs Insights forecast

Explicitly **not** required for Phase 3 core:

- [ ] Second gateway / Account Aggregator live bank API
- [ ] Supplier payouts
- [ ] Full double-entry cash GL (Phase 5)
- [ ] GSTR-2A/2B (Phase 2.5)

---

## 11. Open questions (resolve before named wave)

| # | Question | Default | Freeze before |
|---|----------|---------|---------------|
| Q1 | Primary gateway? | Razorpay | 3.1 |
| Q2 | Payment Link allow partial by default? | **No** for invoice links | 3.1 |
| Q3 | Record gateway fee as reduced receipt vs separate expense? | Gross receipt + fee note | 3.1 / Phase 5 |
| Q4 | Auto-match exact without human confirm? | Off by default | 3.2 |
| Q5 | Public pay page hosted on app domain vs provider hosted? | Provider hosted checkout + thin status page | 3.1 |
| Q6 | Require UTR for all UPI receipts in pilot? | Warn-only first | 3.0 |

---

## 12. Slice order (first 10 engineering days)

1. PAY-000 BankAccount  
2. PAY-002 UPI QR amount-lock  
3. PAY-001 instrument + UTR  
4. PAY-003 invoice panel  
5. PAY-100 credentials shell (even if sandbox only)  
6. PAY-101 sandbox adapter  
7. PAY-102/104 link + webhook happy path  
8. PAY-103 public page  
9. Outstanding invariant tests  
10. Pilot UAT on 1 company before bank import

---

## 13. Non-engineering track

| Track | Owner | Start |
|-------|-------|-------|
| Gateway merchant KYC | PM / founder | Day 1 of 3.0 |
| Settlement bank account confirmed | Founder | Before 3.1 prod |
| Sample bank statements from 3 pilots | CS | Before 3.2 presets |
| Support macros: failed webhook, duplicate pay | Support | 3.1 exit |

---

*Documents remain source of truth. Gateway and bank feeds only create or match documents — they never invent a parallel paid-state.*
