# BizBoard — Phase 5: Light Accounting

**Status:** Implemented in code (2026-08-02) — opt-in CoA/posting, journals, TB/P&L/BS overlay, bank recon, cost centers, fixed assets. `accounting_enabled` stays default False until #9 is signed.  
**Canonical path:** [`docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md`](./PHASE_5_LIGHT_ACCOUNTING.md)  
**Root pointer:** [`PHASE5_IMPLEMENTATION_PLAN.md`](../../PHASE5_IMPLEMENTATION_PLAN.md)  
**Stack:** Django 5 + DRF · React 18 + MUI · today: **no GL tables** — `LedgerService` derives party statements from documents · Phase 3 bank lines feed recon · Phase 4 valuation feeds inventory/COGS · CA validation baseline in `ACCOUNTING_VALIDATION.md`.

---

## Start gate — books only when pilots demand it (read first)

| Prerequisite | Source of truth | Why it matters |
|--------------|-----------------|----------------|
| Phase 0 Go | [`docs/pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) | Books on wrong invoices = wrong TB forever |
| Marketing still says billing-first / documents-as-truth | README + onboarding | Phase 5 must not silently rebrand as “full Tally replacement” |
| **Demand gate:** ≥ 3 paid pilots ask for journals / TB / P&L in writing | Sales / support | Avoid speculative GL |
| Phase 3.2 bank statement import live | [`docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md`](../phase3/PHASE_3_PAYMENTS_CASH_OPS.md) | Bank recon (5.3) needs statement lines |
| Phase 1 outstanding + CN/DN correct | Phase 1 DoD | AR/AP control accounts must tie to party ledgers |
| CA workshop on default Indian SME CoA | External | Wrong CoA = unusable TB |
| Phase 4.2 valuation recommended before claiming inventory on BS | Phase 4 | Else inventory BS line is qty×last purchase hack — disclose |

**Do not start journal UI before document→GL posting rules are locked and reconciliable to registers.** Manual journals without auto-posting recreate the dual-write hell MVP explicitly avoided.

**Why last among 3–5:** Payments and inventory deepen *operational* truth. Accounting is a **projection** for CA packs and founder P&L. Building it earlier invites editing books instead of documents.

### Plan map

| Document | Role |
|----------|------|
| `MVP_IMPLEMENTATION_PLAN.md` §19 item 10 | Historical: “Manual accounting module” deferred |
| `ACCOUNTING_VALIDATION.md` | CA score / gaps — TB/P&L/BS out of MVP by design |
| Phase 3 | Cash instruments + bank lines (recon input) |
| Phase 4 | Valuation / COGS inputs |
| **This file** | **Phase 5** — Light accounting |
| Phase 6 | Insights must read same P&L factors when present — never invent books |
| Phase 7 Tally | Export/import should map to same CoA codes when both exist |

### Headcount / calendar (solo senior full-stack)

| Wave | Duration | Same person? |
|------|----------|--------------|
| Phase 5.0 — CoA + document posting engine | ~5–6 weeks | Yes |
| Phase 5.1 — Journal vouchers | ~2–3 weeks | Yes — after posting engine |
| Phase 5.2 — Trial Balance → P&L → Balance Sheet | ~3–4 weeks | Yes — after 5.0+5.1 |
| Phase 5.3 — Bank reconciliation (ties to Phase 3) | ~3–4 weeks | Yes — after 5.0 cash/bank accounts + Phase 3.2 |
| Phase 5.4 — Cost centers | ~3–4 weeks | **Later / demand-gated** |
| Phase 5.5 — Fixed assets | ~4–5 weeks | **Last / demand-gated** |
| **Calendar consequence** | **~14–20 weeks** for 5.0–5.3 | 5.4–5.5 not in core calendar |

**5.0 + 5.2 (read-only books from documents, minimal journals): ~8–10 weeks** if journal wave is thin.

---

## 0. Current-state snapshot (as of 2026-08-02)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Party ledgers | Derived `LedgerService` | Ledgers pages | ✅ No stored ledger rows |
| Journals / vouchers | ❌ | ❌ | Missing |
| Chart of accounts | ❌ | ❌ | Missing |
| Trial Balance | ❌ | ❌ | Missing |
| P&L / Balance Sheet | ❌ | ❌ | Missing — correctly out of MVP |
| Bank recon (GL sense) | ❌ | ❌ | Phase 3 has statement↔receipt match; not GL clear |
| Cost centers | ❌ | ❌ | Missing |
| Fixed assets | ❌ | ❌ | Missing |
| GST “books” | Return aids (Phase 2) | Reports | Compliance ≠ financial accounting |

**Patterns to preserve:**

1. **Documents remain source of truth** for operational money and stock.  
2. GL entries are **generated** from documents (immutable posting batches) + **sparse** manual journals.  
3. Never allow GL edits that silently change invoice totals.  
4. Party outstanding UX continues to use `LedgerService` (document-derived); GL AR/AP **must reconcile** to it via control-account checks.  
5. Reuse Report Service patterns + Health-style “books integrity” alerts.

---

## 1. Locked product decisions

| # | Decision | Lock |
|---|----------|------|
| D1 | **Documents as truth** — GL is a projection. Invoice amount changes only via CN/DN / allowed amend paths, which re-post or reverse GL batches | No “edit journal to fix invoice” |
| D2 | Double-entry **JournalEntry** (header) + **JournalLine** (account, debit, credit); every batch `debits == credits` | Soft delete forbidden; reverse via contra voucher |
| D3 | Auto-posting on document Complete / payment create / stock valuation period close (config) | Draft documents never post |
| D4 | Cancel / return / CN/DN post **reversing or offsetting** entries — never mutate posted lines | Append-only journal lines |
| D5 | Standard Indian SME **Chart of Accounts** seeded (Assets, Liabilities, Equity, Income, Expenses) + GST payable/ITC accounts | Company may add accounts; system accounts flagged `is_system` |
| D6 | Control accounts: Accounts Receivable, Accounts Payable, Inventory, Cash, Bank(s), Sales, Purchase, GST output/input | Mapping table from document events → accounts |
| D7 | Trial Balance, P&L, Balance Sheet are **reports as-of / for period** from journal lines | Optional period snapshot for performance |
| D8 | Bank reconciliation (5.3) clears **GL bank account** lines against Phase 3 `BankStatementLine` | Builds on Phase 3 match; adds GL clear flag / recon session |
| D9 | Cost centers (5.4) = optional dimension on journal lines + document headers; reporting slice only | Not required for TB |
| D10 | Fixed assets (5.5) = asset register + depreciation journals (SLM default); last priority | |
| D11 | Phase 5 is **opt-in per company** (`Company.accounting_enabled`) | Pilots without demand never see Journals nav |
| D12 | Permissions: `can_view_books`, `can_post_journals` (Owner default); Staff view optional | |
| D13 | Multi-currency / multi-company consolidated BS = **out** | |
| D14 | Do not replace Tally for complex books in marketing | Honest scope: “light books from your BizBoard documents” |

---

## 2. Scope split — waves

### Phase 5.0 — Chart of accounts + document→GL posting

- CoA models + seed + settings UI
- `AccountingMapping` (event → debit/credit accounts)
- `PostingService`: from sales/purchase/CN/DN/receipt/payment/adjustment → balanced `JournalEntry`
- Idempotent posting keyed by `(company, source_type, source_id, purpose)`
- Books Health: `AR_CONTROL_MISMATCH`, `AP_CONTROL_MISMATCH`, `UNBALANCED_ENTRY` (should be impossible), `DOCUMENT_MISSING_POSTING`
- Feature flag `accounting_enabled`

### Phase 5.1 — Journal vouchers

- Manual journal voucher UI (draft → post)
- Reversing voucher
- Attachment + narration + audit
- Block posting to locked period (reuse GST period soft-close ideas or `AccountingPeriod`)

### Phase 5.2 — Trial Balance → P&L → Balance Sheet

- TB as-of date
- P&L for date range (Income − Expense)
- BS as-of (Assets = Liabilities + Equity); P&L net into Equity
- XLSX export + CA pack section
- Inventory line from Phase 4 valuation when available; else disclose “at cost approximation”

### Phase 5.3 — Bank reconciliation (ties to Phase 3)

- `BankReconSession` for GL bank account × statement period
- Import already in Phase 3; here: match statement lines to **journal lines** (cash/bank), not only receipts
- Cleared vs outstanding GL items (unpresented cheques, etc.)
- Recon report: statement balance vs GL balance + outstanding list

### Phase 5.4 — Cost centers (later)

- `CostCenter` tree; optional on docs + journal lines
- P&L by cost center

### Phase 5.5 — Fixed assets (last)

- Asset master, category, depreciation method SLM
- Monthly Celery depreciation journals
- Disposal voucher

### Explicitly out of Phase 5 core

- Full audit-trail statutory “Books of Account” claim without CA letter
- Branch consolidation
- Budget vs actual
- Payroll GL
- Automatic GST payment challan posting to bank (manual journal ok)

---

## 3. Architecture

```text
  Sales / Purchase / CN/DN / Receipt / Payment / Transfer / Valuation close
                              │
                              ▼
                     PostingService (idempotent)
                              │
                              ▼
              JournalEntry + JournalLines (balanced, append-only)
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    Trial Balance          P&L / BS         Bank Recon Session
          │                                       │
          └──────── Books Health alerts ──────────┘
                              ▲
                              │
                    Manual Journal Voucher
```

### 3.1 New modules (proposed)

| Module | Responsibility |
|--------|----------------|
| `backend/accounting/` **new app** | CoA, journals, posting, periods, reports |
| `accounting/posting.py` | Document event → lines |
| `accounting/reports.py` | TB / P&L / BS |
| `accounting/bank_recon.py` | GL↔statement clear (uses payments bank models) |
| `web/src/pages/accounting/*` | CoA, Journals, TB, P&L, BS, Bank recon |

### 3.2 Key models (sketch)

```text
Account(company, code, name, type[ASSET|LIABILITY|EQUITY|INCOME|EXPENSE],
        parent?, is_system, is_control, gst_role?, bank_account_fk?)

AccountingPeriod(company, name, start, end, status[OPEN|SOFT_CLOSED|CLOSED])

JournalEntry(company, number, entry_date, status[DRAFT|POSTED|REVERSED],
             source_type, source_id, purpose, narration, posted_at, posted_by)

JournalLine(entry, account, debit, credit, cost_center?,
            party_content_type?, party_id?, recon_status, bank_statement_line?)

AccountingMapping(company, event_key, debit_account, credit_account, …)
# Prefer rule table + code strategies for complex GST splits

BankReconSession(company, account, statement, status, gl_balance, statement_balance)
```

### 3.3 Posting matrix (MVP light books)

| Event | Typical DR | Typical CR |
|-------|------------|------------|
| Sales invoice Complete (debtor) | AR | Sales + Output GST |
| Sales invoice cash/bank at Complete + receipt | Cash/Bank | Sales + Output GST (or AR then receipt clears AR) |
| Customer receipt | Cash/Bank | AR |
| Purchase Complete | Purchase/Expense + ITC | AP |
| Supplier payment | AP | Cash/Bank |
| Sales CN | Sales/GST (or CN account) | AR |
| Sales return (stock) | also inventory/COGS effects per mapping | |
| Stock purchase (inventory mode) | Inventory | AP |
| Sale COGS (if perpetual) | COGS | Inventory |
| Gateway fee | Bank charges expense | Bank |
| Manual journal | as entered | as entered |

**Q1 lock required:** Periodic vs perpetual inventory posting. Default: **perpetual** if Phase 4.2 live; else periodic purchase expense (trading concern) with disclosure.

### 3.4 Reconciliation invariants (mandatory tests)

1. `sum(JournalLine.debit) == sum(JournalLine.credit)` per entry.  
2. For each company as-of: AR control balance ↔ sum(`LedgerService` customer outstandings) within paise tolerance.  
3. AP control ↔ supplier outstandings.  
4. Every COMPLETED sales invoice with `accounting_enabled` has exactly one active posting batch (or defined multi-batch purposes).  
5. BS equation holds for report fixture.

---

## 4. API surface (draft)

| Method | Path | Notes |
|--------|------|-------|
| CRUD | `/api/v1/accounting/accounts/` | System accounts restricted |
| CRUD | `/api/v1/accounting/journals/` | draft/post/reverse |
| POST | `/api/v1/accounting/repost/{source}/` | Owner repair tool — audited |
| GET | `/api/v1/accounting/trial-balance/` | `?as_of=` |
| GET | `/api/v1/accounting/profit-and-loss/` | `?from=&to=` |
| GET | `/api/v1/accounting/balance-sheet/` | `?as_of=` |
| CRUD | `/api/v1/accounting/bank-recon-sessions/` | 5.3 |
| GET | `/api/v1/accounting/books-health/` | |

---

## 5. Frontend surfaces

| Route / area | Work |
|--------------|------|
| Settings → Accounting | Enable flag, valuation/posting mode, mappings (advanced) |
| Accounting → Chart of accounts | Tree view |
| Accounting → Journals | List + voucher editor |
| Accounting → Trial Balance | New |
| Accounting → Profit & Loss | New |
| Accounting → Balance Sheet | New |
| Accounting → Bank reconciliation | Uses Phase 3 statements |
| Accounting → Books Health | Alert dashboard |
| Nav | Hidden unless `accounting_enabled` |

Reuse MUI report pages + journal-like grids; keep UX simpler than Tally (guided vouchers, not keyboard-first clone).

---

## 6. Work breakdown (tickets)

### Wave 5.0 — CoA + posting (~48–60 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| ACC-000 | `accounting` app + Account model + Indian SME seed | 8 | CA CoA workshop |
| ACC-001 | Feature flag + permissions + nav gate | 3 | — |
| ACC-002 | AccountingPeriod + soft close | 5 | ACC-000 |
| ACC-003 | PostingService skeleton + idempotency keys | 8 | ACC-000 |
| ACC-004 | Post sales invoice + CN/DN + receipt mappings | 8 | ACC-003 |
| ACC-005 | Post purchase + supplier payment + ITC/output GST | 8 | ACC-003 |
| ACC-006 | Inventory/COGS posting hooks (Phase 4 aware) | 5 | ACC-003, Phase 4.2 optional |
| ACC-007 | Books Health AR/AP control checks | 5 | ACC-004/005 |
| ACC-008 | Backfill command for historical completed docs | 5 | ACC-004 |
| ACC-009 | Tests: balanced entries + control reconcile fixtures | 8 | ACC-004..007 |

### Wave 5.1 — Journals (~18–24 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| ACC-100 | Manual journal API draft/post/reverse | 8 | ACC-000 |
| ACC-101 | Journal FE voucher editor | 8 | ACC-100 |
| ACC-102 | Period lock blocks post | 3 | ACC-002 |
| ACC-103 | Attachment + audit | 3 | ACC-100 |

### Wave 5.2 — Financial statements (~28–34 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| ACC-200 | Trial Balance report + API | 5 | ACC-003 |
| ACC-201 | P&L report | 5 | ACC-200 |
| ACC-202 | Balance Sheet report + equation check | 8 | ACC-200 |
| ACC-203 | FE pages + XLSX export | 8 | ACC-200..202 |
| ACC-204 | CA golden month fixture (TB/P&L/BS) | 5 | ACC-202 |

### Wave 5.3 — Bank recon (~28–36 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| ACC-300 | Link Account ↔ BankAccount; cash/bank posting uses it | 5 | Phase 3 PAY-000, ACC-003 |
| ACC-301 | BankReconSession model + APIs | 8 | Phase 3.2 statements |
| ACC-302 | Match GL lines ↔ statement lines (reuse scores) | 8 | ACC-301 |
| ACC-303 | Recon FE + outstanding list + report | 8 | ACC-302 |
| ACC-304 | Tests: recon ties statement to GL | 5 | ACC-302 |

### Wave 5.4 — Cost centers (~22–28 pts) — later

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| ACC-400 | CostCenter model + doc field | 5 | ACC-000 |
| ACC-401 | Journal line dimension + P&L slice | 8 | ACC-400, ACC-201 |
| ACC-402 | FE + allocation rules light | 8 | ACC-401 |

### Wave 5.5 — Fixed assets (~32–40 pts) — last

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| ACC-500 | Asset category + register | 8 | ACC-000 |
| ACC-501 | Capitalize from purchase / manual | 5 | ACC-500 |
| ACC-502 | SLM depreciation job + journals | 8 | ACC-501 |
| ACC-503 | Disposal voucher | 5 | ACC-501 |
| ACC-504 | FE + reports | 8 | ACC-502 |

**Core exit (5.0–5.3):** ~122–154 pts ≈ **14–20 weeks**  
**5.0+5.2 thin journals:** ~94–118 pts ≈ **10–14 weeks**

---

## 7. Testing strategy

| Layer | Must cover |
|-------|------------|
| Unit | Mapping matrix; debit=credit; period lock |
| Integration | Complete invoice → TB moves; CN reverses income; receipt clears AR |
| Control reconcile | AR/AP vs LedgerService golden tenant |
| Bank recon | Statement balance + uncleared items = GL |
| CA fixtures | One month pack: registers ↔ TB ↔ P&L ↔ BS |
| FE | Flag off hides nav; journal unbalanced blocked |
| E2E | Enable accounting → backfill → TB → bank recon session |

---

## 8. Security & ops

| Topic | Rule |
|-------|------|
| Enablement | Owner only toggles `accounting_enabled` |
| Repost tools | Owner + audit; rate-limited |
| Period close | Owner; reopen audited |
| Performance | Indexes on `(company, account, entry_date)`; snapshots if TB slow |
| Support | “Books disagree with invoice” runbook → fix document, then repost — never hack lines |

---

## 9. Risk register

| Risk | Mitigation |
|------|------------|
| Dual truth (GL vs documents) | D1; control account Health; no line edit |
| Building GL without pilot demand | Start gate ≥ 3 pilots |
| Perpetual inventory without Phase 4 | Disclosure + periodic mode default |
| Scope to full Tally | D14; cost centers/FA gated |
| Bank recon duplicate of Phase 3 | 5.3 clears **GL**; Phase 3 matches **receipts** — document relationship in UI |
| Backfill performance / locking | Chunked Celery; off-peak |
| GST accounts wrong vs GSTR | Mapping reviewed with CA; Health compare output GST vs GSTR liability hint |

---

## 10. Definition of Done

### Phase 5.0 exit

- [ ] Seeded CoA; `accounting_enabled` gate
- [ ] Auto-post core sales/purchase/receipt/payment/CN/DN
- [ ] Idempotent posting; cancel/CN reverse correctly
- [ ] AR/AP control Health vs LedgerService green on golden tenant
- [ ] Historical backfill command

### Phase 5.1 exit

- [ ] Manual journal draft/post/reverse with balance validation
- [ ] Period lock enforced

### Phase 5.2 exit

- [ ] TB / P&L / BS APIs + FE + XLSX
- [ ] BS equation holds on CA fixture
- [ ] Inventory line policy documented (Phase 4 or disclosure)

### Phase 5.3 exit

- [ ] Bank recon session clears GL bank lines against Phase 3 statements
- [ ] Recon report explains statement vs GL difference

### Phase 5.4 / 5.5

- [ ] Only after separate PM charter + demand

Explicitly **not** required for Phase 5 core:

- [ ] Cost centers / fixed assets  
- [ ] “Replaces Tally” claim  
- [ ] Multi-company consolidation  
- [ ] Editable posted journal lines  

---

## 11. Open questions

| # | Question | Default | Freeze before |
|---|----------|---------|---------------|
| Q1 | Perpetual vs periodic inventory? | Perpetual if Phase 4.2; else periodic | 5.0 |
| Q2 | Cash sales: direct income or AR+receipt? | AR+receipt when credit; direct Cash CR Sales when full pay at Complete | 5.0 |
| Q3 | GST cash vs accrual books? | **Accrual** aligned to invoice Complete | 5.0 |
| Q4 | Single bank GL account vs per BankAccount? | Per `BankAccount` GL sub-account | 5.3 |
| Q5 | Auto-enable for new companies? | **Off** until demand | 5.0 |
| Q6 | FY lock aligned to GST periods? | Separate AccountingPeriod; warn if diverge | 5.1 |

---

## 12. Slice order (first 10 engineering days)

1. CA CoA workshop → ACC-000 seed  
2. ACC-001 feature flag / nav  
3. ACC-003 PostingService + idempotency  
4. ACC-004 sales + receipt postings  
5. ACC-007 AR control Health  
6. ACC-005 purchase side  
7. ACC-009 golden reconcile tests  
8. ACC-200/201 TB + P&L thin  
9. ACC-100/101 minimal manual journal  
10. Pilot enable on **one** demanding tenant before bank recon

---

## 13. Dependency summary

```text
Phase 1 docs/outstanding ──┐
Phase 2 GST (accounts map) ┼──▶ Phase 5.0 posting quality
Phase 3.2 bank statements ──▶ Phase 5.3 bank recon
Phase 4.2 valuation ────────▶ BS inventory + COGS honesty
Pilot demand (≥3) ──────────▶ start gate
```

---

*Stay billing-honest: books are a balanced projection of documents plus rare journals — never a second place to “fix” sales.*
