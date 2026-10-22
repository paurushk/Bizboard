# Business agents: test gap assessment and plan (2026-10-21)

## 1. Where we are

| Suite | Tests today | Verdict |
| --- | --- | --- |
| Platform (`test_models_and_spec`, `test_registry_and_gateway`, `test_runner`, `test_proposals`, `test_api`, `test_platform_contract`, `test_text_safety`) | about 130 | Strong. State machine, idempotency, runner limits, safety checks, RLS list, backup round trip. |
| Collections (`test_collections`, `test_outcomes`, eval) | about 50 | Good. |
| Order Intake (`test_order_intake`, eval) | 21 + 57-case replay | **Thin on the executor, the edit path and security.** |
| Inventory Risk (`test_inventory_risk`, eval) | 9 + 36-case grid | **Thin.** One happy path per executor, no negative paths, no role or cross-company tests. |
| Bill Check (`test_bill_check`, eval) | 12 + 36-case grid | **Thin.** Goods-receipt comparisons are not tested at all. |
| Postgres races | 4 (platform only) | No race tests for the new executors. |
| Web (`agents.test.tsx`, paste panel, tray, comparison, help) | about 26 | **Thin.** `OrderRenderer` interactions, the multi-draft button, the bill page button, the Quick Order mount and the FAQ page are untested. |
| Browser journeys | 0 | None written. |

So: enough for the platform and Collections, **not enough** for R3 to R5 and the web layer. The evaluation sets measure matching quality; they are not a substitute for negative-path, security and interaction tests.

## 2. Plan

Each block lists the tests to add, grouped by risk. Order is by risk: money-adjacent and security first.

### A. Security and tenancy (highest priority, backend, about 14 tests)
1. Order edit payload with a **product or customer id from another company**: approve must fail and create nothing. Same for the transfer payload (warehouse, product, batch ids) and the purchase payload (supplier, product ids).
2. A user without the kind's approve permission (staff) gets 403 on approve, edit, reject and cancel for each of the four new proposal kinds.
3. Pasting text as a user without create-sales rights, with agents off, with the master switch off, and with the global kill switch: 403 and no run row.
4. Another company's run id and proposal id are 404 for the new kinds (the generic test uses the example kind only).
5. The text run with the **same Idempotency-Key** twice returns the same run and creates one draft.
6. Raw pasted text is never stored: assert no `AgentRun`/`AgentStep` column or JSON contains it, and that the model call receives scrubbed text (phone numbers masked).

### B. Order Intake (backend, about 22 tests)
- Parsing: empty and whitespace text, 100-line cap, 101 lines, Devanagari digits, decimals with comma, quantity 0 and negative, huge numbers, "x" and "×" forms, a line that is only a number.
- Resolver: ambiguous customers give alternatives not a guess, two products with equal scores, inactive and soft-deleted masters are never matched, phone match with country code, alias pointing to a deleted product.
- Draft building: stock warning exactly at the boundary, unit mismatch warning, blocked and inactive customer warning, credit-limit warning, products with no inventory tracking get no stock warning.
- Model path: `customer_hint` not in the text is dropped, a bool or string quantity is rejected, more than 100 lines is rejected, markdown-fenced JSON falls back to rules.
- Executor: inactive product becomes STALE, deleted customer fails cleanly, decimal quantity such as 2.5, duplicate product on two lines, payload edited to zero quantity, two approvals racing creates one order (Postgres).
- Alias learning: a corrected alias repoints, a wrong alias is not re-learned from a code or exact-name match, hits increment once per approval, aliases are written in the same transaction as the order (force a failure after the order, assert no alias).
- Payload serializer: quantity bounds, 0 lines, 101 lines, unknown source value.

### C. Inventory Risk (backend, about 18 tests)
- Executor negative paths: source equals destination, inactive or system godown, missing product, expired batch at approval, batch belonging to another product, quantity above availability by 0.001.
- Purchase executor: supplier deleted, product rounding for whole-unit items (3.2 becomes 4), the duplicate-draft-within-the-hour refusal becomes FAILED with a readable message and can be retried after an edit, two lines for one supplier produce one order.
- Context: a second sweep the same day is idempotent (same dedupe keys, no duplicates), an item covered by open orders is not drafted, an item with no supplier is reported in the run facts, quarantine godown as destination is skipped, track-batch item with only partly usable lots suggests only that part.
- Roles: a purchases-only user can approve the purchase draft but not the transfer, and the reverse.
- Edit: changing a quantity and approving uses the edited quantity; editing to more than available fails at approval as STALE.
- Scheduling: the scheduled run is skipped when `ENABLE_PURCHASE_PLANNING` is off.

### D. Bill Check (backend, about 20 tests)
- Goods-receipt comparisons with real receipts: `QTY_VS_GRN` over and under, `GRN_NOT_BILLED`, rate against GRN when there is no PO, several receipts for one PO, a receipt that is not completed is ignored.
- `NOT_ON_PO`, multi-line bills with a mix of clean and different lines, a product on two PO lines at different rates (either rate passes, as in the 3-way match).
- Protection rules: duplicate number ignores cancelled bills and other suppliers and is case-insensitive, `AMOUNT_HIGH` boundary at exactly the 95th percentile and with five earlier bills, cancelled GSTIN with and without a date.
- Draft: all differences appear in the text, an edited message is kept on approve, a text over the length limit is rejected on edit, the model path with two bills in the sweep falls back to rules, `still_open` cancels the draft when the bill is completed or cancelled.
- Executor: another company's bill id fails, a bill completed meanwhile is STALE, stale after a rate fix, stays valid when only an unrelated field changes.
- Roles: a user who cannot create purchases cannot prepare or approve.

### E. Platform additions (backend, about 8 tests)
- `AgentSpec.accepts_text` contract: spec with `accepts_text` must not declare a schedule; text above `text_max_chars` is refused for a spec with a lower limit; text for an agent that does not accept it is refused.
- `proposal_ids_out` returns existing live drafts; a failed run returns an empty list and an error code.
- Linked drafts: the proposal list filter by `group_key`; bulk approve refuses the order and stock kinds.
- Unknown renderer in the catalog test list stays in the allowed set; adding a fifth agent package needs no change outside `catalog/` (the existing import-boundary test extended to the three new packages).

### F. Concurrency on Postgres (about 5 tests, `test_races_postgres.py`)
Two simultaneous approvals of an order draft create one sales order and one alias row; two simultaneous approvals of a transfer draft create one transfer; two simultaneous pastes of the same text give one draft; a purchase draft approved twice in parallel gives one order; an edit racing an approve either wins cleanly or is refused with the revision error.

### G. Web components (Vitest, about 25 tests)
- `OrderRenderer`: changing a quantity, picking an alternative chip for a product and for a customer, clearing a product, warnings shown, invalid quantity marked, read-only when disabled, camelCase keys written back.
- `isPayloadReady` edge cases (string quantity, zero, missing customer).
- Drawer: approve button disabled for an incomplete order and the A key does nothing, label reads "Create draft order", the help link points to the FAQ, failed draft shows the retry label.
- `AgentPrepareButton`: `agentKind` mode, several linked drafts with next and previous, "nothing to send" message after a run with no draft, error text on failure, hidden for a user who cannot prepare.
- `DraftsTray`: bulk select only on bulk-approvable kinds, order drafts never bulk-selectable, empty state.
- `PasteOrderPanel`: 6,000-character cap, button disabled for blank text, edit then approve sends the saved revision, a 409 stale error shows the translated message, hidden when the agent is off.
- Quick Order Entry: the panel shows in order mode only and not in bill mode (existing page test extended).
- Purchase detail: the check button shows only on a draft bill for a user who can write.
- `ComparisonRenderer`: edited message round trip, no rows.
- Help: the FAQ page renders the "Business agents" category, a deep link such as `#agents-order-intake` opens its answer, search for "holdout" finds its entry; every `t:` token in the new entries resolves (the existing check covers this; add an explicit count).
- Accessibility: axe check on the order drawer and the paste panel; 44 px touch targets on the quantity and chip controls.
- i18n: parity already tested; add a check that the Hindi review CSV lists every `agents.*` key.

### H. Browser journeys (Playwright golden, 4 specs, run against a live stack)
1. Paste order to draft sales order, with a learned alias on the second paste.
2. Reminder: prepare from a Needs attention row, switch to Hindi and firm, approve.
3. Low-stock row to a linked transfer and purchase draft, approve both, check both drafts exist and stock did not move.
4. Draft purchase bill to supplier query: rate difference, approve, then fix the bill and see the old draft refuse as stale.
Each also runs an axe pass and a phone-width pass.

### I. Quality of the evaluation sets
- Add 20 real, anonymised cases per agent from the pilot (QOS-0152) and keep the thresholds in the test.
- Add a "mutation" check: break a rule on purpose in a scratch run (wrong tolerance, wrong sign) and confirm an eval test fails, so the sets are known to bite.

### J. Performance guards (about 4 tests)
Query-count and time bounds: the product index with 5,000 products stays under a time limit; the order draft makes a bounded number of queries for 50 lines; the inventory sweep for 200 low items and the bill sweep for 100 drafts stay within a query budget.

## 3. Sizing and order

| Block | Tests | Rough effort | Do |
| --- | --- | --- | --- |
| A Security and tenancy | 14 | 1 day | first |
| D Bill Check | 20 | 1 day | with A |
| B Order Intake | 22 | 1 day | next |
| C Inventory Risk | 18 | 1 day | next |
| F Postgres races | 5 | 0.5 day (a 15-minute database build each run) | after B, C |
| E Platform | 8 | 0.5 day | with F |
| G Web | 25 | 1.5 days | in parallel with B to D |
| J Performance | 4 | 0.5 day | after B to D |
| H Browser journeys | 4 specs | 2 days (needs the live stack) | last |
| I Real cases and mutation check | ongoing | needs pilot data | when available |

Total new automated tests: about 120 backend, 25 web, 4 browser specs. Exit criteria: every new proposal kind has a negative-path test for each executor check, a cross-company test, a role test and a double-approve test; the web layer has an interaction test for every control a user can change; CI runs the suite on Postgres.

## 4. Implementation status (2026-10-21)

Blocks **A, D, B, C, E and G are implemented and passing**. F (Postgres races for the new executors), H (browser journeys), I (real pilot cases and mutation check) and J (performance guards) are not done.

| Block | Added | File |
| --- | --- | --- |
| A Security and tenancy | 25 | `tests/agents/test_security_new_kinds.py` |
| D Bill Check | 28 | `tests/agents/test_bill_check_more.py` |
| B Order Intake | about 55 | `tests/agents/test_order_intake_more.py` |
| C Inventory Risk | about 25 | `tests/agents/test_inventory_risk_more.py` |
| E Platform | 8 | `tests/agents/test_platform_additions.py` |
| G Web | about 55 | `OrderRenderer.test.tsx`, `AgentPrepareButton.test.tsx`, `agentsMore.test.tsx`, `agentsHelpPage.test.tsx`, additions to `QuickEntryPage.test.tsx` and `PurchaseDetailPage.test.tsx` |

Backend agent suite: 421 passed, 4 Postgres race tests skip on SQLite. Web agent, help, purchase detail and Quick Order tests pass; `tsc -b` and eslint are clean.

**Defects the new tests found and that are now fixed**
1. A model answer with a non-numeric quantity ("lots") crashed the Order Intake run instead of falling back to the rules parser (`decimal.InvalidOperation` was not caught). Fixed in `catalog/order_intake/context.py`.
2. A bare number such as "12" was parsed as product "1", quantity 2. A product hint now needs at least one letter (`catalog/order_intake/parsing.py`).
3. The review drawer jumped from a level-2 heading to a level-6 one (accessibility `heading-order`); the evidence heading is now level 3.
4. Registering a text-input agent with a schedule was allowed although it can never run without text; `register()` now refuses it.

Checks that were weaker than planned and why: the stale-test of an expired lot after approval, the 100-line model cap and the code-fence case are tested through the run path, not by calling parse functions alone.

## 5. Second implementation pass (2026-10-21)

- **J performance guards:** `test_performance_guards.py` (4 tests: 5,000-product index, 50-line order, 200-item inventory sweep, 60-bill sweep). It found a real defect: a supplier with more than 100 low items made the whole Inventory Risk run fail on the payload limit. Long lists now split into drafts of at most 100 lines.
- **I mutation check:** `test_eval_mutations.py` breaks one rule on purpose per evaluation (fuzzy matching, strictness, quantity parsing, rate tolerance, quantity tolerance, expired lots, planning quantities, amounts in reminders) and asserts the evaluation goes red. It showed the Bill Check set was too lenient (a removed tolerance still passed at the 0.9 floor); the set now requires precision and recall of exactly 1.0, since the rules are deterministic.
- **F races:** `test_races_new_kinds_postgres.py` (5 tests) for order, transfer and purchase double approval, simultaneous pastes, and an edit racing an approve. Skipped on SQLite; run on Postgres (all 9 Postgres race tests, old and new, pass on Postgres 17).
- **Features that were partial:** items with no supplier now produce one "items with no supplier on record" draft (acknowledge only); owner-only Bill Check findings (high amount, cancelled GSTIN, duplicate) now produce a "Bill notes for you" draft; a missing goods receipt alone still produces nothing.
- **H browser journeys:** `web/e2e-golden/agents-golden.spec.ts` (paste order, fix one line, create the draft order, learned wording on the next paste; panel absent when the agent is off). `grant_rollout_flag` now accepts `ENABLE_AGENTS` and `AGENT_*` for the e2e run.

## 6. Deep code review (2026-10-21)

Fixed, each with a regression test in `tests/agents/test_review_fixes.py` or the web agent tests:

1. **Async runs never ran under row-level security.** `run_agent_async.delay(run.pk)` sent no company, so the worker could not set its RLS context and could not see the run. It now passes `company_id`.
2. **Expiry and "condition cleared" tasks saw nothing under RLS.** `expire_proposals` and `cancel_resolved` scanned all companies with no company set, so on Postgres with RLS they matched no rows and drafts never expired or auto-cancelled. They now scan company by company (the pattern `contracts.tasks` uses) and always clear the context.
3. **A long pasted message made the model path fail.** `normalize` cut text to 255 characters, so any model line near the end of a longer message was rejected as "not from the text" and the run fell back to the rules. The cap now applies only to alias keys.
4. **A phone number elsewhere in the message could pick the wrong customer.** A delivery contact's number matched a different customer before the sender's name was tried. A named exact match now wins; the phone is used when there is no name.
5. **A very large catalogue was truncated silently** at 20,000 products. The draft now warns.
6. **Two approvals learning the same new wording could break an order** (unique-constraint race on `AgentAlias`). The write now uses a savepoint and falls back to updating the winner.
7. **One odd document lost a whole sweep.** Validation and saving were all-or-nothing per run, and a bill with many differences produced a message over the length limit (which made the run fail). Drafts are now validated and saved one by one (a run fails only if every draft is refused), and the message lists at most 8 differences plus "and N more".
8. **The "usual range" for a supplier used an arbitrary 200 bills.** It now uses the most recent 200.
9. **Payload lists were unbounded** (alternatives, warnings, notes, rows, columns): now capped.
10. **A paste ran for up to 60 seconds inside a web request.** Capped at 30.
11. **Inventory Risk did one godown query per transfer row.** Now one query.
12. **Web:** a failed reload after approving left an unhandled rejection; a run that ended with a real reason (limit, timeout, switched off) always said "nothing could be read"; comparison rows could collide as React keys.

Backend agent suite after the review: 469 passed, 9 Postgres-only tests skipped on SQLite (all 9 passed on Postgres earlier in this session; the review changes did not touch them). Web agent tests: 65 passed; `tsc -b` and eslint clean.

Known limits left as they are, on purpose: the Bill Check sweep looks at the 60 newest draft bills; a live draft keeps its old figures until it expires or is approved (the approval step re-reads the books and refuses stale ones); the model-reworded supplier message is rarely accepted for the duplicate-number difference because it must repeat the sentence.
