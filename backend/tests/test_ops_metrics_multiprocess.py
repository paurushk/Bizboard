"""WP-D2: with PROMETHEUS_MULTIPROC_DIR set, /metrics adds up every worker process.

prometheus_client decides multiprocess mode when it is first imported, so each "worker" is a
real subprocess. Two workers record traffic; a third process renders what a scrape would see.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

WORKER = """
import os
from core import ops_metrics as m
for i in range({n}):
    m.record_http_result(status={status}, duration_ms=120)
m.bump_event("money_in_receipt_created")
m.observe_celery_task(task="sales.tasks.generate_invoice_pdf", status="success", duration_ms=1500)
"""

SCRAPE = """
from prometheus_client import CollectorRegistry, generate_latest, multiprocess
r = CollectorRegistry()
multiprocess.MultiProcessCollector(r)
print(generate_latest(r).decode())
"""

DEAD = """
import os
from prometheus_client import multiprocess
multiprocess.mark_process_dead({pid})
"""


def _run(code: str, env: dict) -> str:
    out = subprocess.run(  # noqa: S603 - fixed test snippets defined in this file
        [sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, check=True, timeout=60,
    )
    return out.stdout


def _env(tmp_path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    env["PROMETHEUS_MULTIPROC_DIR"] = str(tmp_path)
    env["PYTHONPATH"] = str(BACKEND)
    return env


def _value(text: str, prefix: str) -> float:
    for line in text.splitlines():
        if line.startswith(prefix + " ") or line.startswith(prefix + "{") and line.split(" ")[0] == prefix:
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"{prefix} not in scrape:\n{text}")


def test_counters_and_histograms_sum_across_worker_processes(tmp_path):
    env = _env(tmp_path)
    _run(WORKER.format(n=60, status=200), env)
    _run(WORKER.format(n=40, status=503), env)
    text = _run(SCRAPE, env)
    assert _value(text, 'bizboard_http_requests_total{status_class="2xx"}') == 60
    assert _value(text, 'bizboard_http_requests_total{status_class="5xx"}') == 40
    assert _value(text, "bizboard_http_5xx_total") == 40
    assert _value(text, "bizboard_http_latency_ms_count") == 100
    assert _value(text, 'bizboard_business_events_total{event="money_in_receipt_created"}') == 2
    assert 'bizboard_celery_task_duration_seconds_count{status="success",task="sales.tasks.generate_invoice_pdf"} 2.0' in text


def test_a_dead_workers_files_can_be_marked_without_losing_counters(tmp_path):
    env = _env(tmp_path)
    _run(WORKER.format(n=5, status=200), env)
    files = list(tmp_path.glob("*.db"))
    assert files, "multiprocess mode wrote no files"
    pid = int(files[0].stem.rsplit("_", 1)[-1])
    _run(DEAD.format(pid=pid), env)
    text = _run(SCRAPE, env)
    assert _value(text, 'bizboard_http_requests_total{status_class="2xx"}') == 5


def test_without_the_directory_the_process_local_output_is_unchanged():
    from core import ops_metrics

    assert not ops_metrics.multiprocess_enabled()
    assert ops_metrics._mp() is None
