# Business Logic Review

## Wave 22 (2026-08-06)

FIFO cancel/return/transfer/H9 (717–721); PR serial drop (722); WO lot/serial (723–724); SO convert drops serial (732); price_role dead (728); CRM re-entrant convert (731); no GRN (735).

## Wave 21 (2026-08-05)

BB-000657 price lists FE-only; BB-000659 SO/challan WH; BB-000681 BOM status ignored.

## Wave 20 (2026-08-05)

BB-000648 outstanding-capped CNs; BB-000649 live-master POS on notes.

## Wave 19 missed (2026-08-05)

BB-000608 period close; BB-000615 serial SM; BB-000619 return CN cess.

## Wave 19 (2026-08-05)

WO state machine has no cancel (BB-000565); BOM not snapshotted (BB-000583); CRM is status CRUD (BB-000582); SALE enum overload (BB-000593).


**Date:** 2026-08-02

## Document lifecycle

Draft → Complete → Cancelled / Returned. Stock moves on invoice complete (not challan). Notes are value-only (by design).

## Issues

| Area | IDs / topics |
|------|----------------|
| Credit limit race | BB-000019 |
| Doc number uniqueness | BB-000021 |
| Allocation constraints | BB-000022 |
| Orphan purchase returns | BB-000020 |
| Return+CN double relief | G32 |
| DN cumulative cap | G36 |
| Hard deletes on masters | F97 / medium |
| Negative stock WARN | F25 |
| No SO reservation | F26 |
| H9 price amend semantics | BB-000011 |

## Cross-module dependency risks

1. Completing sales touches inventory + ledger + optional GL + events + PDF task.
2. Failure mid-path relies on atomic blocks — good — but GL optional creates partial truth.
3. Tally import uses special-case complete paths.
4. Insights assistant can propose writes — confirm path must stay allowlisted.

## Score: 5.5 / 10


## Wave 8 (2026-08-03)

Purchase amend / journal RBAC / payment settle paths are business-integrity defects — see BB-000196–200.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
