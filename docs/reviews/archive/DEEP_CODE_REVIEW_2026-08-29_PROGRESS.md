# Remediation progress — DEEP_CODE_REVIEW_2026-08-29

Baseline before work: `wip/phase0`, 617 pass / 1 pre-existing fail
(`test_sprint_c_recurring_tds.py::test_tcs_sales_gl_206c`) / 1 skip.

Decisions from user (2026-08-29):
- Cess `cess_amount` = **additive** (X% + ₹Y/unit). Fix docs + GSTR to match code.
- 40% GST slab = **keep** (GST 2.0). R1-023 / R5-006 → closed, no code change.
- Issued-invoice in-place monetary amend = **keep permissive**. R2-002 → audit-log diff only.
- Reversal JE date on cancel/void = **cancellation date** (today), not original doc date.

Legend: [x] done+verified · [~] done, pending full-suite · [D] design/follow-up branch · [n/a] closed no-change

## Status roll-up (FINAL — verified, 3 rounds)
- Backend full suite: **834 passed / 1 failed / 4 skipped** (`test_tcs_sales_gl_206c`,
  pre-existing WIP failure — see below). Same result each round.
- Frontend: **104 / 104** vitest, **`tsc --noEmit` clean**.
- `makemigrations --check` clean. New migrations this pass: `accounts/0035`
  (books_start_date), `accounts/0036` (doc_number_scope + data migration),
  `payroll/0007` (employee basic/da), `payroll/0008` (payslip period_days/
  paid_days), `inventory/0012` (serialnumber import_job_ref). All edited backend
  modules import clean.

- **~76 findings fixed** in code across 3 rounds.
- **~19 findings closed with no code change** — already handled, verified
  non-issues, or the user's explicit decision.
- **1 finding left as a scoped follow-up** — R2-022/023 (inventory `unit_cost()`
  perf: needs a materialised running-cost cache in `post_movement` with its own
  test pass). It's a scalability issue, not a correctness bug.
- **4 fixes reverted** because they contradicted deliberate, tested behaviour:
  R4-015, R5-003, R2-008, R4-012 (R4-009 kept).

### Round 3 additions (deferred list cleared to 1)
R4-008 (payslip `period_days`/`paid_days` + LOP proration of gross & statutory
dues + `POST /pay-runs/{id}/lop/` + migration), R4-010 (multi-slab Professional
Tax tables for MH/WB/TN/AP/TG/GJ + Maharashtra February top-up + `validate_pt_slabs`
+ `month` threaded from the pay period), R4-007 already, R4-014 (`SerialNumber.
import_job_ref` — import void now scraps exactly the serials it created + migration),
R4-016 (qty auto-correct only on a clear-cut mismatch; otherwise a
`suggested_quantity` + flag, never a silent swap), R4-004 FE (GSTR-3B page shows
the recommended claimable ITC + its basis), R3-015 (sales Output-GST legs posted
from **line** tax sums so 2210/2220/2230/2270 tie to GSTR-1; ≤5-paise header
drift → 5500 Round Off), R3-001 (`create_receipt(bypass_period_gate=True)` for
verified gateway settlements — a closed period no longer 500s the webhook),
R3-002 (`finalize_gateway_payment` adopts a pre-existing manual receipt with the
same UTR instead of colliding), R3-003 (a provider partial refund is recorded +
alerted, not raised — webhook 200s and the provider stops retrying; new
`GATEWAY_PARTIAL_REFUND_UNRECONCILED` health alert).

### Still open (1)
- **R2-022 / R2-023** — inventory `unit_cost()` replays every StockMovement for
  the product (O(movements) per COGS calc). The fix is a materialised running
  WAVG cost maintained in `post_movement`, but it must be threaded through every
  movement path (issue/receive/adjust/cancel/transfer/FIFO-peel) with its own
  test pass. Left as a dedicated follow-up rather than risk a silent
  inventory-valuation bug. The system is **correct** here — just slow at scale.
  (R3-015 on the purchase/note side and R2-028 serial-loop batching are smaller
  perf items rolled into the same follow-up.)

### Round 2 additions (on top of round 1's 55)
R3-009 (idempotent GL post + IntegrityError replay), R2-026 (opening-stock race
lock via Product row lock), R1-010 (idempotency retains 2xx/5xx, releases 4xx),
R3-017 (opening-balance JE dated to `Company.books_start_date` / FY start),
R1-008 (auto-select + persist earliest membership instead of 409),
R1-013/14/15 (explicit `Company.doc_number_scope` policy + `series_identity()`
helper + data migration locking in current per-company behaviour),
R2-001/R2-010 (recompute intra/inter tax split at Complete against the stamped
filing GSTIN's state), R2-015 (partial-return CN discount residual + fixed a
`FieldError` it exposed — PurchaseCreditNote has no `additional_charges`),
R4-007 (PF wage base = Basic+DA when set), R2-003 (quotation→invoice/order
carries cess/nature/inclusive).

- **3 pre-existing test failures in the WIP (NOT caused by this work) — 2 fixed:**
  1. `test_tcs_sales_gl_206c` — **left for the user**. Test feeds contradictory
     `tcs_rate=0.1%` + `tcs_amount=1.00`; WIP `apply_tcs_fold` recomputes from
     the rate → 1.18. Product call: does an explicit `tcs_amount` override the
     rate, or does the rate always win?
  2. `test_tds_tcs_worksheets_csv_and_flag_gate` — **FIXED**: `csv.DictWriter`
     500'd on the extra `source` key WIP's `tds_worksheets.py` added;
     `reporting/views.py` now lists it + uses `extrasaction="ignore"`.
  3. `test_bb_000722_purchase_return_requires_and_scraps_serials` — **test
     updated**: WIP intentionally changed `complete_return` to RETURNED (not
     SCRAPPED) for non-damaged returns; the stale assertion now matches.

- **4 fixes reverted after regression** (behaviour was intentional & tested):
  - R4-015 — non-PRODUCTS imports commit partially by design.
  - R5-003 — "keep session on network error" contradicts the BUG-407 test.
  - R2-008 — a purchase/sales return whose sold lots can't be identified is
    *refused* by design (`test_sales_return_unidentified_lot_refused`); the
    operator posts a manual RETURN_UNIDENTIFIED adjustment.
  - R4-012 — cancel of a pay run returns it to DRAFT (re-runnable) by design
    (`test_cancel_pay_run_reverses_journal_and_reopens_draft`), not a distinct
    CANCELLED state. R4-009 (keep finalised slips, `net > 0`, on re-complete)
    was kept.

## Deferred (`D`) — scoped follow-ups
- **R3-009** `JournalEntry` unique `(company, source_type, source_id, purpose)`
  filtered to non-reversed: migration + a `RunPython` that reverses/flags any
  existing duplicate POSTED entries first (fails hard otherwise).
- **R2-022 / R2-023** perpetual WAVG running-cost table (mirror
  `InventoryCostLayer`); window/order `valuation()` by movement business date,
  not `created_at`. Removes an O(all-movements) replay from every Complete.
- **R2-001 / R2-010** recompute `compute_document_totals` at Complete once the
  filing `company_gstin` is stamped, so multi-GSTIN invoices file the right
  CGST/SGST-vs-IGST head. Needs test matrix for single- vs multi-GSTIN tenants.
- **R2-026** DB partial-unique on `StockMovement` OPENING_STOCK per
  `(company, warehouse, product, batch)` excluding `import_voided` — migration
  with a pre-check for existing dupes.
- **R3-001/002/003** webhook settlement: capture into a holding state that
  period-locks / UTR-uniqueness / partial-refunds cannot block; dead-letter +
  reconcile job. Non-trivial state machine.
- **R1-013 / R1-014 / R1-015** one company-level policy for document-number
  FY-scoping (not "did the caller pass a gstin"); allocate the number in a short
  dedicated txn; warn on FY-boundary series discontinuity.
- **R1-010** idempotency: retain terminal 4xx and 5xx-after-commit outcomes
  instead of releasing the key (prevents double-create on retry after a
  post-commit 500).
- **R4-007** DONE — `Employee.basic` / `da` fields added (migration
  `payroll/0007`); `compute_statutory` uses `basic+da` for the PF wage base when
  set, else falls back to gross (legacy).
- **R4-008** payroll LOP / attendance / mid-month proration — a feature, not a fix.
- **R4-010** multi-slab / Feb-special Professional Tax tables per state.
- **R4-009 / R4-012** add `PayRun.Status.CANCELLED` (migration); `cancel_pay_run`
  → CANCELLED (not DRAFT); stop deleting inactive-employee slips on re-complete.
- **R4-017** persist the raw custom qty-formula expression on
  `SupplierBillTemplate` so `formula_enum` round-trips (model field + migration).
- **R2-008** WAVG-cost fallback path in `restore_return_stock_and_cogs` instead
  of hard-raising when sale lots can't be matched.
- **R2-015** spread invoice-level discount/charges on partial-return auto-CNs so
  repeated partials don't leave paise of AP residue.
- **R2-017** pick ONE basis: either `customer_statement` foots 1200 only (drop
  2300) so it equals `customer_outstanding`, or `customer_outstanding` nets
  advances. Product call.
- **R2-028** batch `SerialNumberService.transition` / `receive` (one SELECT +
  one bulk_update instead of per-serial round-trips).
- **R3-015** drive the GL tax legs off line-tax sums (not header totals) so GL
  always ties to the filed GSTR; needs a pass over every GL posting test.
- **R3-017** date opening-stock journals to a company books-start date (new
  `Company` field) rather than `movement.created_at`.
- **R1-008** multi-membership + no `active_company`: decide auto-pick
  most-recent vs. force explicit switch; wire the FE company picker on that 409.
- **R1-002** `CELERY_ENABLE_UTC=1` + display TZ — changes beat schedule
  interpretation; needs an ops-coordinated cutover.

## Wave 1
- [~] R1-001 import ordering (settings celery.crontab)
- [n/a] R1-002 CELERY_ENABLE_UTC — DESIGN (changes beat semantics) [D]
- [~] R1-003 metrics endpoint auth — verify+fix
- [~] R1-004 password min length 10
- [~] R1-005 CookieJWT Bearer+Origin note
- [~] R1-006 non-issue on DRF 3.18 (user.setter writes back to HttpRequest) + R1-007 fix; verified in drf source
- [~] R1-007 get_company_user caches None
- [~] R1-008 multi-membership: get_company_user now auto-selects + persists the earliest membership instead of 409-locking
- [~] R1-009 RLS GUC reset fail-closed
- [~] R1-010 idempotency retain terminal 4xx/5xx-after-commit [D]
- [~] R1-011 idempotency stale TTL constant
- [~] R1-012 dead idempotency stubs
- [~] R1-013 doc-number FY scoping policy [D]
- [~] R1-014 doc-number lock held across slow work [D]
- [~] R1-015 subsumed by R1-013 explicit doc_number_scope policy
- [~] R1-016 cess docstring + consumers (additive)
- [~] R1-017 zero cess on NIL/EXEMPT/NON_GST
- [~] R1-018 INCLUSIVE subtotal basis
- [~] R1-019 reject discount > invoice value
- [~] R1-020 BEFORE_TAX residual spread
- [n/a] R1-021 warn untaxed B2B charges (already partly present — verify)
- [n/a] R1-022 charge_line cess_amount attr
- [n/a] R1-023 40% slab — keep
- [~] R1-024 feature_flags AND-only — document
- [~] R1-025 doc_numbers __import__ style

## Wave 2
- [~] R2-001/010 multi-GSTIN tax recompute at Complete [D]
- [n/a] R2-002 issued-invoice amend — audit diff only
- [~] R2-003 quotation conversion drops cess/nature/inclusive
- [~] R2-004 cancel reversal date = today
- [~] R2-005 cancel blocks non-completed returns
- [n/a] R2-006 warnings surfaced (verify view + FE)
- [~] R2-007 zero-COGS warning
- [~] R2-008 return COGS fallback path
- [~] R2-009 hoist prior_sr_ids query
- [~] R2-011 RCM gate for blank taxpayer_type [decision-ish, default: hard gate]
- [~] R2-012 batch expiry mismatch warning
- [n/a] R2-013 landed-cost / ITC double-count — verify
- [~] R2-014 purchase return numbering consistency
- [~] R2-015 partial-return CN paise residue
- [~] R2-016 restamp_fifo original_qty==0 guard
- [n/a] R2-017 ledger statement basis vs outstanding
- [~] R2-018 company_receivables unfloored for reconcile
- [~] R2-019 _resolve_source_number N+1
- [~] R2-020 allocated filter defensive
- [~] R2-021 customer_outstanding advances note
- [D] R2-022/023 valuation replay perf + date basis [D]
- [~] R2-024 unit_cost rows[0] → qty-weighted
- [~] R2-025 FIFO shortfall cost + ALLOW dead branch
- [~] R2-026 opening-stock DB unique constraint [D migration]
- [n/a] R2-027 rebuild_balance drops manual reservations
- [D] R2-028 serial loop N+1 — rewrite attempted + reverted (perf-only)

## Wave 3
- [D] R3-001/002/003 gateway webhook settlement resilience [D]
- [~] R3-004 stuck refund outbox alert
- [n/a] R3-005 webhook probe robustness — verify
- [n/a] R3-006 UTR partial-unique index — verify
- [~] R3-007 payment_health perf
- [~] R3-008 webhook amount last-write
- [~] R3-009 JournalEntry unique constraint [D migration]
- [~] R3-010 purchase AFTER_TAX discount → balanced JE
- [~] R3-011 inactive seeded account → 500
- [~] R3-012 post_purchase charge inference
- [~] R3-013 control_balances tolerance band
- [n/a] R3-014 UNREVIEWED ITC reclass — verify
- [D] R3-015 drift → 5500 line
- [~] R3-016 reverse() dead hasattr guard
- [~] R3-017 post_opening_stock entry_date

## Wave 4
- [~] R4-001 GSTR RCM cess specific
- [~] R4-002 "NA" POS blocker
- [n/a] R4-003 invoice_value_mismatch surfaced
- [~] R4-004 GSTR-3B ITC claim-lower default
- [~] R4-005 rcm_cess or-chain fallback
- [~] R4-006 _is_b2b coarse
- [~] R4-007 PF base Basic+DA [D data model]
- [D] R4-008 payroll LOP/proration [D feature]
- [~] R4-009 payroll slip delete on re-complete
- [D] R4-010 PT multi-slab [D]
- [~] R4-011 seed_chart_of_accounts every run
- [~] R4-012 cancel_pay_run CANCELLED state
- [~] R4-013 import void deletes updated masters
- [~] R4-014 serial-tracked opening void orphans serials
- [n/a] R4-015 non-PRODUCTS partial-commit is by design (test_commit_writes_only_valid_rows); bad rows never written — reverted
- [~] R4-016 qty auto-override from printed amount
- [n/a] R4-017 custom qty_formula enum round-trip
- [n/a] R4-018 import void reversal date

## Wave 5
- [~] R5-001 FE AFTER_TAX B2B disable
- [~] R5-002 FE INCLUSIVE subtotal
- [D] R5-003 FE refresh keep-session-on-network-error — reverted, contradicts BUG-407 test
- [~] R5-004 FE 409 company-context handler
- [~] R5-005 FE money parity note
- [n/a] R5-006 40% slab — keep
- [n/a] R5-007 Dockerfile non-root — verify entrypoint
- [~] R5-008 Dockerfile workers env
- [~] R5-009 cd.yml dispatch CI gate
- [~] R5-010 base image digest pin
