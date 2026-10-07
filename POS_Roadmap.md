# POS roadmap (after the fix plan)

**Status:** R-01 through R-20 are implemented in the counter. The score column is still unmeasured. No cashier study, timed task, or contrast lab has been run.
**Depends on:** [POS_Fix.md](POS_Fix.md) Waves 0–5. Do not pull these items into those waves.
**Revised:** 2026-10-07

The numbers below are planning estimates from a code review. They are not a result. Do not cite “4 → 7” as evidence that a wave shipped.

## Rubric

A 10 on a dimension means a cashier can finish that kind of work on this screen without guessing, without a wrong book entry, and without leaving for another screen to recover. A score is assigned only after the check in the last column has been run and written down. Until then the score cell stays blank.

| Dimension | Estimate before Waves 0–5 | Estimate if Waves 0–5 ship as written | Measured |
|---|---:|---:|---|
| Purpose clarity | 8 | 9 | — |
| UX | 5 | 7 | — |
| Cognitive load | 4 | 6 | — |
| Flow | 5 | 7 | — |
| Functionality | 6 | 8 | — |
| Business logic | 4 | 8 | — |
| Data/state handling | 5 | 7 | — |
| Error handling | 7 | 8 | — |
| Cross-product integration | 5 | 7 | — |
| Consistency | 5 | 7 | — |
| Accessibility | 6 | 7 | — |
| Overall | 4 | 7 | — |

## Later product items

Each item has an id so it can be tracked. None of them are in the POS_Fix wave tables.

| ID | Priority | Item | Conflicts with the fix plan | Status | Check |
|---|---|---|---|---|---|
| R-01 | P2 | Show scale and drawer only when that hardware is connected. Bill discount and extra charge sit behind “Adjust bill”. | None | Implemented | A shop with no scale does not see the scale button |
| R-02 | P2 | One primary tender (the last one). Other modes under “More”. | None | Implemented | A cash-only till does not show six pay buttons |
| R-03 | P2 | Show credit remaining before Pay. | POS-013 still decides at complete | Implemented | Cashier sees the limit before the server rejects |
| R-04 | P3 | First-run states: no godown, no items, no walk-in flag, each with one setup link. | POS-036 creates the flag | Implemented | Empty company can start without a generic error |
| R-05 | P2 | Reprint the last five bills from this counter. | F11 today reprints only the latest | Implemented | An earlier bill from today reprints without opening history |
| R-06 | P3 | UPI second confirm names the amount. Cashier and time are stored on the receipt. | POS-009 still forbids polling | Implemented | Receipt audit shows who pressed Payment received |
| R-07 | P2 | Hide the godown selector when the company has one warehouse. | POS-001 still scopes stock | Implemented | Single-warehouse till has no godown field |
| R-08 | P2 | Remember the customer for the shift, then return to the flagged walk-in. | POS-036 | Implemented | Next bill after a named sale starts on walk-in |
| R-09 | P1 | Return or exchange the last bill here, through the existing sales-return flow. | Out of Waves 0–5 on purpose. Cash handed back is P1-A and P1-E in `POS_Implementation_Plan.md`. | Partial | Cash, bank, and advance refunds post. Exchange can apply the peeled advance. The return screen picks lines. A pilot close has not re-checked the day. |
| R-10 | P1 | A failed offline sync reopens that cart here with the error on the line. | POS-031 makes the flush atomic; this is the cashier’s recovery screen | Implemented | Cashier does not need the outbox page to see which line failed |
| R-11 | P2 | Collect an unpaid UPI invoice from this screen. | None | Implemented | Collect-later does not require invoice detail |
| R-12 | P2 | Held bills follow the user to another terminal. | **Replaces** the device-only store in POS-007. Do not add a second hold list beside it. | Implemented | F8 parks the bill on the server and F9 recalls it. A bill held on terminal A opens on terminal B for the same user. The bill on screen still has a device draft. |
| R-13 | P2 | Line price change requires a reason and is stored. Discount above the company cap needs approval. | POS-035 is the cap. This is the price field. | Implemented | A changed price is on the invoice and in the audit log |
| R-14 | P2 | Cash drop during the shift, on the existing `CashShiftRegister`. | POS-002 called this a later slice. It stays on that register. No second till model and no variance journal. | Implemented | A drop reduces that cashier’s expected cash |
| R-15 | P2 | Round-off is its own visible line and matches the server. | POS-015 must already have switched tender math | Implemented | Screen round-off equals the posted round-off |
| R-16 | P2 | Closed period, missing HSN, and missing bank account fail on the field before the customer pays. | POS-012 and POS-023 cover bank and UTR | Implemented | Missing HSN, a missing bank account, and a closed period block Pay. The settings response carries `period_blocked` from a read-only check. |
| R-17 | P1 | One cash sale, one UPI sale, and one credit sale traced to stock, the customer ledger, cash or bank, and the shift. | This is the acceptance test for POS-012, not a new feature | Implemented | `test_pos_counter_policy.py` traces cash to 1100, UPI to the mapped bank, credit to a due date with no receipt, and an intra-state GST sale to CGST and SGST. It does not file a return. |
| R-18 | P2 | GSTIN sale missing HSN shows a handoff. This screen does not file the IRN. | None | Implemented | No IRN call from `PosPage` |
| R-19 | P2 | One word for warehouse or godown, shared confirm dialogs, Hindi and English for every new string. | POS-011 is layout only | Implemented | New counter strings exist in English and Hindi. The counter says godown. |
| R-20 | P1 | Accessibility pass: contrast, 200% zoom, phone width with Pay visible, keyboard cart, live errors, screen reader on search. | POS-018 keeps F5 as refresh | Implemented | The tender panel stays on screen, Pay targets are 48px, the error alert is live, and search is labeled and on F2. Contrast was not lab-measured, so the score stays blank. |

The rubric scores stay blank. Shipping the work is not a measured 10.
