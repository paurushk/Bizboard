# Needs attention — dedupe key contract

A row's `dedupe_key` is its identity. Dismissals, snoozes, assignments, outcomes and the audit log all
hang off it, so **changing a key orphans that state**. If a detector must change a key, write a migration
that copies state to the new key (see `insights/migrations/0015_copy_customer_receivable_state.py`) and
update this file. `backend/tests/test_dan_phase_d_attention.py` fails when a key shape or a code in
the detectors is missing here.

Default key, when a detector does not set one: `{code}:{entity_type}:{entity_id}`.

## Explicit key shapes

| Shape | Scope | Source |
|---|---|---|
| `ABNORMAL_STOCK_ADJUSTMENT:{mv.id}` | one stock movement | alerts.py |
| `CONTRACT_RENEWAL:{contract.id}` | one contract | alerts.py |
| `DEAD_STOCK:{company.id}` | company | alerts.py |
| `DUPLICATE_PAYMENT:{d['customer_id']}:{d['receipt_date']}:{d['amount']}:{ident}` | one suspected duplicate | alerts.py |
| `JOB_READY_TO_INVOICE:{job.id}` | one job | alerts.py |
| `MILESTONE_OVERDUE:{milestone.id}` | one milestone | alerts.py |
| `TICKET_SLA_BREACH:{ticket.id}` | one ticket | alerts.py |
| `VOID_RATE_HIGH:{company.id}:{day_start.isoformat()}` | company, per day | alerts.py |
| `WALK_IN_UNALLOCATED_RECEIPT:{rec.id}` | one receipt | alerts.py |
| `{'QUOTATION_EXPIRED' if expired else 'QUOTATION_EXPIRING'}:{quote.id}` | one quotation | alerts.py |
| `AR_CUSTOMER:{customer_id}` | one customer (merged receivable signals) | attention.py |
| `EXPIRING_STOCK:{pid}` | one product | attention.py |
| `FEED_DEGRADED:{company.id}` | company | attention.py |
| `GST_GUARDRAIL:{alert.get('code')}:{doc_type}:{doc_id}` | one document and rule | attention.py |
| `GST_RATE_EXPOSURE:{company.id}` | company | attention.py |
| `ITC_AT_RISK:{period}` | company, per month | attention.py |
| `PROMISE_TO_PAY_DUE:{promise.id}` | one promise (inside `AR_CUSTOMER`) | attention.py |
| `{code}:hint:{company.id}` | company growth hint | attention.py |
| `{code}:{raw.get('subject_key') or f'{doc_type}:{doc_id}'}` | legacy alert subject | attention.py |
| `WO_LATE:{wo.pk}` | one work order | manufacturing/attention.py |
| `WO_SHORTAGE:{wo.pk}` | one work order | manufacturing/attention.py |
| `WIP_STALE:{wo.pk}` | one work order | manufacturing/attention.py |
| `BATCH_ON_HOLD:{lot.pk}` | one batch | manufacturing/attention.py |
| `NCR_OVERDUE:{ncr.pk}` | one quality problem | manufacturing/attention.py |
| `JOBWORK_AGEING:{r['challan_line']}` | one challan line | manufacturing/attention.py |
| `ITC04_DUE:{label}` | one ITC-04 period | manufacturing/attention.py |
| `WO_APPROVAL_WAITING:{issue.pk}` | one extra-material request | manufacturing/attention.py |
| `CHURN_RISK:{customer_id}` | one customer | customer_actions.py |
| `CROSS_SELL:{customer_id}:{missing}` | customer and product | customer_actions.py |
| `REPEAT_ORDER_DUE:{customer_id}:{product_id}` | customer and product | customer_actions.py |

## Codes

Every code a detector can emit. A new code must be added here, and in `NON_DISMISSIBLE` /
`REASON_REQUIRED_CODES` if it needs the rules in `attention.py`.

ABNORMAL_STOCK_ADJUSTMENT, AP_DUE_7D, AR_COLLECTION_RISK, AR_CUSTOMER, AR_OVERDUE_CRITICAL,
AR_OVERDUE_WARN, AR_RESIDUAL_AFTER_RETURN, CASH_TIGHT_14D, CHURN_RISK, CONTRACT_RENEWAL,
CREDIT_LIMIT_NEAR, CROSS_SELL, CUSTOMER_CONCENTRATION, DEAD_STOCK, DISCOUNT_FREQUENCY,
DISCOUNT_OVER_THRESHOLD, DISCOUNT_STACKED, DUPLICATE_PAYMENT, EXPIRING_STOCK, FEED_DEGRADED,
GST_GUARDRAIL, GST_HEALTH_CRITICAL_OPEN, GST_RATE_EXPOSURE, IRN_FAILED, ITC_AT_RISK,
JOB_READY_TO_INVOICE, LOW_STOCK_FAST_MOVER, MARGIN_COMPRESSION, MARGIN_DROP_SKU, MILESTONE_OVERDUE,
NO_SALES_TODAY, OVERDUE_CONCENTRATION, PAID_PENDING_BOOKS, PREDICTED_LATE_PAYMENT,
PROMISE_TO_PAY_DUE, PURCHASE_PRICE_CREEP, PURCHASE_PRICE_JUMP, QUOTATION_EXPIRED,
REPEAT_ORDER_DUE, SALE_BELOW_COST, TICKET_SLA_BREACH, VOID_RATE_HIGH, WALK_IN_UNALLOCATED_RECEIPT,
WO_LATE, WO_SHORTAGE, WIP_STALE, BATCH_ON_HOLD, NCR_OVERDUE, JOBWORK_AGEING, ITC04_DUE, WO_APPROVAL_WAITING

The last seven are the Manufacturing rows (`manufacturing/attention.py`). They appear only for a company with Manufacturing on, and the quality and job-work ones only with those sub-modules on.

Every code above is in `KNOWN_CODES` in `attention.py`; dismiss, snooze and assign refuse a key whose code is not. A code must also have an entry in the `attention.rows` catalogue (`web/src/i18n/en.ts` and `hi.ts`), except `GST_GUARDRAIL`, whose text is the GST health module's own message.

Reserved (classified in `attention.py` but no detector emits them today): EINVOICE_FAILED,
EINVOICE_PENDING, GSTR2B_UNMATCHED.

## Audit

Dismiss, snooze, assign and reopen each write an audit event (`attention.dismissed`,
`attention.snoozed`, `attention.assigned`, `attention.reopened`) in the same transaction as the change,
with the full key, the reason and the state before and after.
