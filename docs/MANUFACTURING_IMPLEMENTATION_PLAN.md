# Manufacturing — implementation plan

Date: 2026-10-20. Status: **BUILT, uncommitted on branch `feat/mfg-p0-foundations` (2026-10-21).** Plan rev 2 was implemented end to end except the items listed under "Left open" in section 12. Every new part sits behind its own switch, so nothing changes for a company until it is granted.
Rev 2 (2026-10-20): review comments applied. See section 13, "Revision log", for what changed and why.
Source: [roadmap/MANUFACTURING_ENHANCEMENT_PLAN_2026-10-20.md](roadmap/MANUFACTURING_ENHANCEMENT_PLAN_2026-10-20.md)
(the "feature plan": analysis, competitor scan, phases, decisions D-1…D-11).
This file is the **how**: engineering rules, data model, service and API design, migrations,
tests, rollout, and an exit gate per work package (WP).
Related: [TESTING_STRATEGY.md](TESTING_STRATEGY.md), [INVENTORY_DEEP_REVIEW_IMPLEMENTATION_PLAN.md](INVENTORY_DEEP_REVIEW_IMPLEMENTATION_PLAN.md)
(pattern for stock-write rules), [STAGING_DEPLOYMENT_IMPLEMENTATION_PLAN.md](STAGING_DEPLOYMENT_IMPLEMENTATION_PLAN.md),
`.github/workflows/ci.yml`.

Contents
1. Goals and non-goals
2. Engineering rules (apply to every WP)
3. Architecture and target data model
4. Cross-cutting standards: API, errors, idempotency, security, migrations, flags, UI, i18n, observability, performance
5. Test strategy
6. Delivery process: branches, reviews, Definition of Ready / Done, CI gates
7. Work packages, phase by phase (MFG-00 … MFG-36, MFG-X1 … X5)
8. Schedule, dependencies and critical path
9. Rollout, pilots and rollback
10. Risk register
11. Open decisions (blocking map)
12. Execution record (fill in as WPs land)
13. Revision log

Naming: **DEF-n** = a defect in today's code (feature plan §3.2). **D-n** = an open decision
(section 11). They were both "D-n" in rev 1.

---

## 1. Goals and non-goals

**Goals**
1. A small Indian manufacturer can run day-to-day production in Bizboard for a month with
   stock, WIP and GL reconciling to the paisa (Phase 0–1 exit).
2. Planning, quality and Indian job work at SME setup effort (Phases 2–4).
3. True product cost including conversion cost, signed off by a CA (Phase 5).
4. No regression to the existing BOM / work-order behaviour for tenants already using it.

**Non-goals for this programme**
- Finite-capacity scheduling, IoT, energy, AI forecasting (see feature plan §5.13).
- Bins inside godowns, product variants (size / colour), full multi-UoM (D-7, D-8).
- A separate MES app. Shop-floor screens are part of the web PWA (Phase 6).

---

## 2. Engineering rules (apply to every WP)

These extend the founder's section 14 and the rules already used in the inventory programmes.

| # | Rule | How it is enforced |
|---|---|---|
| R-1 | **One stock ledger.** Every quantity change goes through `InventoryService.post_movement`. No direct writes to `StockBalance`, `InventoryCostLayer` or `SerialNumber.status` outside `inventory/services.py` | Code review checklist; a guard in `scripts/ci_gates/guards/` that greps `manufacturing/`, `quality/`, `jobwork/` for `StockBalance.objects.*update`/`.save(` (MFG-X4) |
| R-2 | **Server enforces, UI helps.** Every rule lives in a service function; serializers validate shape only | Service-level tests for every rule; API tests only for wiring |
| R-3 | **Document pattern.** Every posting thing is a document: DRAFT → POSTED → (REVERSED). Posting = `transaction.atomic` + `select_for_update` on the header + status guard + movements + JE + audit, all in one transaction | Shared base helper `post_document()` (MFG-06), tests for double-post |
| R-4 | **Reverse, never delete or edit** a posted document. Reversal is a new movement set with `reason`, `reversal_of`, business date and period gate | API has no DELETE/PATCH on POSTED rows; tests |
| R-5 | **Idempotent writes.** Every POST that posts or creates a document goes through `core.idempotency.wrap_idempotent` with a scope like `mfg.issue.post`; the document status is the exactly-once guard | API tests replaying the same key; IDR-01 rule (new key per user gesture) |
| R-6 | **Period gate** with the document's business date (`reporting.gst_periods.assert_period_allows_money_amend`), never wall-clock "today" | Tests at the lock boundary |
| R-7 | **Money in `Decimal`.** Qty 3 dp, unit cost 4 dp, money 2 dp `ROUND_HALF_UP`. GL amount is computed from the same total that built the cost layer; any rounding goes to a rounding/variance account, never silently | Unit tests on rounding; invariant `wip_subledger_matches_gl` |
| R-8 | **Snapshot what was used.** A WO pins its BOM revision and copies lines; a receipt stores its cost split; a posted document never re-reads live master data | Tests that edit the master after posting |
| R-9 | **Tenant isolation.** Every new tenant table: `CompanyScopedModel` (or a `company` FK set in `save()` for line tables), added to an RLS catch-up migration in `core`, and to `accounts/tenant_backup.py` | MFG-X5 checklist; existing RLS coverage tests; backup round-trip test |
| R-10 | **Least privilege.** Permissions per action (section 4.5), cost fields masked through `planwave.services.cost_visible` for non-money roles | Role-matrix test per endpoint |
| R-11 | **Feature flags** for every behaviour change that touches money, approvals or existing tenants. Default **off** until the exit gate and any sign-off pass | Flag tests on/off; `dark_module` marker |
| R-12 | **Concurrency.** Lock balance rows before planning an allocation (B8-010 pattern). Every new posting path gets a Postgres race test (`@pytest.mark.postgres`) | MFG-X4 |
| R-13 | **Invariants.** New manufacturing invariants in `core/invariants/` run in the existing teardown hook | Every test that posts is checked automatically |
| R-14 | **Backward compatibility.** API changes are additive. Old fields keep meaning. Old behaviour stays behind a company setting until switched | OpenAPI diff reviewed in each PR |
| R-15 | **No reading generated files whole** (`docs/openapi-snapshot.json`, `web/src/api/openapi-types.ts`). Grep | CLAUDE.md |
| R-16 | **Both valuation methods.** `Company.inventory_valuation_method` defaults to **WAVG** (FREEZE_SCOPE C3: running weighted cost is the pilot model); FIFO is opt-in. Every manufacturing path must be correct under both. Cost is always read from the **stamped** `StockMovement.unit_cost` of the movement that was actually posted, never re-derived later | Service tests parametrised over `["WAVG", "FIFO"]`; invariants for both |
| R-17 | **Reversal dependency order.** A document can be reversed only when nothing posted later depends on it (section 4.12) | Service guards + tests |
| R-18 | **Posting order is the cost order.** Availability and cost are read from the live ledger at posting time (as everywhere else in Bizboard, B8-036). `doc_date` sets the period gate and the JE date only. Back-dating is limited by a window (section 4.13) | Tests at the window edge |

---

## 3. Architecture and target data model

### 3.1 App layout

| App | Owns | Why separate |
|---|---|---|
| `manufacturing` (existing) | BOM revisions, outputs, work orders, issue / return / receipt, close and variance, reservations-by-WO, quick entry, trace queries, MRP, routing, job cards, costing rates | Core production |
| `quality` (new) | Inspection templates, inspections, NCR / CAPA, CoA | Used by purchases (GRN) and manufacturing; avoids a purchases → manufacturing import |
| `jobwork` (new) | Job-work OUT orders, challans, receipts; job-work IN principal-material ledger; ITC-04 | Different GST rules and documents; own flag |
| `inventory` (existing) | New: `TraceLink`, `BatchLot.quality_status`, `SerialNumber.CONSUMED`, reservation reference fields, new movement types | Stock primitives stay in one place (R-1) |
| `accounting` (existing) | New `PostingService.post_*` methods and chart accounts | Single JE writer |

Turn `manufacturing/services.py` into a package without breaking imports:

```
manufacturing/services/__init__.py   # re-exports release_work_order, complete_work_order, cancel_work_order, assert_no_bom_cycle
manufacturing/services/bom.py        # revisions, explosion, cycle check, cost roll-up
manufacturing/services/documents.py  # post_document() helper, numbering, reversal
manufacturing/services/issue.py      # MaterialIssue post/reverse, backflush
manufacturing/services/receipt.py    # ProductionReceipt post/reverse, cost split
manufacturing/services/close.py      # WO close, variance, WIP subledger
manufacturing/services/reservation.py
manufacturing/services/quick_entry.py
manufacturing/services/trace.py
manufacturing/services/legacy.py     # today's release/complete/cancel, kept for AUTO_AT_RELEASE tenants
manufacturing/services/mrp.py        # Phase 2
manufacturing/services/costing.py    # Phase 5
```

Dependency direction (enforced by review, optionally import-linter later):
`manufacturing → inventory, accounting, masters, core`; `quality → inventory, core`;
`jobwork → inventory, accounting, masters, sales (print / e-way helpers only), core`.
`inventory` never imports `manufacturing`.

### 3.2 Target data model

New fields are **bold**. All new tenant tables are `CompanyScopedModel` (gets `company`,
`created_at/by`, `updated_at/by`) unless marked "line" (company FK set in `save()`, the
`BomLine` pattern).

**`manufacturing.Bom`.** One row per **revision**. Keeping a row per revision means the
existing `WorkOrder.bom` FK already pins a revision.
- existing: `product`, `name`, `status` (DRAFT / ACTIVE / ARCHIVED)
- **`revision_no`** int ≥ 1; unique (company, product, revision_no)
- **`effective_from`**, **`effective_to`** date, nullable
- **`is_default`** bool; partial unique (company, product) where `is_default` and `status=ACTIVE`
- **`customer`** FK `masters.Customer`, nullable (customer-specific revision)
- **`parent_revision`** self FK, nullable; **`change_reason`** text
- **`locked_at`** datetime; set when the first WO is created on it; locked revisions are read-only
- **`output_qty`** Decimal(12,3) default 1 (batch size); **`yield_pct`** Decimal(5,2) default 100
- **`notes`**; attachments through `core/services/files.py`

**`manufacturing.BomLine`** (line). Qty is per `bom.output_qty`.
- existing `component`, `qty`
- **`unit`** FK `masters.Unit` nullable (must equal the product's base or alternate unit; converted with `conversion_rate`)
- **`scrap_pct`** Decimal(5,2) default 0; **`issue_method`** MANUAL / BACKFLUSH
- **`is_optional`**; **`alternate_group`** small int null; **`alternate_priority`** small int
- **`source_warehouse`** FK nullable (blank = default by the component's `mfg_role`, see the warehouse defaults below)
- **`sequence`**; **`notes`**

**`manufacturing.BomOutput`** (line, new). Co-products, by-products, scrap.
- `bom`, `product`, `qty` (per `output_qty`), `kind` CO_PRODUCT / BY_PRODUCT / SCRAP
- `cost_share_pct` (main + co-products = 100; by-products and scrap 0 and valued at `recovery_rate`)
- `recovery_rate` Decimal(12,4) nullable
- **`target_warehouse`** FK nullable (blank = default by role)
- The main product's target is on the BOM: **`Bom.fg_warehouse`** FK nullable

**Warehouse defaults (rev 2).** Real factories keep raw material, finished goods and scrap in
different godowns. Resolution order, for each issue line and each output line:
1. the document line (user edit);
2. the WO line or WO output (snapshot);
3. the BOM line or BOM output;
4. the company default for the product's `mfg_role`: new company settings
   `mfg_rm_warehouse`, `mfg_fg_warehouse`, `mfg_scrap_warehouse`, `mfg_wip_warehouse` (optional);
5. `WorkOrder.warehouse`;
6. `InventoryService.default_warehouse`.

This logic lives in one function, `resolve_warehouse(line_kind, product, wo, bom_line=None)`.

**`manufacturing.WorkOrder`**
- existing fields kept. `warehouse` becomes the **default source** godown; **`fg_warehouse`** is added for outputs
- **`kind`** STANDARD / REWORK. A REWORK WO has `bom = NULL` (the FK becomes nullable), a **`product`** FK (always set; equals `bom.product` for STANDARD) and lines added directly (rev 2, MFG-11)
- **`number`** (document series `WO`), **`due_date`**, **`planned_start`**, **`priority`** (1–5)
- **`sales_order`**, **`sales_order_item`** FK nullable (MTO pegging)
- **`issue_mode`** AUTO_AT_RELEASE (legacy) / SEPARATE. Copied from the company setting at creation
- **`qty_completed`**, **`qty_rejected`**, **`qty_rework`** (cached; invariant-checked against receipts)
- **`estimated_unit_cost`** Decimal(12,4), frozen at release (section 4.14)
- **Cost summary cache (rev 2):** **`cost_issued`**, **`cost_returned`**, **`cost_absorbed`** (conversion), **`cost_received`**, **`cost_variance`**, all Decimal(14,2). Updated inside `post_document()` in the same transaction, so no list or report sums `StockMovement` on the fly. `wip_value = issued − returned + absorbed − received − variance` (computed property). Checked against the ledger by the `wo_cost_summary_matches_ledger` invariant
- **`closed_at`**, **`delay_reason`** (choices), **`parent_work_order`** (rework, child WOs)
- status: DRAFT → RELEASED → IN_PROGRESS → COMPLETED → CLOSED; CANCELLED. (IN_PROGRESS after the first issue; COMPLETED when output ≥ planned or "mark complete"; CLOSED after variance settlement.)

**`manufacturing.WorkOrderLine`** (line, existing snapshot)
- **`unit`**, **`scrap_pct`**, **`issue_method`**, **`alternate_of`** self FK nullable, **`source_warehouse`**
- **`source_batch`** FK nullable (REWORK line consuming the rework batch)
- **`qty_issued`**, **`qty_returned`** (cached; invariant-checked against movements)

**`manufacturing.WorkOrderOutput`** (line, new): the planned outputs copied from `BomOutput`
at creation, with `target_warehouse`.

**New documents** (each with lines, `number`, `status` DRAFT / POSTED / REVERSED, `doc_date`,
`reversal_of`, `reason`):
- `MaterialIssue` / `MaterialIssueLine`: component, warehouse, qty, unit, batch, lot_allocations, serials, `is_extra`, `extra_reason`
- `MaterialReturn` / `MaterialReturnLine`
- `ProductionReceipt` / `ProductionReceiptLine`: product, kind (MAIN / CO / BY / SCRAP), qty_good, qty_rejected, qty_rework, batch, serials, `unit_cost`, `cost_amount`
- `WorkOrderVariance` (rows written at close): component or cost element, standard qty / cost, actual qty / cost, variance, kind

**`inventory`**
- `MovementType` **+ `MANUFACTURE_RETURN` (+1), `MANUFACTURE_REVERSAL` (signed like ADJUSTMENT)**, subject to D-11. Job-work OUT reuses `TRANSFER_OUT` / `TRANSFER_IN` to a job-worker warehouse (no new type), with the cost rules in MFG-24
- **Reference-type registry (rev 2).** `_apply_cost_layers` now decides layer behaviour from two hard-coded tuples of `reference_type` strings: "inbound restore, do not create a layer" (`cancel_restore`) and "outbound that retires a specific layer, do not peel oldest". Move both into named sets in `inventory/costing_refs.py` (`RESTORE_INBOUND_REFS`, `RETIRE_SPECIFIC_LAYER_REFS`) with a docstring per entry. Every new manufacturing and job-work reference type is registered there in MFG-01 / MFG-06 / MFG-24, and a unit test fails if any `reference_type=` literal used with `post_movement` in `manufacturing/` or `jobwork/` is missing from the registry
- `SerialNumber.Status` **+ `CONSUMED`**
- **`TraceLink`** (new): `work_order`, `receipt`, `input_product`, `input_batch`, `input_serial`, `output_product`, `output_batch`, `output_serial`, `qty`
- `StockReservation` **+ `reference_type`, `reference_id`; `expires_at` nullable** (null = held until released by the document)
- `BatchLot` **+ `quality_status`** QUARANTINE / HOLD / RELEASED / REJECTED (default RELEASED, so existing data is unchanged)
- `Warehouse` **+ `kind`** NORMAL / QUARANTINE / JOB_WORKER / SCRAP; **+ `job_worker`** FK Supplier nullable. **Picker hygiene (rev 2):** add `Warehouse.objects.selectable(purpose)` (purposes: SALE, COUNT, REORDER, TRANSFER, MFG_ISSUE, MFG_RECEIPT) and move the ~16 existing `is_system=False` filters onto it. JOB_WORKER godowns are never offered for sale, count sessions or reorder alerts; QUARANTINE and SCRAP are offered only where the purpose allows. A test asserts no sales or count endpoint returns a non-NORMAL godown

**`masters.Product`** **+ `mfg_role`** (RAW / SEMI_FINISHED / FINISHED / PACKING / CONSUMABLE / SCRAP / BY_PRODUCT, blank allowed)

**Phase 2:** `MrpRun`, `MrpLine` (product, need date, demand, supply, net, suggestion kind PURCHASE / MAKE, supplier, converted_to). `Company` / settings: `mfg_default_issue_mode`, `mfg_backflush_default`.

**Phase 3, `quality`:** `InspectionTemplate` (product or category, stage INCOMING / IN_PROCESS / FINAL, sample size), `InspectionParameter` (name, kind NUMERIC / TEXT / PASS_FAIL, min, max, unit, mandatory), `Inspection` (template snapshot, source GRN line or receipt line, batch, decision PASS / FAIL / HOLD / REWORK, inspector, date), `InspectionResult`, `NonConformance` (source, supplier or customer, defect code, root cause, action, owner, due, status), `DefectCode`.

**Phase 4, `jobwork`:**
- `JobWorkOrder` (supplier, direction OUT, process, expected return date)
- `JobWorkChallan` + **`JobWorkChallanLine`**: number series `JWC`, e-way fields mirroring `DeliveryChallan`; line has `product`, `batch`, `qty`, `unit_cost` (stamped), `goods_kind` INPUT / CAPITAL_GOOD, `origin` OWN_PREMISES / DIRECT_FROM_SUPPLIER (with the supplier GRN), `qty_settled` (cached)
- `JobWorkReceipt` + **`JobWorkReceiptLine`**: kind PROCESSED / UNPROCESSED_RETURN / SCRAP_RETURNED / SCRAP_RETAINED / CONSUMED / SENT_TO_OTHER_JOB_WORKER / SUPPLIED_FROM_JOB_WORKER
- **`JobWorkSettlement`** (rev 2): receipt line ↔ **challan line** with qty. FIFO auto-allocated with user override. **Required** for every receipt line. It drives the exact deemed-supply clock per challan line and ITC-04 Table 5 rows (original challan number and date)
- `PrincipalMaterial` / `PrincipalMaterialMovement` (job work IN: qty-only ledger, **never valued, never in WAVG, FIFO or GL**)
- `Itc04Filing` (period, status, export file)

**Phase 1 (rev 2, MFG-37):** `BomAdditionalCost` (revision, label, basis PER_UNIT / PER_BATCH, amount, absorption account), a flat additional cost per batch or unit.
**Phase 5:** `BomCostRate` (revision, element LABOUR / OVERHEAD / MACHINE, basis PER_UNIT / PER_BATCH / PER_HOUR, rate). It generalises `BomAdditionalCost` and migrates its rows. Also `StandardCost` (product, effective_from, material, labour, overhead) and chart accounts (section 7, MFG-28/29).

**Phase 6:** `WorkCentre`, `RoutingOperation` (bom revision, sequence, work centre, setup / run minutes, subcontract flag), `JobCard`, `TimeLog`, `DowntimeReason`, `Machine`, `MaintenancePlan`, `MaintenanceLog`.

### 3.3 Posting map (GL), with sub-flag `MFG_COSTING_GL` where marked

| Event | Stock | GL (accounting_enabled) |
|---|---|---|
| Material issue | MANUFACTURE_ISSUE −qty; cost = the **stamped** consumed cost (WAVG pool average under the lock, or FIFO peels) | Dr 1450 WIP / Cr 1400 Inventory (Σ stamped cost) |
| Material return | MANUFACTURE_RETURN +qty at the issue movement's stamped cost. FIFO: `restore_fifo_peels`; WAVG: inbound to the running pool at that cost | Dr 1400 / Cr 1450 |
| Production receipt, main / co-product | MANUFACTURE_RECEIPT +qty at the receipt cost (section 4.14) | Dr 1400 / Cr 1450 |
| By-product / scrap receipt | MANUFACTURE_RECEIPT at recovery rate (0 allowed) | Dr 1400 / Cr 1450 (recovery) |
| Rework qty at receipt | MANUFACTURE_RECEIPT into a REWORK batch in the quarantine godown at the receipt unit cost | Dr 1400 / Cr 1450 |
| Additional cost per batch (Phase 1, MFG-37) | none (in the FG unit cost) | Dr 1450 / Cr Manufacturing expenses absorbed |
| Conversion cost absorption (Phase 5) | none (in the FG unit cost) | Dr 1450 / Cr Labour absorbed, Overhead absorbed |
| Close with residual WIP (short-close only, section 4.14) | none | Dr/Cr Manufacturing variance / Cr/Dr 1450 → WO WIP = 0 |
| Job-work send (Phase 4) | TRANSFER_OUT from own godown, TRANSFER_IN to the job-worker godown at the **out-movement's stamped cost** | none (still own stock) |
| Scrap retained by job worker | ADJUSTMENT out of the job-worker godown (reference `jobwork_scrap_retained`) at stamped cost | Dr Scrap / process loss / Cr 1400 (or into WIP of the linked WO) |
| Job charges | via purchase invoice | Dr 1450 (open WO) or Dr 1400 / Cr Supplier |
| Reversal of any of the above | mirror, at the original stamped cost | mirror JE via the existing reversal path |

Account codes for "Labour absorbed", "Overhead absorbed" and "Manufacturing variance": pick
free codes in `PostingService._ensure_chart` (**verify** the chart for collisions in MFG-09).

---

## 4. Cross-cutting standards

### 4.1 API design
- REST under the existing manufacturing router (`manufacturing/urls.py`). New apps get their own routers mounted in `config/urls.py` behind their flags.
- Resource style: `/boms/`, `/boms/{id}/revise/`, `/work-orders/`, `/work-orders/{id}/release|complete|close|cancel/`, `/material-issues/`, `/material-issues/{id}/post/`, `/material-issues/{id}/reverse/`, `/production-receipts/…`, `/quick-production/`, `/trace/?batch=…|serial=…`, `/mrp-runs/`, `/mrp-runs/{id}/convert/`.
- State changes are **POST actions**, never PATCH on `status`.
- List endpoints are paginated with server-side filters (status, product, date range, due-before, warehouse) and default ordering. No unbounded lists.
- Every response that carries cost is passed through a masking serializer mixin (`cost_visible(role)`); fields are **omitted**, never zeroed (existing `mask_commercial` rule).
- OpenAPI: `drf-spectacular` annotations on every action. Regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` in the same PR (CI drift check).

### 4.2 Errors
- Rule violations raise `core.exceptions.BusinessRuleError` with a **stable `code`** (`MFG_BOM_LOCKED`, `MFG_REVISION_OVERLAP`, `MFG_SHORT_STOCK`, `MFG_BATCH_ON_HOLD`, `MFG_ZERO_COST_COMPLETE`, `MFG_PERIOD_LOCKED`, `JW_DEEMED_SUPPLY`, …).
- Each new code gets an entry in `help_codes.py` and `helpCodes.json` (CI asserts they match) and en + hi messages.
- User-fixable stock errors are added to the idempotency **transient** list (IDR-01 rule) so a retry after fixing input is not replayed as the old error.

### 4.3 Idempotency
- All POST create / post / reverse actions use `wrap_idempotent(scope="mfg.<doc>.<action>")`.
- The web client mints a new key per user gesture (`userGestureIdempotencyKey()` in `web/src/api/client.ts`). The offline queue keeps a stable key per queued item.

### 4.4 Concurrency
- Header `select_for_update()` first, then balance rows in a deterministic order (product id, warehouse id, batch id) to avoid deadlocks.
- No reads of `available` outside the lock when the result decides an allocation.
- Reservation create / release lock the same balance rows as issue.

### 4.5 Security and permissions

Permission matrix (MFG-00). ✔ = allowed, 👁 = read-only, — = none.

| Action | OWNER | MANAGER | INVENTORY_STAFF | ACCOUNTANT | AUDITOR | VIEWER | SALES_STAFF |
|---|---|---|---|---|---|---|---|
| BOM create / revise / activate | ✔ | ✔ | — | 👁 | 👁 | 👁 | — |
| WO create / release / cancel | ✔ | ✔ | create, release | 👁 | 👁 | 👁 | 👁 (MTO status only) |
| Issue / return / receipt / quick entry | ✔ | ✔ | ✔ | 👁 | 👁 | — | — |
| Reverse a posted document | ✔ | ✔ | — | — | — | — | — |
| WO close (variance) | ✔ | ✔ | — | ✔ | 👁 | — | — |
| See costs / variance | ✔ | ✔ | — | ✔ | ✔ | — | — |
| Quality decisions | ✔ | ✔ | ✔ (if inspector) | — | 👁 | — | — |
| Job work send / receive | ✔ | ✔ | ✔ | 👁 | 👁 | — | — |
| ITC-04 export | ✔ | — | — | ✔ | 👁 | — | — |
| MRP run / convert | ✔ | ✔ | run only | — | 👁 | — | — |

- Implement as DRF permission classes in `manufacturing/permissions.py` (`CanPlanProduction`, `CanPostProduction`, `CanReverseProduction`, `CanCloseProduction`), keeping `assert_manufacturing_enabled` (404 when off).
- Extra issue above a threshold, and reversal of a closed-period document, go through `ApprovalRequest`.
- Input limits: qty > 0 at DB level (CheckConstraint, the B8-017 pattern), percentages 0–100, max lines per document (e.g. 500), attachment AV scan (existing ClamAV rule).
- Audit: `core.services.audit.record_document_event` on create, post, reverse, close, and BOM activate or revise.
- No PII in telemetry (`ShopFloorEvent` rule). Operator PIN (Phase 6) needs a separate security review (D-10).
- `security-review` skill run on each phase's diff before merge.

### 4.6 Migrations
- **Expand → migrate → contract.** Add nullable or defaulted columns first, backfill in a separate data migration, add constraints last. Never rename or drop in the same release as the code that stops using a column.
- Data migrations are **idempotent, reversible (or explicitly `RunPython.noop` with a reason), batched** (`iterator(chunk_size=500)`), and log counts.
- Every new tenant table gets an RLS catch-up migration in `core` (pattern: `core/migrations/0026_rls_shopfloorevent.py`, a local `RLS_TABLES` list, `SET LOCAL lock_timeout = '5s'`, Postgres only), plus `accounts/tenant_backup.py` coverage.
- `makemigrations --check` clean (CI). Each migration-carrying WP is rehearsed with `scripts/migration_rehearsal.sh` on a staging copy before release.
- Test DB rebuild after migrations: `--create-db` once (≈ 9 min), then `--reuse-db`.

### 4.7 Feature flags and settings

| Flag / setting | Scope | Default | Guards |
|---|---|---|---|
| `ENABLE_MANUFACTURING` (exists) | company | off | whole module |
| `MFG_SEPARATE_ISSUE` (company setting `mfg_default_issue_mode`) | company | SEPARATE for new companies, AUTO_AT_RELEASE for existing | D-2 |
| `MFG_PLANNING` | company | off until Phase 2 exit | MRP, board, MTO |
| `MFG_QUALITY` | company | off | quality app, batch status enforcement |
| `MFG_JOB_WORK` | company | off | jobwork app, ITC-04 |
| `MFG_COSTING_GL` | company | **off until CA sign-off** | conversion-cost absorption, variance JEs, standard cost |
| `MFG_SHOP_FLOOR` | company | off | Phase 6 |

Register every flag in `core/services/feature_flags.py` (and billing entitlements if it is
sold), plus a web `VITE_ENABLE_*` mirror where the menu needs it. Flag on/off tests per WP.

### 4.8 Web UI
- Pages under `web/src/pages/manufacturing/`, lazy-loaded routes (bundle budget check in CI).
- Use the shared form and table components and the settings "frame" pattern; no new design system.
- A11y: labelled inputs, keyboard flow for quick entry, focus on the first error; existing `a11y.spec.ts` covers new routes.
- Numbers right-aligned, units shown next to every qty, costs hidden for masked roles (omitted fields → "—", never 0).
- Optimistic UI is **not** used for posting; show pending until the server confirms.
- Offline: only quick entry and (Phase 6) job cards use the offline queue, with a stable key per item.
- Type-check with `tsc -b` (not `tsc -p .`); eslint 0 errors; vitest for every new page and hook.

### 4.9 i18n and help
- No string literals in JSX (`literalRatchet.test.ts`, `jsxLiteralRatchet.test.ts`). Keys in `en.ts` and `hi.ts` (`fullParity.test.ts`).
- Shop-floor screens Hindi-first; human Hindi review is a QOS sign-off item per phase.
- Context help entries for BOM revision, backflush, variance, ITC-04 and deemed supply.

### 4.10 Observability
- Structured logs at INFO on every post / reverse / close with company id, document id, counts and duration; never quantities with customer names.
- Metrics: post latency per document type; error counts by `code`; MRP run duration and line count.
- `ShopFloorEvent` new events (no PII): `mfg_quick_entry`, `mfg_issue_posted`, `mfg_receipt_posted`, `mfg_wo_closed` with duration and line count. Used for the Phase 1 success measure (share of entries by non-owner roles).
- Needs-attention codes (MFG-X2): add to `insights/attention.py` `KNOWN_CODES` (CI test asserts every emitted code is known).

### 4.11 Performance
- Query budget tests (`django_assert_max_num_queries`) for list endpoints and post actions; no N+1 (use `select_related` / `prefetch_related`).
- Indexes: (company, status, due_date) on WO; (company, work_order) on documents; (company, input_batch) and (company, output_batch) on `TraceLink`; (company, run, product) on `MrpLine`.
- Targets on the `slow` 10k-row fixture: post an issue with 50 lines < 1.5 s; MRP for 2,000 SKUs × 3 levels < 20 s (run as a Celery task beyond 500 SKUs); trace one batch < 500 ms.
- Multi-level explosion is iterative with a visited set (no recursion-depth risk) and is cached per (revision, date) during a run.
- WO lists, the board and the WIP report read the WO cost-summary cache (§3.2), never sums over `StockMovement`.

### 4.12 Reversal dependency rules (rev 2)
Reversal runs newest-first. Each reversal checks, under the WO header lock:

| Reversing | Allowed only if |
|---|---|
| Any document on a **CLOSED** WO | Never directly. Reverse the close first (`reopen`, MANAGER+, period-gated, reverses the variance JE), then the document |
| ProductionReceipt | Its output stock is still on hand in that batch, serial and godown (CR-014 pattern), **and** no later receipt on the same WO is posted (reverse the later ones first, so the remaining-pool arithmetic stays exact) |
| MaterialIssue | After reversal, net issued cost (issued − returned − this issue) ≥ received cost + variance on the WO. Otherwise reverse receipts first. Its serials are not linked by a posted receipt's `TraceLink` |
| MaterialReturn | The returned stock is still available |
| WO close | No later period lock covers the close date (or an approval exists) |
| Job-work challan | No settlement rows exist against its lines |

Error code `MFG_REVERSAL_ORDER` names the blocking document so the UI can link to it.

### 4.13 Back-dated entries (rev 2)
- Small units enter yesterday's production today. Bizboard costs and checks stock in **posting order** (live balances and live cost pools; see B8-036 in `inventory/services.py`). Manufacturing follows the same rule. It does **not** check historical availability as of `doc_date`, and it does not re-cost earlier documents.
- `doc_date` drives the period gate, the JE date, the batch mfg date and reports by date.
- Company setting `mfg_backdate_days` (default 7): `doc_date` older than today − N needs MANAGER role and an `ApprovalRequest`. Future dates are refused.
- The UI shows "Stock and cost are taken as of now, not as of the entry date" when `doc_date < today`.
- Consequence (documented in help): if raw material bought today at ₹120 is issued against yesterday's batch, the batch is costed from today's pool. This matches how sales are already costed.

### 4.14 Receipt costing (rev 2, replaces the rev 1 formula in MFG-08)
Rev 1's "split by the receipt's share of planned qty" under-costs later partial receipts and
mis-costs receipts made before full issue. The rule is now:

1. **At release**, freeze `WorkOrder.estimated_unit_cost`: Σ(component required qty × current unit cost from `InventoryValuationService.unit_cost`) + additional cost (MFG-37), divided by the planned qty. The main and co-product split uses `cost_share_pct`.
2. **Partial receipt** (WO not being completed by this receipt):
   - By-product and scrap lines are valued at `recovery_rate × qty`.
   - Main, co-product and rework lines are valued at `estimated_unit_cost × share × qty`.
   - **Cap:** if this would make the WO's WIP value negative (receipt cost > net pool), the receipt is refused with `MFG_RECEIPT_EXCEEDS_WIP` ("issue materials first"). MANAGER may override ("materials will be issued later"), and the WO then shows a `WIP_NEGATIVE` attention item until it is fixed.
3. **Final receipt** (it completes the WO, or the user ticks "last receipt") takes the **whole remaining pool** for its main, co-product and rework lines, after by-product and scrap recovery. The FG therefore carries the true actual cost in total.
   - Company setting `mfg_final_receipt_tolerance_pct` (default blank = absorb everything). If set, any part of the residual beyond ±N% of the estimate goes to the variance account at close instead of into the last batch.
4. **Close** posts a GL variance only for:
   - a short-close (remaining pool, no more output);
   - the tolerance overflow above;
   - standard costing (MFG-29).
   Usage variance (quantity and value per component) is always **reported**.
5. Property test: for any sequence of issues, returns, receipts and close, Σ receipt cost + Σ recovery + posted variance = Σ issued − Σ returned + Σ absorbed, to 0.01.

This is the common SME-ERP approach (provisional cost at estimate, true-up on the last receipt).
The known trade-off: earlier partial batches carry the estimate, and the last batch carries
the true-up. The trade-off is written into the help text, and the CA reviews it in the
Phase 1 sign-off.

### 4.15 Valuation methods (rev 2)
Verified in code:
- `Company.inventory_valuation_method` defaults to `"WAVG"`.
- `_apply_cost_layers` and `restore_fifo_peels` return immediately unless the method is FIFO.
- Under WAVG, `_apply_running_cost` consumes at the pool's own average under the row lock (B8-003). However, the outbound `StockMovement.unit_cost` keeps whatever the caller passed: today `InventoryValuationService.unit_cost(...)` is read **before** the lock and can differ from what the pool actually consumed.

So, in MFG-01:
- **Stamp the consumed WAVG cost.** `post_movement` stamps the average actually consumed onto outbound WAVG movements, through the existing row-locked `StockMovement.stamp_cost` path that FIFO already uses. Callers stop passing a pre-read cost for outbound movements.
- **One cost source.** `_issue_cost_total` (and the new WO cost cache) read only stamped movement costs.
- **Returns and reversals** pass the original movement's stamped cost:
  - FIFO restores the peels (`restore_fifo_peels`) or retires the exact layer (`retire_source_layers`);
  - WAVG posts an inbound to the running pool at that cost. No layer helpers are called, because they are no-ops for WAVG.
- **Both methods in the suite.** The whole manufacturing suite runs under both methods (pytest parametrisation on a company fixture).
- **Check the shared stock paths.** Stamping changes a stock-wide path, so the inventory suite and the `rebuild_running_cost` value-drift check must stay green. This is a separate commit inside MFG-01, reviewed on its own.

### 4.16 Incoming inspection and the GRN (rev 2)
Verified in code: GRN accept and reject quantities are set on the **draft**, and
`GoodsReceiptService.complete` posts only `quantity_accepted`. So:
- **Default, inspect before complete.** An incoming inspection is recorded on the draft GRN line. Its decision writes `quantity_accepted` and `quantity_rejected`, and the GRN is then completed as today. Completing a GRN whose product requires inspection is refused until an inspection exists (when `MFG_QUALITY` is on).
- **Option for slow tests ("receive into quarantine")**, for products with that flag (lab results take days):
  - The GRN completes with the accepted quantity into a batch with `quality_status=QUARANTINE`, in the quarantine godown.
  - **Pass:** the batch becomes RELEASED, with an optional transfer to the RM godown.
  - **Fail:** a purchase return through the existing return flow, or a transfer to the SCRAP godown with a write-off through the IDR-02 stock-loss service.
  - **Partial pass:** the batch is split by transfer.
- The rejected quantity on a draft GRN never enters stock (unchanged behaviour).

---

## 5. Test strategy

Follows [TESTING_STRATEGY.md](TESTING_STRATEGY.md). Every WP lists its own tests; this is the frame.

| Layer | What | Tooling | Gate |
|---|---|---|---|
| Unit | Pure functions: explosion, cost split, variance maths, unit conversion, deemed-supply clock, ITC-04 period | pytest, `hypothesis` for cost split and explosion if already a dependency (**verify**; otherwise table-driven) | CI |
| Service | Every rule and posting path, flags on/off, period lock, roles | pytest + factories; `dark_module` marker | CI, coverage ≥ 83% total, ≥ 80% diff |
| Invariant | Teardown hook checks stock = Σ movements, valuation = Σ layers, plus new manufacturing invariants (below) | `core/invariants/` | automatic on every test that posts |
| API | Wiring, permission matrix, masking, idempotency replay, pagination, OpenAPI shape | DRF test client | CI |
| Concurrency | Two releases / issues / reservations on the same stock; double-post the same document; quick entry vs sale on the last unit | `@pytest.mark.postgres`, private Postgres test DB recipe | before phase exit (not in the SQLite lane) |
| Migration | Forward / backward on a DB holding legacy rows (several ACTIVE BOMs, released WOs, serials SCRAPPED by WO) | `migrator` tests or manual rehearsal script | per migration WP |
| Web unit | Pages, hooks, masking, i18n keys | vitest | CI |
| E2E | Golden journeys (below) | Playwright, `web/e2e/dark-modules/` | per phase exit |
| Regression | One permanent test per fixed defect (DEF-1, DEF-2, DEF-3, B8-009, B8-018, WAVG stamp) | `tests/regression/`, `regression` marker | CI |
| Valuation matrix | Every service and invariant test that posts runs under **WAVG and FIFO** (`valuation_method` fixture parametrised) | pytest parametrisation | CI |
| Manual | CA review, Hindi review, device / shop-floor usability | QOS items | release gate (not merge gate) |

**New invariants (MFG-X4)**
- `wo_issue_qty_matches_movements`: `WorkOrderLine.qty_issued − qty_returned` = −Σ issue movements + Σ return movements.
- `wo_output_matches_receipts`: `qty_completed` = Σ posted receipt main qty.
- `wip_subledger_matches_gl`: Σ open-WO (issued + absorbed − received − variance) = GL 1450 balance (accounting-enabled companies).
- `closed_wo_has_zero_wip`.
- `consumed_serial_has_trace`: every CONSUMED serial has a `TraceLink`.
- `no_hold_batch_outbound`: no SALE / challan movement from a batch not RELEASED (when `MFG_QUALITY` is on).
- `wo_cost_summary_matches_ledger`: each WO's cached `cost_issued`, `cost_returned`, `cost_received` equal the sums of the stamped costs of its movements; `cost_absorbed` and `cost_variance` equal its JEs.
- `wo_wip_non_negative`: WIP ≥ 0 unless an approved override exists (section 4.14).
- `principal_material_non_negative` (job work IN).
- `jobworker_stock_matches_open_orders`: stock in each job-worker godown = Σ challan line qty − Σ settled qty. Retained scrap and consumption are settlement kinds that post their own out-movements, so the invariant holds when scrap stays with the job worker.
- `jobwork_settlement_complete`: every receipt line is fully settled against challan lines.
- `no_stock_in_job_worker_godown_from_sale`: no SALE / challan movement out of a JOB_WORKER godown unless direct supply (MFG-24) is used.

**Golden journeys (E2E, one per phase)**
1. Quick entry: spice batch with 2 % process loss, a by-product and ₹500 / batch grinding and packing cost (MFG-37), issued from the RM godown and received into the FG godown → sell from the batch → trace back to the supplier batch.
2. Partial run: WO for 1,000 → issue 600 → receive 400 (at estimate) → extra issue with reason → receive 550 + 30 rejected + 20 rework (final, takes the residual) → rework WO → return leftovers → close → variance report. Run under WAVG and FIFO.
3. MTO: SO → WO from SO → shortage → MRP suggestion → PO draft → GRN → release → receipt reserved to SO → challan.
4. Quality: GRN into quarantine → failed inspection → NCR → partial accept → final inspection HOLD blocks the invoice → release → invoice.
5. Job work: send to a job worker with an e-way bill → partial return + scrap → ageing alert → ITC-04 export matches.
6. Costing (flag on): labour and overhead absorbed → FG cost → margin report → month close with WIP reconciled.

**Test recipe** (from earlier programmes): private pytest settings with their own TEST DB
name, `--reuse-db`, `--runxfail` to catch hidden setup errors; rebuild with `--create-db`
after migrations; Postgres lane via the private Postgres DB used for IDR-14.

---

## 6. Delivery process

### 6.1 Branching and commits
- One branch per phase: `feat/mfg-p0-foundations`, `feat/mfg-p1-execution`, … cut from `main`.
- **One commit (or small set) per WP**, message `MFG-06: material issue document`, ending with the agreed Co-Authored-By line.
- Merge to `main` through a PR when the phase exit gate passes; flags keep unfinished work dark. Do not let a phase sit uncommitted in the working tree (lesson from earlier programmes: stash wipes, mixed sessions).
- Rebase on `main` at least weekly; regenerate OpenAPI after each rebase.

### 6.2 Definition of Ready (before a WP starts)
- [ ] Blocking decisions answered (section 11)
- [ ] Data model and endpoint list agreed (this file updated)
- [ ] Acceptance criteria written as testable statements
- [ ] Flag named and default decided
- [ ] Migration plan (expand / contract) written if the schema changes

### 6.3 Definition of Done (per WP)
- [ ] Service code, API, UI (if any), en + hi strings, help codes
- [ ] Tests: service, API, permission matrix, flag on/off, invariants pass, regression test for any bug fixed
- [ ] Postgres race test for new posting paths (can batch per phase, must pass before phase exit)
- [ ] `ruff check .`, `makemigrations --check`, OpenAPI snapshot and web types regenerated, `tsc -b`, eslint, vitest, build, bundle budget, `scripts/ci_gates/run_guards.py`
- [ ] RLS migration and tenant-backup coverage for new tables
- [ ] Code review: `code-review` skill (high) on the WP diff; findings fixed or recorded
- [ ] Docs: this file's execution record, user help, QOS item for any human sign-off
- [ ] Demo data updated (`enable_full_demo`, `provision_ux_audit`) if screens are new

### 6.4 Phase exit gate
- All WPs Done; full suite green; Postgres lane green; golden journey E2E green;
  `security-review` skill on the phase diff; staging deploy and smoke
  (`scripts/post_deploy_smoke.py`); migration rehearsal on a staging copy; flags still default off.

### 6.5 CI gates (existing; every PR must pass)
`ruff`, `pip-audit`, `makemigrations --check`, OpenAPI snapshot clean, help codes match, test
suite with coverage ≥ 83%, diff coverage ≥ 80%, Freeze Gate guards, web `npm run lint`,
`test:run`, `build`, service-worker and bundle-budget checks, `npm audit`, OpenAPI types
clean, register-claims check, `qos-lint`.

---

## 7. Work packages

Effort = ideal engineer-days, including tests. "Mig" = schema migration.

### Phase 0 — Foundations and fixes

#### MFG-00 Roles, permissions and sub-flags (2.5 d, no mig)
- **Goal:** non-owners can work; every later WP has its flag.
- **Build:** permission classes from §4.5 replacing `IsOwner` in `manufacturing/views.py`; cost-masking serializer mixin using `cost_visible`; register `MFG_PLANNING`, `MFG_QUALITY`, `MFG_JOB_WORK`, `MFG_COSTING_GL`, `MFG_SHOP_FLOOR` in `feature_flags.py`; web menu gating.
- **Tests:** role × endpoint matrix (parametrised); masked fields omitted for INVENTORY_STAFF; 404 when `ENABLE_MANUFACTURING` is off.
- **Accept:** INVENTORY_STAFF can create and release a WO but cannot see `unit_cost` or reverse.

#### MFG-01 Fix DEF-1, DEF-2, DEF-3 and the costing foundations (7 d, mig: inventory status + types, data migration)
Split into four commits, each reviewed on its own.
- **(a) WAVG cost stamping (§4.15):**
  - `post_movement` stamps the consumed pool average onto outbound WAVG movements (`StockMovement.stamp_cost`);
  - `release_work_order` stops pre-reading the cost for issues;
  - `_issue_cost_total` reads stamped costs only.
  - Tests: concurrent issue and purchase on the same pool → the stamped cost equals the pool consumption; the inventory suite and `rebuild_running_cost` value-drift check stay green.
- **(b) Reference-type registry (§3.2):** move the two hard-coded tuples in `_apply_cost_layers` into `inventory/costing_refs.py`, behaviour unchanged (pure refactor, existing tests prove it), then register `work_order_cancel`, `mfg_issue_reverse`, `mfg_return`, `mfg_receipt_reverse`, `jobwork_*`. Includes the guard test that every manufacturing and job-work `reference_type` literal is registered.
- **(c) DEF-1, zero-cost completion:** complete refuses with `MFG_ZERO_COST_COMPLETE` when issue cost is 0 and any component tracks inventory (D-6). Otherwise the GL amount always equals the FG layer total (build the layer from the quantized total, post the same number).
  - Regression tests: zero-cost component → refusal; normal path → GL 1400 movement = layer value; both valuation methods.
- **(d) DEF-2 consumed serials:**
  - Add `SerialNumber.Status.CONSUMED`; release and issue move component serials to CONSUMED and write `TraceLink` rows; cancel moves CONSUMED → AVAILABLE.
  - **Data migration:** `SerialNumber` has no reference fields; the only record of which serials a WO consumed is `WorkOrderLine.serial_numbers`, which cancel clears to `[]`. So the migration:
    1. joins WOs with `status in (RELEASED, COMPLETED)` → their `WorkOrderLine.serial_numbers` (JSON list) for that line's `component_id`;
    2. matches `SerialNumber` rows (company, product = component, number) with `status = SCRAPPED`;
    3. sets them to CONSUMED and creates `TraceLink` rows (to the WO's FG batch or serials when COMPLETED).
  - SCRAPPED serials not referenced by any such line stay SCRAPPED (genuine scrap, or history lost to a cancel). The migration logs counts per company. Idempotent; reverse = CONSUMED → SCRAPPED for rows it touched (tracked in a migration audit table).
  - Update the `serial_traceability` invariant.
- **DEF-3 reversal movements:** cancel uses `MANUFACTURE_REVERSAL` (signed) with `reference_type="work_order_cancel"` instead of ADJUSTMENT. Needs D-11. Grep every `MovementType` consumer (reports, GSTR stock summaries, invariants, `_replay`) and update the ones that group by type; the adjustment report excludes the new type.
- **Accept:** regression tests pass under WAVG and FIFO; existing `test_sprint_b_manufacturing_cancel.py`, the manufacturing tests and the full inventory suite still pass.

#### MFG-02 Work order header, statuses, kinds and godowns (5 d, mig)
- Fields per §3.2, including `kind`, `product`, `fg_warehouse`, the cost-summary cache (backfilled from movements and JEs for existing WOs), the `resolve_warehouse()` defaults and the company role-godown settings; number from `core/services/document_numbers.next_number(company, "WO")` (add the doc type; **verify** series config UI picks it up); statuses with a transition table in one place (`WorkOrder.can_transition(to)`); delay reasons; company setting `mfg_default_issue_mode` (new companies SEPARATE, existing AUTO_AT_RELEASE via data migration).
- Release with SEPARATE mode: validates BOM, snapshots, creates reservations (MFG-10; until then, no stock effect).
- Backfill `number` for existing WOs as `WO-{id}` (matches today's narration).
- `Warehouse.kind` and `Warehouse.objects.selectable(purpose)` land here (§3.2 picker hygiene), so later quarantine, scrap and job-worker godowns never leak into sales or counts.
- **Tests:** transition table exhaustive; legacy mode unchanged (existing tests run with AUTO_AT_RELEASE); numbering unique under concurrency (Postgres); warehouse resolution order table; cache backfill equals the ledger; no sales or count endpoint lists a non-NORMAL godown.

#### MFG-03 BOM revisions (6 d, mig + data migration)
- Fields per §3.2. Service `bom.revise(bom, user, reason)` copies lines and outputs to `revision_no+1` in DRAFT. `activate(revision, make_default=True)` ends the previous default's `effective_to` and checks for no overlap per (product, customer).
- `resolve_bom(product, on_date, customer=None)` is the **only** way code picks a BOM (customer-specific default → generic default → error).
- Locking: `locked_at` set on first WO create; edits on a locked revision raise `MFG_BOM_LOCKED`.
- **Data migration** (B8-018): per (company, product) with several ACTIVE BOMs, the newest becomes `is_default`, `revision_no` assigned by created_at, the others stay ACTIVE non-default. Then add the partial unique index in a **separate** migration. Dry-run command `manage.py mfg_bom_revision_report` lists what will change per tenant.
- **Tests:** overlap refused; resolve by date and customer; locked edit refused; migration on a fixture with 3 ACTIVE BOMs; cycle check uses the default revisions only.

#### MFG-04 BOM enrichment: batch size, units, scrap, outputs (6 d, mig)
- Fields per §3.2 and `BomOutput`. Requirement maths in one pure function:
  `required(line, wo_qty) = line.qty × (wo_qty / bom.output_qty) × (1 + scrap_pct/100) × unit_factor`, rounded to 3 dp at the end only.
- Validation: unit ∈ {product.unit, product.alternate_unit}; cost shares of MAIN + CO = 100; BY / SCRAP share 0; an output product ≠ any component in the same revision.
- WO snapshot copies unit, scrap_pct, issue_method; planned outputs are copied to the WO.
- **Tests:** table-driven maths (batch 100 kg, WO 250 kg, 2 % scrap, g ↔ kg); validation errors; snapshot independence.

#### MFG-05 Product manufacturing role (1.5 d, mig)
- `Product.mfg_role`; default guess in a data migration (has an ACTIVE BOM → FINISHED or SEMI_FINISHED if also used as a component; used only as a component → RAW). Editable in the product form. Used by reports and default filters.

**Phase 0 exit:** suite + Postgres lane green, migration rehearsal on a staging copy with real-shaped legacy data, regression tests for DEF-1…DEF-3 under WAVG and FIFO, B8-018 closed, WAVG stamping soaked on staging.

### Phase 1 — Execution core

#### MFG-06 Material issue document (7 d, mig)
- `MaterialIssue` + lines; `post_document()` helper (R-3) used by every later document.
- Draft auto-filled from the WO (remaining = planned − issued + returned) or partial; extra issue (`is_extra`) needs a reason, and an `ApprovalRequest` above a company threshold (% of planned).
- Allocation reuses `_issue_batches` (moved to `issue.py`) with locking; serials → CONSUMED + `TraceLink` (provisional, completed on receipt).
- Each line issues from its resolved **source godown** (§3.2); lines from different godowns in one document are allowed (balance rows locked in a deterministic order, §4.4).
- JE per posted issue (Dr 1450 / Cr 1400) from the **stamped** movement costs; WO `cost_issued` updated in the same transaction. WO → IN_PROGRESS on the first issue. Reservations released for the issued qty.
- Back-date window per §4.13.
- Reverse per §4.12: mirror movements at the stamped cost (FIFO: `restore_fifo_peels`; WAVG: inbound to the pool at that cost), mirror JE.
- **Tests:** partial and multiple issues; multi-godown issue; extra with or without approval; batch, FEFO and serial paths; double post (same key and new key) → one posting; reverse, including blocked when receipts depend on it; period lock and back-date window; WAVG and FIFO; Postgres race (two issues on the last stock).

#### MFG-07 Material return (3 d, mig)
- `MaterialReturn` against a WO; qty ≤ issued − returned per line, batch and godown; returns at the originating issue movement's stamped cost. Under FIFO it restores the layer it came from (`restore_fifo_peels`); under WAVG it posts an inbound to the running pool at that cost. Serial CONSUMED → AVAILABLE and the provisional trace is removed. JE Dr 1400 / Cr 1450; WO `cost_returned` updated.
- A return that would make WO WIP negative (because receipts already absorbed the cost) is refused with `MFG_REVERSAL_ORDER` (§4.12).
- **Tests:** over-return refused; batch-exact return; cost equals the original stamped cost under WAVG and FIFO; the running-cost value-drift check stays green.

#### MFG-08 Production receipt with outputs (8 d, mig)
- `ProductionReceipt` with MAIN / CO / BY / SCRAP lines pre-filled from the WO's planned outputs (scaled by qty).
- **Receipt costing per §4.14** (pure function `cost_receipt(wo_summary, lines, is_final)`, property-tested): partial receipts at the frozen `estimated_unit_cost`, capped at the WIP pool (override with `WIP_NEGATIVE` attention); the final receipt takes the whole residual after by-product and scrap recovery; main and co-products split by `cost_share_pct`. Each line receives into its resolved **target godown** (FG, scrap, by-product, quarantine for rework).
- Backflush: lines with `issue_method=BACKFLUSH` are issued automatically inside the same transaction for `qty_good + qty_rejected` (one atomic post: an issue document plus a receipt document).
- FG batch per receipt (reuse the batch get-or-create rules from `complete_work_order`, including the expiry-mismatch check); FG serials; `TraceLink` completed (inputs → this output batch or serial).
- Rejected qty → SCRAP godown at recovery value (0 allowed); rework qty → MFG-11.
- **Tests:** property test from §4.14 (any sequence of issues, returns, receipts and close balances to 0.01) under WAVG and FIFO; the rev 1 failure cases as fixed examples:
  - 100-unit WO, full issue ₹1,000, receipts of 40 then 60 → ₹400 and ₹600 when the estimate is ₹10;
  - partial issue of ₹400 then a receipt of 40 → ₹400, not ₹160;
  - by-product at recovery; receipt exceeding WIP refused, then allowed with override;
  - backflush shortage refused atomically; serial genealogy present.

#### MFG-09 WO close, variance and WIP (5 d, mig)
- Close (COMPLETED → CLOSED): computes the standard for actual output per component and writes `WorkOrderVariance` rows (usage, yield, scrap; quantity and value) for **reporting**. It posts a GL variance only for the cases in §4.14: a short-close residual, tolerance overflow, or standard costing. The WO's WIP ends at 0. Leftover reservations are released.
- Auto-close option after N days of COMPLETED (company setting, off by default).
- WIP report: open WOs with issued, received and WIP value, age buckets; matches GL 1450 (invariant).
- Year-close check (`OPEN_WIP`) extended: COMPLETED-not-CLOSED counts as open WIP.
- **Tests:** variance maths; close twice refused; reopen not allowed (reverse receipts instead); GL 1450 = 0 for a closed WO; invariant holds across a mixed fixture.

#### MFG-10 Reservations against a WO (4 d, mig)
- `StockReservation.reference_type/id`, nullable `expires_at`; the beat task skips null-expiry rows (**verify** the beat query).
- Reserve on release (SEPARATE mode), reduce on issue, release on close or cancel. Batch-specific when the line has a batch.
- `available` already subtracts `reserved`; the shortage view (MFG-15) reads it.
- **Tests:** reservation blocks a sale of the reserved qty (where `check_negative_stock` applies); release paths; Postgres race reserve vs sale.

#### MFG-11 Rejection and rework (4 d)
- On a receipt:
  - **Rejected** → SCRAP godown at recovery value.
  - **Rework** → received at the receipt unit cost (§4.14, so it takes its fair share of the parent's pool and good units are not over-costed) into a REWORK batch in the quarantine godown.
- **Rework WO without a BOM (rev 2):** a `WorkOrder(kind=REWORK, bom=NULL, product=<FG>, parent_work_order=<parent>)` is created from the receipt.
  - Its lines are added directly: one line consuming the REWORK batch (`source_batch`) at its stamped cost, plus optional extra component lines.
  - It never touches the `Bom` table, so `assert_no_bom_cycle` (which refuses a BOM listing its own finished good) is not involved and stays strict.
  - Its receipt puts the reworked units back into normal FG stock at rework batch cost + extra materials + optional additional cost.
- **Tests:**
  - parent good units carry the parent's actual cost minus the rework share;
  - the rework WO output cost = the rework batch cost + extras;
  - the cycle check still refuses a self-referencing BOM;
  - rejected and rework stock is not saleable (quarantine godown + `selectable`).

#### MFG-12 Quick production entry (5 d, no new tables)
- `POST /quick-production/`: product, qty, date (back-date window §4.13), optional source godown (default RM by role) and FG godown (default FG by role), optional batch / expiry, optional actual component qtys, outputs and additional cost override (MFG-37). One transaction: create WO (from `resolve_bom`) → issue (actuals or BOM) → receipt → close. Returns the WO with all documents.
- UI: one screen, keyboard-first, last-used product memory, shows "can make" (MFG-15 lite: available ÷ per-unit need), editable actuals, Hindi labels. Offline-queue capable (stable key).
- **Tests:** books identical to the long path for the same inputs (golden comparison); offline replay posts once; role INVENTORY_STAFF allowed.

#### MFG-13 Traceability and reversals (4 d)
- `/trace/?batch=` (backward: inputs and supplier GRNs; forward: outputs → sales invoices / challans → customers). Iterative walk over `TraceLink` + movements, depth limit 10, cycle-safe.
- Recall view with export (customer list for a supplier batch).
- Reversal UX for issue, return, receipt and close, following the dependency rules in §4.12. When a reversal is blocked, the UI names the blocking document and links to it. Reopen of a CLOSED WO (MANAGER+, approval if the period is soft-closed).
- **Tests:** two-level trace; every row of the §4.12 table (allowed and blocked); reverse receipt 1 while receipt 2 exists → blocked; reverse an issue after a receipt absorbed its cost → blocked; reopen → reverse → re-close round trip balances; performance budget on the slow fixture.

#### MFG-37 Additional cost per batch or unit (3 d, mig; rev 2, pulled forward from Phase 5)
- **Why now:** Tally, Busy and Vyapar all let a maker add expenses (grinding, packing, labour) to a production entry. Waiting for Phase 5 would block adoption.
- `BomAdditionalCost` rows on the BOM revision (label, PER_UNIT or PER_BATCH, amount, absorption account), snapshotted to the WO, editable on quick entry and on the final receipt.
- Absorbed at receipt: Dr 1450 / Cr "Manufacturing expenses absorbed" (new chart account; pick a free code in `_ensure_chart`). Included in `estimated_unit_cost` and in the pool.
- Gate: behind `MFG_COSTING_GL`, but this narrow piece gets its **own CA review in Phase 1** (QOS item), so it can be switched on at the Phase 1 release. Standard costing, multi-element rates and revaluation stay in Phase 5 (MFG-28 migrates these rows into `BomCostRate`).
- **Tests:** per-batch amount scales with WO qty ÷ `output_qty`; JE balances; flag off → no absorption and no field in the API.

**Phase 1 exit:** golden journeys 1 and 2 green under WAVG and FIFO; CA review of MFG-37 and of the §4.14 receipt costing recorded; 30-day simulation script (seeded daily production for 30 days) with all invariants green; Postgres lane green; staging smoke; one pilot enabled on staging with real-shaped data.

### Phase 2 — Planning (flag `MFG_PLANNING`)

#### MFG-14 Multi-level BOM (6 d)
- `explode(product, qty, on_date)` iterative, using `resolve_bom` per level; phantom handling (explode through, never stocked); where-used; cost roll-up (latest FIFO, moving average or standard; method chosen per call).
- Release option "create child WOs for short sub-assemblies" (linked by `parent_work_order`, due date = parent planned start − lead time).
- **Tests:** 4-level fixture; phantom; cycle across levels refused; roll-up equals the manual sum.

#### MFG-15 Can-I-make and shortages (4 d)
- Per WO: required, issued, reserved, available, short per component (alternates considered, MFG-18). Across open WOs by due date (first-come allocation). "Max producible" per product.
- **Tests:** allocation order by due date; alternates fill shortage.

#### MFG-16 MRP-lite (8 d, mig)
- `MrpRun` (Celery for large tenants): demand = open SO lines (undelivered) + released / in-progress WO remaining + safety stock (`WarehouseReorderLevel`); supply = on hand − reserved + open PO qty + open WO output; net by date bucket (day); lead time from `WarehouseReorderLevel.lead_time_days` (fallback product or supplier default); lot-for-lot (minimum order qty later).
- Output lines: PURCHASE (preferred supplier from the last PO / GRN) or MAKE (multi-level). Convert: purchase lines grouped by supplier → `PurchaseOrder` drafts; make lines → draft WOs. Run is read-only until converted; a re-run supersedes.
- **Tests:** table-driven netting cases; lead-time offset; conversion idempotent; performance on the slow fixture.

#### MFG-17 Make-to-order and ATP (5 d)
- "Create WO" from SO lines (pegging fields); SO detail shows production status and expected date; FG receipt can reserve to the pegged SO line; ATP by date = on hand − reserved + planned receipts.
- **Tests:** pegging survives partial receipts; ATP numbers; SALES_STAFF sees status only.

#### MFG-18 Alternates (2.5 d)
- Alternate groups with priority on BOM lines; issue and shortage pick by priority when the primary is short (manual override allowed); variance tagged "substitution".

#### MFG-19 Production board (4 d, web-heavy)
- List and kanban by status with due-date risk (late, due ≤ 2 days, short material), drag to change priority (POST action, audited), filters. No capacity.

**Phase 2 exit:** golden journey 3 green; MRP performance target met; pilot shortage list validated by hand on 3 WOs.

### Phase 3 — Quality (flag `MFG_QUALITY`)

#### MFG-20 Batch quality status (4 d, mig)
- `BatchLot.quality_status`; product option "receive into quarantine". One check in `InventoryService` outbound paths (sale, challan, issue, transfer out): a non-RELEASED batch is refused with `MFG_BATCH_ON_HOLD` when the flag is on. FEFO skips non-released lots. Status changes audited.
- **Tests:** every outbound path blocked; FEFO skip; flag off = no behaviour change.

#### MFG-21 Inspection templates and records (9 d, new app + mig)
- Templates per product or category and stage; inspections from **draft** GRN lines (incoming, default) and production receipts (final); the template is snapshotted into the inspection; numeric results auto-evaluate against min / max.
- **GRN flow per §4.16:**
  - **Default:** inspect on the draft. The decision writes `quantity_accepted` / `quantity_rejected` and GRN complete is blocked until an inspection exists.
  - **"Receive into quarantine" products:** the inspection runs after complete. Pass releases the batch. Fail goes to a purchase return (existing flow) or to the scrap godown through the IDR-02 stock-loss service. Partial pass splits by transfer.
- **Tests:** auto-evaluation; GRN complete blocked without inspection; draft decision sets accepted / rejected; quarantine pass, fail and partial paths post the right movements and JEs; template change does not alter past inspections.

#### MFG-22 NCR, CAPA light, supplier scorecard (5 d)
- NCR from a failed inspection, a GRN rejection or a customer complaint (`complaints` link); workflow OPEN → ACTION → VERIFIED → CLOSED; attention code when overdue. Scorecard: rejection %, on-time % (PO due vs GRN date), NCR count per supplier and period.

#### MFG-23 Certificate of analysis (2 d)
- Printable CoA per FG batch from its final inspection (company letterhead template); attach to invoice email optionally.

**Phase 3 exit:** golden journey 4; invariant `no_hold_batch_outbound`; Hindi review of quality screens.

### Phase 4 — Job work, India (flag `MFG_JOB_WORK`; CA review before release)

#### MFG-24 Job work OUT (12 d, new app + mig)
- **Godown.** A job-worker godown is auto-created per supplier (`Warehouse.kind=JOB_WORKER`). It is excluded from sale, count and reorder pickers by `selectable()` (landed in MFG-02).
- **Send (challan).** `JobWorkOrder` → `JobWorkChallan` posts TRANSFER_OUT from own godown and TRANSFER_IN into the job-worker godown (own stock, still valued).
  - **Cost rule:** the TRANSFER_IN is posted with the TRANSFER_OUT movement's **stamped** cost (WAVG average consumed, or FIFO peels), never 0. This avoids the legacy zero-cost TRANSFER_IN path that `_replay` special-cases.
  - Tested under both valuation methods; challan line `unit_cost` stores the same number.
  - Challan print with the required particulars. E-way bill through the existing e-way service with sub-supply type Job Work (**verify** the code value in the e-way integration).
- **Direct from supplier → job worker (ITC-04 Table 4):** a GRN may be completed straight into a job-worker godown; this auto-creates a challan line with `origin = DIRECT_FROM_SUPPLIER` and the supplier invoice reference.
- **Receive (`JobWorkReceipt`).** Every line must settle against challan lines through `JobWorkSettlement` (FIFO auto-allocation, user override). Line kinds:
  - **PROCESSED:** consumes the settled input in the job-worker godown (MANUFACTURE_ISSUE there) and receives the output into own godown. Cost = consumed stamped cost + job charges when invoiced.
  - **UNPROCESSED_RETURN:** a transfer back at the stamped cost.
  - **SCRAP_RETURNED:** a receipt at recovery value.
  - **SCRAP_RETAINED:** the scrap stays with the job worker. A movement out of the job-worker godown (reference `jobwork_scrap_retained`, registered in `costing_refs`) records it, with the JE to process loss or to the linked WO's WIP. This keeps `jobworker_stock_matches_open_orders` true.
  - **SENT_TO_OTHER_JOB_WORKER (ITC-04 5B):** a transfer between job-worker godowns with a new challan.
  - **SUPPLIED_FROM_JOB_WORKER (ITC-04 5C):** a sale invoice from the job-worker godown, allowed only when the job worker's premises are recorded as the principal's additional place of business, or the job worker is registered (company + supplier flags). Otherwise refused with `JW_DIRECT_SUPPLY_NOT_DECLARED`.
- **Job charges.** A purchase invoice line (SAC 9988) linked to the order, capitalised to WIP or FG, or to variance if the goods are already sold.
- **Ageing.**
  - Measured **per challan line** from its date, net of settled qty.
  - Attention codes at 300 days (inputs) and 1,000 days (capital goods); thresholds in settings.
  - A deemed-supply report lists overdue lines with the original challan number and date.
- **Tests:**
  - send and return cycles, partial, FIFO settlement with override;
  - stamped cost carried on TRANSFER_IN (WAVG and FIFO); retained-scrap invariant;
  - direct supplier → job worker; job worker → job worker; direct supply refused when not declared;
  - ageing per challan line; e-way payload; balance per job worker.

#### MFG-25 ITC-04 (6 d)
- Period by turnover rule (half-yearly above ₹5 crore, annual otherwise; threshold in settings).
- **Table 4** (goods sent) from challan lines, flagging DIRECT_FROM_SUPPLIER.
- **Tables 5A / 5B / 5C** (received back / sent to another job worker / supplied from the job worker's premises) from settlement rows. Each row carries the **original challan number and date** from the settled challan line (deterministic, no heuristics).
- Export in the offline-utility format (**verify** the current template before building); `Itc04Filing` record with status; attention reminder before 25 Oct and 25 Apr.
- **Tests:** period selection; every 5A / 5B / 5C row traces to a challan line; totals reconcile to challans; export snapshot test.

#### MFG-26 Job work IN, as the job worker (9 d)
- Principal-material ledger (quantity only) per principal and item. It records the inward challan, the return challan and the balance and ageing per principal.
- **Mixed WO (rev 2):** one job-work-IN WO can combine two kinds of line:
  - **`principal_supplied=True`:** drawn from the `PrincipalMaterial` ledger at ₹0, never in WAVG, FIFO or GL;
  - **`principal_supplied=False`:** the job worker's **own** chemicals and consumables, issued through `InventoryService` into WIP like any issue.
  On completion the own-material cost goes to **COGS of the job-charge service** (Dr COGS / Cr 1450). It is not capitalised into stock, because the processed goods belong to the principal.
- The job-charge invoice (SAC 9988) goes through the normal sales invoice, linked to the WO so margin = charges − own consumables.
- **Tests:**
  - principal material never appears in valuation, GL or stock reports;
  - own consumables are costed and expensed under WAVG and FIFO;
  - the `principal_material_non_negative` invariant holds;
  - full cycle with a mixed WO.

#### MFG-27 Operation-wise subcontracting (deferred to Phase 6 with routing; 4 d)

**Phase 4 exit:** golden journey 5; CA sign-off on job-work treatment (QOS item); ITC-04 export checked against one real past period from the pilot.

### Phase 5 — Costing (flag `MFG_COSTING_GL`; CA sign-off before default-on)

#### MFG-28 Conversion cost absorption (4 d, mig)
- `BomCostRate` on the revision (labour, overhead and machine elements; per unit, per batch, later per work-centre hour). It generalises MFG-37's `BomAdditionalCost` and a data migration moves those rows across. Absorbed at receipt (Dr 1450 / Cr absorbed accounts); included in the cost pool and in `estimated_unit_cost`. Chart accounts added in `_ensure_chart`.

#### MFG-29 Standard cost and variances (8 d, mig)
- Optional per product; when on, FG is received at standard and differences go to price / usage / yield / absorption variance accounts. Revaluation run at period end (preview → post).

#### MFG-30 Cost and profit reports (5 d)
- Planned vs actual per WO and batch; yield and wastage; product / batch / customer / job profitability using FG layer cost in COGS (reuse `reporting.InvoiceProfitSnapshot` where it fits; **verify**).

#### MFG-31 Scrap and by-product sale (2 d)
- Scrap register; sale through a normal invoice with the scrap HSN; recovery policy (credit to WIP of an open WO, or to income) as a setting.

#### MFG-32 Period-end reconciliation (4 d)
- GL 1450 vs WIP subledger, GL 1400 vs valuation split by `mfg_role`, job-worker stock, principal material; drill-down; hooked into the books-health and year-close checks.

**Phase 5 exit:** golden journey 6; one closed pilot month reconciled; CA sign-off recorded.

### Phase 6 — Factory depth (flag `MFG_SHOP_FLOOR`; start only with a named pilot)

| WP | Summary | Effort |
|---|---|---|
| MFG-33 | Work centres and routing on the BOM revision; cost per hour feeds MFG-28 | 8 d |
| MFG-34 | Job cards per operation, start / stop / qty / reject, downtime reasons; shop-floor PWA screen; offline; operator PIN after security review (D-10) | 12 d |
| MFG-35 | Infinite-capacity load view per work centre per day | 4 d |
| MFG-36 | Machine master, preventive schedule, breakdown log | 5 d |
| MFG-27 | Operation-wise subcontracting (from Phase 4) | 4 d |

### Cross-cutting

| WP | Contents | Effort | When |
|---|---|---|---|
| MFG-X1 | Excel BOM import through `backend/imports` (header, lines, outputs, multi-level by product code, dry-run preview with row errors); exports of WOs, registers, variance; WO, issue-slip and batch-label print | 6 d | Phase 1 (BOM import), rest per phase |
| MFG-X2 | Reports pack per phase; attention codes `WO_LATE`, `WO_SHORTAGE`, `WIP_STALE`, `BATCH_ON_HOLD`, `NCR_OVERDUE`, `JOBWORK_AGEING`, `ITC04_DUE` added to `KNOWN_CODES` with actions | 2 d per phase | each phase |
| MFG-X3 | en + hi strings, context help, Hindi human review (QOS) | 1.5 d per phase | each phase |
| MFG-X4 | Invariants (§5), guard against direct balance writes (R-1), Postgres race suite, golden E2E, 30-day simulation script, slow-fixture budgets | 8 d spread | each phase |
| MFG-X5 | RLS catch-up migration per phase (next free `core` migration after `0063`), tenant backup coverage, OpenAPI and web types, demo-data commands, QOS items for sign-offs (next free IDs after QOS-0139, **verify**) | 1.5 d per phase | each phase |

---

## 8. Schedule, dependencies and critical path

Ideal days (one engineer working with Claude); calendar ≈ ideal × 1.4 for reviews, sign-offs and pilot feedback.

| Phase | WPs | Ideal days (rev 2) | Calendar (approx.) |
|---|---|---|---|
| 0 | MFG-00…05 | 28 (was 24: WAVG stamping, ref registry, godowns, cost cache) | 6–7 weeks |
| 1 | MFG-06…13, MFG-37 + X1 (BOM import) + X2–X5 share | 49 (was 45: MFG-37, rework, reversal rules) | 10–11 weeks |
| 2 | MFG-14…19 + share | 33 | 6–7 weeks |
| 3 | MFG-20…23 + share | 24 (was 23: GRN flow) | 5 weeks |
| 4 | MFG-24…26 + share | 31 (was 26: settlement, direct dispatch, 5A/5B/5C, mixed WO) | 6–7 weeks |
| 5 | MFG-28…32 + share | 27 (was 28: part moved to MFG-37) | 5–6 weeks + CA review |
| 6 | MFG-27, 33…36 | 33 | pilot-gated |

Total ≈ 225 ideal days (rev 1: ≈ 212).

**Dependencies**
- MFG-00 → everything (permissions and flags).
- MFG-01 → MFG-06, MFG-08 (CONSUMED status, reversal type).
- MFG-02 → MFG-06…12 (statuses, issue mode).
- MFG-03 → MFG-04 → MFG-08, MFG-12, MFG-14, MFG-16.
- MFG-06 → MFG-07, MFG-08 → MFG-09, MFG-11, MFG-12, MFG-13.
- MFG-10 → MFG-15 → MFG-16 → MFG-17.
- MFG-20 → MFG-21 → MFG-22, MFG-23.
- MFG-24 → MFG-25; MFG-26 independent of MFG-24 (after MFG-06).
- MFG-08 → MFG-37 → MFG-12 (quick entry carries the additional cost); MFG-37 → MFG-28 → MFG-29; MFG-09 → MFG-32.
- MFG-01(a) WAVG stamping → every posting WP (cost source of truth).
- MFG-02 `selectable()` → MFG-20, MFG-24 (new godown kinds).
- MFG-21 GRN flow → MFG-24 direct supplier → job-worker GRN.
- MFG-33 → MFG-34, MFG-35, MFG-27.

**Critical path:** MFG-00 → 01 → 02 → 03 → 04 → 06 → 08 → 37 → 09 → 12 → (Phase 1 exit) → 14 → 15 → 16.

**Can run in parallel** (separate sessions; different files):
- MFG-05 alongside MFG-03 / 04;
- MFG-X1 BOM import alongside MFG-06 / 07;
- Phase 3 (quality app) alongside Phase 2 once MFG-08 exists;
- MFG-26 alongside MFG-24.

---

## 9. Rollout, pilots and rollback

**Environments:** local → staging (`bizboard-staging`, tag-based deploy) → pilot tenants → general.

**Per phase:**
1. Merge with flags off. Deploy to staging, run smoke, golden E2E against staging.
2. Enable for the internal demo tenant; then 1–3 pilots (feature plan §7 suggests spice / food, job-work textile or fabrication, assembly).
3. Watch for 2 weeks: invariant job (nightly, all flagged tenants), error codes by frequency, `ShopFloorEvent` usage, support tickets.
4. Widen after the checklist passes (zero invariant breaks, no data fixes needed, sign-offs done).

**Legacy tenants:** keep AUTO_AT_RELEASE; offer the switch in settings only when no WO is RELEASED (switching mid-flight is refused).

**Rollback:**
- Flags off restores the old UI and APIs; data stays.
- Migrations are additive, so code rollback to the previous tag is safe while new columns are unused.
- Documents posted under a new flow are not deleted on rollback; they reverse through the normal reversal path if needed.
- Before each migration-carrying release, take a backup with the existing encrypted backup flow and rehearse restore on staging.

---

## 10. Risk register

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| K-1 | Cost split or variance mis-states stock or COGS | M | H | Pure functions with property tests; invariants; `MFG_COSTING_GL` off until CA sign-off | Eng + CA |
| K-2 | BOM revision migration breaks a tenant with messy data | M | M | Dry-run report command; separate constraint migration; rehearsal on a staging copy | Eng |
| K-3 | Serial data migration mislabels history (D-2) | M | M | Only convert rows with a provable WO reference; log the rest; no deletes | Eng |
| K-4 | Deadlocks under concurrent issue / sale | L | H | Deterministic lock order; Postgres race suite | Eng |
| K-5 | Job-work GST reading wrong | M | H | CA review; thresholds in settings; ITC-04 checked against a real past period | Founder + CA |
| K-6 | Shop floor finds it too heavy | M | H | Quick entry in Phase 1; usability session with a real operator before Phase 1 exit | Founder |
| K-7 | Scope creep into Phase 6 | H | M | Phase 6 needs a named pilot; decisions logged | Founder |
| K-8 | Long-lived uncommitted work lost | M | H | Branch per phase, commit per WP (section 6.1) | Eng |
| K-9 | MRP slow on large tenants | L | M | Celery task, per-run caching, slow-fixture budget | Eng |
| K-10 | Movement-type change (D-11) breaks reports | M | M | Grep every `MovementType` consumer in MFG-01; report tests | Eng |
| K-11 | WAVG stamping in `post_movement` (MFG-01a) changes a path every module uses | M | H | Own commit and review; full inventory suite + `rebuild_running_cost` value-drift check; staging soak before Phase 0 exit | Eng |
| K-12 | Estimate-then-true-up costing surprises users (last batch differs) | M | M | Help text; tolerance setting; CA review in Phase 1; variance report | Eng + CA |
| K-13 | Back-dated entries cost at today's pool | H | L | Documented rule (§4.13), window + approval, UI notice; same as sales today | Founder |

---

## 11. Open decisions (blocking map)

From the feature plan §9. A WP cannot start until its blocking decisions are answered.

| Decision | Recommendation (feature plan) | Blocks |
|---|---|---|
| D-1 BOM version model | Effective-dated revisions, one default per product, customer-specific allowed | MFG-03 |
| D-2 Release behaviour for existing tenants | New: SEPARATE; existing: AUTO_AT_RELEASE until switched | MFG-02 |
| D-3 Backflush default | Off; per line; quick entry always backflushes | MFG-04, MFG-08 |
| D-4 Costing default | Actual + rate-based conversion; standard opt-in | MFG-28, MFG-29 |
| D-5 Job work scope | OUT and IN in Phase 4; pull forward if a pilot is a job worker | Phase 4 order |
| D-6 Zero-cost completion (DEF-1) | Refuse | MFG-01 |
| D-7 Units | Line unit = base or alternate only | MFG-04 |
| D-8 Variants | Out of scope | — |
| D-9 Pricing / packaging | Founder call | MFG-00 entitlements |
| D-10 Operator PIN | Phase 6 after a security review | MFG-34 |
| D-11 New movement types | Add MANUFACTURE_RETURN, MANUFACTURE_REVERSAL; reuse transfers for job work | MFG-01, MFG-07 |
| D-12 Partial-receipt costing (rev 2) | Provisional at frozen estimate, capped at WIP; final receipt takes the residual; GL variance only on short-close, tolerance or standard (§4.14) | MFG-08 |
| D-13 Back-dating (rev 2) | Live posting-order cost and stock; window 7 days, older needs approval (§4.13) | MFG-06, MFG-12 |
| D-14 Incoming inspection model (rev 2) | Inspect on the draft GRN by default; per-product "receive into quarantine" option (§4.16) | MFG-21 |
| D-15 Job-work direct dispatch (rev 2) | Support supplier → job worker and job worker → job worker; job worker → customer only when declared (§MFG-24) | MFG-24, MFG-25 |
| D-16 WAVG cost stamping (rev 2) | Stamp the consumed pool average on outbound WAVG movements in `post_movement` (shared path) | MFG-01 |

**Before Phase 0 starts:** D-1, D-2, D-6, D-11, D-16 (and D-9 if entitlements change).
**Before Phase 1 starts:** D-3, D-7, D-12, D-13.

---

## 12. Execution record

Built 2026-10-20 and 2026-10-21 on branch `feat/mfg-p0-foundations`. Nothing is committed; the work sits in the working tree
with the other uncommitted programmes. The record is by phase, not by WP: one author built the phases in order and the
tests are shared between WPs.

| Phase | What landed | Where | Verified by |
|---|---|---|---|
| 0 Foundations | DEF-1..3 fixed; movement types and the shared costing-reference registry; godown kinds (job-worker, quarantine) and `selectable(purpose)`; batch quality status; serial CONSUMED state; reservation by document; trace links; BOM revisions; settings; RLS catch-up migration `core 0064`; invariants | `inventory/`, `masters/`, `manufacturing/models.py`, `manufacturing/services/legacy.py`, migrations `inventory 0033`, `masters 0034`, `manufacturing 0011-0014`, `core 0064` | `test_mfg_phase0.py` under WAVG and FIFO; `test_rls_coverage.py`; `makemigrations --check` clean; full migration chain on a fresh Postgres |
| 1 Execution core | Issue, return and receipt documents with reversal order rules; estimate-then-true-up receipt costing (4.14); co/by-product and scrap; phantom kits; alternates; quick production; recipe import and export; genealogy | `manufacturing/services/{issue,receipt,flow,allocation,reservation,quick_entry,bom,bom_import,trace}.py`, `views_docs.py` | `test_mfg_documents.py`, `test_mfg_quick_import_trace.py`, both valuation methods |
| 2 Planning | Explosion, where-used, availability, can-make, available-to-promise, shortages, MRP-lite with conversion, make-to-order from a sales order, board | `services/planning.py`, `views_planning.py` | `test_mfg_planning.py` |
| 3 Quality | Templates, inspections, results, decisions that move stock, batch holds enforced in the ledger and FEFO, NCR with follow-up, supplier scorecard, certificate page, GRN inspection on the draft | new app `quality` | `test_mfg_quality.py` |
| 4 Job work | Job-work orders, challans with cost carried, receipts and settlements, ageing against the time limits, direct-from-supplier challan, customer's goods book (never valued), ITC-04 tables, filing log | new app `jobwork` | `test_mfg_jobwork.py` |
| 5 Costing | Journals for WIP, absorption, variance and scrap; reversal; standard cost on receipts; reports (WIP, cost, variance, yield, consumption, output, on-time, scrap, profitability, reconciliation) | `accounting/services.py`, `services/reports.py` | `test_mfg_costing.py`; invariant `wip_matches_gl` |
| 6 Factory depth | Work centres, routing, job cards with time and cost, downtime, load, utilisation, machines and maintenance, operators with PIN and lock-out, the tablet API | `services/shopfloor.py`, `views_shopfloor.py` | `test_mfg_shopfloor.py` |
| X1-X5 | Attention rows (8 codes); print sheets; guard against direct stock writes; Postgres race suite; 30-day simulation and demo seeding; tenant backup, wipe and restore for every new table; OpenAPI and web types regenerated; QOS items | `manufacturing/attention.py`, `printing.py`, `demo.py`, `management/`, `accounts/mfg_backup.py`, `scripts/ci_gates/guards/guard_no_direct_stock_writes.py`, `qos/backlog/QOS-0141..0148` | `test_mfg_attention.py`, `test_mfg_backup.py`, `test_mfg_concurrency_postgres.py`, `test_mfg_demo_commands.py`, `test_mfg_web_contract.py` |
| Web | Quick production, recipe editor with versions and routing, work order detail (material, returns, output, job cards, print), planning, quality, job work, shop floor, reports with batch trace and standard costs, settings with recipe import, the tablet page `/floor`; role-based menu; Hindi and English; help pages | `web/src/api/mfg.ts`, `web/src/pages/manufacturing/` | tsc, eslint (0 errors), production build, vitest (api, permissions, menu, page tests, i18n parity and key usage, context help), Playwright journeys against the live backend |

### Second pass, 2026-10-21: what the first record listed as open or partial

The first record left five buildable things open. They are now built, tested and closed (QOS-0146, 0147, 0148):

| What | How it works | Where | Verified by |
|---|---|---|---|
| Standard-cost revaluation run (QOS-0146) | Preview lists every lot that would change; posting takes each lot out and back in through the stock ledger at the standard (so running cost and FIFO layers agree), and one journal moves the difference between Inventory 1400 and Manufacturing Variance 5420. Scrap and job-worker godowns and serial-tracked items are left out. Reversal as a whole, refused once a lot has moved. | `services/revaluation.py`, `views_revaluation.py`, models `StandardRevaluation[Line]`, `core 0065` (RLS), backup spec | `test_mfg_revaluation.py` (both valuation methods, invariants after each step), a Postgres race test, web panel tests |
| Operation-wise subcontracting (QOS-0147) | A subcontract job card raises the job-work order and challan with the step material; issuing the challan starts the step; the return receipt writes quantity and charge back to the card and drafts the issue into the work order; the order cannot finish or be cancelled while a step is out; closing an empty job-work order re-opens the step. The charge is in the cost of the returned goods, so it is never absorbed twice. | `services/subcontract.py`, hooks in `jobwork/services/out.py`, `JobCard.outside_cost`, `JobWorkOrder.work_order_id/job_card_id` | `test_mfg_subcontract.py` (both methods), web dialog tests |
| Extra-material approval request (was deviation 2) | A floor user keeps the draft and asks; a manager approves (which posts it) or turns it down with a reason; the draft can be asked about again. | `services/issue.py` (`request_approval`, `decide_approval`), `MaterialIssue.approval*`, work order Material tab | `test_mfg_documents.py`, `test_mfg_web_payloads.py`, web workflow tests |
| Tablet works without a connection (QOS-0148) | Taps are kept on the tablet with the time of each tap and a key, sent in order when the connection is back; the server replays by key, so a resend is never applied twice; a time older than a day or in the future is not believed. | `web/src/api/mfg.ts`, `FloorTabletPage.tsx`, `shopfloor.when`, tablet views | `test_mfg_shopfloor.py`, `mfgTablet.test.ts` |
| Batch label, work order list export, quality and job-work browser journeys (QOS-0148) | Label page per posted receipt; CSV of the work orders on screen (costs only for cost roles); two more Playwright journeys. | `printing.batch_labels`, `WorkOrderViewSet.export`, `e2e-golden/manufacturing-golden.spec.ts` | `test_mfg_left_outs.py`, the five browser journeys |

### Test results (2026-10-21)

Final figures after the second pass:

- **Backend:** The whole backend suite on SQLite (3 workers, `--nomigrations`): 5,720 passed, 90 skipped, 8 failed. Of the 8, three were real faults this work caused and are fixed (an error code without a description; the architecture note not naming the two new apps; 41 new manufacturing routes the tenant-isolation matrix could not probe, now covered by a hand-written cross-tenant test that tries every one with another company's ids), four are timing tests that pass alone (15 passed) and fail only when the machine is loaded, and one invoice-PDF test needs the tax-rate catalogue that a data migration seeds, so it cannot pass under `--nomigrations`. After the fixes the manufacturing, FIFO and serial, tenancy, architecture and RLS-coverage suites together: 490 passed, 7 skipped (the skips are the PostgreSQL-only race tests). `ruff` clean; `makemigrations --check` clean; all CI guards pass.
- **PostgreSQL 17:** The 431 tests in the manufacturing files, including six race tests (the new one posts the same revaluation twice at once), pass on PostgreSQL 17. The first run found 15 failures, all fixed: a row lock over a join to a nullable column in the new subcontract code (the same class of fault as before) and the undocumented error code; the files were re-run and 58 passed. The whole migration chain (546 migrations) applies on an empty PostgreSQL database; the new tables are under forced row-level security there. A live check as a non-superuser database role with row-level security on: an owner sees only their own company, the revaluation preview and post, the approval request and the replayed tablet tap all work, and another company's job card is refused. The 30-day simulation ran clean on that database (780 packs, 40 work orders, 2 reversals).
- **Web:** Type-check clean; eslint 0 errors; production build succeeds; the whole unit suite is 369 files and 2,916 tests. On the full run 14 tests in six sales, accounting and support files timed out because the machine was loaded (none of them touch Manufacturing); run alone those six files pass (213 tests).
- **Browser (Chrome, live backend):** five journeys pass: a production day to the tablet, the work order lifecycle with the print sheet, accessibility checks on four screens, the quality hold and release (final-check list, batch held, a bad weight fails, a good weight passes and releases the batch), and job work out and back (challan, held by the job worker, finished work and an untouched return, order closed). The job-work journey found a real fault, now fixed: after a return was recorded, the "who has what" list kept showing the goods because the other job-work lists were not refreshed.

First record (kept for the history):

- **New backend tests: 377 across 14 files; all pass on SQLite and all pass on PostgreSQL 17**, including five
  race tests (the same issue posted twice, the same output received twice, one receipt reversed twice, one challan issued twice,
  one job card started twice). The new files together with the regression suites around the touched areas (RLS coverage, invariants, stock flow,
  FIFO and serial, inventory, purchases, backup, attention, insights) ran as one: 946 passed, 6 skipped. `ruff` clean; `makemigrations --check` clean.
- **Migrations:** the whole chain applies on a fresh PostgreSQL 17 database and on a fresh SQLite one, and the new migrations apply
  on a copy of the populated development database (which held no recipes or work orders, so the data migration is still
  unproven on real manufacturing data; see QOS-0145). `manage.py check_invariants` is clean for all 648 development companies.
- **Row-level security, live:** as a non-superuser role with RLS on, a signed-in owner sees only their own recipes and orders,
  quick production posts, the PIN-signed tablet signs in and works, a bad token and another company's code are refused.
- **Web:** type-check clean, eslint 0 errors (24 older warnings), production build succeeds, the full unit suite passes
  (367 files, 2901 tests). Browser journeys in
  `web/e2e-golden/manufacturing-golden.spec.ts` ran against the live backend in Chrome: a production day through the menu,
  the work order, recipe and every sub-module screen; a work order through issue, return, final output and close with the print
  sheet; the tablet with a wrong then right PIN; axe accessibility checks on four screens. All pass.
- **CI guards:** all pass; the new guard fires on a bad tree in `--selftest`.
- **Simulation:** `manage.py simulate_manufacturing_month` ran 30 days (780 packs, 40 work orders, 2 reversals, no refusals) and
  the invariants held after every day.

### Faults found while verifying (all fixed, each now has a test)

1. A row lock taken over a join to a nullable column failed on PostgreSQL only (MRP conversion and the job-work settlement).
2. The tablet has no account, so under row-level security its sign-in and token lookups would have found nothing; both now name
   the company for the session.
3. The new-inspection screen sent a source type the server does not accept, and the new quality-problem screen the same.
4. "How many can I make" answered 0 for any recipe that uses a kit, because it looked for the kit in stock; it now looks through it.
5. Quick production kept one idempotency key after the form changed, which the server correctly refuses; the key now changes
   with the request.
6. Default dates came from UTC (yesterday for the first five hours of an Indian day) and the financial-year start from the
   calendar year; both now follow India time and April.
7. The trace picker searched lots through an endpoint that ignored the search text and needs inventory rights; there is now a
   read-only batch search open to every manufacturing role.
8. A report page showed a date as money.
9. A test depended on the time of day (it failed between midnight and 2 am).
10. (Second pass) The new subcontract code took a row lock over a join to the nullable routing step, which PostgreSQL refuses;
    found by the PostgreSQL run, fixed with a lock on the card row only.
11. (Second pass) After a job-work return was recorded, the "who has what" and open-quantity lists kept the old numbers because
    only the list being edited was refreshed; found by the new browser journey. All job-work lists now refresh together.
12. (Second pass) 41 new manufacturing routes were missing from the tenant-isolation matrix's ledger, and the architecture note did
    not name the `quality` and `jobwork` apps; found by the whole-suite run. Both fixed, with a hand-written cross-tenant test.

### Code review, 2026-10-21 (findings and fixes)

A line-by-line review of the manufacturing, job-work and quality code found these; each is fixed and has a test in
`backend/tests/test_mfg_review_fixes.py` (or the file named):

1. **Unreadable input answered 500.** `?product=abc`, a bad date, `days=many`, a text quantity on the tablet, a non-numeric
   `horizon_days` and similar raised an unhandled `ValueError` or `InvalidOperation`. A shared `BadInputIs400` mixin on every
   manufacturing, job-work and quality view now answers 400 with `MFG_BAD_INPUT`.
2. **Spreadsheet formula injection.** The work order export, the report CSVs, ITC-04 and the recipe export wrote names and batch
   numbers raw; a product called `=HYPERLINK(...)` ran in Excel. They now go through `core.csv_utils.csv_safe`.
3. **A re-pricing raised "Large stock adjustment" alerts** (it takes a lot out and back in as adjustments). The detector now
   leaves those movements out.
4. **Server-local dates.** `date.today()` and `timezone.now().date()` gave the wrong day for the first five and a half hours of an
   Indian day (ATP, ITC-04 due list, mark-filed, release date on the one-step flow); all use `timezone.localdate()`.
5. **Tablet sign-in counted wrong PINs without a lock and lost the count on refusal risk.** The count is now taken under a row lock
   in its own transaction, kept when the attempt is refused, and an unknown code takes the same time as a wrong PIN.
6. **Job work receipts accepted a negative charge, loss or rate**, and scrap worth more than the material produced goods with a
   negative value. Both are refused (`JW_BAD_QTY`, `JW_NEGATIVE_VALUE`).
7. **Inspection results accepted `NaN` and `Infinity`**, which broke the pass/fail check; and a failed lot could carry an accepted
   quantity although all of it goes to scrap. Both fixed.
8. **Batch labels printed for a draft or reversed receipt**; only a posted receipt prints now.
9. **A manager posting a draft that someone had asked about** left the request looking open; the post now records the approval.
10. **Tenant restore** would have copied the user ids of an approval into the new company; they are skipped.
11. **Tablet queue:** another operator's waiting taps held back this operator's taps; each operator's queue is now separate.
12. **Outside-step material defaults** listed the same material twice if a recipe used it twice; they are added up.

### Deviations from this plan

1. **Default issue mode stays "material and output together".** The plan (D-2) asked for the separate documents on new
   companies. The default was kept until the screens shipped; they now ship, so flipping it is a one-line decision for the
   founder (`MfgSettings.default_issue_mode`), left as it is so that no company changes behaviour without being asked. The owner
   switches in Manufacturing settings; orders already made keep the way they were made.
2. **Extra material has its own approval request on the issue document** (request, approve, turn down), not a generic
   `ApprovalRequest` object. An issue above the planned quantity plus the allowed percentage still needs an owner or manager to post.
3. **Error codes live in `manufacturing/error_codes.py`** (with a test that every code used is described) rather than in the
   general help-code registry.
4. **Hindi text was written by the engineers** and is marked for native review (QOS-0143).

(Two earlier deviations are gone: extra material now has a real approval request, and the batch label is built as a third print page.)

### Left open (each is tracked as a QOS item, none is a silent gap)

Everything that can be built is built. What remains needs a person, a real device or real data, and nothing else:

| What | Why it is open | Item |
|---|---|---|
| CA sign-off on production cost, the journals and the stock revaluation | Needs a chartered accountant; the costing switch is off until signed | QOS-0141 |
| CA review of the job-work rules and ITC-04 | Needs a chartered accountant; the job-work switch is off until signed | QOS-0142 |
| Hindi review | Needs a native speaker | QOS-0143 |
| Shop-floor tablet on a real device, including its offline mode on a real poor connection | Needs a device on a floor | QOS-0144 |
| Migrations on a copy of a real company's data | Needs a real backup | QOS-0145 |

---

## 13. Revision log

### Rev 2, 2026-10-20: review comments applied
Each comment was checked against the code before it was accepted.

| Comment | Verified in code | Change |
|---|---|---|
| 1.1 WAVG is the default; FIFO helpers no-op under WAVG | Yes: `inventory_valuation_method` default `"WAVG"`; `_apply_cost_layers` and `restore_fifo_peels` return unless FIFO; FIFO layers not the pilot model (`core/invariants/inventory.py`). Nuance: under WAVG the outbound movement keeps the caller's pre-lock `unit_cost`, while the pool consumes its own average | R-16, §4.15, MFG-01(a) stamping, both methods in every test, posting map, D-16, K-11 |
| 1.2 Receipt cost split fails on multi-receipt WOs | Yes (arithmetic) | §4.14 estimate-then-true-up rule, MFG-08 rewritten, worked examples as tests, D-12, K-12 |
| 1.3 Hard-coded `reference_type` tuples in `_apply_cost_layers` | Yes | Registry `inventory/costing_refs.py` + guard test (§3.2, MFG-01(b)) |
| 1.4 Job-work transfers: pickers, transfer cost, retained scrap | Yes: `Warehouse.is_system` filtering (~16 sites); `_replay` special-cases zero-cost TRANSFER_IN | `Warehouse.kind` + `selectable(purpose)` in MFG-02; TRANSFER_IN at stamped cost; SCRAP_RETAINED movement; invariant reworded |
| 1.5 D-n used for defects and decisions | Yes | Defects renamed DEF-1…3 here and in the feature plan |
| 1.6 Serial migration lacks an audit trail | Yes: `SerialNumber` has no reference fields; cancel clears `WorkOrderLine.serial_numbers` | MFG-01(d) migration joins RELEASED/COMPLETED WO lines; unmatched rows left SCRAPPED and logged |
| 2.1 Separate RM / FG / scrap godowns | Yes: single `WorkOrder.warehouse` | Line-level source and target godowns, role defaults, `resolve_warehouse()` |
| 2.2 Back-dated production | Yes: live balances and pools (B8-036) | §4.13, R-18, D-13 |
| 2.3 Reversal after later receipts or close | Gap confirmed | §4.12 dependency table, R-17, MFG-13 tests |
| 2.4 Rework BOM collides with the self-cycle check | Yes: `assert_no_bom_cycle` refuses a BOM containing its own FG | `WorkOrder.kind=REWORK` without a BOM; rework qty costed at receipt |
| 2.5 Job-work GST details | Accepted (CA to confirm) | Direct supplier → job worker; 5A / 5B / 5C; `JobWorkSettlement` to challan lines; mixed own and principal lines in job work IN |
| 2.6 Inspection vs GRN stock posting | Yes: GRN posts only `quantity_accepted`, set on the draft | §4.16 (inspect on the draft by default; quarantine option), MFG-21 |
| 3.3 Basic conversion cost too late | Accepted | New MFG-37 in Phase 1 with its own CA review |
| 3.6 WO cost summary cache | Accepted | Cost-summary fields on `WorkOrder` + invariant |

Effort rises from ≈ 212 to ≈ 225 ideal days. No comment was rejected. The reviewer's link
for `GoodsReceipt` pointed at the feature plan; the code location is `purchases/grn_service.py`.

### 12.x Test-depth pass (2026-10-21)
- Manufacturing, job work and quality suites: 619 passed, 12 skipped (SQLite); Postgres concurrency, migration-data, role-matrix and random-invariant files pass.
- Coverage (lines + branches) 92% overall; no file below 90%. CI now enforces a 90% floor for these three apps (`Manufacturing coverage floor` step).
- Web: 380 test files, 3010 tests pass; `tsc -b` and eslint clean. Golden e2e spec has 9 manufacturing journeys.
- Bugs the extra tests found and fixed: stale-WIP attention crash (date vs datetime), IN-direction job-work order could not close, empty recipe could be activated, unit conversion rate 0 accepted, offline tablet queue dropped taps on 409/5xx.
- Known unrelated failure: `test_architecture_doc` fails because the new `agents` app (agentic roadmap work) is not yet named in `docs/architecture.md`.
