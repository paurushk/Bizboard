# Bizboard — Line-by-line code review (2 Sep 2026, night)

Reviewer: Cursor Grok 4.6 · **Current source only.** Morning 2 Sep reports were re-checked; many named P0s are **fixed** (see the bottom of the quality log). This pass logs what is still true.

**Full searchable list:** [DEEP_QUALITY_LOG_2026-09-02_NIGHT.md](./DEEP_QUALITY_LOG_2026-09-02_NIGHT.md) — **210 findings** (14 P0 · 86 P1 · 60 P2 · 12 P3 · 18 UX · 12 GAP · 8 SUGG).

**Severity:** `P0` money/inventory/security/hard crash on a real path · `P1` wrong output / broken flow · `P2` edge/race/validation · `P3` docs/maintainability · `UX` friction · `GAP` partial feature · `SUGG` improvement.

**Coverage:** `core`, `accounts`, `config`, `billing`, `sales`, `purchases`, `inventory`, `masters`, `payments`, `accounting`, `reporting`, `ledgers`, `banking`, `manufacturing`, `payroll`, `crm`, `imports`, `insights`, `integrations/tally`, `search`, `web/src`, `mobile`, CI. Not a live browser walkthrough.

---

## 0. Fix-first cluster

| # | Sev | Finding |
|---|---|---|
| 0.1 | P0 | **FIFO:** partial sales return restores **all** sale peels (`restore_fifo_peels`), then cancel **skips** peel unwind (`sales_return_cancel` in the skip list). Layers drift vs on_hand. |
| 0.2 | P0 | **Destroy-in-place wipe** never deletes `PaymentLink` / `ReconMatch` / `Bom` / `FixedAsset` (all `PROTECT`). Real tenants crash mid-wipe. `unbacked_live_counts` does not warn. |
| 0.3 | P0 | **Staff vs Owner:** party/product mutate is Owner-only; POS walk-in, invoice quick-create, and offline POS flush still call `createCustomer`. Cashiers 403. |
| 0.4 | P0 | **Refunds:** books unwind then gateway; partial provider refunds never unwind; beat `reconcile_gateway_captures` has no `company_id` (RLS-blind); attempts≥8 **reset** and retry forever. |
| 0.5 | P0 | **Identity:** register `IntegrityError` inside `@transaction.atomic` → 500; phone unique is raw string after canonicalize `ValueError`. |
| 0.6 | P0 | **GST:** filing-identity amend with a live IRN; auto CN cancellable while the return stays COMPLETED. |

---

## 1. Core / accounts / billing / config

- H9-A now blocks qty/GST/cess/HSN/serial/batch **if those keys are present**. Description still amends without `confirm_amend`. Omit keys to skip checks.
- Trial plan `modules: {}` and empty plan dict **fail-open** dark modules when `REQUIRE_SUBSCRIPTION` is false.
- `PENDING` subscription always write-blocks — stub checkout without Razorpay bricks the tenant (even if REQUIRE_SUBSCRIPTION is off).
- `safe_delay` swallows broker errors; WhatsApp fails open to wa.me; MSG91 non-JSON 200 = “OTP sent”.
- Celery prerun SELECTs tenant rows before GUC if `company_id` is omitted (`reconcile_gateway_captures_task` still omits it).
- Tenant export/wipe still omit CRM, payroll, WO, banking, payment links. Wipe order hits PROTECT FKs first (0.2).
- RLS default **off**. Outbox/dunning tables missing from FORCE RLS list.
- FeatureFlags 409 when `active_company` empty (multi-company boot).

---

## 2. Sales / purchases / inventory / masters

- FIFO return/cancel pairing is the worst money bug in this pass (N-001, N-002). Purchase-return cancel restores layers; sales does not.
- Invoice cancel restores only the **first** stock-posted challan and leaves `stock_posted=True`.
- Purchase H9 qty amend has no serial/batch refuse (sales does).
- Serial API: `SOLD→RETURNED` with no movement; scrap uses `skip_negative_check` and swallows errors.
- FEFO: line stores first lot only; product-level stock check ignores batch; WARN explicit-batch shortfall is silent.
- Conversions drop commercial fields: challan→invoice, SO→challan cess, quotation→invoice rate_override, PO→purchase GSTIN/warehouse/TDS.
- Auto CN cancel unpaired (sales and purchase).
- Price slabs: overlap not DB-constrained; matcher highest `min_qty`.
- PDFs: challan tax forced off; purchase HSN fallthrough to inclusive `line_total`; thermal omits cess.
- Missing HSN is a warning on sales (except e-invoice B2B); purchases with GSTIN hard-block.

---

## 3. Payments / accounting / GST / ledgers

- Books-first full refund + JSON-only partials + Cashfree/PayU `fee=0` + refund JE dated **today**.
- Holding: mismatch/expired/already-paid never auto-refund. `CAPTURED` + failed allocation still looks “pending books”.
- IMS: offline import trusts client eligibility; WRONG_GSTIN unscoped by period; bulk accept still mass-ACCEPT + GL. Period-lock deemed-accept is a **no-op** (fixed).
- GSTR-2B: null `invoice_date` amount-only MATCH across FY; blank number unique needs a date; sales stamp excludes null `company_gstin`.
- SUPECOM still in B2 / 3.1(a). Without 2B, `recommended_claimable` is `books_provisional`.
- 3.1(a) RCM taxable **is** included now (`_all_sum`) — morning P0 is fixed.
- Ledgers: invoice outstanding document-based vs party GL; floor-at-zero hides credits.
- ITC reclass can move full tax vs parked balance.

---

## 4. Manufacturing / payroll / CRM / Tally / insights / search / mobile / CI

- WO `_snapshot_bom` wipes lot allocations then FEFO-issues. Explicit batch skips availability. Component serials marked SCRAPPED. UI **does** collect serials now (textarea/JSON) — morning “no UI” is fixed, UX is still hostile.
- Payroll LOP placeholder `net=emp.salary` keeps inactive people in GL. UI now has LOP + cancel (morning gap closed). PF ceiling / PT on prorated gross remain.
- CRM convert: first phone match, no unique(lead), `CanCreateSales` gate. Won checkbox **exists**.
- Tally `force=` commits dropping errored rows; no row lock on the sync run; customers keyed by name.
- Insights: GET mutates; alerts swallow exceptions; AP due vs sales receipts; margin vs list cost.
- Search: purchase staff see selling price; no min query length.
- Mobile: Capacitor shell; CI will not prove Play; push token never registered.
- CI mobile job has no Gradle assemble. E2E golden is still one invoice path.

---

## 5. Frontend / offline / ACL / i18n / UX

- **ACL:** history Cancel without `canCancelDocuments`; editors on view routes; party/product create vs Owner (0.3). CN **list** Complete/Cancel is now gated (fixed).
- **Offline:** invoice/purchase Complete does not queue payment (POS does). No cross-tab flush lock. Stock count/transfer no auto-flush. Outbox not in nav.
- Payment-link list and supplier-payment allocation drop page 2+.
- i18n: switcher is en/hi only (ta/gu **no longer offered**). Huge hardcoded English on billing, receipts, journals, settings, PWA reload copy. Hindi money-complete; rest not.
- Preview vs Complete HSN/TCS mismatch. Offline complete without preview.
- GSTR-6/7/8 URL stubs not in sidebar.
- PWA now **confirms** reload (morning “no confirm” is fixed); copy is English.

---

## 6. Partially implemented (still)

WO lot control (wiped on release), payroll statutory filing, CRM pipeline, Tally live sync, GSTR-4/6/7/8/9 engines, invoice templates, POS cash drawer, push, native mobile offline, tenant backup as a full clone, SaaS self-serve portal, HSN-as-GSTN catalog.

---

## 7. Suggested fix order

1. FIFO peel proportional restore + sales-return cancel unwind (N-001, N-002).
2. Wipe order / PROTECT tables + `unbacked_live_counts` (N-003, N-004).
3. Party/product mutate ACL **or** Owner-gate the FE including POS (N-007).
4. Refund: books after gateway success; stop attempt reset; `company_id` on every beat task; RLS on outbox (N-009–N-012, N-011).
5. Register savepoint; E.164 unique phone (N-005, N-006).
6. Block CN cancel while return COMPLETED; block filing amend with live IRN (N-008, N-013, N-014).
7. FE: `canCancelDocuments` on history; payment pagination; offline payment queue; i18n leftovers.

---

## 8. What is in good shape (this pass)

Idempotency no longer caches 5xx; events do not roll back Complete; H9-A money fields are mostly allowlisted; 3.1(a) RCM taxable math matches the comment; Razorpay refund header is `X-Razorpay-Idempotency-Key`; PayU refund passes `var3`; ACTIVE subscriptions honor `current_period_end`; CN list ACL, ConfirmDialog busy, ErrorBoundary i18n, WO serial UI, payroll LOP UI, CRM won checkbox, journals subscription gate, POS receipt/alloc idempotency keys, IMS period-lock no auto-ACCEPT.
