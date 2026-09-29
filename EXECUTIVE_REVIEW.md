# Executive Code Review

**System:** Bizboard multi-tenant ERP / SaaS  
**Date:** 28 September 2026  
**Scope of this pass:** Cross-module execution paths in the uncommitted growth surface (insurance, projects, contracts, complaints, referrals, support, billing ops) and the Celery / row-level-security seam those jobs share with recurring billing. This is not a line-by-line reread of the frozen accounting core.  
**Method:** Code trace from UI → API → service → database. Findings below are from the current tree. They were not re-executed in a browser or under Postgres with `POSTGRES_RLS_ENABLED=1` in this session; that limit is called out on each item that depends on it.  
**Release posture:** **HOLD** for any tenant granted `ENABLE_INSURANCE`, `ENABLE_PROJECTS`, or `ENABLE_CONTRACTS`, and **HOLD** on flipping `POSTGRES_RLS_ENABLED` to 1 (staging soak or the incident-response step in `docs/ops/INCIDENT_RESPONSE.md`) until DR-001 is fixed.

Prior root reports dated 27 September 2026 marked five older items resolved and signed the build off. This pass did not reopen those items. It found a different set of defects. The 27 September “release unblocked” conclusion does not survive this pass.

## Scorecard

| Severity | Count | Release action |
| --- | ---: | --- |
| P0 | 0 | None proven in this pass |
| P1 | 6 | Block the modules or the RLS flip named above |
| P2 | 7 | Fix before those modules leave a pilot |
| P3 | 1 | Cleanup |

No authentication bypass, SQL injection, or cross-tenant read in the new viewsets was proven. New viewsets go through `CompanyScopedViewSet` (`company=self.company`). Postgres RLS remains **off** in production examples (`POSTGRES_RLS_ENABLED=0` in `.env.production.example` and `docs/FREEZE_SCOPE.md`). App-layer `company_id` filters are still the live isolation boundary.

## What is actually broken

1. **DR-001 — Background sweeps go blind when RLS is on.** `refresh_contract_statuses` and `generate_recurring_invoices_task` take no `company_id`. Celery prerun then sets `app.company_id` empty. Under `FORCE ROW LEVEL SECURITY` the queries return no rows, so contract expiry never advances and recurring drafts are never created. Sibling beats (AR dunning, expiry bands, depreciation, refund outbox) already loop `iter_company_ids()` and `set_rls_company`. These two do not. Production today has RLS off, so the jobs still run. Turning RLS on — the documented staging soak and an incident-response lever — stops them with no error.

2. **DR-002 — One prospect can be issued two in-force policies.** `issue_policy` only refuses a second policy on the *same option*. Choosing the other option and issuing again creates a second policy. The insurance screen allows that sequence.

3. **DR-003 — Renewal leads are not tied to the policy.** Deduping is a check-then-insert on the customer’s current name and a message prefix. Two overlapping diary runs insert two leads. Renaming the customer, or editing that message, inserts another or suppresses the real one. There is no unique key on the policy.

4. **DR-004 — Policy end date is `tenure_months * 30` days.** A 12-month policy starting 1 Jan 2026 ends 27 Dec 2026, not the anniversary. Renewal and cover both follow that short date.

5. **DR-005 — A project milestone is marked invoiced against a draft.** `invoice_milestone` creates a `DRAFT` sales invoice, stores the FK, and sets status `INVOICED`. Cancelling or abandoning that draft does not clear the link, and `close_project` treats any linked invoice as billed. The milestone cannot be invoiced again.

6. **DR-006 — The projects screen opens the wrong invoice.** After invoicing, the client navigates to the first milestone on the project that already has `salesInvoice`, not the milestone that was just billed.

## What held up

- Company-scoped querysets on the new viewsets, plus feature-flag 404s.
- Promise-to-pay rejects an invoice that belongs to a different customer (`payments/views.py` around the create path).
- Referral self-match checks and the `(company, opportunity)` unique constraint on rewards.
- `suspend_for_churn` runs inside `transaction.atomic()` in `SubscriptionDetailView.post`.
- Owner-only ticket share, with the RLS bypass limited to the vendor-company write.
- Attachment sniffing uses file magic bytes, not the client `Content-Type`.
- GST Guard override still requires an owner or manager membership before it is applied on invoice and note completion.
- Offline POD drain exists (`drainPodPhotos` in `web/src/offline/photoOutbox.ts`, called from `AppShell`).

## Uncertainty

- Whether staging is actually running with RLS on. `.env.staging.example` sets `POSTGRES_RLS_ENABLED=1`; the checked-in `.env.staging` sets `0`. DR-001 is definite in code and conditional in whatever environment has the flag on.
- Milestone `amount` is passed to `SalesService.set_items` as a pre-tax `unit_price`, and the product GST rate is applied on top. If operators enter a tax-inclusive fee, the invoice is high by the GST. The UI label is only “Amount”. Treated as a product ambiguity in the frontend review, not a proven double-tax bug.
- This pass did not re-run pytest, Playwright, or a browser session.
