# SaaS refund / cancellation (16.4)

Factual product behavior from `billing.services.company_writes_blocked`.
**Not** a finance policy, refund ToS, or Razorpay settlement opinion.

## What the code does

- A **cancelled** subscription keeps writes allowed until `current_period_end`.
  After that timestamp, Completes and other writes are blocked (B9-007).
- **Past-due / unpaid** SaaS dunning is separate from customer AR dunning
  (`billing/dunning.py` vs `payments/dunning.py`).
- Customer **payment-gateway refunds** unwind the captured `GatewayPayment`
  when the signed webhook says REFUNDED. That is A25 sandbox collections, not
  SaaS plan refunds.
- Plan changes (SaaS Phase 2): an upgrade is on at once and the difference for the rest of the
  period is charged now (prorated); a downgrade takes effect at the next renewal with no charge now.
  There is no coupon engine.
- TDS a customer deducts on Bizboard's invoices is credited to the next renewal or refunded after a
  Form 16A claim (Settings → Billing → Claim back TDS).
- Proposed policy text for counsel: `docs/roadmap/SIGNOFF_PACK_2026-10-23.md` §B-4.

## What operators still own

Finance writes the customer-facing cancellation/refund policy. Counsel
publishes it. This file must be updated if `company_writes_blocked` changes.

Gating test: `tests/test_saas_quotas_and_dlq.py::test_cancelled_subscription_keeps_writes_until_paid_period_ends`.
