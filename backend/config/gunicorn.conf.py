"""Gunicorn settings shared by every Compose overlay (WP-D2).

``child_exit`` marks a dead worker in prometheus_client multiprocess mode, so a gauge from a
worker that no longer exists stops counting. Bind, worker count and timeout stay on the
command line in the Compose files.
"""

import os


def child_exit(server, worker):
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return
    try:
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
    except Exception:  # noqa: BLE001 - never block a worker restart on metrics
        pass
