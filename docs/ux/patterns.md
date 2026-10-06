# UX pattern standards (Phase 3)

The standard to apply when touching any screen. Each pattern names the fix it removes from `L2_finding_ledger.csv`. Where a component already exists it is named; the rest are to be built. Existing pieces found in code: `UnsavedChangesGuard`, `lib/deviceDraft.ts`, `NumericField`, `StatusChip`, `utils/status.ts`, `CreditHoldChip`, `DocumentEditorShell`, `VirtualizedTable`, `HelpErrorAlert`, `lib/smartDateParser.ts`, `utils/partyName.ts`, `utils/documentNumber.ts`.

| Pattern | Standard | Existing | To build | Removes |
|---|---|---|---|---|
| Accessible naming | Every input, checkbox, combobox and icon button has a programmatic name; comboboxes reference a visible label id; table row checkboxes say what row | partial | `aria-label` helpers for row checkboxes | UX-N02, N03, N04 |
| Page title | One `h1` per route via one component | – | `PageTitle` | UX-N09 |
| Touch targets | 44px minimum below `sm` for icon buttons, checkboxes, steppers; 48px for primary tender and steppers on POS | POS tender 48 | Theme default in `theme/index.ts` | UX-N08 |
| Contrast | Disabled helper text and secondary text at least 4.5:1, defined once as a theme token | – | Token change | UX-N05 |
| Scroll regions | Horizontally scrolling tables get `tabIndex=0`, `role=region`, a label; below `sm` stack to cards | `VirtualizedTable` | Wrapper | UX-N07 |
| Page states | One wrapper handles loading (skeleton), error (plain copy plus Support ID plus Retry) and empty (next action) | `HelpErrorAlert`, spinners per page | `PageState` | UX-N01, N11 |
| Error copy | Formula: what happened, why if known, what to do; never raw status text | Support ID present | Error-class mapper | UX-N01 |
| Progressive disclosure | Show the default-case fields; put the rest under "More details" with a one-line summary of any non-default value | – | `MoreDetails` section | UX-N12 |
| Blocked action | A disabled primary action always shows the single next missing thing with a button that focuses it | POS tender blocker | Editor version | UX-N14, CW-05 |
| Primary action | One primary, secondary in a menu | – | Split button | UX-N13 |
| Lists | Hide empty columns, show total and page x of N, saved filters where useful | `VirtualizedTable` | Column hider | UX-N15 |
| Drafts and guards | Device draft with schema version and TTL; Stay or Discard on leave | `deviceDraft`, `UnsavedChangesGuard` | Extend to remaining editors | – |
| Status | One status to label, colour and icon map; never colour alone | `utils/status.ts` | – | – |
| Strings | All user-visible text in `en.ts` and `hi.ts`; JSX literals flagged by a test | `fullParity.test.ts` and `literalRatchet.test.ts` on the swept screens | Remaining screens still have literals | UX-N10 |
| Mobile | Check 393px and Hindi for every touched screen; bottom sheet for confirms below `md` | receipt void sheet | POS tender confirm | UX-026 |
| Keyboard | Only shortcuts that exist are advertised; at most 2 hints per screen line | POS hotkeys | – | UX-N13 |
