# O-Gate 2 — staging grep walk

Gate 2 DoD is **manual**. There is no join UI. One failed Complete must share
the same `request_id` in five places.

1. Sign in as Owner on staging.
2. Open Network tab. Click Complete on a draft that will **fail** (blocked
   stock, validation, or a forced 500).
3. Copy **Support ID** from the error alert (or ErrorBoundary).
4. Confirm the Complete request sent `X-Request-ID: <that id>`.
5. Grep API JSON access logs for `"request_id":"<id>"`.
6. If a PDF was queued, grep worker logs for `"event":"celery.task"` and the
   same `request_id`.
7. Sentry search: `request_id:<id>`.
8. On the API box:

```
python manage.py observability_gate_check --request-id <id>
```

Expect a `journey_failed` (or `journey_started`) ShopFloorEvent row with that
`request_id`. No GSTIN, invoice number, or raw company id on the row.

9. Owner dashboard → Counter (last 7 days): started / completed / failed
   move for post-cutover days only (Gate 2 ship date 16 Sep 2026).

Paste the Support ID into the O-Gate 2 sign-off row when this walk succeeds.
