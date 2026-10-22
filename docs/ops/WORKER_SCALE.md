# Worker scale / backpressure (12.4)

Compose worker:

```
celery -A config worker -l info --concurrency=${CELERY_CONCURRENCY:-2}
```

Raise `CELERY_CONCURRENCY` on the host when PDF/import queues lag. Add worker replicas by duplicating the `worker` service (Human). Broker: Redis. `CELERY_BROKER_CONNECTION_TIMEOUT=2` fail-fast.

Backpressure: Complete does not wait on PDF (409 until READY). Do not set `CELERY_TASK_ALWAYS_EAGER=1` in production (boot refuses).

## Month-end and GST deadlines

GSTR-1 is due on the 11th and GSTR-3B on the 20th (the 22nd/24th for quarterly filers); many
owners also close the month on the 10th. On those days most tenants open their GST worksheets and
download the Excel files and invoice ZIPs within a few hours, while invoicing carries on (WP-RS1).

- The day before the 10th, 11th and 20th, double `CELERY_CONCURRENCY` on the `reports` and
  `media_heavy` workers (or add a replica of each), and add one API worker. Scale back two days
  after.
- Watch `bizboard_celery_queue_depth{queue="reports"}` and the invoice Complete p95 during the
  peak; the queue should drain within 15 minutes of the busiest hour.
- Proof: `load/month_end.js` run on hosted staging against the large-tenant seed, recorded in
  `docs/ops/LOAD_RESULTS_TEMPLATE.md` ("Month-end GST peak").

