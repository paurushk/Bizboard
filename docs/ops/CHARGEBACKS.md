# Chargebacks / payment disputes (8.8)

Two different money paths. Mixing them double-touches books.

## A. SaaS (Razorpay subscriptions)

Code: `billing.views.RazorpayWebhookView` → `apply_razorpay_subscription_status`.
Only payloads with a **subscription entity** are applied. Anything else returns
`{"ok": true, "ignored": true}` (including many dispute/chargeback event shapes).

HMAC: `RAZORPAY_WEBHOOK_SECRET` required outside `DJANGO_ENV=test`. Failures after
verify park `DeadLetterEvent` provider=`razorpay_subscription`.

Nightly-ish recon: `billing.tasks.reconcile_saas_subscriptions_task` GETs
Razorpay subscription status, applies the same mapping (`active` → ACTIVE,
`halted|paused|pending` → PAST_DUE, `cancelled|completed|expired` → SUSPENDED),
and parks provider=`billing_recon` on drift. **Skips when keys are unset.**

Operator SOP:

1. Confirm the dispute in the Razorpay dashboard (Human).
2. If local `Subscription.status` disagrees, wait for recon or replay DLQ
   (`manage.py replay_dead_letter <id>`).
3. Writes already follow `Subscription.is_write_blocked` + `BILLING_PAST_DUE_GRACE_DAYS`.
4. `billing_override_active` is Owner-support escape — audit why.
5. **Do not** call `payments.dunning` (that is customer AR WhatsApp/SMS).
6. **Do not** invent refund legal copy. Refund in Razorpay, then let webhooks/recon land.

## B. Collections (A25 sandbox Cashfree/PayU)

Code: `payments/webhook_views.py` + holding park. Chargeback/refund of a
customer invoice capture is **not** SaaS dunning. Replay uses the same DLQ
kind `payment_webhook`. Never complete the invoice a second time to “fix” a dispute.

## C. What this SOP will not do

- GST treatment of a chargeback (Human / CA).
- ToS / chargeback liability clauses (legal).
