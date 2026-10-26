"""QOS-0012 / G-10: the e-invoice submit chain through a real Celery broker, not eager mode.

settings_test forces CELERY_TASK_ALWAYS_EAGER, so the CI "real-broker" lane never sent a task
through Redis. These tests switch the app to a real broker (REAL_BROKER_URL, e.g.
redis://localhost:6379/1), run an in-process worker against the same test database, and assert
the user-visible end state when the IRP fails once (Celery autoretry with backoff, delivered by the
broker) and when the same submit is delivered twice (IRN idempotency).

Skipped unless REAL_BROKER_URL is set; the real-broker CI job sets it.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

from tests.errors.test_webhook_and_async_contracts import _completed_gst_invoice

BROKER = os.environ.get("REAL_BROKER_URL", "")

pytestmark = [
    pytest.mark.skipif(not BROKER, reason="REAL_BROKER_URL not set: no real broker to run against"),
    pytest.mark.django_db(transaction=True),
    pytest.mark.no_invariant_check,
]

IRN = "IRN" + "7" * 61


@pytest.fixture
def live_worker(settings):
    from celery.contrib.testing.worker import start_worker

    from config.celery import app

    settings.CELERY_TASK_ALWAYS_EAGER = False
    keys = ("task_always_eager", "broker_url", "result_backend", "broker_transport_options",
            "broker_connection_timeout", "result_backend_transport_options")
    keys = keys + tuple(f"CELERY_{k.upper()}" for k in keys)
    saved = {k: app.conf.get(k) for k in keys}
    # Production fails fast on a down broker (2 s); a test worker on a busy CI box needs slack.
    slack = {"socket_connect_timeout": 10, "socket_timeout": 30}
    new = dict(
        task_always_eager=False, broker_url=BROKER, result_backend=BROKER, broker_connection_timeout=10,
        broker_transport_options=slack, result_backend_transport_options=slack,
    )
    # The app reads Django settings under the CELERY_ namespace; set both spellings.
    app.conf.update(**new, **{f"CELERY_{k.upper()}": v for k, v in new.items()})
    _drop_cached_connections(app)
    try:
        with start_worker(app, pool="solo", perform_ping_check=False, shutdown_timeout=30):
            yield app
    finally:
        app.conf.update(**saved)
        _drop_cached_connections(app)


def _drop_cached_connections(app):
    # The app caches its broker pool, producer pool and result backend from the first use; a
    # config change after that is ignored unless these are dropped.
    import threading

    app._pool = None
    app.amqp._producer_pool = None
    app._local = threading.local()


def _irp(submit_side_effect):
    adapter = mock.Mock()
    adapter.lookup_by_doc.return_value = None
    adapter.submit.side_effect = submit_side_effect
    return adapter


def _result():
    return mock.Mock(irn=IRN, ack_no="AN-1", ack_date="2026-10-23", einvoice_qr="QR")


def test_a_failed_irp_call_is_retried_through_the_broker_and_ends_generated(live_worker, tenant_a):
    from sales.models import SalesInvoice
    from sales.tasks import submit_einvoice_async

    iid = _completed_gst_invoice(tenant_a)
    adapter = _irp([RuntimeError("IRP gateway 503"), _result()])
    with mock.patch("core.services.gsp_adapters.get_irp_adapter", return_value=adapter), \
         mock.patch("core.services.gsp_adapters.verify_irn_result", return_value=None):
        out = submit_einvoice_async.delay(iid, company_id=tenant_a.company.id).get(timeout=60)

    assert out == {"status": "generated", "irn": IRN}
    assert adapter.submit.call_count == 2  # the retry really went back through the broker
    inv = SalesInvoice.objects.get(pk=iid)
    assert inv.einvoice_status == SalesInvoice.EInvoiceStatus.GENERATED
    assert inv.irn == IRN and inv.einvoice_error == ""


def test_the_same_submit_delivered_twice_generates_one_irn(live_worker, tenant_a):
    from core.models import AuditEvent
    from sales.models import SalesInvoice
    from sales.tasks import submit_einvoice_async

    iid = _completed_gst_invoice(tenant_a)
    adapter = _irp([_result(), _result()])
    with mock.patch("core.services.gsp_adapters.get_irp_adapter", return_value=adapter), \
         mock.patch("core.services.gsp_adapters.verify_irn_result", return_value=None):
        first = submit_einvoice_async.delay(iid, company_id=tenant_a.company.id)
        second = submit_einvoice_async.delay(iid, company_id=tenant_a.company.id)
        outcomes = sorted(r.get(timeout=60)["status"] for r in (first, second))

    assert outcomes == ["already_generated", "generated"]
    assert adapter.submit.call_count == 1
    assert SalesInvoice.objects.get(pk=iid).irn == IRN
    assert AuditEvent.objects.filter(entity_id=str(iid), description="einvoice.submitted_async").count() == 1
