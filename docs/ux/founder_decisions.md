# Founder decisions required

Each open item needs a yes or no. Adopted rows below were taken from the recommendation already written in this file, and the matching behaviour is in the app.

## Adopted from the recommendation (2026-09-30)

| # | Adopted choice | Where it lives |
|---|---|---|
| D-UX-1 | Keep `<=` for low-stock alerts | Already the rule in stock lists and the low-stock payload. No second threshold. |
| D-UX-3 | No undo of a posted bank match. No split pane until a walk shows the current screen fails | Nothing new was built |
| D-UX-4 | Keep the current navigation | G9 stays a measurement only (`docs/ux/g9_nav_measure.md`) |
| D-UX-5 | Do not remap shortcuts to Tally keys | No remap |
| D-UX-6 | Show the expiry already stored on the batch the cashier typed. Do not pick a lot | `web/src/pages/pos/posBatchExpiry.ts` |
| D-UX-7 | Suggest oldest-invoice allocation and allocate only after confirm | Receipts start with the option off. Confirm turns it on |
| D-UX-9 | A bank line with exactly one candidate of the same amount inside the existing date tolerance is applied with the same match action the user would confirm. Two or more candidates stay queued. No undo (D-UX-3) | Operational match on Bank reconciliation (`BankReconPage`). The GL screen stays a separate product |
| D-UX-10 | Wave C disclosure ships now. Invoice type and price mode open as chips; “Change bill type” and More tax options reopen the selects. One godown is the name, not a select. Statutory controls stay behind More tax options and a chip opens them. The stored enums and tax maths do not change | New invoice, new purchase, and stock transfer. Supersedes the wait in D-UX-2 for these four screens |

## Answered in round 5 (GD-22 to GD-37)

| # | Choice | Where it lives |
|---|---|---|
| D-UX-2 | Progressive disclosure on New invoice and New purchase waits until the pilot staff sessions are scheduled. Production editors stay unchanged until then | GD-33. GM-99 does not start before that date. A2-5 and A2-6 wait with it |
| D-UX-8 | Sessions are with staff of Pilot Inter-State, Pilot Multi-User and Pilot Insurance Advisor, in the pilots' first weeks. Names come from those companies | GD-26. Gates A5-7 |
