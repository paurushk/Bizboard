# Worker scale / backpressure (12.4)

Compose worker:

```
celery -A config worker -l info --concurrency=${CELERY_CONCURRENCY:-2}
```

Raise `CELERY_CONCURRENCY` on the host when PDF/import queues lag. Add worker replicas by duplicating the `worker` service (Human). Broker: Redis. `CELERY_BROKER_CONNECTION_TIMEOUT=2` fail-fast.

Backpressure: Complete does not wait on PDF (409 until READY). Do not set `CELERY_TASK_ALWAYS_EAGER=1` in production (boot refuses).
