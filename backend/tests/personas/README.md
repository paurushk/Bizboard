# tests/personas/ — archetype × persona journeys (PJ-*)

Each **PJ** test drives one *kind of user* at one *kind of business* through a
normal day via the API, and asserts three things at once:

1. **Capability boundary** — every in-role action succeeds; a curated set of
   out-of-role actions is denied (401/403/404).
2. **Visibility boundary** — the persona's dashboard / list endpoints return only
   what their role is allowed to see.
3. **Consistency** — `assert_all_invariants(company)` at the end: the whole day
   left the ledger / stock / sub-ledgers consistent.

This is the journey layer above invariants (is the ledger consistent?), workflow
chains (does one flow hang together?), and matrices (does a setting change
behaviour?). A green PJ suite for a persona type is the precondition for
onboarding that type in Phase 4.

Manufacturing, payroll, and CRM journeys are marked `pytest.mark.dark_module`.
They still run, but they must not be counted toward freeze or product-trust coverage.

## Archetypes (`fixtures.seed_archetype`)

| kind | shape | roles seeded |
|---|---|---|
| `retail` | counter shop, 1 godown, GOODS catalogue, POS | owner, sales |
| `trader` | small B2B, books on, batch lines, GSTIN customers | owner, acct, sales, viewer, import |
| `wholesale` | 3 godowns, price list, dunning config, books on | owner, acct, godown |
| `service` | non-stock services only | owner |
| `batch` | ARCH-05: lot tracking, FEFO picking, expiry-block policy | owner, sales, acct, godown |
| `serialized` | ARCH-06: unique serial numbers, warranty fraud guards | owner, sales, acct, godown |
| `contractor` | ARCH-07: hybrid SAC service + HSN spare parts | owner, sales, acct |
| `manufacturing` | ARCH-08: BOM, Work Orders, raw material consumption, WIP accounting | owner, sales, acct, godown |
| `migration` | empty shell — the journey loads the data | owner, acct |

## Personas (ground truth: `CompanyUser.Role` + `capability_defaults_for_role`)

| persona | role | must be able to | must be denied |
|---|---|---|---|
| P1: P-OWNER | OWNER | everything in scope | — |
| P2: P-CLERK | SALES_STAFF | counter POS, receipts, product lookup, draft credit notes | cancel docs, financial reports, import, manage inventory, post journals, purchases |
| P3: P-SALES | SALES_STAFF | quotations, sales orders, delivery challans, invoices | cost prices, financial reports, post journals, period close, einvoice IRN actions |
| P4: P-CUSTODIAN | + `can_manage_inventory` | goods inwarding, batch/serial tracking, transfers, stock counts | financial reports, trial balance export, journals, cancel, manufacturing release (Owner only) |
| P5: P-ACCT | ACCOUNTANT | journals, bank rec, purchases, purchase returns, payroll, tax worksheets | create sales, manage inventory, import, period close |
| P6: P-CA | External Auditor | audit reconciliation: TB balance, AR/AP subledger tie-outs, GSTR vs GL | back-dating into locked periods |
| P-VIEWER | VIEWER | list/read in-scope surfaces | any mutation; financial reports (default off) |
| P-IMPORT | + `can_import` | bulk import products/customers/opening stock, idempotent re-run | (scoped to import) |
| P-MIGRATOR | owner + acct | the day-zero cutover load + reconciliation | — |

## Journey matrix

| Archetype / Domain | P-OWNER | P-SALES / CLERK | P-CUSTODIAN | P-ACCT | P-CA | P-VIEWER / P-IMPORT |
|---|---|---|---|---|---|---|
| retail (ARCH-01) | [x] PJ-RETAIL-OWNER | [x] PJ-RETAIL-SALES | — | — | — | — |
| trader (ARCH-03) | [x] PJ-TRADER-OWNER | [x] PJ-TRADER-SALES | — | [x] PJ-TRADER-ACCT | — | [x] VIEWER / IMPORT |
| wholesale (ARCH-04) | [x] PJ-WHOLE-OWNER | — | [x] PJ-WHOLE-GODOWN | [x] PJ-WHOLE-ACCT | — | — |
| batch (ARCH-05) | [x] PJ-BATCH-EXPIRY | [x] FEFO sale | [x] Lot inwarding | — | — | — |
| serialized (ARCH-06) | [x] PJ-SERIALIZED | [x] Serial sale/return | [x] Serial inward | [x] Invoice journal | — | — |
| contractor (ARCH-07) | [x] PJ-CONTRACTOR | [x] Hybrid invoice | — | [x] Subledger/tax | — | — |
| manufacturing (ARCH-08) | [x] PJ-MFG-BOM | — (Denied) | — (Denied) | — | — | — |
| service (ARCH-07) | [x] PJ-SERVICE-OWNER | — | — | — | — | — |
| audit (P6 Cross) | — | — | — | — | [x] PJ-CA-AUDIT | — |
| bank-recon | — | — (Denied) | — | [x] PJ-BANK-RECON | — | — |
| returns-and-notes | — | [x] Credit Notes | — | [x] Purchase Returns | — | — |
| payroll-statutory | [x] Setup / Cancel | — (Denied) | — (Denied) | [x] PayRun / Post GL | — | — |
| einvoice-eway | [x] Mark/Submit IRN | [x] Invoice / E-Way | — | — | — | — |
| crm-lead-to-order | — | [x] Lead $\to$ SO $\to$ Challan | [x] Stock dispatch | — | — | — |
| migration | [x] PJ-MIGRATION-TRADER | — | — | [x] PJ-MIGRATION-WHOLESALE | — | (owner+acct together) |
| cross-flow | [x] PJ-NEWUSER | [x] Boundaries | [x] Boundaries | [x] Boundaries | [x] Reconcile | [x] Consistency |

Cross-flow consistency and Founder lifecycle synchronization is verified in `test_cross_flow_consistency.py`.
Specialized journeys are implemented in `test_pj_batch_expiry.py`, `test_pj_serialized.py`, `test_pj_contractor_hybrid.py`, `test_pj_ca_audit.py`, `test_pj_manufacturing_bom.py`, `test_pj_bank_reconciliation.py`, `test_pj_returns_and_notes.py`, `test_pj_payroll_and_advances.py`, `test_pj_einvoice_eway.py`, and `test_pj_crm_quote_to_order.py`.

**PJ-TRADER-VIEWER note:** in the current build VIEWER is a UI-only role —
BB-000422 denies masters browsing, BUG-319 denies financial reports, and the
transactional lists + every mutation are denied too. The journey pins that
"deny-all API surface" so a capability regression is caught.

## PJ-MIGRATION — the highest-stakes journey

A business moving to BizBoard with its own data. Asserts, beyond the standard sweep:

- **Opening reconciliation** (`core.invariants.reports.opening_ties_out`): computed
  opening AR == AR control in the opening TB; opening AP == AP control; inventory
  control == Σ opening-stock valuation.
- **Import idempotency at scale** — re-running any import doubles nothing.
- **Partial-failure resume** — a bad row is reported; re-run imports only the rest.
- **Numbering continuity** — first live invoice = old-system last number + 1.
- **Redo path** — void/re-enter a wrong opening TB; invariants hold before & after.
- **Cross-tenant safety** — a bulk load for company A never touches company B.

## Limitation guards

Every PJ adds one line per demoted D6–D11 flow — e.g.
`assert client.get("/api/v1/accounting/fixed-assets/").status_code == 404` — so
the KNOWN-LIMITATION claim is enforced per persona, not once globally.

## Frontend counterparts

`web/e2e/personas/*.spec.ts` — the same journeys as Playwright click-throughs,
asserting the **UI hides** what the role cannot do (this is §H1's concrete form).
