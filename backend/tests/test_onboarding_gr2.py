"""WP-GR2: onboarding checklist steps come from real actions only; card hides at 100% or dismiss."""

import pytest
from django.core.cache import cache

from billing.models import TenantActivation
from billing.onboarding import STEPS, checklist, mark
from insights.models import ShopFloorEvent
from masters.models import Customer, Product, Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _done(company):
    return {s["step"] for s in checklist(company)["steps"] if s["done_at"]}


def test_steps_complete_from_the_real_action_only(tenant_a):
    TenantActivation.objects.filter(company=tenant_a.company).delete()
    cache.clear()
    Customer.objects.create(company=tenant_a.company, name="Walk-in", is_pos_walk_in=True)
    assert "first_party" not in _done(tenant_a.company)  # the POS walk-in row is not a real party
    Customer.objects.create(company=tenant_a.company, name="Real Buyer")
    Supplier.objects.create(company=tenant_a.company, name="Real Seller")
    assert {"first_party"} <= _done(tenant_a.company)
    # The timestamp is the record; no second telemetry row (OG2-E8 no dual write).
    assert not ShopFloorEvent.objects.filter(company=tenant_a.company, journey="onboarding").exists()


def test_the_api_lists_steps_and_the_owner_can_dismiss(tenant_a):
    body = tenant_a.client.get("/api/v1/billing/onboarding/").json()["data"]
    assert [s["step"] for s in body["steps"]] == [s for s, _ in STEPS]
    assert body["visible"] is True
    assert tenant_a.staff_client.post("/api/v1/billing/onboarding/dismiss/").status_code == 403
    assert tenant_a.client.post("/api/v1/billing/onboarding/dismiss/").json()["data"]["visible"] is False


def test_card_hides_at_100_percent(tenant_a):
    for step, _ in STEPS:
        mark(tenant_a.company, step)
    state = checklist(tenant_a.company)
    assert state["done"] == state["total"] and state["visible"] is False


def test_each_step_is_stamped_once(tenant_a):
    Product.objects.create(company=tenant_a.company, name="Item 1")
    first = TenantActivation.objects.get(company=tenant_a.company).first_item_at
    cache.clear()
    Product.objects.create(company=tenant_a.company, name="Item 2")
    assert TenantActivation.objects.get(company=tenant_a.company).first_item_at == first
