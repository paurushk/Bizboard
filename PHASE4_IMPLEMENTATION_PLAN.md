# Phase 4 — Inventory depth

This root file is a **pointer stub** (same pattern as Phase 2 / 6). Execute from the canonical doc only.

**Canonical plan:** [`docs/phase4/PHASE_4_INVENTORY_DEPTH.md`](docs/phase4/PHASE_4_INVENTORY_DEPTH.md)

| What you want | Location |
|---------------|----------|
| Phase 0–2 | [`docs/pilot/`](docs/pilot/) · [`docs/phase1/`](docs/phase1/) · [`docs/phase2/`](docs/phase2/) |
| Phase 3 (payments & cash ops) | [`docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md`](docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md) |
| **Phase 4 (this)** | [`docs/phase4/PHASE_4_INVENTORY_DEPTH.md`](docs/phase4/PHASE_4_INVENTORY_DEPTH.md) |
| Phase 5 (light accounting) | [`docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md`](docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md) |
| Phase 6–7 | [`docs/phase6/`](docs/phase6/) · [`docs/phase7/`](docs/phase7/) |

**Start gates:** Phase 1 stock posting on Complete/Cancel/Return stable · append-only `StockMovement` invariants green · ≥ 1 wholesale/distributor pilot asking for batch or multi-location.

**Sequencing:** **4.0** Multi-warehouse + stock transfer → **4.1** Batch/lot ledger + expiry alerts → **4.2** Valuation (WAVG default; FIFO opt-in) → **4.3** Multi-price lists → **4.4** Serial tracking (demand-gated).

At solo headcount: **~16–22 weeks** end-to-end; **~8–10 weeks** for 4.0+4.1 (unblocks most distributors without valuation/serial complexity).

**Numbering note:** Phase 7 previously sketched “multi-branch / warehouse” as 7.2. **Warehouse depth lives here (Phase 4).** Phase 7 keeps POS / Tally / ecosystem only — see Phase 4 § Plan map.
