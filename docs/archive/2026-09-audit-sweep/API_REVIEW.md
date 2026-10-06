# API Review

**Date:** 28 September 2026  
**Scope:** Mutating actions on projects, insurance, complaints, and contracts that bypass serializers or idempotency.

Company-scoped list filters and flag gates are in place. The failures are custom `@action` bodies that read `request.data` directly.

---

### DR-010

| Field | Description |
| --- | --- |
| ID | DR-010 |
| Severity | P2 |
| Category | API |
| Location | `backend/projects/views.py` `milestones` line 52, `ready` lines 56–59, `invoice` lines 63–66; `backend/insurance/views.py` `PolicyViewSet.create` line 111; `RenewalDiaryView.post` line 161 |
| Problem | Several actions turn bad input into an unhandled exception. `int(request.data.get("sequence") or 1)` raises `ValueError` on `"abc"`. `mark_ready(None)` / `invoice_milestone(None)` when the milestone id is not on that project (`.first()` is `None`, then `.pk` blows up). `date.fromisoformat` on a missing or garbage `start_date` raises `ValueError`. `int(within_days)` does the same. None of these are `BusinessRuleError`, so the view’s 400 handler does not run. The client gets 500. |
| Root Cause | Actions were written against the happy-path types. DRF serializers are not used, so type and existence checks never become 400. |
| User Impact | A stale UI, a bad bookmark, or a blank date field is an internal error instead of a validation message. Support cannot tell a missing milestone from an outage. |
| Reproduction | `POST /api/v1/projects/{id}/milestones/` with `{"sequence": "x", "name": "A", "amount": "10", "service_product": <valid>}`. `POST .../milestones/999999/ready` on a real project. `POST` policy create with `"start_date": "tomorrow"`. Each responds 500. |
| Recommended Fix | Small request serializers: integer fields, required dates, and `get_object_or_404` scoped by `company` and parent. Map `BusinessRuleError` on the project and insurance viewsets the way `ContractViewSet.handle_exception` already does. |
| Regression Risk | Low. Clients sending numeric strings (`"1"`) still parse. Clients depending on 500 for “not found” should not exist. |

---

### DR-005 (API half)

| Field | Description |
| --- | --- |
| ID | DR-005 |
| Severity | P1 |
| Category | API |
| Location | `backend/projects/views.py` `invoice` lines 62–74 |
| Problem | `wrap_idempotent(..., scope="project_milestone_invoice")` does not include the milestone id in the scope. The web client does not send `Idempotency-Key` on this call (only POS and invoice editors do), so the wrapper is a no-op today and the row lock in the service is what prevents a double draft. A client that **does** send one key for the whole project session will replay the first milestone’s response for every later milestone and never invoice the rest. `project_milestone_invoice` is also absent from `MONEY_IDEMPOTENCY_SCOPES`, so a stale in-flight row can be reclaimed while the first request is still committing. |
| Root Cause | One scope string was reused for every milestone. Money scopes were updated for sales documents and not for this new creator of sales drafts. |
| User Impact | API clients with a stable idempotency key silently skip billing on the second milestone and receive the first milestone’s project payload. |
| Reproduction | POST invoice for milestone 1 with `Idempotency-Key: same`. POST invoice for milestone 2 with the same key. The stored response is replayed. Milestone 2 stays `READY`. |
| Recommended Fix | Scope `project_milestone_invoice:{milestone_id}` (and the same for any other per-row action). Add that scope to `MONEY_IDEMPOTENCY_SCOPES` if the action starts completing invoices (DR-005 data fix). |
| Regression Risk | Keys already stored under the old scope will not replay. That is what you want. |

---

### DR-012 (API half)

See `SECURITY_AUDIT.md`. Commission, endorse, cancel, claim, and KYC are the same unvalidated `request.data.get` pattern. Endorse and cancel do raise `BusinessRuleError` for a blank note. Commission and claim do not validate amount or summary length. Claim will create a ticket with an empty summary.

## HTTP semantics that are fine

- Creates return 201.
- Flag-off modules return 404.
- Contract status is read-only except cancel / un-cancel (`ContractSerializer.validate_status`).
- Complaint duplicate-return warning is 201 with `warning`, which is easy for a client to miss, but it is not a silent overwrite of the first link (`existing: true` returns the first document).

## Pagination

List endpoints inherit the project default pagination via `CompanyScopedViewSet`. `advisor_book` slices to 100 rows in Python (`campaigns`, `leads`, `policies` each `[:100]`) with no `next` cursor. A book larger than 100 is silently truncated. P3, noted here so it is not mistaken for a full book export.
