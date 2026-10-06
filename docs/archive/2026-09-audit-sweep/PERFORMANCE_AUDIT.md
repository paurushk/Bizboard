# Performance Audit

**Date:** 28 September 2026  
**Scope:** Hot paths touched by the new modules and the route sequencer. No load test was run. Findings are from query shape and algorithmic bounds in code.

## Not a regression

`ContractViewSet.get_queryset` prefetches `covered_products`. Listing contracts does not query products per row.

`advisor_book` is three queries plus Python slices of 100. Fine at pilot volume. Truncation is an API correctness issue (see `API_REVIEW.md`), not a latency issue.

Ticket assignment locks `CompanyUser` rows for `SALES_STAFF` and counts open tickets in one aggregate. That serializes ticket creates per company. Acceptable until a company has a large sales team creating tickets concurrently. Not raised as a defect.

GST Guard caches HSN and rate checks per distinct HSN on the document (`reporting/gst_guard.py`). Repeat lines do not repeat the history query.

## Bounds that are intentional

`NearestNeighborTwoOptStrategy` (`backend/sales/route_optimization.py`) is nearest neighbour plus 2-opt capped at 300 swap attempts. Distance is haversine on PIN centroids, not a road network. The module states it is a single-vehicle heuristic with no capacity or time windows. For a dispatch route of a few dozen stops this is cheap enough to run inline. It will not scale to a city-wide VRP. That is a product limit, not a bug, as long as routes stay in the dozens. If Beat or the request path starts sequencing hundreds of stops, move `sequence()` to the existing `suggest_route_sequence_task` and keep the cap.

Pincode grouping sorts pins as strings. Equal-length Indian PINs sort numerically by accident. A shorter digit string sorts in dictionary order (`"99999"` after `"100000"`). Stops with those pins are still all emitted. Wrong order, not dropped stops. P3 given the usable-pin rule already allows non-6-digit values.

## Index note

`ProjectMilestone` has no composite index on `(company, project)`. Postgres still has the FK index on `project_id`. At pilot cardinality this is noise. Add `(company, project)` when milestone lists show up in slow-query logs. Same comment for other new child tables. Not a release blocker.

## The performance-shaped correctness bug

DR-001’s silent empty scan is cheap (it returns immediately) and wrong. Do not “optimize” it. A correct per-company loop is more queries and is the required shape. See `ARCHITECTURE_AUDIT.md`.

`refresh_contract_statuses` uses `.iterator()` and, when RLS is off, loads every non-cancelled contract in every tenant once a night. That is a full table walk. Once DR-015 derives status on read, this job can be deleted or limited to contracts with `end_date` near `today`. Until then it is O(all contracts) per night, which is fine at current volume and bad if it holds a worker with no time limit distinct from the global 600s soft limit.

## Frontend renders

`ProjectsPage` re-renders every project card when the shared milestone string changes (DR-013). That is wasted rendering and the data bug. Fixing the state split fixes both. No other page in this pass showed a list virtualization problem; the lists are unpaginated only in `advisor_book`’s 100-row cap.
