"""PJ-WHOLE-ROUTE-OPTIMIZATION — delivery route stop-sequencing (sales.route_optimization).

A wholesale distributor (3 godowns, per fixtures.seed_archetype("wholesale"))
plans a delivery route with several stops, asks for a suggested stop order,
and applies it. This pins two things `tests/test_route_optimization.py`
cannot: that the feature is reachable from a real persona's day (route
created + orders added through the API, exactly as a dispatcher would), and
that the *new* default strategy (NearestNeighborTwoOptStrategy) is genuinely
wired in -- not silently falling back to the older pincode-grouping heuristic
-- by showing the two strategies produce different orders on the same stops.

`DeliveryRouteViewSet` now exposes `suggest-sequence` / `apply-sequence`
actions (see sales/route_views.py) wired to the same `CanCreateSales` gate as
add-orders/remove-stop, so this journey drives every step -- including the
suggest/apply calls -- through the real HTTP API. Endpoint-level coverage
(permission denial on suggest-sequence and apply-sequence individually,
PLANNED-only enforcement, persistence, cross-tenant 404) lives in
tests/test_route_sequencing_api.py; this file keeps its original job of
proving the feature is reachable from a real persona's day end-to-end.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from core.invariants import assert_all_invariants
from inventory.models import MovementType
from inventory.services import InventoryService
from sales.models import DeliveryRouteStop
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_wholesale_owner_route_sequencing_suggest_and_apply(boundary):
    ns = seed_archetype("wholesale")
    company = ns.company
    company.feature_flags = {"ENABLE_ROUTE_OPTIMIZATION": True}
    company.save(update_fields=["feature_flags"])

    oc = ns.owner_client
    wh = ns.warehouses[0]
    product = next(p for p in ns.products if not p.track_batch)
    today_str = timezone.localdate().isoformat()

    InventoryService.post_movement(
        company=company, product=product, warehouse=wh, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("100.000"), unit_cost=Decimal("60.00"), user=ns.owner,
    )

    # Three delivery customers, pincodes chosen so nearest-neighbor+2-opt (the
    # new default) and pincode-ascending grouping (the old fallback) visibly
    # disagree on the order -- proving which one is actually wired in.
    far, mid, near = ns.customers[0], ns.customers[1], ns.customers[2]
    for cust, pin in ((far, "560090"), (mid, "560050"), (near, "560010")):
        cust.pincode = pin
        cust.save(update_fields=["pincode"])

    order_ids = []
    for cust in (far, mid, near):
        so = oc.post(
            "/api/v1/sales/orders/",
            {"customer": cust.id,
             "items": [{"product": product.id, "quantity": "5.000", "unit_price": "100.00", "gst_rate": "18"}]},
            format="json",
        )
        assert so.status_code == 201, so.data
        assert oc.post(f"/api/v1/sales/orders/{so.data['id']}/confirm/").status_code == 200
        order_ids.append(so.data["id"])

    route_resp = oc.post("/api/v1/sales/delivery-routes/", {"route_date": today_str}, format="json")
    assert route_resp.status_code == 201, route_resp.data
    route_id = route_resp.data["id"]

    add_resp = oc.post(
        f"/api/v1/sales/delivery-routes/{route_id}/add-orders/", {"order_ids": order_ids}, format="json",
    )
    assert add_resp.status_code == 200, add_resp.data
    assert len(add_resp.data["stops"]) == 3

    # Capability boundary: P-ACCT has no can_create_sales (ACCOUNTANT default,
    # see accounts.models.CompanyUser.capability_defaults_for_role) and is
    # denied on every mutating delivery-route action, including the new
    # suggest/apply-sequence ones.
    boundary.denied(
        ns.acct_client, "post", f"/api/v1/sales/delivery-routes/{route_id}/add-orders/",
        data={"order_ids": []}, format="json",
    )
    boundary.denied(
        ns.acct_client, "post", f"/api/v1/sales/delivery-routes/{route_id}/suggest-sequence/",
    )
    boundary.denied(
        ns.acct_client, "post", f"/api/v1/sales/delivery-routes/{route_id}/apply-sequence/",
        data={"sequence": []}, format="json",
    )

    # The new default strategy actually runs, and differs from the old
    # pincode-ascending fallback on these stops.
    suggest_resp = oc.post(f"/api/v1/sales/delivery-routes/{route_id}/suggest-sequence/")
    assert suggest_resp.status_code == 200, suggest_resp.data
    default_suggestion = suggest_resp.data
    assert {s["stop_id"] for s in default_suggestion} == set(
        DeliveryRouteStop.objects.filter(route_id=route_id).values_list("id", flat=True)
    )
    default_by_pin = {s["pincode"]: s["sequence"] for s in default_suggestion}
    # Nearest-neighbor starts at the first stop added (far, 560090) and greedily
    # visits the closest remaining pincode at each step: far -> mid -> near.
    assert default_by_pin == {"560090": 1, "560010": 2, "560050": 3}

    pincode_resp = oc.post(
        f"/api/v1/sales/delivery-routes/{route_id}/suggest-sequence/",
        {"strategy_name": "pincode_grouping"}, format="json",
    )
    assert pincode_resp.status_code == 200, pincode_resp.data
    pincode_by_pin = {s["pincode"]: s["sequence"] for s in pincode_resp.data}
    # Pincode grouping sorts by pincode ascending: near -> mid -> far.
    assert pincode_by_pin == {"560010": 1, "560050": 2, "560090": 3}
    assert default_by_pin != pincode_by_pin, (
        "suggest-sequence must be running the new NearestNeighborTwoOptStrategy "
        "default, not silently falling back to pincode grouping"
    )

    # Apply the (default-strategy) suggestion through the API and confirm it persists.
    apply_resp = oc.post(
        f"/api/v1/sales/delivery-routes/{route_id}/apply-sequence/",
        {"sequence": default_suggestion}, format="json",
    )
    assert apply_resp.status_code == 200, apply_resp.data
    stops_by_id = {s.id: s for s in DeliveryRouteStop.objects.filter(route_id=route_id)}
    for seq_stop in default_suggestion:
        assert stops_by_id[seq_stop["stop_id"]].sequence == seq_stop["sequence"]

    assert_all_invariants(company)
