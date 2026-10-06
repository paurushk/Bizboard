"""Latency histogram on /metrics (perf programme: read p95 from the server too)."""

from __future__ import annotations

import os
import re

import pytest

from core import ops_metrics

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset():
    ops_metrics._BUCKET_COUNTS[:] = [0] * len(ops_metrics._BUCKET_COUNTS)
    ops_metrics._DURATION_COUNT = 0
    ops_metrics._DURATION_MS_SUM = 0
    yield


def _bucket(text, le):
    m = re.search(rf'bizboard_http_latency_ms_bucket\{{le="{re.escape(str(le))}",pid="{os.getpid()}"\}} (\d+)', text)
    assert m, f"bucket {le} missing"
    return int(m.group(1))


def test_buckets_are_cumulative_and_inf_equals_count():
    for d in (10, 60, 400, 790, 3000, 9000, 40000):
        ops_metrics.record_http_result(status=200, duration_ms=d)
    text = ops_metrics.render_prometheus()
    assert _bucket(text, 50) == 1          # 10
    assert _bucket(text, 100) == 2         # + 60
    assert _bucket(text, 500) == 3         # + 400
    assert _bucket(text, 800) == 4         # + 790   (the Complete SLO edge)
    assert _bucket(text, 5000) == 5        # + 3000
    assert _bucket(text, 8000) == 5        # 9000 is over the 8 s gate
    assert _bucket(text, 30000) == 6       # + 9000
    assert _bucket(text, "+Inf") == 7      # + 40000
    assert f'bizboard_http_latency_ms_count{{pid="{os.getpid()}"}} 7' in text


def test_boundary_value_lands_in_its_own_bucket():
    ops_metrics.record_http_result(status=200, duration_ms=800)
    text = ops_metrics.render_prometheus()
    assert _bucket(text, 800) == 1 and _bucket(text, 500) == 0


def test_histogram_family_does_not_reuse_the_counter_names():
    text = ops_metrics.render_prometheus()
    # The pre-existing unlabelled counters stay as they are...
    assert "# TYPE bizboard_http_request_duration_ms_sum counter" in text
    # ...and the histogram family must not redeclare them under another TYPE.
    assert "# TYPE bizboard_http_request_duration_ms histogram" not in text
    assert "# TYPE bizboard_http_latency_ms histogram" in text


# --- end to end: real requests through the middleware reach /metrics ------------------------

def _metrics(client, settings):
    settings.METRICS_TOKEN = "t0ken"
    return client.get("/metrics/", HTTP_AUTHORIZATION="Bearer t0ken")


def _count(text):
    m = re.search(rf'bizboard_http_latency_ms_count\{{pid="{os.getpid()}"\}} (\d+)', text)
    assert m, "histogram count line missing"
    return int(m.group(1))


def test_real_requests_are_recorded_in_the_histogram(tenant_a, settings):
    before = _count(_metrics(tenant_a.client, settings).content.decode())
    for _ in range(3):
        assert tenant_a.client.get("/api/v1/health/").status_code in (200, 503)
    after = _count(_metrics(tenant_a.client, settings).content.decode())
    # 3 health calls + the first /metrics call itself are all timed requests
    assert after - before >= 3


def test_every_timed_request_lands_in_exactly_one_bucket(tenant_a, settings):
    tenant_a.client.get("/api/v1/health/")
    text = _metrics(tenant_a.client, settings).content.decode()
    pid = os.getpid()
    inf = int(re.search(rf'le="\+Inf",pid="{pid}"\}} (\d+)', text).group(1))
    assert inf == _count(text)
    # buckets are cumulative, so they must be non-decreasing and end at +Inf
    vals = [int(v) for v in re.findall(rf'bizboard_http_latency_ms_bucket\{{le="[^"]+",pid="{pid}"\}} (\d+)', text)]
    assert vals == sorted(vals) and vals[-1] == inf


def test_metrics_endpoint_still_requires_the_token(tenant_a, settings):
    settings.METRICS_TOKEN = "t0ken"
    assert tenant_a.client.get("/metrics/").status_code == 401
    assert tenant_a.client.get("/metrics/", HTTP_AUTHORIZATION="Bearer wrong").status_code == 401
    settings.METRICS_TOKEN = ""
    assert tenant_a.client.get("/metrics/", HTTP_AUTHORIZATION="Bearer anything").status_code == 404


def test_5xx_responses_are_counted_in_the_5xx_counter():
    before = ops_metrics._HTTP_5XX
    ops_metrics.record_http_result(status=503, duration_ms=12)
    ops_metrics.record_http_result(status=200, duration_ms=12)
    assert ops_metrics._HTTP_5XX == before + 1


def test_edges_include_the_slo_boundaries():
    """The SLO tables (500 dashboard, 800 complete, 2000 list, 8000 gate) must be bucket edges,
    otherwise histogram_quantile cannot answer 'are we inside the SLO'."""
    for edge in (500, 800, 2000, 8000):
        assert edge in ops_metrics.LATENCY_BUCKETS_MS
    assert list(ops_metrics.LATENCY_BUCKETS_MS) == sorted(ops_metrics.LATENCY_BUCKETS_MS)
