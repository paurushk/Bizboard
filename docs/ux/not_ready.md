# Not-ready modules

Owner: the UX programme. Review this list at each phase exit.

A screen that loads and then errors stays in the menu and shows `ModuleNotReady` (or `ErrorState`, which has its own heading). A route that cannot load at all is hidden via `markNavNotReady` in `web/src/navigation/notReadyNav.ts` until it is fixed.

Every other gated page in `docs/ux/L1_surface_ledger.csv` loads and has a heading.

| Phase | Route | Case | Why | Nav |
|---|---|---|---|---|
| G2 | `/reports/gstr6` | (b) hidden by decision | Page only says the return is not prepared; nothing is calculated | Hidden (`report-gstr6`) |
| G2 | `/reports/gstr7` | (b) hidden by decision | Same | Hidden (`report-gstr7`) |
| G2 | `/reports/gstr8` | (b) hidden by decision | Same | Hidden (`report-gstr8`) |

The routes still exist for direct links. Remove an id from `DEFAULT_NOT_READY` in `notReadyNav.ts` when the return is built.
