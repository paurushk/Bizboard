"""QOS-0022 — the standalone invariant-sweep command a restore drill runs
against a restored database (no pytest fixtures, no INVARIANTS_STRICT)."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from core.invariants import InvariantViolation
from inventory.models import StockBalance
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_check_invariants_clean_company_passes(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "10", unit_cost="60")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    out = StringIO()
    call_command("check_invariants", stdout=out)
    assert f"ok    company={tenant_a.company.id}" in out.getvalue()
    assert "All " in out.getvalue()


def test_check_invariants_single_company_filter(tenant_a, tenant_b):
    out = StringIO()
    call_command("check_invariants", company=tenant_a.company.id, stdout=out)
    body = out.getvalue()
    assert f"company={tenant_a.company.id}" in body
    assert f"company={tenant_b.company.id}" not in body


def test_check_invariants_raises_and_reports_a_broken_company(tenant_a):
    """QOS-0022: a corrupted restore (balance drifted from movements) must
    fail the drill loudly, not print 'ok' and exit 0."""
    product = make_product(tenant_a.company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "10", unit_cost="60")
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    balance.on_hand = Decimal("999999")
    balance.save(update_fields=["on_hand"])

    out = StringIO()
    with pytest.raises(InvariantViolation):
        call_command("check_invariants", company=tenant_a.company.id, stdout=out)
    assert f"FAIL  company={tenant_a.company.id}" in out.getvalue()


def test_nightly_invariants_beat_is_registered_and_dry_runs(tenant_a):
    from django.conf import settings

    from core.tasks import nightly_invariants_task

    assert "core-nightly-invariants" in settings.CELERY_BEAT_SCHEDULE
    assert (
        settings.CELERY_BEAT_SCHEDULE["core-nightly-invariants"]["task"]
        == "core.tasks.nightly_invariants_task"
    )
    result = nightly_invariants_task.apply()
    assert result.successful(), result.result
    payload = result.result
    assert payload["failed"] == 0
    assert payload["checked"] >= 1
