# Manufacturing enhancement — feature analysis and plan

**Date:** 2026-10-20
**Status:** Built (2026-10-21) as set out in docs/MANUFACTURING_IMPLEMENTATION_PLAN.md, section 12. The recommended decisions were taken as approved. Everything that can be built is built (a second pass on 2026-10-21 added the stock revaluation, outside-step job work, the extra-material approval request, the offline tablet, the batch label and the work order export). What remains open needs a person, a device or real data, and is tracked as QOS-0141 to QOS-0145.
**Input:** the founder's 15-section feature list (pasted in chat, 2026-10-20), the current code
in `backend/manufacturing/`, `backend/inventory/`, `backend/accounting/services.py`,
`backend/purchases/`, `backend/sales/`, and a competitor scan.
**Implementation plan:** [../MANUFACTURING_IMPLEMENTATION_PLAN.md](../MANUFACTURING_IMPLEMENTATION_PLAN.md)
(engineering rules, data model, tests, rollout, per-WP exit gates).
**Supersedes:** the "Manufacturing" part of
[PAYROLL_AND_MANUFACTURING_CAPABILITY_2026-09-28.md](PAYROLL_AND_MANUFACTURING_CAPABILITY_2026-09-28.md)
only as a plan. That note stays correct as a description of today's code.

---

## 1. Summary

- The founder's list describes a full manufacturing ERP, about 150 features. Bizboard has
  about 10 today.
- The list is a good catalogue, but it is not a plan. It mixes features that already exist in
  other Bizboard modules, features no Indian MSME competitor has, and features that need a
  separate product (IoT, AI forecasting).
- **The real opportunity:** Indian SME tools (Tally, Busy, Marg, Vyapar) do BOM and job-work
  vouchers, but little planning, quality or costing. Global SME tools (MRPeasy, Katana,
  Odoo, ERPNext) do planning but are weak on Indian job-work and GST, and cost much more to
  set up. TranZact sits in between and is the closest direct competitor.
- **Bizboard's edge:** one stock ledger, WAVG running cost (FIFO layers optional), batch and serial tracking, GL
  posting, GST, e-way bill and period locks are already built and tested. Manufacturing
  should *use* these, not rebuild them.
- **Two items the original list under-weights:**
  1. **Job work as the job worker** ("job work IN"). Many MSMEs are job workers for a
     bigger principal. The list only covers sending work out.
  2. **A one-screen production entry.** Most small units record production after the fact
     ("made 200 kg today, used this"). A heavy work-order flow loses them.
- **Fix three defects first.** Today's module has three defects that must be fixed before
  anything is built on top (section 3.2).

Recommended shape: **7 phases (0–6), 38 work packages (MFG-00 … MFG-37; MFG-37 added in rev 2) plus 5 cross-cutting (MFG-X1 … X5)**. Phases 0–2
are the product; later phases are pilot-driven.

---

## 2. What exists today (verified in code, 2026-10-20)

### 2.1 Manufacturing module

| Area | Today | Where |
|---|---|---|
| BOM | Header (product, name, status DRAFT/ACTIVE/ARCHIVED) and lines (component, qty > 0) | `manufacturing/models.py` `Bom`, `BomLine` |
| BOM basis | Qty is per **1 unit** of finished good. No batch size, no unit per line | `BomLine.qty` |
| BOM versions | None. Several ACTIVE BOMs per product allowed (B8-018) | model docstring |
| Multi-level | Refused at release with a clear error. Cycle check exists | `services.py` B8-008, `assert_no_bom_cycle` |
| Work order | Status DRAFT → RELEASED → COMPLETED / CANCELLED. No number series, due date, priority or sales-order link | `WorkOrder` |
| Snapshot | Component lines frozen at WO creation, editable in draft (batch, lots, serials) | `WorkOrderLine`, B8-019 |
| Issue | **All** components issued at release. No partial issue, no extra issue, no return | `release_work_order` |
| Receipt | **One** receipt of the full qty at completion. No partial, no by-product or scrap (B8-009) | `complete_work_order` |
| Batch / serial | FEFO or explicit lot allocation on issue. FG batch with mfg/expiry date. FG serials | `_issue_batches`, `complete_work_order` |
| Cancel | Reverses FG (if unsold) and component issues, restores FIFO peels, reverses GL | `cancel_work_order` |
| GL | Release: Dr 1450 WIP / Cr 1400 Inventory. Complete: Dr 1400 / Cr 1450. Material cost only | `accounting/services.py` `post_work_order_*` |
| Period | Period gate on release, complete and cancel. Year close blocked by open WIP (`OPEN_WIP`) | `accounting/services.py`, `reports.py` |
| Access | **Owner only** (`IsOwner`), behind `ENABLE_MANUFACTURING` | `views.py`, `permissions.py` |
| UI | `BomsPage.tsx` (376 lines), `WorkOrdersPage.tsx` (525 lines) | `web/src/pages/manufacturing/` |

### 2.2 Building blocks elsewhere in Bizboard that manufacturing can reuse

| Block | What it gives | Where |
|---|---|---|
| `InventoryService.post_movement` | Locked, single stock ledger with FIFO layers and peel restore | `inventory/services.py` |
| `StockReservation` / `reserve_stock` | Timed holds that reduce `available`. Needs a non-expiring, document-linked mode for WOs | `inventory/models.py` |
| `WarehouseReorderLevel` | Per-warehouse reorder level, **lead_time_days**, **safety_stock_qty**: MRP inputs already exist | `inventory/models.py` |
| `BatchLot` | Batch, mfg date, expiry. Needs a quality status | `inventory/models.py` |
| `GoodsReceipt` | GRN against PO with **quantity_accepted / quantity_rejected**: incoming inspection half-exists | `purchases/models.py` |
| `PurchaseOrder` | Purchase suggestions can create PO drafts | `purchases/models.py` |
| `DeliveryChallan` | Challan with e-way bill fields and `sub_supply_type` (now always "8" Others). Job work is e-way sub-type "Job Work" | `sales/models.py` |
| `Product` | `track_batch`, `track_serial`, `regulated_category` (FOOD/DRUG), `unit` + **one** `alternate_unit` + `conversion_rate` | `masters/models.py` |
| `imports` app | Excel import pipeline with validation | `backend/imports/` |
| Roles | OWNER, MANAGER, INVENTORY_STAFF, ACCOUNTANT, AUDITOR, VIEWER | `accounts/models.py` `Role` |
| Approvals, audit | `ApprovalRequest`, audit service, period locks | `planwave/`, `core/services/audit.py` |
| Needs attention | Attention codes and actions (DAN programme) | dashboard / attention services |
| Offline queue | Web offline enqueue and flush | `web/src/offline/` |
| Complaints, care | Customer complaint records for the NCR/CAPA link | `backend/complaints/` |

---

## 3. Findings in today's code

### 3.1 Design gaps (expected for an MVP)

1. Release issues everything at once. A real floor issues in parts, issues extra, and returns
   leftovers.
2. One receipt per WO. Partial output, by-products, co-products and scrap are impossible.
3. No variance. Actual usage always equals the BOM, because issue happens from the snapshot.
4. Only material cost reaches the finished good. Labour and overhead are never absorbed, so
   FG cost is understated and gross margin is overstated.
5. BOM per 1 unit only. Process makers (spices, chemicals, food) think in batch size
   ("100 kg batch uses 62 kg chilli …").
6. No unit on BOM lines. A component bought in kg and used in g needs a unit on the line.
7. Owner only. The person on the floor is usually INVENTORY_STAFF or MANAGER.
8. Product has no "role" (raw material, semi-finished, finished, packing, scrap). Reports
   cannot split RM/WIP/FG stock.

### 3.2 Defects to fix before building (MFG-01)

| # | Defect | Effect | Evidence |
|---|---|---|---|
| DEF-1 | When issue cost is 0, completion values FG at the components' `purchase_price` but posts **no** GL entry (`gl_amount = issue_cost`, posted only when > 0) | Stock valuation and GL 1400 drift apart. Inventory value appears from nothing | `complete_work_order`, the `unit_cost` fallback and `gl_amount` |
| DEF-2 | Consumed component serials move to **SCRAPPED** | Genealogy (which serial went into which FG serial) is lost. Scrap reports would count normal consumption | `release_work_order` → `SerialNumberService.transition(... target=SCRAPPED)` |
| DEF-3 | Cancel of a completed WO posts plain **ADJUSTMENT** movements | Adjustment reports and audits show manufacturing reversals as manual adjustments | `cancel_work_order` |

Also worth noting: FG unit cost is rounded to 4 dp while GL uses 2 dp. On large quantities
the FG layer total and the WIP credit can differ by paise. The fix is to post the GL from the
same total that built the layer, and to send any rounding to a variance account.

Also found in the rev 2 review: the default valuation method is **WAVG**, not FIFO. Under WAVG
an outbound movement keeps the caller's pre-lock cost, while the running pool consumes its own
average, so the work order's issue cost can differ slightly from what stock actually gave up.
MFG-01 stamps the consumed cost. Details: implementation plan §4.15.

---

## 4. Competitor comparison

Sources are vendor docs and marketing pages, checked 2026-10-20. Vendor claims are not
independently verified. ✅ = documented, ◐ = partial or claimed, ❌ = not found.

| Capability | Bizboard now | Tally Prime | Busy | Vyapar | Zoho Inventory | TranZact | MRPeasy / Katana | ERPNext / Odoo |
|---|---|---|---|---|---|---|---|---|
| Single-level BOM | ✅ | ✅ | ✅ | ✅ | ✅ (composite items) | ✅ | ✅ | ✅ |
| Multi-level BOM | ❌ | ◐ | ✅ (claimed) | ❌ | ❌ | ✅ | ✅ | ✅ |
| BOM versions | ❌ | ❌ | ❌ | ❌ | ❌ | ◐ | ◐ | ✅ |
| By-product / co-product / scrap in BOM | ❌ | ✅ | ◐ | ❌ | ❌ | ◐ (scrap) | ◐ | ✅ |
| Expenses or labour in BOM cost | ❌ | ◐ | ◐ | ✅ ("recipe + expenses") | ❌ | ✅ | ✅ | ✅ |
| One-step production entry | ❌ | ✅ (stock journal) | ✅ (production voucher) | ✅ | ✅ (assemble) | ✅ | ✅ | ◐ |
| Partial issue / receipt | ❌ | ◐ | ◐ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Batch / expiry / FEFO | ✅ | ✅ | ✅ | ◐ | ✅ | ✅ | ✅ (Katana: top tier) | ✅ |
| Serial genealogy | ◐ (D-2) | ◐ | ◐ | ❌ | ◐ | ◐ | ✅ | ✅ |
| MRP / purchase suggestions | ❌ (inputs exist) | ❌ | ◐ | ❌ | ◐ (reorder) | ✅ | ✅ | ✅ |
| Make-to-order from sales order | ❌ | ◐ | ◐ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Routing / work centres | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Shop-floor operator screen | ❌ | ❌ | ❌ | ❌ | ❌ | ◐ | ✅ | ✅ |
| Quality inspection / hold | ◐ (GRN accept/reject) | ❌ | ❌ | ❌ | ❌ | ✅ (FG testing) | ✅ (MRPeasy higher tier) | ✅ |
| Job work OUT (principal) | ❌ | ✅ | ✅ | ❌ | ❌ | ◐ (subcontracting) | ◐ (subcontracting) | ◐ |
| Job work IN (as job worker) | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ found | ❌ | ❌ |
| ITC-04 | ❌ | ✅ | ✅ | ❌ | ❌ | ◐ | ❌ | ◐ (India app) |
| GST e-invoice / e-way | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ◐ |
| Integrated GL with WIP | ✅ (material only) | ✅ | ✅ | ◐ | ◐ (Books) | ◐ (Tally sync) | ❌ (sync out) | ✅ |
| Period locks / audit | ✅ | ◐ | ◐ | ❌ | ◐ | ◐ | ◐ | ✅ |

**What the scan says:**

1. **Table stakes for an Indian MSME** (every local tool has these, and Bizboard does not):
   - by-products and scrap in the BOM;
   - a one-step production entry;
   - BOM expenses or labour in cost;
   - job work in **both** directions, with registers and ITC-04.
   Without these, a Tally or Busy user will not switch.
2. **The gap no Indian tool fills**: planning (shortage, MRP, MTO), quality hold, and real cost
   versus estimate, at SME price and setup effort. MRPeasy and Katana gate quality and
   subcontracting behind higher tiers. Katana's batch traceability is top-tier only.
3. **TranZact** is the most direct competitor (Indian, SME, cloud, multi-level BOM, routing,
   Tally sync). Its documented gap is Indian job work. Bizboard's edge is one integrated
   ledger with GL, GST, e-way bill and period locks, instead of syncing to Tally.
4. **ERPNext and Odoo** are the depth benchmark. Copy their data model (versioned BOM, issue
   and receipt documents, quality inspection templates). Do not copy their setup weight.

---

## 5. Review of the founder's list, section by section

Verdicts: **Build**, **Reuse** (exists in another module and needs a link only), **Later**
(gated by a pilot), **Cut** (not for this programme).

### 5.1 Product and master data
| Item | Verdict | Note |
|---|---|---|
| Product / RM / component / sub-assembly master | Build (small) | Add a manufacturing role to Product (MFG-05). The master itself exists |
| BOM | Exists | Extend |
| Multi-level BOM | Build | MFG-14 (explosion, where-used, cost roll-up) |
| BOM versioning and revisions | Build | MFG-03. Blocks MRP and costing |
| UoM and conversions | Build (small) | Unit per BOM line (MFG-04). Product has only one alternate unit, so more is a masters change. Decision D-7 |
| Alternates / substitutes | Build | MFG-18 |
| Yield, scrap, wastage | Build | MFG-04 (line scrap %, BOM yield %), MFG-08 (actual) |
| Routing | Later | MFG-33, Phase 6 |
| Specs, drawings, attachments | Build (small) | Reuse `core/services/files.py` on BOM and WO |
| **Added:** BOM batch size (output qty) | Build | MFG-04. Process industries need it |
| **Added:** BOM outputs (co-product, by-product, scrap) with cost share | Build | MFG-04 / MFG-08. Closes B8-009 |
| **Added:** Phantom / kit lines | Build (small) | Explode at use, never stocked |

### 5.2 Production planning
| Item | Verdict | Note |
|---|---|---|
| Production / work orders | Extend | MFG-02 (number, due date, priority, SO link, statuses) |
| SO-based production, MTS / MTO | Build | MFG-17 |
| MRP | Build lite | MFG-16. Net requirements with lead time; not finite scheduling |
| Availability and shortage | Build | MFG-15 |
| Purchase suggestions | Build | MFG-16 → PO drafts (reuse PurchaseOrder) |
| Scheduling and priority | Build simple | MFG-19 board by due date and priority |
| Work-centre capacity | Later | MFG-35 |
| Due dates and delay tracking | Build | MFG-02 + attention code (MFG-X2) |
| **Added:** "How many can I make now?" | Build | MFG-15. Most-asked question in small units |

### 5.3 Purchase and procurement
| Item | Verdict | Note |
|---|---|---|
| Requisitions from production | Build | MFG-16 output |
| Quotation comparison, PO, delivery tracking, GRN | Reuse | Purchases module; not a manufacturing WP |
| Incoming inspection | Build | MFG-21 on top of GRN accepted/rejected |
| PO–GRN–invoice matching | Reuse | Purchases (exists) |
| Supplier lead time | Reuse | `WarehouseReorderLevel.lead_time_days`; add actual lead time from PO→GRN dates in reports |
| Supplier quality / rejections | Build | MFG-22 scorecard from GRN rejections and NCRs |
| Subcontractor procurement | Build | MFG-24 |

### 5.4 Production execution
| Item | Verdict | Note |
|---|---|---|
| Work order / job card | Extend / Later | WO now; operation job cards in MFG-34 |
| Reservation against WO | Build | MFG-10, extend StockReservation |
| Issue, actual consumption, return | Build | MFG-06, MFG-07 |
| Operation-wise tracking | Later | MFG-34 |
| Partial completion, WIP tracking | Build | MFG-08, MFG-09 |
| Labour time, machine time, downtime | Later | MFG-34. Labour **cost** comes earlier via rates (MFG-28) |
| Output recording | Build | MFG-08 |
| Rework and rejection | Build | MFG-11 |
| Scrap and wastage | Build | MFG-08 |
| Delay reasons | Build | MFG-02 (reason codes on due-date change) |
| **Added:** one-screen production entry with backflush | Build | MFG-12 |
| **Added:** extra issue with reason and approval | Build | MFG-06 (reuse ApprovalRequest over a threshold) |

### 5.5 Inventory and warehouse
| Item | Verdict | Note |
|---|---|---|
| RM / WIP / FG / scrap inventory | Build (reports) | Needs product role (MFG-05) and WIP subledger (MFG-09) |
| Multi-godown | Reuse | Exists. **Bins**: Later, not needed for MSME pilots |
| Batch, serial, FIFO, movement history | Reuse | Exists. Fix DEF-2 for genealogy |
| Traceability and genealogy | Build | MFG-13: forward and backward trace by batch or serial |
| Barcode / QR | Later | Label print first (MFG-X1); scanning with the shop-floor PWA |
| Reservation | Build | MFG-10 |
| Quarantine / blocked stock | Build | MFG-20 batch quality status |
| Physical verification | Reuse | `StockCountSession` exists |

### 5.6 Quality
| Item | Verdict | Note |
|---|---|---|
| Incoming, in-process, final inspection | Build | MFG-21 (in-process needs routing; until then, at receipt) |
| Templates, parameters, tolerances | Build | MFG-21 |
| Pass / fail / hold / rework | Build | MFG-20, MFG-21, MFG-11 |
| NCR, defects, CAPA | Build light | MFG-22 |
| Supplier scorecards | Build (report) | MFG-22 |
| Certificates / test reports | Build | MFG-23 CoA |
| Release approval before dispatch | Build | MFG-20 (HOLD batches blocked in sales and challans) |

### 5.7 Costing
| Item | Verdict | Note |
|---|---|---|
| BOM estimate | Build | MFG-14 roll-up |
| Actual material cost | Exists | FIFO layers |
| Labour, machine, overhead | Build | MFG-28 rate-based absorption. CA sign-off |
| Standard cost, variances | Build | MFG-29. CA sign-off |
| Subcontract cost | Build | MFG-24 job charges into WIP |
| Scrap recovery | Build | MFG-31 |
| Yield and wastage analysis | Build | MFG-30 |
| Product / batch / customer / job profitability | Build | MFG-30 (uses FG layer cost in COGS) |

### 5.8 Sales and dispatch
| Item | Verdict | Note |
|---|---|---|
| Quotations, packing, challans, GST invoice, e-invoice, e-way, returns, warranty, complaints | Reuse | All exist in sales / complaints |
| SO → production, delivery commitment | Build | MFG-17 |
| ATP | Build | MFG-17 (stock − reservations + planned output by date) |
| FG allocation | Build | MFG-10 / MFG-17 (reserve output to SO) |
| Customer-specific specs | Build (small) | Customer-specific BOM version (MFG-03 field `customer`) |

### 5.9 Job work and subcontracting
All **Build** in Phase 4 (MFG-24 … MFG-27). The list's version is principal-only. **Add the job
worker side (MFG-26)** and the deemed-supply clock (MFG-24).

### 5.10 Finance, accounting, GST
| Item | Verdict | Note |
|---|---|---|
| RM consumption, WIP, FG accounting | Exists, extend | MFG-01 fixes, MFG-09 close, MFG-28 / 29 |
| Purchase, expense, payments, HSN, GST, audit | Reuse | Exist |
| Tally integration | Reuse | Existing Tally gate. Add manufacturing vouchers only when a pilot needs them |
| Period-end stock and WIP reconciliation | Build | MFG-32 |
| **Added:** ITC-04 | Build | MFG-25 |
| **Added:** GST on scrap sales | Build | MFG-31 |

### 5.11 Reports and dashboards
All Build as a pack (MFG-X2), gated per phase. Machine utilisation and labour productivity wait
for MFG-34.

### 5.12 Business types
Not features. They are **configurations** of the same engine. See section 7 for which work
packages each vertical needs. Use this to pick pilots.

### 5.13 Advanced
| Item | Verdict |
|---|---|
| Preventive maintenance, breakdowns | Later (MFG-36, light) |
| Shift and operator management, tablet entry, offline | Later (MFG-34, reuse offline queue) |
| Capacity optimisation, advanced scheduling | Cut for now. Needs routing data that MSMEs rarely keep |
| IoT, sensors, energy | Cut. Separate product |
| ECO, document revisions | Build light: BOM revision with reason (MFG-03) covers most of it |
| AI forecasting, anomaly detection, recommendations | Cut for now. Revisit through the Insights module after 6 months of production data exist |

### 5.14 Technical and control requirements
All accepted as **rules for every WP**, not phases. Section 8 turns them into checks.

---

## 6. Phased plan with work packages

Size: S ≤ 3 days, M ≈ 1 week, L ≈ 2 weeks (one developer with Claude, including tests).

### Phase 0 — Foundations and fixes (≈ 2–3 weeks)

| WP | Title | Contents | Size |
|---|---|---|---|
| MFG-00 | Roles and sub-flags | Permission matrix: OWNER and MANAGER get everything; INVENTORY_STAFF can issue, return and receive; ACCOUNTANT can view cost and close; AUDITOR and VIEWER are read-only. Cost fields hidden from roles without cost access (same pattern as purchase-price masking). Sub-flags `MFG_JOB_WORK`, `MFG_QUALITY`, `MFG_COSTING_GL` (default off) | M |
| MFG-01 | Fix DEF-1, DEF-2, DEF-3 + WAVG cost stamping | DEF-1: GL posted from the same total that built the FG layer; zero-cost receipt posts nothing and values at 0, or refuses (decision D-6). DEF-2: new serial status `CONSUMED` plus a genealogy row (FG serial or batch ↔ component serial or batch). DEF-3: dedicated reversal movement types. Data migration for existing SCRAPPED-by-WO serials | M |
| MFG-02 | Work order header | Number series (reuse document series), due date, planned start, priority, sales-order link, notes, delay reason codes. Statuses: DRAFT → RELEASED → IN_PROGRESS → COMPLETED → CLOSED, plus CANCELLED. RELEASED no longer auto-issues (behind a per-company setting so existing tenants keep today's behaviour) | M |
| MFG-03 | BOM versioning | `revision_no`, `effective_from`, `effective_to`, `is_default`, optional `customer`, `change_reason`. Revision is immutable once a WO uses it; editing creates a new revision. Data migration resolves today's multiple-ACTIVE case: newest becomes default, the rest stay ACTIVE non-default; then a partial-unique index on (company, product) where default. Closes B8-018 | L |
| MFG-04 | BOM line and output enrichment | BOM `output_qty` (batch size) and `yield_pct`. Line: `unit` with conversion, `scrap_pct`, `issue_method` (manual / backflush), `is_optional`, `alternate_group`, notes. New `BomOutput` (product, qty, kind = CO_PRODUCT / BY_PRODUCT / SCRAP, cost_share_pct). Validation: cost shares of the main product and co-products sum to 100 | L |
| MFG-05 | Product manufacturing role | `mfg_role` on Product: RAW, SEMI_FINISHED, FINISHED, PACKING, CONSUMABLE, SCRAP, BY_PRODUCT (blank allowed). Used by reports and default warehouse picks | S |

### Phase 1 — Execution core (≈ 5–6 weeks). The minimum to sell.

| WP | Title | Contents | Size |
|---|---|---|---|
| MFG-06 | Material issue document | `MaterialIssue` with lines against a WO: partial, multiple, extra issue with reason (approval over a threshold), batch, lot and serial picks (reuse `_issue_batches`). Posts MANUFACTURE_ISSUE and the WIP JE per document | L |
| MFG-07 | Material return | `MaterialReturn` of unused material to store, restores FIFO peels (reuse `restore_fifo_peels`), credits WIP | M |
| MFG-08 | Production receipt | `ProductionReceipt`, many per WO: good qty, FG batch per receipt, co-product, by-product and scrap lines from `BomOutput` (editable actuals). Cost split by cost share; scrap at a set recovery value. Backflush lines consumed here | L |
| MFG-09 | WO close and WIP | Close computes standard-for-actual-output against actual issued: **usage variance per component**. Residual WIP goes to a variance account (not back to FG). WIP subledger = open WO issued cost − received cost. WIP ageing | M |
| MFG-10 | Reservation against WO | Non-expiring, document-linked reservations (extend `StockReservation` with reference fields and nullable expiry). Release on issue, close or cancel. `available` respects them | M |
| MFG-11 | Rejection and rework | Receipt splits good / rejected / for rework. Rework creates a linked WO (BOM = the item itself plus rework materials). Rejected goes to scrap or quarantine | M |
| MFG-12 | Quick production entry | One screen: product, qty, batch, date → picks the default BOM revision, shows components with editable actual qty, posts issue + receipt + close in one transaction. Built on MFG-06 / 08 / 09 so the books stay identical. **This is the Vyapar / Tally parity screen** | M |
| MFG-13 | Traceability and reversals | Forward and backward trace by batch or serial (uses the MFG-01 genealogy). Reverse any issue, return or receipt with reason, period gate and audit, newest-first with dependency checks. Recall view: "which customers got FG made from supplier batch X" | M |
| MFG-37 | Additional cost per batch or unit (rev 2) | Flat grinding, packing or labour cost per batch or unit on the BOM and on quick entry, absorbed into FG cost. Pulled forward from Phase 5 because Tally, Busy and Vyapar all have it. Own CA review in Phase 1 | S |

Rev 2 also adds to Phase 1:
- separate RM, FG and scrap godowns per line;
- estimate-then-true-up costing for partial receipts;
- rework as a BOM-less work order;
- a cost summary on each work order.
Details are in the implementation plan.

**Phase 1 exit:** a small unit can run real production for a month with stock, WIP and GL
reconciling to the paisa, partial runs, scrap and by-products, and a traceable batch.

### Phase 2 — Planning (≈ 4–5 weeks)

| WP | Title | Contents | Size |
|---|---|---|---|
| MFG-14 | Multi-level BOM | Indented explosion with versions as of a date, where-used, cost roll-up (latest FIFO, average or standard), phantom lines. Release still needs sub-assemblies in stock, or offers "create child WOs" | L |
| MFG-15 | Can-I-make and shortages | Per WO and across open WOs: required, reserved, available, short. Maximum producible qty per product. Respects alternates | M |
| MFG-16 | MRP-lite | Demand (open SOs, confirmed WOs, safety stock) − supply (stock, open POs, open WOs) netted by date with `lead_time_days`. Output: planned WOs and purchase suggestions grouped by supplier → PO drafts. Run on demand, stored as a run with lines; no auto-posting | L |
| MFG-17 | Make-to-order | Create WO(s) from SO lines with pegging. SO shows production status and expected date. ATP by date. FG output can be reserved to the SO on receipt | M |
| MFG-18 | Alternates | Alternate groups with priority; issue and shortage use them; usage logged as a variance cause | S |
| MFG-19 | Production board | Kanban or list by status, due date and priority with drag-to-reprioritise. Late and at-risk flags. No finite capacity | M |

### Phase 3 — Quality (≈ 3–4 weeks, sub-flag `MFG_QUALITY`)

| WP | Title | Contents | Size |
|---|---|---|---|
| MFG-20 | Batch quality status | `BatchLot.quality_status`: QUARANTINE / HOLD / RELEASED / REJECTED. Optional "receive into quarantine" per product. Sales, challans and WO issue refuse non-released batches (one central check in inventory) | M |
| MFG-21 | Inspection templates and records | Template per product and stage (incoming / final / in-process later). Parameters: numeric min/max, text, pass/fail, sample size. Record against a GRN line or production receipt; decision sets batch status and GRN accepted/rejected | L |
| MFG-22 | NCR, CAPA light, supplier score | NCR from a failed inspection or customer complaint (link `complaints`), root cause, action, owner, due date. Supplier scorecard: rejection %, on-time %, NCR count | M |
| MFG-23 | Certificate of analysis | Printable CoA from final inspection (company template). Important for chemical, food and pharma buyers | S |

### Phase 4 — Job work, India (≈ 5–6 weeks, sub-flag `MFG_JOB_WORK`)

Rules (CGST s.143 and Rule 45, as commonly applied; confirm with a CA before release):
- Inputs sent for job work must come back within **1 year**, capital goods within **3 years**
  (moulds, dies, jigs and tools excluded). Otherwise the dispatch is a deemed supply on the
  day it was sent.
- ITC-04 is **half-yearly** above ₹5 crore aggregate turnover (due 25 Oct and 25 Apr) and
  **annual** at or below ₹5 crore (due 25 Apr), since notification 35/2021.

| WP | Title | Contents | Size |
|---|---|---|---|
| MFG-24 | Job work OUT (principal) | `JobWorkOrder` to a supplier with send lines and expected returns (processed item, scrap). Send challan reuses the DeliveryChallan print and e-way path with sub-supply type Job Work. Stock moves to a per-job-worker virtual warehouse (still own stock, still valued). Receive processed goods, unprocessed returns and scrap. Consumption at the job worker is recorded. Job charges by purchase invoice (SAC 9988) capitalised into WIP or FG. Balance per job worker, ageing, and **deemed-supply alerts at 300 / 1,000 days** | L |
| MFG-25 | ITC-04 | Report and export of goods sent and received per period per the ITC-04 tables, with an offline-tool Excel or JSON format. Frequency from turnover. Reconcile against challans. Needs-attention reminder before due dates | M |
| MFG-26 | Job work IN (as job worker) | Principal's material register **outside** own valuation (separate quantity-only ledger, never in FIFO or GL). Receive, process (WO consuming principal stock), return with challan, and invoice job charges only. Balance per principal. Without this, job-worker MSMEs cannot use Bizboard | L |
| MFG-27 | Operation-wise subcontracting | Send WIP out for one operation (plating, heat treatment) and back into the same WO. Needs routing; ship with Phase 6 | M |

### Phase 5 — Costing and accounting (≈ 3–4 weeks, sub-flag `MFG_COSTING_GL`, CA sign-off)

| WP | Title | Contents | Size |
|---|---|---|---|
| MFG-28 | Conversion cost | Labour and overhead rates on the BOM revision (per unit or per batch), later per work-centre hour. Absorbed at receipt: Dr WIP / Cr Labour absorbed, Overhead absorbed. FG at full cost | M |
| MFG-29 | Standard cost and variances | Optional standard cost per product; variances for material price, usage, yield and under/over-absorbed overhead to configured accounts. Off by default; actual costing stays the default | L |
| MFG-30 | Cost and profit reports | Planned vs actual per WO and batch, yield and wastage, product, batch, customer and job profitability (COGS from FG layers) | M |
| MFG-31 | Scrap and by-product sale | Sell through the normal invoice with the scrap item's HSN; recovery value credited per policy. Scrap register | S |
| MFG-32 | Period-end reconciliation | GL 1450 vs WIP subledger, GL 1400 vs valuation split RM / FG / scrap, job-work stock at job workers. Hooks into the existing year-close check (`OPEN_WIP`) | M |

### Phase 6 — Factory depth (pilot-gated)

| WP | Title | Contents | Size |
|---|---|---|---|
| MFG-33 | Work centres and routing | Work centre master (hour rate, capacity per shift). Routing per BOM revision: operations, setup and run time | L |
| MFG-34 | Operation job cards and shop-floor PWA | Job card per operation, start / stop / qty / reject, downtime reasons. Operator PIN or QR (a sign-in mode for staff without accounts, needs a security review). Offline queue reuse. Hindi first | L |
| MFG-35 | Load view | Infinite-capacity load per work centre per day; overload flags | M |
| MFG-36 | Maintenance light | Machine master, preventive schedule by date or hours, breakdown log feeding downtime | M |

### Cross-cutting (spread across phases)

| WP | Title | Contents |
|---|---|---|
| MFG-X1 | Import / export and print | Excel BOM import (header + lines + outputs, multi-level by product code) through the `imports` pipeline; export of WOs and registers; WO, issue slip and label print |
| MFG-X2 | Reports and attention | Report pack per phase. Needs-attention codes: `WO_LATE`, `WO_SHORTAGE`, `BATCH_ON_HOLD`, `JOBWORK_AGEING`, `ITC04_DUE`, `WIP_STALE`. Follow the KNOWN_CODES rule |
| MFG-X3 | Language and help | Hindi strings for all shop-floor screens; context help |
| MFG-X4 | Test programme | Inventory invariant (stock = Σ movements, valuation = Σ layers, GL 1450 = WIP subledger) after every service; Postgres race tests on issue and reservation; golden e2e for quick entry, partial run and job-work round trip |
| MFG-X5 | Platform hygiene | RLS migration for every new tenant table (`core` RLS pattern), tenant backup coverage (`accounts/tenant_backup.py`), regenerated OpenAPI snapshot and web types, QOS backlog items for each human sign-off |

---

## 7. Vertical fit (which work packages each business type needs)

| Vertical | Must-have WPs beyond Phase 1 | Notes |
|---|---|---|
| Food and spices | MFG-04 batch size and yield, MFG-20 / 21 quality, MFG-23 | FSSAI batch and expiry already on Product (`regulated_category=FOOD`); moisture and process loss = yield |
| Chemicals and cosmetics | MFG-04 batch size, MFG-21, MFG-23 CoA | Formula-style BOMs; scale by batch |
| Textile and garments | MFG-24 / 25 / 26 job work, MFG-14 | Very job-work heavy (dyeing, stitching, embroidery). Size and colour variants are a masters question (decision D-8) |
| Furniture, custom MTO | MFG-17 MTO, MFG-14 | Customer-specific BOM revision |
| Fabrication and machining | MFG-24 / 27, MFG-33 / 34 | Routing matters here first |
| Electrical and electronics | MFG-14, MFG-13 serial genealogy, MFG-21 | Serial trace is the selling point |
| Assembly / discrete | MFG-14, MFG-15 / 16 | Shortage-driven |
| Job workers | MFG-26 | Can be served almost alone by MFG-26 plus quick entry |

**Pilot suggestion:** one spice or food unit, one job-work textile or fabrication unit, one
assembly unit. Together they cover Phases 1–4.

---

## 8. Control rules for every WP (from the founder's section 14)

1. **One ledger.** Every quantity change goes through `InventoryService.post_movement`. No
   module writes `StockBalance` directly. Job-work IN principal stock is the only
   non-valued ledger, and it is a separate model.
2. **Idempotent posting.** Every posting document has a unique (company, source_type,
   source_id, purpose) on JEs (existing pattern) and a status guard under `select_for_update`.
3. **Snapshot what was used.** WO keeps the BOM revision id and its line snapshot. Receipts
   keep their cost split.
4. **Reverse, never delete.** Posted documents reverse with reason, date and period gate.
5. **Atomic.** One `transaction.atomic` per document; JE inside the same transaction.
6. **Concurrency.** Lock balance rows before planning allocations (existing B8-010 pattern);
   Postgres race tests for issue, reservation and quick entry.
7. **Roles, audit and period locks.** On every endpoint and service.
8. **Multi-company and multi-godown.** CompanyScopedModel plus an RLS policy on every new table.
9. **Invariant check.** Add manufacturing invariants to `core/invariants/inventory.py`.

---

## 9. Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D-1 | BOM version model | Effective-dated revisions with one default per product. Customer-specific revisions allowed |
| D-2 | Release behaviour for existing tenants | New companies: release reserves and issue is separate. Existing: keep auto-issue until switched |
| D-3 | Backflush default | Off. Per BOM line option. Quick entry always backflushes |
| D-4 | Costing default | Actual (WAVG by default, FIFO for FIFO tenants) plus rate-based conversion cost. Standard costing opt-in |
| D-5 | Job work scope | Build both OUT and IN in Phase 4. Pull Phase 4 forward if a pilot is a job worker |
| D-6 | Zero-cost completion (defect D-1) | Refuse to complete when components have no cost, with a clear message, instead of inventing value |
| D-7 | Units | Unit per BOM line limited to the product's base or alternate unit. Full multi-UoM is a masters project |
| D-8 | Variants (size / colour) | Out of scope here. Needed only for the garment pilot |
| D-9 | Pricing | Manufacturing as a paid pack: Phase 1 = "Production", Phase 4 = "Job work" add-on? Founder call |
| D-10 | Operator PIN login | Phase 6 only, after a security review |
| D-11 | New movement types | Movement types are "locked (§7)". Adding MANUFACTURE_RETURN and MANUFACTURE_REVERSAL needs founder sign-off. Job work reuses transfers (rev 2), so JOBWORK_OUT / JOBWORK_IN are no longer needed |
| D-12 | Partial-receipt costing (rev 2) | Provisional at a frozen estimate, final receipt takes the residual |
| D-13 | Back-dated entries (rev 2) | Live stock and cost in posting order; 7-day window, older needs approval |
| D-14 | Incoming inspection (rev 2) | Inspect on the draft GRN; "receive into quarantine" option per product |
| D-15 | Job-work direct dispatch (rev 2) | Supplier → job worker and job worker → job worker supported; job worker → customer only when declared |
| D-16 | WAVG cost stamping (rev 2) | Stamp the consumed average on outbound WAVG movements (shared inventory path) |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| GL changes mis-state stock or COGS | Every GL change behind `MFG_COSTING_GL`, CA sign-off (QOS item), invariant tests |
| Migrating existing BOMs and WOs | Data migrations are idempotent and dry-run first on the staging copy |
| Scope creep toward ERPNext | Phases 5–6 start only with a named pilot asking |
| Shop-floor UX too heavy | Quick entry (MFG-12) ships in Phase 1; usability test with a real operator |
| Job-work law reading wrong | CA review of MFG-24 / 25 / 26 before release; rule values (1 year / 3 years, ₹5 cr) kept in settings, not code |

---

## 11. Success measures

- Phase 1: a pilot runs 30 days with **zero** stock / WIP / GL reconciliation differences, and
  at least 80% of production entries made by non-owner roles.
- Phase 2: shortage list matches a manual count for 3 random WOs; PO drafts raised from
  suggestions.
- Phase 3: no HOLD batch invoiced (enforced, tested).
- Phase 4: ITC-04 for one half-year reconciles to challans with no manual edits.
- Phase 5: CA signs off WIP and FG valuation for one closed month.

---

## Sources (competitor and GST facts, checked 2026-10-20)

- Tally job work: https://help.tallysolutions.com/tally-prime/inventory/job-work/
- Busy job work FAQ: https://busy.in/faqs/features/inventory-job-work/5/ ; manufacturing pages: https://busy.in/accounting-software/manufacturing/auto-parts/
- Vyapar manufacturing: https://vyaparapp.in/manufacturing
- TranZact production: https://letstranzact.com/solutions/production-management-software
- Zoho composite item limitation (community thread): https://help.zoho.com/portal/en/community/topic/single-item-composite-items
- MRPeasy vs Katana: https://www.mrpeasy.com/mrpeasy-vs-katana ; https://craftybase.com/compare/katana-vs-mrpeasy
- ITC-04 frequency: https://cleartax.in/s/gst-on-job-work ; https://www.oxyzo.in/resources/blogs/itc-04-filing-process-benefit-exemption-and-penalties
