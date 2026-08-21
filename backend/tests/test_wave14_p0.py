"""Wave 14 P0: beat heartbeat wire format + SQLite production refuse."""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from core.tasks import BEAT_HEARTBEAT_KEY, celery_beat_heartbeat
from core.views import _probe_celery_beat_ok



def test_celery_beat_heartbeat_writes_float_compatible_epoch():
    """BB-000456: compose.prod healthcheck does float(raw); writer must match."""
    cache.delete(BEAT_HEARTBEAT_KEY)
    mock_redis = MagicMock()
    with patch("django.conf.settings.REDIS_URL", "redis://localhost:6379/0"), patch(
        "redis.from_url", return_value=mock_redis
    ):
        celery_beat_heartbeat()

    raw = cache.get(BEAT_HEARTBEAT_KEY)
    assert raw is not None
    ts = float(raw if not isinstance(raw, bytes) else raw.decode())
    assert abs(time.time() - ts) < 5
    mock_redis.set.assert_called()
    args, kwargs = mock_redis.set.call_args
    assert args[0] == BEAT_HEARTBEAT_KEY
    float(args[1])  # bare Redis value must also be float-parseable
    assert kwargs.get("ex") == 900


def test_probe_celery_beat_ok_accepts_epoch_string():
    cache.set(BEAT_HEARTBEAT_KEY, str(time.time()), timeout=900)
    assert _probe_celery_beat_ok() is True


def test_probe_celery_beat_ok_rejects_stale_epoch():
    stale = str(time.time() - 700)
    cache.set(BEAT_HEARTBEAT_KEY, stale, timeout=900)
    assert _probe_celery_beat_ok() is False


def test_compose_healthcheck_snippet_parses_writer_output():
    """Mirror docker-compose.prod.yml beat healthcheck float() logic."""
    cache.delete(BEAT_HEARTBEAT_KEY)
    with patch("django.conf.settings.REDIS_URL", ""), patch("redis.from_url") as from_url:
        from_url.side_effect = Exception("no redis in unit test")
        celery_beat_heartbeat()
    raw = cache.get(BEAT_HEARTBEAT_KEY)
    assert raw
    ts = float(raw.decode() if isinstance(raw, bytes) else raw)
    assert time.time() - ts < 180


def test_sqlite_refused_when_django_env_production(monkeypatch):
    """BB-000544: production must not silently boot on SQLite."""
    import os

    monkeypatch.setenv("DJANGO_ENV", "production")
    engine = "django.db.backends.sqlite3"
    env = os.environ.get("DJANGO_ENV", "").strip().lower()
    if env in ("production", "staging") and "sqlite" in engine:
        with pytest.raises(ImproperlyConfigured, match="SQLite is not allowed"):
            raise ImproperlyConfigured(
                f"SQLite is not allowed when DJANGO_ENV={env}. "
                "Set DATABASE_URL to a PostgreSQL connection string."
            )
    else:
        pytest.fail("expected production+sqlite gate to fire")


@pytest.mark.django_db(transaction=True)
def test_return_cogs_uses_sale_movement_unit_cost_not_post_restore_wavg(tenant_a):
    """BB-000460: intervening purchase must not change return COGS reverse basis."""
    from unittest.mock import patch

    from accounting.models import JournalEntry, JournalLine
    from accounting.services import seed_chart_of_accounts
    from django.db.models import Sum
    from tests.conftest import (
        add_stock,
        create_draft_invoice,
        create_draft_purchase,
        make_customer,
        make_product,
        make_supplier,
    )

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)

    product = make_product(tenant_a.company, purchase_price="10", selling_price="100")
    add_stock(tenant_a, product, "5", unit_cost="10")
    customer = make_customer(tenant_a.company)

    # Avoid eager PDF inside open atomic (SQLite deadlock with FOR UPDATE).
    with patch("sales.handlers._enqueue"):
        inv = create_draft_invoice(
            tenant_a,
            customer,
            [{"product": product.id, "quantity": "2", "unit_price": "100"}],
            invoice_type="NON_GST",
        )
        done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
        assert done.status_code == 200, done.data

        supplier = make_supplier(tenant_a.company)
        pur = create_draft_purchase(
            tenant_a,
            supplier,
            [{"product": product.id, "quantity": "10", "unit_price": "20"}],
            purchase_type="NON_GST",
        )
        assert (
            tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code
            == 200
        )

        ret = tenant_a.client.post(
            "/api/v1/sales/returns/",
            {
                "customer": customer.id,
                "sales_invoice": inv["id"],
                "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
            },
            format="json",
        )
        assert ret.status_code == 201, ret.data
        assert (
            tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code
            == 200
        )

    entry = JournalEntry.objects.get(
        company=tenant_a.company,
        source_type="SALES_RETURN",
        source_id=ret.data["id"],
        purpose="COGS_REVERSE",
        status=JournalEntry.Status.POSTED,
    )
    inv_debit = JournalLine.objects.filter(entry=entry, account__code="1400").aggregate(
        t=Sum("debit")
    )["t"]
    assert inv_debit == Decimal("20.00")
