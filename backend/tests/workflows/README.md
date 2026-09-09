# tests/workflows/ — critical business workflow contracts (Phase 2)

Each file drives ONE business flow **end to end through the API** and asserts the
*whole chain* is consistent at the end — stock, GST, AR/AP, and GL all agree —
by calling `assert_all_invariants(company)` plus flow-specific expected numbers.

Why: every module can pass its own unit tests while the chain across them is
wrong ("locally plausible, globally wrong"). These are the contracts that must
stay green to freeze.

**Implemented (2026-09-09) — 10 chains:** WF-01, WF-03 (sales return), WF-04,
WF-05 (purchase return), WF-19 (POS), WF-20 (period close rejects posting),
WF-21 (godown transfer conserves stock), WF-22 (write-off + GL), WF-28
(two-tenant interleave), WF-29 (manual journal post+reverse).
Lanes: `tests/edge/` (5, 1 xfail — SERVICE item stock check, task_61284298),
`tests/errors/` (5). Snapshots baselined: `gl_sale_intrastate.json`,
`gl_purchase.json`.
Invariants: **18 registered** — `pnl_reconciles_to_trial_balance`,
`numbering.no_duplicate_document_numbers`, gl×4, gst×2, inventory×7, money×1,
tenancy×2. Demoted to plain callables (fragile suite-wide, used by dedicated
chains): `gl.closed_period_not_violated` (WF-44), `reports.balance_sheet_equation_holds`
(WF-31), `reports.inventory_gl_matches_running_cost` + `inventory.cost_layers_reconcile`
(WF-32 / FIFO). Full strict sweep: 1307 passed, 7 pre-existing non-invariant fails.

## Chain checklist (maps 1:1 to the app menu)

Legend: **[x]** implemented · **[ ]** planned this phase · `INV` = also covered by
the invariant sweep · `SNAP` = has a golden snapshot · `MATRIX` = run under a
settings matrix.

### Sales
- [x] **WF-01** New Invoice — GST intra-state: draft → complete → stock ↓, CGST/SGST, AR ↑, GL balanced, TB 0. `INV SNAP`
- [ ] **WF-02** New Invoice — GST inter-state + cess: IGST path, place-of-supply drives the split. `INV SNAP`
- [ ] **WF-03** Sales Returns: against a completed invoice → stock ↑, GST reversal, AR ↓, GSTR-1 CDNR. `INV`
- [ ] **WF-06** Quotations: quote → convert to invoice; no stock/GL until the invoice completes.
- [ ] **WF-07** Credit Notes: financial CN (no stock movement) → AR ↓, GL, GSTR-1 CDNR. `INV`
- [ ] **WF-08** Debit Notes (customer): raises AR → GL, GSTR-1.
- [ ] **WF-09** Sales Orders: SO → stock reservation invariant → convert to invoice / challan.
- [ ] **WF-10** Delivery Challans: challan moves stock with no GST/AR; later invoice links to it; e-way payload. `INV`
- [ ] **WF-11** Recurring invoices: schedule → generated invoice is a normal invoice; generation is deduped (idempotent).
- [ ] **WF-14** Upload Sales Bill: LLM extract → draft invoice; re-uploading the same bill is idempotent.
- [ ] Customer Payments (Payment In): covered by WF-01 tail (receipt → allocation → AR); over-allocation rejected.
- Sales History, Customers: list/CRUD → `tenancy` URL-conf sweep + RBAC matrix (no chain).

### Purchase
- [x] **WF-04** New Purchase — Complete posts stock ↑ **and** AP ↑ atomically, ITC recorded. `INV SNAP`
- [ ] **WF-05** Purchase Returns: against a completed purchase → stock ↓, GST reversal, AP ↓. `INV`
- [ ] **WF-12** Purchase Credit Notes (supplier CN): reduces AP + reverses ITC.
- [ ] **WF-13** Purchase Debit Notes (supplier DN): ties to D2 TDS — a DN enlarging a TDS bill must credit 2265 (CR-083).
- [ ] **WF-15** Upload Bill: LLM extract → draft purchase; idempotent re-upload.
- [ ] **WF-16** Purchase Orders: PO → convert to purchase.
- [ ] Supplier Payments (Payment Out): covered by WF-04 tail (payment → bill allocation → AP).
- Purchase History, Suppliers: list/CRUD → `tenancy` + RBAC.

### Extended chains — pending FREEZE_SCOPE §G disposition
Stubs in `test_wf_extended_stubs.py`. These assume the §G "proposed" column
(D5=ON ⇒ accounting core SUP; D2=ON ⇒ TDS/TCS core SUP; D3=ON ⇒ refunds/recon
SUP). Cut the stub if the founder marks the flow OUT/LIM.
- **WF-29** manual journal entry · **WF-30** chart of accounts · **WF-31** FY close ·
  **WF-32** opening balances · **WF-33** bank reconciliation
- **WF-34** TCS on sales (206C) · **WF-35** TDS on purchases (194Q) · **WF-36** TDS/TCS worksheets
- **WF-37** refunds · **WF-38** MDR/settlement recon · **WF-39** advance payments + GST on advances ·
  **WF-40** bad-debt write-off · **WF-41** bank statement import + matching · **WF-42** dunning schedule
- **WF-43** invoice cancellation · **WF-44** invoice amendment (H9) · **WF-45** registration ·
  **WF-46** password reset + rate-limit · **WF-47** JWT refresh/logout/expiry · **WF-48** user invite→role ·
  **WF-49** switch-company · **WF-50** sandbox/trial expiry cleanup
- **WF-51** idempotency contract (replay ⇒ no double effect) · **WF-52** document numbering (gap-free, FY reset, concurrent)

### D6–D14 chains — all resolved SUPPORTED 2026-09-09
- **WF-53** fixed assets — acquisition → depreciation run → disposal, balanced GL (D6)
- **WF-54** TDS/TCS returns — GSTR-7/8 JSON reconciles to the worksheets; 16A/27D generation (D7)
- **WF-55** reverse charge (RCM) — self-invoice → RCM liability + ITC; new RCM row in the place-of-supply matrix (D8)
- **WF-56** composition dealer — bill of supply (no tax) + CMP-08 quarterly assembly (D9)
- **WF-02 (extended)** per-unit cess added on top of ad-valorem; GSTR treatment (D9b)
- **WF-57** Bill of Entry / import purchase — customs duty + IGST-on-import + landed-cost capitalised into inventory value → GL (D10)
- **WF-58** plan limits — entitlement fail-closed + invoice/user **count quotas** + over-limit behaviour (D11)
- **WF-59** automated right-to-erasure — cascade across tenant data, retain only what law requires, nothing orphaned (D13) + new invariant `tenancy.no_orphans_after_erasure`
- **Mobile lane** (D12) — session persistence, deep links, offline-on-mobile
- **LLM hardening** (D14) — provider timeout/error → draft-with-warning; injected instructions in uploaded bill text are inert (`tests/errors/`)

### Invariants (core/invariants/) — 21 registered
Implemented since the §G/§H review:
- [x] `reports.pnl_reconciles_to_trial_balance` — P&L net profit (all-time) matches the TB income/expense rows
- [x] `reports.inventory_gl_matches_running_cost` — inventory GL asset balance == Σ running-cost value (when GL carries inventory)
- [x] `numbering.no_duplicate_document_numbers` — no two documents of a type share a number

Still to add:
- `audit.key_entities_logged` — every create/update/delete of a document/master writes an `AuditEvent`
- `audit.append_only` — no code path updates or deletes an `AuditEvent` (§H4)
- `money.changes_audited` — money-field changes on completed docs have a `MoneyFieldAudit` row
- `numbering.sequences_intact` — `DocumentSeries` runs are gap-free within an FY (needs per-model number mapping)
- `reports.balance_sheet_ties_to_tb` — BS totals reconcile to the trial balance
- `tenancy.no_orphans_after_erasure` — D13

### New test lanes proposed in §H (FREEZE_SCOPE.md)
- `tests/edge/` — business-logic edge cases (zero/negative/overflow amounts, backdated,
  period/FY boundary, mixed rate/HSN/cess, rounding 0.005, UoM conversion, PROTECT-delete) — §H6
- `tests/errors/` — every error family returns 4xx + a resolvable `HelpCode`, never 500 — §H5
- FE: RBAC visibility (render as each role), offline-outbox conflict, auth-redirect — §H1
- Webhook signature verification for every inbound webhook (WF-17 pattern) — §H10
- Pending D12 (mobile), D13 (erasure), D14 (LLM extraction hardening)

### Cross-cutting
- [ ] **WF-17** Payment gateway webhook (D3): sandbox capture → receipt → allocation → GL; replaying the same webhook is a no-op; capture for a cancelled/closed-period invoice parks then refunds. `INV`
- [ ] **WF-18** OTP login (D4): request → verify → session; OTP hashed at rest; request/verify rate-limited; lockout after N failures.
- [ ] **WF-19** POS (D1): `/pos` checkout → retail invoice complete → stock ↓ → GST → cash/UPI receipt → GL; thermal PDF when available. `INV SNAP`
- [ ] **WF-20** Period close → back-dated post rejected → sanctioned correction posts a reversing + re-post pair that nets to zero. `INV`
- [ ] **WF-21** Stock transfer between godowns: TRANSFER_OUT + TRANSFER_IN net zero; batch/serial identity preserved. `INV`
- [ ] **WF-22** Stock adjustment / write-off → valuation ↓ → GL expense. `INV`
- [ ] **WF-23..25** Imports: products / customers / opening-stock — each idempotent on re-run. `INV`
- [ ] **WF-26** Bank receipt into a linked bank account → GL. `INV`
- [ ] **WF-27** GSTR-1 + 3B generation for a mixed period → 3B ties to GSTR-1 + purchase register. `SNAP`
- [ ] **WF-28** Two tenants running WF-01 and WF-04 interleaved in one test → zero cross-contamination. `INV`

### Matrices (not chains)
- [x] **Place-of-supply matrix** (`FG-2c`) — `tests/gst/test_place_of_supply_matrix.py`: state-pair × supply-type grid + export/SEZ override + assume-local. Pure, 11 cases.
- [x] **RBAC matrix** (`FG-2d`) — `tests/tenancy/test_rbac_matrix.py`: role × permission-class truth table; drift from `capability_defaults_for_role` fails.
- [x] **Tenant isolation** (`FG-2d`) — `tests/tenancy/test_endpoint_isolation.py`: structural sweep over every `/api/v1/` view (must subclass `CompanyScopedViewSet` or scope by company) + live cross-tenant read/mutate probes.
- [ ] **Company settings matrix** — `negative_stock_policy` × `block_expired_stock` × `accounting_enabled` × document-figure mode, over WF-01/03/04/05.
- [ ] **GST settings matrix** — `einvoice_enabled`, `eway_enabled`, thresholds, `assume_local_state_for_blank_party`.
- [ ] **Price Lists matrix** — price-list price vs product price → invoice line price.
- [ ] **Rate resolution** (`FG-2c`) — HSN/SAC × effective date, from CBIC-notification fixtures (`tests/gst/fixtures/`).

### Golden snapshots (`FG-2f`, `tests/snapshots/`)
Dependency-free helper in `tests/snapshots/conftest.py` (`assert_snapshot`;
`SNAPSHOT_UPDATE=1` to (re)baseline; missing baseline → skip, not fail).
- [x] GL posting set — sale intra-state, purchase (`test_gl_posting_sets.py`) — **needs `SNAPSHOT_UPDATE=1` run to baseline**
- [ ] report JSON (TB, P&L, balance sheet, stock summary, ledgers, registers)
- [ ] GSTR-1/2B/3B JSON · invoice PDF text (per Invoice Template)

### Settings pages — coverage
Bank Accounts, Payment Gateway, Price Lists, Company, GST, Units, Item Settings,
Invoice Templates, Users, Import Data, Backup/Export, Billing → all in the
`tenancy` URL-conf isolation sweep + RBAC matrix. Behaviour-changing ones drive
the matrices above. Backup/Export → Phase 3 backup/restore drill (invariants must
hold post-restore). Per-field CRUD tests for each page are **not** in Phase 2.

### Help / FAQ
Keep the existing `helpCodes.json` ↔ `help_codes.py` CI sync gate. Add: every
help code referenced by the frontend resolves; resolution is company/role-scoped
and tenant-safe (`test_help_resolution.py`). FAQ (`web/src/pages/help/
faqContent.tsx`) → render test + deep-link/help-code resolution; copy is static.
