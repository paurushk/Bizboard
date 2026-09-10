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

## Archetypes (`fixtures.seed_archetype`)

| kind | shape | roles seeded |
|---|---|---|
| `retail` | counter shop, 1 godown, GOODS catalogue, POS | owner, sales |
| `trader` | small B2B, books on, batch lines, GSTIN customers | owner, acct, sales, viewer, import |
| `wholesale` | 3 godowns, price list, dunning config, books on | owner, acct |
| `service` | non-stock services only | owner |
| `migration` | empty shell — the journey loads the data | owner, acct |

## Personas (ground truth: `CompanyUser.Role` + `capability_defaults_for_role`)

| persona | role | must be able to | must be denied |
|---|---|---|---|
| P-OWNER | OWNER | everything in scope | — |
| P-SALES | SALES_STAFF | invoices, quotations, receipts, POS, product lookup | cancel docs, financial reports, import, manage inventory, post journals |
| P-ACCT | ACCOUNTANT | journals, bank rec, purchases, payments, FY close, reports, export | create sales, manage inventory, import |
| P-VIEWER | VIEWER | list/read in-scope surfaces | any mutation; financial reports (default off) |
| P-IMPORT | + `can_import` | bulk import products/customers/opening stock, idempotent re-run | (scoped to import) |
| P-MIGRATOR | owner + acct | the day-zero cutover load + reconciliation | — |

## Journey matrix (build these)

| | P-OWNER | P-SALES | P-ACCT | P-VIEWER | P-IMPORT |
|---|---|---|---|---|---|
| retail | [x] PJ-RETAIL-OWNER | [x] PJ-RETAIL-SALES | — | — | — |
| trader | [x] PJ-TRADER-OWNER | [ ] PJ-TRADER-SALES | [ ] PJ-TRADER-ACCT | [ ] PJ-TRADER-VIEWER | [ ] PJ-TRADER-IMPORT |
| wholesale | [ ] PJ-WHOLE-OWNER | — | [ ] PJ-WHOLE-ACCT | — | — |
| service | [ ] PJ-SERVICE-OWNER | — | — | — | — |
| migration | [x] **PJ-MIGRATION-TRADER** | — | (owner+acct together) | — | [ ] PJ-MIGRATION-WHOLESALE |
| cross | [ ] PJ-NEWUSER (register → setup → first invoice) | — | — | — | — |

`[x]` implemented · `[ ]` spec'd skip in `test_pj_stubs.py`.

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
