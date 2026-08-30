# Item, Stock, Godown, and Expiry Management

**Status:** Proposed (revised after architecture + gap reviews)  
**Date:** 24 Aug 2026  
**Sources:** Competitor Create New Item screens, `Bulk Upload.xlsx`, Bizboard `Product` / `Warehouse` / `BatchLot` / `SerialNumber` / `StockBalance` / `StockMovement` / `InventoryCostLayer` / FEFO / expiry alerts.

---

## 1. Goal

Replace the competitor create-item + Excel path with a Bizboard flow that:

- Lets operators create and bulk-import items the same way they already think (name, HSN, prices, opening qty, godown).
- Tracks stock **per godown**.
- Tracks **expiry on batch lots**, not on the item master.
- Reuses the stock engine Bizboard already has. Do not invent a second inventory system.

**Hard architectural rule:** no inventory quantity changes anywhere without creating a `StockMovement` through `InventoryService.post_movement`. UI, import, POS, purchase, sale, transfer, adjustment, and expiry write-off all use that one path.

---

## 2. Non-negotiable design rule

**Do not put expiry or live quantity on the item itself.**

Milk, wallpaper, and biscuits in the sample file will have many inbound lots over time. Expiry belongs to a batch lot at a godown. Current stock is a derived balance, not a field you edit on the item after go-live.

The competitor UI mixing catalog + location + opening qty on one screen is acceptable as a **create wizard**. The saved data must stay in four layers.

---

## 3. Four-layer model

| Layer | What it is | What it is not | Bizboard today |
|---|---|---|---|
| **1. Item** | Catalog identity: name, SKU, barcode, HSN, unit, GST, prices, MRP, category, brand, goods vs service, track-inventory / track-batch / track-serial flags | Live quantity, expiry date | `Product`. Create form is missing type, tax-inclusive flags, alternate unit, description, category, MRP. |
| **2. Godown** | Stock location. Company always has one default. UI label = **Godown**. API name stays `Warehouse`. | Item field | `Warehouse` (name, code, default, active). Create-item only posts opening to a single dropdown. |
| **3. Batch lot** | One inbound identity: batch no, manufacturing date, expiry date. Created on opening, purchase, or manufacture | A date on the item | `BatchLot` unique on `(company, product, batch_no)`. Balances live at lot × godown. |
| **4. Stock balance** | Derived on-hand / reserved at item × godown × optional lot. Written only by append-only movements | A mutable cell on Product | `StockBalance` + `StockMovement`. Excel Current stock maps to one `OPENING_STOCK` movement. |

```
Godowns → Item master → Opening lots
                      → Purchases  → Sales (FEFO) → Expiry alerts
                       Opening lots ──────────────↗
                       Purchases ─────────────────↗
```

---

## 4. Hard rules

1. **Goods vs Service on every item.** Services (Internet 30MBPS in the xlsx) must not accept godown, opening qty, batch, or expiry. e-invoice already looks for `IsServc`.
2. **Opening qty is create-once per SKU × godown × lot.** After that `OPENING_STOCK` posts, quantity/expiry mistakes are corrected with `ADJUSTMENT` (or a new purchase). Never edit or delete the original opening movement.
3. **Track batch implies expiry on inbound.** If `track_batch` is on, every inbound row (opening or purchase) requires batch no + expiry. Blank expiry is only allowed when `track_batch` is off.
4. **One default godown always exists.** Blank Godown on bulk upload posts to the company default. Multi-location firms add named godowns first.
5. **FEFO on sale, not FIFO-by-item.** Outbound without an explicit lot consumes earliest expiry first. Expired lots are blocked when `company.block_expired_stock` is on.
6. **v1: batch and serial are mutually exclusive** on the same SKU.
7. **Do not auto-create godowns from bulk typos.**
8. **Do not treat Current stock as an upsert.** Re-upload of the same SKU must not rewrite balances.
9. **No quantity change without a `StockMovement`.**
10. **Posted movements are never edited or deleted.** Corrections are reversal movements.
11. **Stock posting is concurrency-safe and atomic.**

---

## 5. Item type matrix

Two independent fields. Do not collapse them into a single enum.

```
product_type:      GOODS | SERVICE
track_inventory:   true | false
track_batch:       true | false
track_serial:      true | false
```

| Product type | Track inventory | Track batch | Track serial | Stock, godown, opening, expiry |
|---|---|---|---|---|
| GOODS | Yes | Optional | Optional (xor batch) | Yes |
| GOODS | No | Forced false | Forced false | No (still Goods for GST) |
| SERVICE | Forced false | Forced false | Forced false | No |

**Server-side validation:** `SERVICE` always forces `track_inventory = track_batch = track_serial = false` and rejects any opening qty / lot / godown payload. UI hiding is not enough.

---

## 6. Competitor Excel → Bizboard

Sheet `bulk_upload`: 22 named columns, 5 samples (Milk, Wallpaper, Jeans, Internet 30MBPS, Monaco), cap 4,000 rows. **No godown, batch, expiry, or as-of-date column.**

| Excel column | Sample | Bizboard today | Decision |
|---|---|---|---|
| Item Name* | Milk | `Product.name` | Keep. Only mandatory field. |
| Description | Milk Boxes | `Product.description` | Expose on Basic Details. Import it. |
| Category | Dairy | `Product.category` | Auto-create Category on import. |
| Unit | MILLILITRE / PIECES | `Product.unit` | Map + auto-create Unit. Prefer UQC short codes. |
| Alternate Unit | (empty) | Missing | Phase 2. Conversion lives on the item, not on stock. |
| Conversion Rate | (empty) | Missing | Phase 2 with alternate unit. |
| Item code | MILK1 | `Product.sku` | Treat as SKU. Generate if blank. |
| HSN Code | 4010 / 05 / 8-digit | `Product.hsn_code` | Validate 4/6/8. Reject `05` unless padded. |
| GST Tax Rate(%) | 0.25 / 5 / 18 | `Product.gst_rate` | Keep. 0 is valid (service sample). |
| Sales Price | 40 | `Product.selling_price` | Keep. |
| Sales Tax inclusive | Inclusive / Exclusive | Missing | New flag. Default Exclusive if blank. |
| Purchase Price | 100 | `Product.purchase_price` | Keep. Also default opening unit cost. |
| Purchase Tax inclusive | Inclusive / Exclusive | Missing | New flag. Independent of sales. |
| MRP | 45 | `Product.mrp` | Expose on Pricing tab. Import it. |
| Current stock | 10000 | opening_stock CSV only | Do **not** store on Product. See §16. |
| Low stock alert quantity | 1000 | `Product.reorder_level` | Keep. Off unless > 0. Company-wide in Phase 1. |
| Item type | Product / Service | Missing | New `Product.product_type`. Service skips stock. |
| Visible on Online Store? | Yes / No | No store in Bizboard | Ignore on import. Do not block the file. |
| Discount | (empty) | Line-level only | Optional default sales discount %. Phase 2. |
| Brand Code | (empty) | Custom field in competitor | Custom field or `Brand.name`. Configurable. |
| Brand Form | (empty) | Custom field | Item Settings, not a hard column. |
| Sub Brand Form | (empty) | Custom field | Same. |

**What the Create New Item screens add that the xlsx does not:** Godown dropdown, opening qty, as-of date, Generate Barcode, Find HSN, + Alternative Unit, + Low stock warning, tax-inclusive price mode, Disc. on MRP, wholesale rate, Custom Fields tab.

**Expiry is missing in both the screens and the spreadsheet.** Close that gap in Stock Details, not in Pricing.

---

## 7. Create / edit item UI

Keep the competitor left-nav modal. Move opening stock into a real lot grid.

- Width: large dialog
- Footer: **Cancel · Save & New · Save Item**
- Save stays disabled until Name is filled and HSN (if entered) is valid
- Left nav: Basic Details * · Stock Details · Pricing Details · Custom Fields

### 7.1 Basic Details (required)

| Field | Behavior |
|---|---|
| Item type | Goods (default) or Service. Service hides Stock Details and rejects qty. |
| Item name * | Required. Warn on duplicate name; SKU must still be unique. |
| Item code / SKU | Optional. Generate if blank (`ITEM-…`). Unique per company. |
| Generate barcode | Fills barcode with a unique company-scoped value. Unique index already exists. |
| HSN / SAC | 4/6/8 digits. Find HSN opens the existing HSN helper. SAC when type is Service. |
| Measuring unit | Required for Goods. Standard UQC list (PCS, KG, LTR, …). **Immutable after the first stock movement.** |
| + Alternative unit | Phase 2 UI. Conversion **rules are locked now** (§23). Do not implement billing conversion in Phase 1. |
| Description | Free text. Maps to `Product.description`. |

Godown / opening qty do **not** live here even though the competitor screenshot places them under Basic.

### 7.2 Stock Details (Goods only)

This is the expiry home. Tracking flags first, then a repeatable opening-lot grid. Edit mode locks the grid and links to Stock Adjustment.

| Control | Rules |
|---|---|
| Track inventory | On for Goods. Off = non-stock item (still Goods for GST) — no godown, no movements. |
| Tracking mode | Radio: **None · Batch / expiry · Serial**. Mutually exclusive. Disabled after any stock movement exists. Tooltip: batch = lots with expiry; serial = one ID per physical unit. |
| Opening lots grid | Shown when tracking = Batch. Rows: Godown · Qty · As of date · Unit cost · Batch no · Expiry · Mfg date optional. **+ Add godown / lot**. Header: **Apply godown to all rows**. |
| Opening serials grid | Shown when tracking = Serial. One row per unit: Godown · Serial no · As of date · Unit cost. Paste/import a list of serials. Qty is implied = number of serial rows. |
| Godown | Defaults to company default. Must already exist. **+ New godown** inline (name + code) then select. |
| As of date | Accounting date of `OPENING_STOCK`. Default today. See §17. |
| Low stock warning | Collapsed **+ Enable…** then reorder qty. 0 or blank = off. Compared to **company-wide available** in Phase 1 (not per lot / not per godown). Schema must not block a later per-godown reorder rule. |

**Opening grid example (Milk, batch on)**

| Godown | Qty | As of | Batch no | Expiry | Unit cost |
|---|---|---|---|---|---|
| Main godown | 6,000 ML | 01 Apr 2026 | LOT-A | 15 Sep 2026 | ₹0.01 |
| Cold room | 4,000 ML | 01 Apr 2026 | LOT-B | 22 Sep 2026 | ₹0.01 |

Two lots, two expiry dates, one item. This is the shape Excel Current stock cannot express.

### 7.3 Pricing Details

| Field | Rules |
|---|---|
| Sales price | ₹ + With tax / Without tax. Persist `selling_tax_inclusive`. See §7.3.1. |
| Purchase price | ₹ + With tax / Without tax. Persist `purchase_tax_inclusive`. Independent of sales. Default opening `unit_cost` is always **tax-exclusive**. |
| MRP | Optional. Disc. on MRP is display-only: `(MRP − sales) / MRP`. |
| GST tax rate | 0, 0.25, 3, 5, 12, 18, 28 + None. None stores 0. |
| Discount on sales price | Optional default %. Invoice lines can override. |
| + Wholesale rate | Phase 2 PriceList. Not required for stock go-live. |

#### 7.3.1 Tax-inclusive vs exclusive

Reuse existing invoice `price_mode` math. Item flags only set the **default** for new documents.

| Flag | Meaning |
|---|---|
| `selling_tax_inclusive = false` (default if blank) | GST added on top: `tax = exclusive × rate/100` |
| `selling_tax_inclusive = true` | Price includes GST: `exclusive = inclusive / (1 + rate/100)`, `tax = inclusive − exclusive` |
| `purchase_tax_inclusive` | Same formulas, independent of sales |

- Opening `unit_cost` and cost layers always store **tax-exclusive** cost. If the import/UI purchase price is inclusive, extract exclusive before posting `OPENING_STOCK`.
- Existing products with no flag → Exclusive (matches current invoice default).
- UI may show both inclusive and exclusive, but stock valuation never stores GST in `unit_cost`.

### 7.4 Custom Fields

Yellow banner: manage definitions in Item Settings. Brand Code / Brand Form / Sub Brand Form are the first three custom keys for firms migrating from that template — not first-class Product columns.

If Brand is already a master, map Brand Code → Brand when the value matches; otherwise store as a custom field so import does not fail.

### 7.5 Pages outside the modal

| Page | Job |
|---|---|
| `/inventory/warehouses` | Godown master. Rename label to **Godowns**. Default + active. |
| `/inventory/stock` | Current stock. Filter by godown; expand row to lots + expiry. |
| `/inventory/adjustments` | Post-go-live qty correction. Never edit `Product.opening`. |
| `/inventory/transfers` | Godown A → B, same lot / serial. Atomic OUT+IN. |
| `/inventory/expiry-alerts` | Lots with on-hand and expiry within 7 / 30 / 60 / 90 days. |
| `/inventory/low-stock` | Available ≤ reorder level (company-wide in Phase 1). |
| `/inventory/serials` | Only when `track_serial`. |

---

## 8. Inventory movement model

Use the **existing** `MovementType` enum. Do not add a parallel taxonomy for this feature.

| Movement type | Qty | Value | When |
|---|---:|---|---|
| `OPENING_STOCK` | + | + at `unit_cost` | Item create / opening import |
| `PURCHASE` | + | + at purchase line cost | Posted purchase invoice (Phase 1: invoice **is** the receipt) |
| `SALE` | − | − COGS of consumed lot/layer | Posted sales invoice / POS |
| `SALES_RETURN` | + | + restore original sale cost | Posted sales return / credit note |
| `PURCHASE_RETURN` | − | − | Posted purchase return |
| `ADJUSTMENT` | ± | configurable; expiry write-off uses reason `EXPIRED` | Manual adjustment, physical excess/shortage, expiry write-off |
| `TRANSFER_OUT` | − | no company-level value change | Stock transfer complete |
| `TRANSFER_IN` | + | same `unit_cost` as the paired OUT | Same transfer |
| `MANUFACTURE_ISSUE` | − | − | Existing manufacturing engine only — **out of this feature’s Phase 1 UI** |
| `MANUFACTURE_RECEIPT` | + | + | Same |

Expiry write-off is **not** a new movement type in Phase 1. It posts `ADJUSTMENT` with `reason=EXPIRED` so the ledger stays one enum.

**Purchase posting (Phase 1):** posting a purchase invoice immediately posts `PURCHASE` stock. No separate GRN / goods-receipt document in this phase.

---

## 9. Stock valuation

Reuse `company.inventory_valuation_method` (`WAVG` | `FIFO`) and `InventoryCostLayer`. Do not invent a third method for this feature.

### Batched items (`track_batch = true`)

> Each inbound lot carries its `unit_cost`. Outbound consumes the cost of the **consumed lot**. FEFO chooses *which* lot; that lot’s cost is COGS.

Example: Lot A 100 @ ₹10, Lot B 100 @ ₹20, sell 50 with FEFO → Lot A, COGS = ₹500, remaining Lot A 50 @ ₹10.

### Unbatched items

Follow the company method already on `Company`:

- **FIFO:** peel `InventoryCostLayer` oldest first (already implemented).
- **WAVG:** moving weighted average (already implemented).

### Other movements

| Event | Cost rule |
|---|---|
| Transfer | OUT and IN share the same `unit_cost`. Company inventory value unchanged. |
| Sales return | Restore the original sale movement’s `unit_cost` into the original lot when identifiable (already the sales-return path). |
| Purchase return | Reverse the purchase layer / lot qty. |
| Adjustment in | Operator supplies `unit_cost` (default: current valuation unit cost). |
| Adjustment out / expiry write-off | Consume FEFO (batched) or company method (unbatched). |

Do not support standard cost or multiple concurrent valuation methods in Phase 1.

---

## 10. FEFO allocation (partial consumption)

FEFO must split a line across lots and **persist** which lots were consumed. Do not allocate in memory and then post a single unbatched movement.

Example: lots A=10 (1 Sep), B=20 (10 Sep), C=30 (20 Sep). Order qty 25 → A 10 + B 15.

**Persistence (existing engine, make it mandatory for this feature):**

```
SalesInvoiceLine
    → one StockMovement per consumed lot (movement_type=SALE, batch=that lot)
    → InventoryCostLayer peels on each movement (`layer_peels`)
```

Do not add a separate `StockAllocation` table unless the current movement-per-lot path cannot answer:

- Which lot was sold?
- Which expiry remains?
- Which lot to restore on return?
- What was actual COGS?

If a line pins a lot, consume only that lot (still refuse expired / insufficient).

**Tie-break when expiry dates are equal:**

1. Expiry date ascending (FEFO)
2. Manufacturing date ascending (older first; nulls last)
3. Batch no ascending
4. `BatchLot.id` ascending

Partial lots are first-class: consume 10 from a lot of 10, 15 from a lot of 20. Expired lots (`expiry_date < business_date`) are excluded when `block_expired_stock` is on.

Use existing balances + `select_for_update`; do not add a new allocation table. Index already present on `BatchLot.expiry_date`.

---

## 11. Returns and reversals

Posted stock is never edited. Wrong stock is reversed.

### Sales return (must define before production; implement in Phase 1 if sales returns already exist)

```
Sales return line
  → original sale movements for that invoice line (lot + unit_cost)
  → post SALES_RETURN into the original lot and godown
```

| Case | Phase 1 rule |
|---|---|
| Original lot identifiable | Return to that lot at original sale `unit_cost`. |
| Lot now expired | Still restore qty to that lot; **sale of that lot remains blocked** until write-off or company allows expired stock. Do not silently dump into a new lot. |
| Lot / godown unknown (no original allocation) | Refuse auto-restore. Operator must post an Adjustment in (reason `RETURN_UNIDENTIFIED`) after inspection. |
| Damaged return | Do not restore sellable stock. Adjustment in to a write-off path, or restore then immediate `ADJUSTMENT` out with reason `DAMAGED`. Prefer restore + write-off so the lot history stays intact. |
| Different godown | Phase 1: return to the **original sale godown** only. Transfer afterwards if needed. |

Purchase returns post `PURCHASE_RETURN` against the original purchase lot. Cannot return more than remaining on that lot at that godown.

---

## 12. Negative stock and reservation

### Negative stock

Phase 1 default: **do not allow negative stock** (`company.negative_stock_policy = BLOCK`, already exists).

Availability check uses:

```
available = on_hand − reserved
```

Selling 15 when available is 10 → API 400 `Insufficient stock`. Do not post a movement that would take `on_hand` or `available` below zero under BLOCK.

WARN policy (existing company setting) is out of this feature’s UI; do not change its meaning.

### Reservation (Phase 1 of *this* item-flow)

`StockBalance.reserved` already exists for sales-order reservation. **This feature does not add a new reservation engine** (no POS cart reserve, no draft-invoice reserve, no e-commerce reserve, no reservation expiry job).

For item create / opening / bulk import: reserved stays 0.

When posting a sale against a reserved SO, consume reserved first via the existing `InventoryService` reserve/release path. Do not double-count.

---

## 13. Batch uniqueness and lifecycle

**Logical lot identity** (already constrained):

```
unique (company, product, batch_no)
```

The same batch **may** have stock in many godowns. That is a `StockBalance` per `(warehouse, product, batch)`, not a second `BatchLot`.

Repeated purchase receipts of the same batch no **add qty to the existing lot**, they do not create a second lot. If the new receipt’s expiry differs from the existing lot’s expiry → **reject** (do not silently overwrite expiry).

Batch no is unique per item, not per godown. Transfers keep the same `BatchLot` id.

---

## 14. Item lifecycle restrictions

Once any stock movement exists for the product, the following are **immutable** (API 400):

- Base unit
- `product_type` (GOODS ↔ SERVICE)
- `track_inventory` on → off or off → on
- `track_batch` on → off or off → on
- `track_serial` on → off or off → on

To change tracking after stock exists, the operator must:

1. Adjust remaining qty to zero (and write off / transfer as needed).
2. Then change the flag (still blocked if any movement exists — so this remains a **support / data-migration** path, not a self-serve toggle in Phase 1).

Phase 1 product decision: **block the toggle as soon as any `StockMovement` exists**, including historical zeroed stock. Simpler and safer than a migrate-wizard.

SKU / barcode uniqueness: still unique per company when non-blank.

### 14.1 Opening correction (not an edit)

| Mistake | Correction |
|---|---|
| Wrong qty | `ADJUSTMENT` in/out with reason `OPENING_CORRECTION`. Original `OPENING_STOCK` stays. |
| Wrong expiry / batch no | Adjustment out of the wrong lot + adjustment (or purchase) in of the correct lot. Do not mutate `BatchLot.expiry_date` if that lot already has outbound movements. If the lot has **only** opening remaining, still prefer adjustment out/in so the ledger stays append-only. |
| Wrong godown | Transfer, or adjustment out + in. |
| Need batch tracking later | Phase 1: **blocked** once any movement exists (including opening). Support/data-migration only. Do not ship a self-serve “zero stock then flip flag” wizard in this phase. |

“Create-once” = one `OPENING_STOCK` per **SKU × godown × lot** (unbatched: SKU × godown).

---

## 15. Godown master and lifecycle

Phase 1 fields (existing `Warehouse` plus labels). **No hierarchy, bins, or godown-type enum.**

| Field | Required | Notes |
|---|---|---|
| Name | Yes | Display name. UI: Godown. |
| Code | Yes | Unique per company. |
| Address | No | Free text. |
| Active | Yes | Default true. Inactive cannot receive new stock. |
| Default | Yes | Exactly one per company. |

| Action | Allowed when |
|---|---|
| Delete | Never if any `StockMovement` exists for that warehouse. If unused (no movements, not default) → allow. |
| Deactivate | `on_hand = 0` and `reserved = 0` on all balances, and not the default godown. Else require transfer out first. |
| Change default | Target must be active. Exactly one default remains. |

---

| Action | Allowed when |
|---|---|
| Delete | Never if any `StockMovement` exists for that warehouse. If unused (no movements, not default) → allow. |
| Deactivate | `on_hand = 0` and `reserved = 0` on all balances, and not the default godown. Else require transfer out first. |
| Change default | Target must be active. Exactly one default remains. |

---

## 16. Bulk upload — atomicity and idempotency

Operators will upload this exact xlsx. Import must alias their headers onto the existing PRODUCTS job, then split quantity out of the item row.

### Sheet 1 — `items`

Catalog only. Current stock on this sheet is allowed **only** when track batch is off **and** the row is Goods: it becomes one opening movement on the default godown, as-of = upload date.

### Sheet 2 — `opening_lots` (new)

Required whenever track batch is on, or stock is split across godowns. One item, many rows.

| Column | Required | Notes |
|---|---|---|
| Item code / SKU | Yes | Must match sheet 1. |
| Godown | If blank → default | Must exist (match name or code, case-insensitive trim). Unknown godown **fails the job**. Error lists available godowns. Do **not** skip the row, do **not** fall back to default when a name was supplied. |
| Quantity | Yes | > 0. Base unit of the item. |
| As of date | No | Default upload date / FY start if provided in job options. |
| Batch no | If item tracks batch | Unique per item (logical lot). Same batch in two godowns = two balance rows, one `BatchLot`. |
| Expiry date | If item tracks batch | ISO or Excel date. Cannot be before as-of. |
| Manufacturing date | No | Optional; must be ≤ expiry. |
| Unit cost | No | Else purchase price from the item row (tax-exclusive). |

### Sheet 3 — `opening_serials` (new, serial-tracked SKUs only)

| Column | Required | Notes |
|---|---|---|
| Item code / SKU | Yes | Must match sheet 1 and `track_serial`. |
| Godown | If blank → default | Same match/fail rules as lots. |
| Serial no | Yes | Unique per item. Duplicate in file or DB fails the job. |
| As of date | No | Default upload date. |
| Unit cost | No | Exclusive; default purchase price. |

One serial = qty 1. Do not put serials on sheet 1 Current stock.

### Job flow

```
Upload → Parse → Validate → Preview → User confirms → Commit
```

Statuses (align with existing import job if present): `DRAFT` → `VALIDATING` → `VALIDATED` → `COMMITTED` | `FAILED`. Optional later: `ROLLED_BACK`.

**Phase 1 opening-stock import is atomic per job.** If any critical row fails, post **no** opening movements. Catalog-only rows (no qty) may still be created only if the whole job is valid; simpler rule: **any error → commit nothing.**

Do not silently import 3,998 of 4,000 opening rows.

### Idempotency

```
ImportJob: id, company, file_hash, uploaded_at, status
StockMovement: reference_type=BULK_IMPORT, reference_id=ImportJobRow.id
```

- Same file hash while a job is `COMMITTED` → reject or no-op, do not double-post.
- Network retry of the same job id is idempotent.
- Re-upload of the same SKU in a **new** file still must not create a second `OPENING_STOCK` if one already exists for that SKU × godown × lot (existing “opening already recorded” check).

### Category and unit matching (import)

- Category: match `trim + casefold` of name. If found, reuse. If not, create with defaults **only on import** (not on manual create). Do not merge “Dairy” vs “Dairy Products”.
- Unit: match UQC code first (`ML`, `PCS`, `KGS`, …), then name casefold. Prefer mapping MILLILITRE → ML. If unmappable → fail the job with the valid UQC list. Do not create free-text units that are not UQC.
- No Phase 1 admin toggle for “allow auto-create”. Always auto-create category; never auto-create unknown units.

### Template, preview, errors

- Download `.xlsx` template: sheet `items` + sheet `opening_lots`, frozen header, sample rows, notes (“use default godown if blank”). Cap **4,000 rows** / **5 MB**.
- Validate **all** rows before commit. Preview: valid count, error table (sheet, row, column, message).
- Atomic commit: any error → commit nothing. Do **not** “proceed with 12 valid items”.
- Error copy (examples):
  - `Godown 'X' not found. Available: Main, Cold room.`
  - `Batch tracking is on but row 14 has no Batch no or Expiry.`
  - `Service items cannot have opening stock (row 8, Current stock=100).`
  - `HSN '05' is invalid. Use 4, 6, or 8 digits.`
  - `Duplicate Item code 'MILK1' in this file.`
  - `Expiry 01 Mar 2026 cannot be before As of 01 Apr 2026.`
  - `This file was already committed (job {id}).`

---

## 17. Opening stock date vs books

Opening as-of date must satisfy **all** of:

| Bound | Rule |
|---|---|
| Max | ≤ today (company timezone). Cannot be after books lock / period close if one exists. |
| Min | ≥ company books start / FY start configured on the company (if set). If unset, allow any past date but warn in preview. |
| vs item create | Backdated opening is allowed (create item on 1 Aug, opening as-of 1 Apr) **only if** no other stock movements exist yet for that SKU and the date passes the bounds above. |
| vs GST | Opening does not generate GST invoices. It must not rewrite posted GST periods. If as-of falls in a locked GST period, reject. |

---

## 18. Day-to-day operating flow

### Purchase (inbound)

Posting the purchase invoice immediately posts `PURCHASE`. If the item tracks batch, each line must choose or create a lot (batch no + expiry). If it tracks serial, the line must list `qty` distinct serials. Godown is the document warehouse on the purchase header.

### Sale / POS (outbound)

Leave batch blank → FEFO allocates earliest expiry with available qty, persisted per lot. Operator may pin a lot. Expired lots are refused when `block_expired_stock` is on (company default). Serial items require `qty` `AVAILABLE` serials at that godown, not lots.

### Transfer between godowns

One `StockTransfer` document. Complete posts `TRANSFER_OUT` + `TRANSFER_IN` in **one transaction** sharing `reference_id = transfer.id`. Never leave an unpaired OUT. Same lot identity; expiry does not change. Cannot transfer more than available at source.

### Expiry definition

Centralize in one function (POS, invoice, API, alerts, jobs all call it):

> A lot is expired when `expiry_date < business_date`, where `business_date` is `timezone.localdate()` in the **company timezone**. Stock remains sellable through the end of the expiry date.

Do not use `<=` (that would block on the expiry day itself).

### Expiry desk

`/inventory/expiry-alerts` already lists lots with on-hand and expiry within N days. Add:

- Horizon chips: 7 / 30 / 60 / 90 days
- Godown filter
- Remaining qty
- One-click `ADJUSTMENT` out with `reason=EXPIRED`
- Nearest expiry on Current stock rows when the item tracks batch

**Notifications** (email/push per remaining-day) are **not Phase 1**. If added later: fire once per lot per threshold (90 / 60 / 30 / 7 / expired), not every calendar day.

### Operators must never

- Add an Expiry date field on Basic Details
- Let Current stock on the item edit screen become a live spinner
- Auto-create godowns from bulk typos
- Allow `track_batch` and `track_serial` on the same SKU in v1

---

## 19. Backend invariants

UI validation improves usability. **Every rule below is enforced server-side.**

Reject (400) when any of:

- `product_type=SERVICE` with opening qty, godown, `track_inventory`, `track_batch`, or `track_serial`
- `track_batch` and `track_serial` both true
- `track_batch` inbound without batch no or expiry
- Expiry date &lt; manufacturing date
- Expired lot on opening / purchase / sale when `block_expired_stock` is on (sale/issue only; opening of already-expired stock: **reject** in Phase 1)
- Negative qty or negative `unit_cost`
- Unknown / inactive godown
- Duplicate SKU or barcode (non-blank) per company
- HSN/SAC not 4/6/8 digits when provided
- Insufficient `available` under BLOCK
- Transfer OUT without matching IN in the same transaction
- Mutation of a posted `StockMovement`
- Tracking-flag or base-unit change after any movement exists
- Batch expiry mismatch on a second receipt of the same `batch_no`

---

## 20. Concurrency and audit

Stock posting must:

```
BEGIN
  lock StockBalance (and cost layers) FOR UPDATE
  validate available
  insert StockMovement(s)
  update derived balance / layers
COMMIT
```

Two cashiers selling the last 5 units: one succeeds, one gets insufficient stock. Do not both read 5 and both post.

Every `StockMovement` already carries / must carry:

`id, company_id, warehouse_id, product_id, batch_id?, movement_type, quantity (signed), unit_cost, reference_type, reference_id, reason, created_at, created_by`

If a posted movement is wrong: original + reversal. Never update/delete.

`StockMovement` **is** the stock audit trail. Do not add a parallel `stock_audit_log`. Balances stay a derived cache of movements (`StockBalance`); rebuild command already exists.

---

## 21. Serial numbers (Phase 1 basics)

Reuse `SerialNumber` (`AVAILABLE` / `SOLD` / `RETURNED` / `SCRAPPED`). Unique on `(company, product, serial_number)`.

| Event | Rule |
|---|---|
| Opening | One serial row = qty 1. Post `OPENING_STOCK` qty = serial count at that godown; attach serials on the movement. Status `AVAILABLE`. |
| Purchase | Require N distinct unused serials for qty N. Status `AVAILABLE` at document godown. |
| Sale | Require N `AVAILABLE` serials at that godown. Status `SOLD`. |
| Sales return | Original serials → `RETURNED` then `AVAILABLE` at original godown (same as lot restore). Damaged → `SCRAPPED` via adjustment. |
| Transfer | Serials must be `AVAILABLE` at source; godown FK moves with atomic OUT+IN. |
| Adjustment out | Status `SCRAPPED`. |

No serial format regex in Phase 1 (trim, non-empty, unique). Batch + serial together remains 400.

---

## 22. Alternate UOM (design now, build Phase 2)

Do not ship conversion in Phase 1. When built:

1. Base unit is the only stock unit.
2. `1 alternate = X base` (`X > 0`).
3. Documents may enter qty in alternate; convert to base before `post_movement`.
4. Conversion uses 4 decimal places internally; money still 2.
5. Alternate must be a UQC. Reverse: inbound in alternate converts to base.
6. Cannot change base unit after movements (already §14).

---

## 23. Existing-product migration

On deploy of this feature:

- Existing products → `product_type=GOODS`, `track_batch=false`, `track_serial=false` unless already set.
- Do **not** invent a `Product.opening_stock` field. Historical qty already lives in movements/balances.
- New create/import uses the wizard + `OPENING_STOCK`.
- Enabling batch on a live SKU is blocked (§14). Tenant that needs it: support migration, not self-serve.

---

## 24. APIs (extend existing, do not fork)

| Need | Existing / extend |
|---|---|
| Create item + opening lots | `POST` products (extend payload with opening rows) then existing `opening-stock/` |
| Bulk import | Existing import job `kind=PRODUCTS` + new `opening_lots` sheet |
| Stock summary | `GET inventory/balances/` (filter product, warehouse) |
| Lots | `GET inventory/batches/?product=` |
| Serials | `GET/POST inventory/serials/` |
| Expiry alerts | `GET inventory/alerts/expiry/?days=&warehouse=` |
| Adjustments | `POST inventory/adjustments/` |
| Godowns | `inventory/warehouses/` |

All stock-changing endpoints call `InventoryService.post_movement`. Permissions: item create / opening / import = inventory mutate roles already used on Products; godown create = same as warehouse create; adjustments = existing adjustment permission. No new RBAC matrix in this feature.

---

## 25. Out of scope (do not build in this Phase 1)

- Multi-level warehouse / bin locations
- New reservation engine (POS cart, draft invoice, e-commerce)
- Manufacturing / BOM UI (engine types already exist; leave them alone)
- Separate GRN vs purchase invoice
- Advanced replenishment / auto PO
- Per-godown pricing
- Complex approval workflows
- Multiple valuation methods beyond existing WAVG/FIFO
- Alternate units, wholesale price lists, Find HSN / Generate barcode (Phase 2 of the UI)
- Per-godown reorder levels (schema-ready later; company-wide only now)
- Expiry notification engine (UI page only)
- Stock count session / physical inventory **workflow** (adjustment remains the Phase 1 correction tool; count session is the natural next module)
- Godown hierarchy / bins / godown-type enum
- Partial import (“skip invalid rows”)
- Auto-create godowns from Excel
- Self-serve tracking-flag change after movements
- Separate stock audit table
- Expiry email/push engine; customizable horizons beyond 7/30/60/90 in Phase 1
- Serial format validation beyond uniqueness
- i18n of the word Godown (platform i18n later)

---

## 26. Delivery

### Phase 1 (stock go-live)

- [ ] `Product.product_type` (`GOODS` / `SERVICE`) + `track_inventory` matrix; hide/reject stock for services
- [ ] Tabbed Create Item modal: Basic, Stock (lot grid), Pricing (MRP + tax inclusive), Custom Fields
- [ ] Opening lots: multi-godown, as-of date, batch + expiry when `track_batch`; post one `OPENING_STOCK` per row via `post_movement`
- [ ] Opening serials grid when tracking = Serial (existing `SerialNumber`)
- [ ] Tax-inclusive flags; opening `unit_cost` stored exclusive
- [ ] UI copy **Godown** for Warehouse; inline create godown from the item modal
- [ ] Template download; preview + error table; atomic job; file-hash idempotency; unknown godown fails the job with available list
- [ ] Accept `Bulk Upload.xlsx` aliases; two-sheet `opening_lots`; reject service qty and batched Current stock
- [ ] FEFO sale persists per-lot movements; insufficient stock BLOCK; no negative on-hand
- [ ] Transfer complete is atomic OUT+IN
- [ ] Expiry = `expiry_date < local business date`; alerts: horizon + godown + remaining qty; write-off as `ADJUSTMENT` / `EXPIRED`
- [ ] Freeze unit and tracking flags after first movement
- [ ] Godown deactivate/delete rules

### Phase 2 (later)

- [ ] Alternate unit + conversion rate on item and billing (rules in §22)
- [ ] Opening serial bulk paste UX polish if needed
- [ ] Configurable item custom fields (Brand Code / Form) and wholesale price list
- [ ] Find HSN + Generate barcode actions in Basic Details
- [ ] Sales/purchase return inspection states if current return path is too thin
- [ ] Per-godown reorder rules
- [ ] Stock count session → variance → adjustment
- [ ] Expiry notification thresholds (once per lot per band)

### Phase 1 done when

**Happy path**

| Scenario | Pass |
|---|---|
| Create Milk as Goods, track batch, two godown lots with different expiry | One Product, one `BatchLot` per batch no, two balances. Item edit cannot change qty. |
| Create Internet 30MBPS as Service | No warehouse, no opening, no track batch. Invoice line `IsServc = Y`. API rejects opening payload. |
| Upload their xlsx as-is (unbatched goods) | Five items. Four openings on default godown. Service has zero stock. Online Store ignored. |
| Upload xlsx + `opening_lots` for Milk | Sheet-1 Current stock ignored because lots exist; FEFO sale picks earliest expiry and splits lots. |
| Sell 25 across lots 10+20+30 | Movements: 10 of A + 15 of B. C untouched. |
| Sell after expiry with `block_expired_stock` on | API 400. Alert page still shows remaining expired qty for write-off. |
| Transfer Main → Cold room, same lot | One transfer id, OUT+IN, value unchanged. |
| Two concurrent sales of last 5 | One 400 insufficient; on-hand never negative. |

**Failure / edge (mandatory)**

| Scenario | Pass |
|---|---|
| Duplicate SKU or barcode | 400 / import reject |
| Invalid HSN | 400 / import reject |
| Service + opening qty | 400 / import reject |
| Batch + serial both on | 400 |
| Missing batch no or expiry when track_batch | 400 |
| Expiry before manufacturing | 400 |
| Expired opening lot | Reject in Phase 1 |
| Sell more than available | 400 |
| Transfer more than source available | 400 |
| Adjustment that would go negative | 400 under BLOCK |
| Enable batch after any movement exists | 400 |
| Disable batch while lots have stock | 400 |
| Change base unit after movements | 400 |
| Same import file uploaded twice | Second commit no-ops / rejects; qty not doubled |
| 1 invalid row among 4,000 opening rows | Entire job fails; zero opening movements |
| Duplicate SKU inside same file | Job fails |
| Opening lot unknown SKU or inactive godown | Job fails |
| Deactivate godown with stock | 400 |
| Unpaired transfer OUT | Impossible (same transaction) |
| Duplicate serial on opening | 400 / import reject |
| Sell serial not AVAILABLE at godown | 400 |
| Inclusive purchase price on opening | Cost layer stores exclusive |
| 4,000-row valid file | Commits; preview &lt; 30s target |
| File with 100% errors | FAILED; zero products/movements |
| Edit opening qty after save | Impossible; must use adjustment |
