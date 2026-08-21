# Phase 5 — Light accounting

This root file is a **pointer stub** (same pattern as Phase 2 / 6). Execute from the canonical doc only.

**Canonical plan:** [`docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md`](docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md)

| What you want | Location |
|---------------|----------|
| Phase 0–2 | [`docs/pilot/`](docs/pilot/) · [`docs/phase1/`](docs/phase1/) · [`docs/phase2/`](docs/phase2/) |
| Phase 3 (payments & bank recon feed) | [`docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md`](docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md) |
| Phase 4 (inventory / COGS inputs) | [`docs/phase4/PHASE_4_INVENTORY_DEPTH.md`](docs/phase4/PHASE_4_INVENTORY_DEPTH.md) |
| **Phase 5 (this)** | [`docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md`](docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md) |
| Phase 6–7 | [`docs/phase6/`](docs/phase6/) · [`docs/phase7/`](docs/phase7/) |

**Start gates:** Phase 0 Go · “documents as truth” still marketing-accurate · **≥ 3 pilots explicitly demand books** (journals / TB / P&L) · Phase 3.2 bank statement import live (bank recon ties to Phase 3) · CA workshop on chart-of-accounts defaults.

**Sequencing:** **5.0** Chart of accounts + document→GL posting rules (derived books) → **5.1** Journal vouchers → **5.2** Trial Balance → P&L → Balance Sheet → **5.3** Bank reconciliation (consumes Phase 3 bank lines) → **5.4** Cost centers (later) → **5.5** Fixed assets (last).

At solo headcount: **~14–20 weeks** for 5.0–5.3; cost centers + fixed assets are **explicitly later** and demand-gated.

**Principle:** Stay “documents as truth”; add books only when pilots demand it. GL is a **projection** of documents (+ sparse journals), never a second editable money truth that can diverge from invoices/receipts.
