# Frontend Review

**Date:** 28 September 2026  
**Scope:** `web/src/pages/projects/ProjectsPage.tsx`, `web/src/pages/insurance/InsurancePage.tsx`, and the API shapes they call.  
**Not done:** A browser pass. These findings are from the component source and the serializers. Loading, focus, and mobile layout were not exercised in a live session.

The API renderer camelCases JSON. `sales_invoice` arrives as `salesInvoice`. The projects bug below is not a snake/camel mismatch.

---

### DR-006

| Field | Description |
| --- | --- |
| ID | DR-006 |
| Severity | P1 |
| Category | UI |
| Location | `web/src/pages/projects/ProjectsPage.tsx` `invoice` mutation `onSuccess` lines 61–68 |
| Problem | After a successful invoice call the page does `milestones.map((m) => m.salesInvoice).find(Boolean)` and navigates to that id. `find` returns the **first** milestone that already has an invoice, not the one the click targeted. The click handler knows `milestoneId` and drops it. |
| Root Cause | The response is the whole project. The client guessed which invoice was new instead of reading the milestone it posted. |
| User Impact | On a project that already has one invoiced milestone, invoicing the next one opens the previous draft/invoice. The operator edits or completes the wrong document. Combined with DR-005, the new milestone is already stuck in `INVOICED` while they are looking at another invoice. |
| Reproduction | Project with milestone A invoiced and milestone B ready. Click Invoice on B. The router goes to A’s `salesInvoice`. B’s new draft is never opened. |
| Recommended Fix | From the response, select the milestone whose `id` equals the id that was posted, and navigate to that `salesInvoice`. Disable the button while `invoice.isPending`. |
| Regression Risk | Projects with a single milestone keep working. Add a component test with two milestones so `find(Boolean)` cannot come back. |

---

### DR-013

| Field | Description |
| --- | --- |
| ID | DR-013 |
| Severity | P2 |
| Category | UI |
| Location | `web/src/pages/projects/ProjectsPage.tsx` lines 32–37 and 82–94; `web/src/pages/insurance/InsurancePage.tsx` lines 78–86 and 120–135 |
| Problem | Milestone name, amount, and service product are one piece of state rendered inside every open project. Typing in one card fills every card. Add on project 2 submits whatever was typed for project 1. There is no Close control, though `POST /projects/{id}/close/` exists. The insurance screen never shows `end_date`, premium, or policy actions (cancel, endorse, claim, renewal). After Issue, `chosen` stays set and the button stays enabled, which is the UI path for DR-002. There is no pending state on Issue, so a double click fires twice (the second is idempotent for the **same** option only). |
| Root Cause | The pages were built as a single happy-path form. Per-row state and the rest of the API were left off the screen. |
| User Impact | Wrong milestone text lands on the wrong project. Projects cannot be closed in the product UI. Advisors cannot see that cover ends on the 360-day date (DR-004) because the date is not rendered. |
| Reproduction | Open two projects. Type a milestone name. Both cards show it. Add on the second project. Its milestone uses that shared name. On insurance, issue a policy and confirm the in-force list has a number and status only, no end date. |
| Recommended Fix | Move milestone fields inside each project card’s own state. Add Close, with the server’s error text. On the policy list, render `endDate`, premium, and status. After a successful issue, clear `chosen` or navigate to the policy. Disable buttons while mutations are pending. |
| Regression Risk | Tests only cover the feature-flag empty state (`ProjectsPage.test.tsx`). Extending them is safe. |

## Accessibility and keyboard

Insurance product pickers are native checkboxes with `aria-label` set to the product name. That part is fine. Milestone and prospect actions are icon-less text buttons, which is fine. Error text is a `Typography color="error"` with no `role="alert"`, so a screen reader is not moved to the new error. P3.

Shared form fields have visible labels (`Milestone`, `Amount`, `Service`, `Nominee`, `Start`). Date uses `type="date"`. No positive `tabIndex` hacks showed up.

## State races

React Query keys are `['projects']` and `['advisor-book']`. Invalidation after create is correct. Invoice success navigates away without invalidating, so a back navigation can show a stale list until refetch. P3 next to DR-006.

No optimistic cache writes. A failed request does not leave a local “invoiced” flag. The server is the problem (DR-005), not a stale optimistic UI.

## Memory

These pages do not subscribe to timers, sockets, or object URLs. Nothing to leak on unmount beyond the usual Query Client cache, which is app-wide.
