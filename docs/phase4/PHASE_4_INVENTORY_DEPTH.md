# BizBoard — Phase 4: Inventory Depth

**Status:** Implemented in code (2026-08-02) — warehouses, batch/expiry, WAVG/FIFO, price lists, serials. SO reservation is live (D5); challan stock remains opt-in.  
**Canonical path:** [`docs/phase4/PHASE_4_INVENTORY_DEPTH.md`](./PHASE_4_INVENTORY_DEPTH.md)  
**Root pointer:** [`PHASE4_IMPLEMENTATION_PLAN.md`](../../PHASE4_IMPLEMENTATION_PLAN.md)  
**Stack:** Django 5 + DRF (`backend/inventory/`, `masters.Product`) · React 18 + MUI · append-only `StockMovement` + rebuildable `StockBalance` · line `batch_no` already on sales/purchase items (UI optional) · single-warehouse MVP lock on `Company`.

---

## Start gate — stock integrity (read first)

| Prerequisite | Source of truth | Why it matters |
|--------------|-----------------|----------------|
| Phase 0 Go | [`docs/pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) | Multi-location on broken stock math multiplies ghosts |
| Complete/Cancel/Return movement matrix green | `InventoryService` + sales/purchase services | Transfers must reuse same posting path |
| Append-only movement invariant tests | `StockMovement.save/delete` guards | Batch/serial layers must not allow updates/deletes |
| Negative-stock policy understood | `Company.negative_stock_policy` | Per-warehouse policy inheritance |
| Demand signal | ≥ 1 pilot needs multi-location **or** batch/expiry | Avoid building warehouse for retail-only shops |

**Do not start FIFO/serial before warehouse + batch quantity ledger is correct.** Valuation on wrong qty is expensive fiction.

**Why after Phase 3 (payments):** Not a hard technical dependency — inventory depth can parallel payments if headcount > 1. At solo headcount, prefer finishing **3.0+3.1** first (cash collection) unless a distributor pilot is blocked on stock. Phase 5 COGS / Balance Sheet inventory line **needs** 4.2 valuation.

### Plan map (numbering clarification)

| Document | Role |
|----------|------|
| `MVP_IMPLEMENTATION_PLAN.md` §19 item 9 | Historical: multi-warehouse deferred |
| [`docs/phase7/...`](../phase7/PHASE_7_ECOSYSTEM_SCALE.md) D5 / 7.2 | Earlier sketch of branch/warehouse — **superseded by this Phase 4** for stock depth; Phase 7 keeps POS/ecosystem |
| **This file** | **Phase 4** — Inventory depth |
| [`docs/phase5/...`](../phase5/PHASE_5_LIGHT_ACCOUNTING.md) | Consumes valuation method + stock value for BS/P&L |

### Headcount / calendar (solo senior full-stack)

| Wave | Duration | Same person? |
|------|----------|--------------|
| Phase 4.0 — Multi-warehouse + stock transfer | ~4–5 weeks | Yes |
| Phase 4.1 — Batch/lot ledger + expiry alerts | ~4–5 weeks | Yes — after 4.0 locations exist |
| Phase 4.2 — Valuation (WAVG / FIFO) | ~3–4 weeks | Yes — after batch qty stable (FIFO prefers lots) |
| Phase 4.3 — Multi-price lists | ~2–3 weeks | Yes — can overlap lightly with 4.2 FE if needed |
| Phase 4.4 — Serial tracking | ~3–4 weeks | **Demand-gated** — electronics/appliance vertical only |
| **Calendar consequence** | **~16–22 weeks** with 4.4; **~13–17** without serial | Do not overlap 4.0 schema with 4.2 valuation at headcount 1 |

**4.0 + 4.1: ~8–10 weeks** — unblocks distributors / pharma-lite / FMCG without valuation complexity.

---

## 0. Current-state snapshot (as of 2026-08-02)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Single warehouse | Implicit (company-level balance) | Current stock page | **MVP lock** |
| Stock movements | ✅ typed append-only | Adjustment UI | No warehouse/batch dims |
| Stock balance cache | ✅ `(company, product)` | ✅ | Must become `(company, warehouse, product[, batch])` |
| `batch_no` on lines | ✅ sales/purchase item fields | Optional columns | **Not ledgered** — free text only |
| Expiry | ❌ | ❌ | Missing |
| Stock transfer doc | ❌ | ❌ | Missing |
| Valuation report | Thin / qty-focused | Partial | No FIFO/WAVG engine |
| Price lists | Single product sell price | Product master | Missing multi-list |
| Serial numbers | ❌ | ❌ | Missing |
| Reservation | Field `reserved=0` | — | Still deferred behaviour |

**Patterns to extend:**

- Keep **append-only** movements; correct via reverse movements / transfer docs / adjustments
- `InventoryService.post_movement` remains the only writer of stock deltas
- Balances always **rebuildable** from movements
- Document Complete still atomic with stock side-effects
- New movement types: `TRANSFER_OUT`, `TRANSFER_IN` (or single transfer doc posting both)
- Never delete historical movements when enabling warehouses — backfill default warehouse

---

## 1. Locked product decisions

| # | Decision | Lock |
|---|----------|------|
| D1 | `Warehouse` (or `Branch` stock location) is company-scoped; every tenant gets **one default** warehouse via data migration | Existing balances map to default |
| D2 | Documents that move stock gain required `warehouse` (sales out, purchase in, adjustment); transfer has `from` + `to` | Default warehouse pre-selected in UI |
| D3 | Stock transfer = first-class document (`StockTransfer`) with status DRAFT → COMPLETED → CANCELLED; posts OUT+IN movements | Not a pair of ad-hoc adjustments |
| D4 | Batch/lot = optional per product (`Product.track_batch`); when on, issue/receipt **requires** batch; balance grain includes batch | Products without flag keep warehouse-only grain |
| D5 | Expiry date stored on batch master / receipt lot; alerts at configurable days (default 30/60/90) | Block sale of expired when `block_expired_stock=true` (default true) |
| D6 | Default valuation method = **Weighted Average**; FIFO available per company (or per product category later) | Method change does not rewrite history — prospective + report-as-of engine |
| D7 | Valuation is a **report/service**, not a second mutable stock table; optional `StockValuationSnapshot` for period close | Same philosophy as ledger derivation |
| D8 | Multi-price lists = named lists (`MRP`, `Wholesale`, `Retail`, customer-assigned list); invoice line picks rate from list with manual override | Does not replace GST tax engine |
| D9 | Serial tracking = **Phase 4.4 demand-gated**; `Product.track_serial`; one serial one warehouse at a time | Not built for grocery pilots |
| D10 | Negative stock policy applies per warehouse available qty | Company-level setting still governs |
| D11 | Inter-warehouse in-transit: MVP transfer is **instant** on Complete (no in-transit warehouse) unless pilot requires — then 4.0b | Prefer instant for SMB |
| D12 | Manufacturing / BOM = **out** (still Phase 7+ / never in 4.x) | |
| D13 | Cost on SALE movement: continue storing `unit_cost` snapshot from valuation service at Complete | Needed for COGS in Phase 5 |

---

## 2. Scope split — waves

### Phase 4.0 — Multi-warehouse + stock transfer

- `Warehouse` model + default backfill
- Migrate `StockBalance` → unique `(company, warehouse, product)`
- Add `warehouse` to `StockMovement`
- Thread warehouse through purchase/sales/return/adjustment complete paths
- `StockTransfer` document + FE
- Current stock + low stock filters by warehouse / all
- Permissions: `can_transfer_stock` (Owner default true)

### Phase 4.1 — Batch/lot stock ledger + expiry alerts

- `Product.track_batch`, `BatchLot` (product, batch_no, expiry_date, optional mfg)
- Movement + balance grain optional batch FK
- Purchase complete creates/updates lots; sales complete requires FEFO suggestion (earliest expiry first)
- Expiry alerts API + page (clone low-stock alerts)
- Backfill: empty batch_no lines → “UNBATCHED” virtual only if track_batch enabled later (Q2)

### Phase 4.2 — Proper valuation (WAVG / FIFO)

- `Company.inventory_valuation_method` = `WAVG` \| `FIFO`
- `InventoryValuationService`: stock value as-of date; COGS for a sale movement
- FIFO layers from purchase/opening movements (batch-aware when present)
- Reports: Stock valuation, COGS estimate by period
- Golden fixtures for method math (CA-reviewed)

### Phase 4.3 — Multi-price lists

- `PriceList`, `PriceListItem`, `Customer.price_list` optional
- Billing editors: list picker + unit price default fill
- Import prices via existing import pipeline extension

### Phase 4.4 — Serial tracking (optional)

- `SerialNumber` state machine: AVAILABLE → SOLD → RETURNED → SCRAPPED
- Capture on purchase/sales lines when `track_serial`
- Transfer moves serial warehouse
- Reports: serial history

### Out of scope for Phase 4

- MRP / production orders
- Putaway / bin locations (aisle/rack) — too WMS
- Landed cost multi-allocation engine (simple unit_cost on purchase remains)
- Non-zero SO reservation workflows (still deferred)

---

## 3. Architecture

```text
                    Warehouse (default + N)
                           │
     Purchase / Sale / Return / Adjustment / Transfer
                           │
                           ▼
              InventoryService.post_movement
                (warehouse [, batch] [, serial])
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     StockMovement   StockBalance    BatchLot / Serial
     (append-only)   (cache)         (masters)
            │
            ▼
     InventoryValuationService (WAVG / FIFO)
            │
            ▼
     Reports + Phase 5 COGS hooks
```

### 3.1 Schema migration strategy (critical)

1. Create `Warehouse`; backfill `DEFAULT` per company.  
2. Add nullable `warehouse` on movements/balances; fill default.  
3. Enforce NOT NULL.  
4. Change `StockBalance` unique_together; rebuild all balances from movements.  
5. Only then add transfer document.  
6. Batch columns nullable forever for non-tracked products.

**Downtime:** Prefer expand-migrate-contract; rebuild_balance management command mandatory in release notes.

### 3.2 New movement types

| Type | Sign / effect |
|------|----------------|
| `TRANSFER_OUT` | − qty at from warehouse |
| `TRANSFER_IN` | + qty at to warehouse |

Same `reference_type=StockTransfer`, `reference_id`. Cancel transfer posts reversing pair.

### 3.3 Valuation algorithms (locked sketch)

**WAVG:**  
`new_avg = (qty_on_hand * avg + receipt_qty * receipt_cost) / (qty_on_hand + receipt_qty)`  
Store running avg on balance cache **or** compute from movements (prefer compute + optional cache).

**FIFO:**  
Maintain layers `(qty_remaining, unit_cost, received_at, batch?)` derived from movements; consume oldest first on SALE/TRANSFER_OUT/PURCHASE_RETURN as applicable.

**Report as-of:** Replay movements ≤ timestamp — do not mutate layers historically when method flag changes (Q3).

### 3.4 FEFO for batches

When `track_batch` and multiple lots: default allocate earliest `expiry_date`, then earliest receipt. User may override with permission.

---

## 4. API surface (draft)

| Method | Path | Notes |
|--------|------|-------|
| CRUD | `/api/v1/inventory/warehouses/` | |
| CRUD | `/api/v1/inventory/transfers/` | + complete/cancel |
| GET | `/api/v1/inventory/stock/` | `?warehouse=&batch=` |
| GET | `/api/v1/inventory/batches/` | + expiry filters |
| GET | `/api/v1/inventory/alerts/expiry/` | |
| GET | `/api/v1/reports/stock-valuation/` | `?method=&as_of=` |
| CRUD | `/api/v1/masters/price-lists/` | 4.3 |
| CRUD | `/api/v1/inventory/serials/` | 4.4 |

Sales/purchase serializers gain `warehouse_id`; lines gain `batch_id` / `serial_numbers[]` when flags on.

---

## 5. Frontend surfaces

| Route / area | Work |
|--------------|------|
| Settings → Warehouses | New |
| Inventory → Transfers | New document UI |
| Inventory → Current stock | Warehouse filter; batch drilldown |
| Inventory → Expiry alerts | New |
| Inventory → Serials | 4.4 |
| Masters → Products | track_batch / track_serial toggles |
| Masters → Price lists | 4.3 |
| Sales/Purchase editors | Warehouse select; batch picker; FEFO hint; price list |
| Reports → Stock valuation | Method + as-of |

---

## 6. Work breakdown (tickets)

### Wave 4.0 — Warehouses + transfers (~42–52 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| INV-000 | `Warehouse` model + default backfill + API/FE | 5 | — |
| INV-001 | Movement + balance warehouse grain + rebuild command | 8 | INV-000 |
| INV-002 | Thread warehouse through sales/purchase/return/adjustment | 8 | INV-001 |
| INV-003 | FE warehouse on editors + stock pages | 5 | INV-002 |
| INV-004 | `StockTransfer` model/service complete/cancel | 8 | INV-001 |
| INV-005 | Transfer FE + print/PDF optional | 5 | INV-004 |
| INV-006 | Low stock per warehouse | 3 | INV-001 |
| INV-007 | Migration tests + dual-warehouse e2e | 5 | INV-004 |

### Wave 4.1 — Batch / expiry (~36–44 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| INV-100 | `track_batch` + `BatchLot` + movement/balance grain | 8 | INV-001 |
| INV-101 | Purchase/sales complete batch rules + FEFO helper | 8 | INV-100 |
| INV-102 | Billing FE batch picker + expiry columns | 5 | INV-101 |
| INV-103 | Expiry alerts API + page + optional notify | 5 | INV-100 |
| INV-104 | Block expired issue setting | 3 | INV-101 |
| INV-105 | Transfer preserves/moves batch qty | 5 | INV-004, INV-100 |
| INV-106 | Fixtures: multi-batch FEFO | 5 | INV-101 |

### Wave 4.2 — Valuation (~28–36 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| INV-200 | Company valuation method + service skeleton | 5 | — |
| INV-201 | WAVG engine + tests | 8 | INV-200 |
| INV-202 | FIFO engine + tests (batch-aware) | 8 | INV-200, INV-100 helpful |
| INV-203 | Sale `unit_cost` snapshot from engine | 5 | INV-201 |
| INV-204 | Stock valuation report + export | 5 | INV-201/202 |
| INV-205 | CA golden valuation fixtures | 3 | INV-201/202 |

### Wave 4.3 — Price lists (~18–24 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| INV-300 | PriceList models + API | 5 | — |
| INV-301 | Customer default list + billing fill | 5 | INV-300 |
| INV-302 | FE price list admin + editor integration | 5 | INV-301 |
| INV-303 | Import prices | 3 | INV-300 |

### Wave 4.4 — Serials (~28–34 pts) — demand-gated

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| INV-400 | Serial model + state machine | 8 | INV-001 |
| INV-401 | Purchase/sales serial capture | 8 | INV-400 |
| INV-402 | Transfer + return serial rules | 5 | INV-400 |
| INV-403 | FE + history report | 5 | INV-401 |
| INV-404 | Tests unique serial per company | 3 | INV-400 |

**4.0+4.1 exit:** ~78–96 pts ≈ **8–10 weeks**  
**Through 4.3:** ~124–156 pts ≈ **13–17 weeks**  
**With 4.4:** ~152–190 pts ≈ **16–22 weeks**

---

## 7. Testing strategy

| Layer | Must cover |
|-------|------------|
| Unit | Transfer out/in qty conservation; FEFO pick; WAVG/FIFO math |
| Integration | Purchase WH-A → transfer → sale WH-B; cancel transfer restores |
| Migration | Single-WH tenant rebuilds identical on_hand after backfill |
| Invariant | `sum(movements)=balance` per warehouse×product×batch |
| Valuation | Golden CA fixtures; method switch does not change past snapshots |
| E2E | Two warehouses, transfer, stock pages, expiry alert |

**Mandatory invariant:** For every completed `StockTransfer`, `sum(TRANSFER_OUT qty) == sum(TRANSFER_IN qty)` per product (and batch/serial).

---

## 8. Security & ops

| Topic | Rule |
|-------|------|
| Permissions | Transfers + valuation reports behind financial/inventory flags |
| Audit | Warehouse create, transfer complete/cancel, valuation method change |
| Performance | Indexes `(company, warehouse, product)`; valuation as-of may need Celery for large catalogs |
| Support | Rebuild balances command documented in runbook |

---

## 9. Risk register

| Risk | Mitigation |
|------|------------|
| Balance unique_together migration pain | Expand/contract + rebuild command; pilot dry-run |
| Free-text `batch_no` vs BatchLot dual truth | D4: ledger uses BatchLot FK; line snapshot stores batch_no string |
| FIFO without batches inaccurate | Prefer enabling FIFO after 4.1; WAVG default |
| Serial scope creep | D9 demand gate |
| Phase 7 doc conflict | This file owns warehouse depth |
| Valuation treated as editable GL | Report-only until Phase 5 posts COGS |

---

## 10. Definition of Done

### Phase 4.0 exit

- [ ] Default warehouse backfilled; all movements have warehouse
- [ ] Stock transfer complete/cancel with qty conservation test
- [ ] UI warehouse filters on stock + documents
- [ ] Rebuild balance command verified on pilot dump

### Phase 4.1 exit

- [ ] Batch-tracked products require lot on stock moves
- [ ] FEFO suggestion; expiry alerts; optional block expired
- [ ] Transfer moves batch quantities correctly

### Phase 4.2 exit

- [ ] WAVG + FIFO engines with CA golden fixtures
- [ ] Stock valuation report as-of date
- [ ] Sale movements snapshot unit_cost from engine

### Phase 4.3 exit

- [ ] ≥ 2 price lists; customer default; invoice line fill + override

### Phase 4.4 exit (if chartered)

- [ ] Serial unique; sale/transfer/return state machine; history report

Explicitly **not** required:

- [ ] Bin/rack WMS  
- [ ] Manufacturing  
- [ ] Landed-cost worksheet  
- [ ] SO soft reservation behaviour  

---

## 11. Open questions

| # | Question | Default | Freeze before |
|---|----------|---------|---------------|
| Q1 | Name: Warehouse vs Branch vs Godown? | **Warehouse** in UI; model `Warehouse` | 4.0 |
| Q2 | Existing batch_no strings when enabling track_batch? | Require opening lot entry; don’t auto-invent expiry | 4.1 |
| Q3 | Changing WAVG→FIFO mid-year? | Allowed prospectively; reports show method used | 4.2 |
| Q4 | In-transit warehouse? | Instant transfer only | 4.0 |
| Q5 | Price list tax-inclusive rates? | Follow document `price_mode` | 4.3 |
| Q6 | Which vertical needs serials for 4.4? | PM charter before INV-400 | 4.4 |

---

## 12. Slice order (first 10 engineering days)

1. INV-000 Warehouse + backfill  
2. INV-001 movement/balance grain + rebuild  
3. INV-002 thread through Complete paths  
4. INV-003 FE warehouse  
5. INV-004/005 Stock transfer  
6. Dual-WH e2e  
7. INV-100 batch schema  
8. INV-101 FEFO on sale  
9. Expiry alerts  
10. Pilot UAT with one distributor tenant

---

*Stock movements stay append-only and document-driven. Warehouses, batches, and serials are dimensions on the same ledger — not parallel inventable quantities.*
