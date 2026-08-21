# Phase 2 — GST returns readiness

This root file is a **pointer stub** (same pattern as keeping phase docs namespaced under `docs/`). It is not an archived full plan — unlike [`PHASE1_IMPLEMENTATION_PLAN.md`](PHASE1_IMPLEMENTATION_PLAN.md), which marks a superseded document and points at [`docs/archive/PHASE1_IMPLEMENTATION_PLAN.md`](docs/archive/PHASE1_IMPLEMENTATION_PLAN.md).

**Canonical plan:** [`docs/phase2/PHASE_2_GST_RETURNS_READINESS.md`](docs/phase2/PHASE_2_GST_RETURNS_READINESS.md)

| What you want | Location |
|---------------|----------|
| Phase 0 (pilot hardening) | [`docs/pilot/PHASE_0_IMPLEMENTATION_PLAN.md`](docs/pilot/PHASE_0_IMPLEMENTATION_PLAN.md) |
| Phase 0 Go / No-Go | [`docs/pilot/GO_NO_GO.md`](docs/pilot/GO_NO_GO.md) |
| Phase 1 (CN/DN / document completeness) | [`docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md`](docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md) |
| **Phase 2 (this)** | [`docs/phase2/PHASE_2_GST_RETURNS_READINESS.md`](docs/phase2/PHASE_2_GST_RETURNS_READINESS.md) |
| Phase 2.5 (GSTR-2A/2B reconcile — compliance track) | Deferred from Phase 2 DoD; not Payments Phase 3 |
| Phase 3 (payments & cash ops) | [`docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md`](docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md) |
| Phase 4 (inventory depth) | [`docs/phase4/PHASE_4_INVENTORY_DEPTH.md`](docs/phase4/PHASE_4_INVENTORY_DEPTH.md) |
| Phase 5 (light accounting) | [`docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md`](docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md) |
| Phase 6 (AI differentiator) | [`docs/phase6/PHASE_6_AI_DIFFERENTIATOR.md`](docs/phase6/PHASE_6_AI_DIFFERENTIATOR.md) |
| Phase 7 (ecosystem & scale) | [`docs/phase7/PHASE_7_ECOSYSTEM_SCALE.md`](docs/phase7/PHASE_7_ECOSYSTEM_SCALE.md) |

**Start gates (all required — see canonical § Start gate):** Phase 0 Go · Phase 1 core DoD · CN/DN + CDNR in offline GSTR · CA sign-off on Tax Invoice + Sales CN/DN PDFs.

**Sequencing:** Phase 1 core exit → Phase 2.0 (line HSN/UQC snapshots, rate-wise GSTR-1, Health, periods; **GSP procurement in parallel**) → 2.1 tax modes + GSTIN verify → 2.2 e-Invoice → 2.3 e-Way → 2.4 GSTR-9.

At solo headcount: **~14–18 weeks** end-to-end; **~8–9 weeks** for 2.0+2.1 (highest compliance value without live NIC).
