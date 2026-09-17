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
- There is no in-product coupon / proration engine in v1.

## What operators still own

Finance writes the customer-facing cancellation/refund policy. Counsel
publishes it. This file must be updated if `company_writes_blocked` changes.

Gating test: `tests/test_saas_quotas_and_dlq.py::test_cancelled_subscription_keeps_writes_until_paid_period_ends`.
