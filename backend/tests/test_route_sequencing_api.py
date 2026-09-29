"""HTTP-level tests for the delivery-route stop-sequencing endpoints:

    POST /api/v1/sales/delivery-routes/{id}/suggest-sequence/
    POST /api/v1/sales/delivery-routes/{id}/apply-sequence/

Added because `RouteService.suggest_stop_sequence` / `apply_stop_sequence`
(tested directly in tests/test_route_optimization.py, and only reachable via
raw RouteService calls -- see the gap noted in
tests/personas/test_pj_route_sequencing.py) previously had no HTTP surface at
all. This file covers the view/permission/serialization layer on top of
`DeliveryRouteViewSet`:

- CanCreateSales gating (same gate as add-orders/remove-stop).
- The new default strategy (NearestNeighborTwoOptStrategy) is actually wired
  in end-to-end through the endpoint, not silently falling back to
  pincode-grouping.
- apply-sequence persists the new stop order.
- apply-sequence is rejected (clean 400, not 500) on a non-PLANNED route.
- Cross-tenant isolation (404, not 403, so existence isn't leaked).
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CompanyUser
from sales.models import DeliveryRoute, DeliveryRouteStop, SalesOrder
from sales.route_service import RouteService
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def _make_route_with_stops(tenant, pincodes, number):
    day = timezone.localdate()
    route = DeliveryRoute.objects.create(company=tenant.company, number=number, route_date=day)
    stops = []
    for i, pin in enumerate(pincodes):
        customer = make_customer(tenant.company, name=f"Cust {number}-{i}", pincode=pin)
        order = SalesOrder.objects.create(
            company=tenant.company, customer=customer, number=f"SO-{number}-{i}",
            status=SalesOrder.Status.CONFIRMED, order_date=day, expected_delivery=day,
        )
        stops.append(DeliveryRouteStop.objects.create(company=tenant.company, route=route, sales_order=order))
    return route, stops


def _accountant_client(tenant, django_user_model, email="acct-route-seq@example.com"):
    # ACCOUNTANT has can_create_sales=False by default (see
    # accounts.models.CompanyUser.capability_defaults_for_role) -- the same
    # role tests/personas/test_pj_route_sequencing.py uses for its
    # CanCreateSales boundary check on add-orders. User.USERNAME_FIELD is
    # "email" (no username field on this custom User model).
    user = django_user_model.objects.create_user(email=email, password="x")
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.ACCOUNTANT, is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _enable_optimizer(tenant):
    tenant.company.feature_flags = {"ENABLE_ROUTE_OPTIMIZATION": True}
    tenant.company.save(update_fields=["feature_flags"])


def test_suggest_sequence_uses_default_strategy_and_differs_from_pincode_grouping(tenant_a):
    _enable_optimizer(tenant_a)
    # Pincodes chosen (as in tests/test_route_optimization.py and the PJ
    # persona journey) so nearest-neighbor+2-opt (new default) and
    # pincode-ascending grouping (old fallback) visibly disagree.
    route, stops = _make_route_with_stops(tenant_a, ["560090", "560050", "560010"], "ROUTE-API-1")

    resp = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/")
    assert resp.status_code == 200, resp.data
    suggestion = resp.data
    assert {s["stop_id"] for s in suggestion} == {s.id for s in stops}
    default_by_pin = {s["pincode"]: s["sequence"] for s in suggestion}
    # Tour starts at the first stop (560090). Great-circle distance then
    # visits 560010 before 560050. Numeric PIN order would do the reverse.
    assert default_by_pin == {"560090": 1, "560010": 2, "560050": 3}
    assert all(s["needs_manual_sequencing"] is False for s in suggestion)

    pincode_resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/",
        {"strategy_name": "pincode_grouping"},
        format="json",
    )
    assert pincode_resp.status_code == 200, pincode_resp.data
    pincode_by_pin = {s["pincode"]: s["sequence"] for s in pincode_resp.data}
    assert pincode_by_pin == {"560010": 1, "560050": 2, "560090": 3}
    assert default_by_pin != pincode_by_pin, (
        "suggest-sequence must run the new NearestNeighborTwoOptStrategy default, "
        "not silently fall back to pincode grouping"
    )


def test_suggest_sequence_denied_for_accountant(tenant_a, django_user_model):
    _enable_optimizer(tenant_a)
    route, _stops = _make_route_with_stops(tenant_a, ["560001", "560002"], "ROUTE-API-2")
    acct_client = _accountant_client(tenant_a, django_user_model, "acct-route-seq-suggest@example.com")

    resp = acct_client.post(f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/")
    assert resp.status_code == 403, resp.data


def test_apply_sequence_denied_for_accountant(tenant_a, django_user_model):
    _enable_optimizer(tenant_a)
    route, stops = _make_route_with_stops(tenant_a, ["560001", "560002"], "ROUTE-API-3")
    acct_client = _accountant_client(tenant_a, django_user_model, "acct-route-seq-apply@example.com")

    resp = acct_client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/apply-sequence/",
        {"sequence": [{"stop_id": stops[0].id, "sequence": 1}, {"stop_id": stops[1].id, "sequence": 2}]},
        format="json",
    )
    assert resp.status_code == 403, resp.data


def test_apply_sequence_persists_new_stop_order(tenant_a):
    _enable_optimizer(tenant_a)
    route, stops = _make_route_with_stops(tenant_a, ["560090", "560050", "560010"], "ROUTE-API-4")

    suggest_resp = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/")
    assert suggest_resp.status_code == 200, suggest_resp.data
    suggestion = suggest_resp.data

    # Echo the suggestion back verbatim, as a real dispatcher UI would.
    apply_resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/apply-sequence/",
        {"sequence": suggestion},
        format="json",
    )
    assert apply_resp.status_code == 200, apply_resp.data

    expected = {s["stop_id"]: s["sequence"] for s in suggestion}
    for stop in stops:
        assert DeliveryRouteStop.objects.get(pk=stop.id).sequence == expected[stop.id]


def test_apply_sequence_accepts_minimal_stop_id_sequence_pairs(tenant_a):
    _enable_optimizer(tenant_a)
    route, stops = _make_route_with_stops(tenant_a, ["560001", "560002"], "ROUTE-API-5")

    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/apply-sequence/",
        {"sequence": [{"stop_id": stops[0].id, "sequence": 2}, {"stop_id": stops[1].id, "sequence": 1}]},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert DeliveryRouteStop.objects.get(pk=stops[0].id).sequence == 2
    assert DeliveryRouteStop.objects.get(pk=stops[1].id).sequence == 1


def test_apply_sequence_rejected_when_route_not_planned(tenant_a):
    _enable_optimizer(tenant_a)
    route, stops = _make_route_with_stops(tenant_a, ["560001", "560002"], "ROUTE-API-6")
    route = RouteService.start_route(route, tenant_a.owner)
    assert route.status == DeliveryRoute.Status.IN_TRANSIT

    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/apply-sequence/",
        {"sequence": [{"stop_id": stops[0].id, "sequence": 2}, {"stop_id": stops[1].id, "sequence": 1}]},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    error = resp.data.get("error") or {}
    assert "PLANNED" in (error.get("message") or "")
    # No partial apply -- original sequence values untouched.
    assert DeliveryRouteStop.objects.get(pk=stops[0].id).sequence == stops[0].sequence
    assert DeliveryRouteStop.objects.get(pk=stops[1].id).sequence == stops[1].sequence


def test_apply_sequence_rejected_on_completed_route(tenant_a):
    _enable_optimizer(tenant_a)
    route, stops = _make_route_with_stops(tenant_a, ["560001", "560002"], "ROUTE-API-7")
    route = RouteService.start_route(route, tenant_a.owner)
    route = RouteService.complete_route(route, tenant_a.owner)
    assert route.status == DeliveryRoute.Status.COMPLETED

    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/apply-sequence/",
        {"sequence": [{"stop_id": stops[0].id, "sequence": 1}]},
        format="json",
    )
    assert resp.status_code == 400, resp.data


def test_suggest_and_apply_sequence_404_for_other_tenant(tenant_a, tenant_b):
    _enable_optimizer(tenant_a)
    route, stops = _make_route_with_stops(tenant_a, ["560001", "560002"], "ROUTE-API-8")

    resp = tenant_b.client.post(f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/")
    assert resp.status_code == 404, resp.data

    resp2 = tenant_b.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/apply-sequence/",
        {"sequence": [{"stop_id": stops[0].id, "sequence": 1}]},
        format="json",
    )
    assert resp2.status_code == 404, resp2.data
