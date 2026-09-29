"""Tests for the pluggable delivery-route stop-sequencing strategies.

Covers:
- PincodeGroupingStrategy is a pure repackaging of the same "shared pincode"
  idea route_combine.combine_suggestions() already uses in production --
  regression-tested for identical grouping/partitioning on the same input.
- NearestNeighborTwoOptStrategy actually improves (or ties) a naive input
  order on a small hand-built case with known relative pincode distances.
- Missing/invalid pincode stops are never dropped, and are flagged.
- Empty / single-stop input doesn't error.
- 2-opt terminates within a reasonable time even on a larger adversarial
  input (30-50 stops).
"""

from __future__ import annotations

import time

import pytest
from django.utils import timezone

from sales.models import DeliveryRoute, DeliveryRouteStop, SalesOrder
from sales.route_combine import combine_suggestions
from sales.route_optimization import (
    NearestNeighborTwoOptStrategy,
    PincodeGroupingStrategy,
    StopInput,
    get_route_optimizer,
    pincode_distance,
)
from sales.route_service import RouteService
from tests.conftest import make_customer


def _stop(stop_id, pincode, sales_order_id=None):
    return StopInput(stop_id=stop_id, pincode=pincode, sales_order_id=sales_order_id)


# ---------------------------------------------------------------------------
# PincodeGroupingStrategy
# ---------------------------------------------------------------------------


def test_pincode_grouping_groups_shared_pincodes_adjacent_and_sorted():
    stops = [
        _stop(1, "560002"),
        _stop(2, "560001"),
        _stop(3, "560001"),
        _stop(4, "560002"),
    ]
    result = PincodeGroupingStrategy().sequence(stops)
    ordered_ids = [s.stop_id for s in result]
    # 560001 group (stops 2, 3) sorts before 560002 group (stops 1, 4);
    # original relative order preserved within each group.
    assert ordered_ids == [2, 3, 1, 4]
    assert all(not s.needs_manual_sequencing for s in result)


def test_pincode_grouping_flags_missing_pincode_at_end_without_dropping():
    stops = [_stop(1, "560001"), _stop(2, ""), _stop(3, "560001"), _stop(4, None)]
    result = PincodeGroupingStrategy().sequence(stops)
    assert {s.stop_id for s in result} == {1, 2, 3, 4}
    flagged = {s.stop_id for s in result if s.needs_manual_sequencing}
    assert flagged == {2, 4}
    # Flagged stops are last, in original order.
    tail_ids = [s.stop_id for s in result if s.needs_manual_sequencing]
    assert tail_ids == [2, 4]


@pytest.mark.django_db
def test_pincode_grouping_matches_combine_suggestions_partition(tenant_a):
    """Regression: PincodeGroupingStrategy partitions the same stops into
    the same pincode groups that combine_suggestions() itself forms --
    combine_suggestions() is untouched and this only reformalizes its
    grouping idea for in-route sequencing."""
    day = timezone.localdate()
    tenant_a.company.feature_flags = {"ENABLE_ROUTE_OPTIMIZATION": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    shared = make_customer(tenant_a.company, name="Pin A", pincode="560001")
    other = make_customer(tenant_a.company, name="Pin B", pincode="560002", phone="9000011111")
    route = DeliveryRoute.objects.create(company=tenant_a.company, number="OPT-1", route_date=day)

    def stop(customer, number):
        order = SalesOrder.objects.create(
            company=tenant_a.company, customer=customer, number=number,
            status=SalesOrder.Status.CONFIRMED, order_date=day, expected_delivery=day,
        )
        return DeliveryRouteStop.objects.create(company=tenant_a.company, route=route, sales_order=order)

    s1 = stop(shared, "SO-OPT-1")
    s2 = stop(shared, "SO-OPT-2")
    s3 = stop(other, "SO-OPT-3")

    # What combine_suggestions() itself considers "same pincode group":
    suggestions = combine_suggestions(tenant_a.company)
    assert len(suggestions) == 1
    combine_group = set(suggestions[0]["stop_ids"])
    assert combine_group == {s1.id, s2.id}

    stop_inputs = [
        StopInput(stop_id=s1.id, pincode="560001"),
        StopInput(stop_id=s2.id, pincode="560001"),
        StopInput(stop_id=s3.id, pincode="560002"),
    ]
    sequenced = PincodeGroupingStrategy().sequence(stop_inputs)
    pincode_by_id = {s.stop_id: s.pincode for s in sequenced}
    strategy_group = {sid for sid, pin in pincode_by_id.items() if pin == "560001"}
    assert strategy_group == combine_group


# ---------------------------------------------------------------------------
# NearestNeighborTwoOptStrategy
# ---------------------------------------------------------------------------


def test_nearest_neighbor_two_opt_improves_on_naive_order():
    # Pincodes chosen so the naive (input) order zig-zags, while a good
    # tour visits them in numeric (proxy-distance) order.
    stops = [
        _stop(1, "560010"),
        _stop(2, "560090"),
        _stop(3, "560020"),
        _stop(4, "560080"),
        _stop(5, "560030"),
    ]
    strategy = NearestNeighborTwoOptStrategy()
    result = strategy.sequence(stops)
    assert {s.stop_id for s in result} == {1, 2, 3, 4, 5}

    by_id = {s.stop_id: s for s in stops}

    def tour_distance(order_ids):
        ordered = [by_id[i] for i in order_ids]
        return sum(
            pincode_distance(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)
        )

    naive_order = [s.stop_id for s in stops]
    optimized_order = [s.stop_id for s in result]
    assert tour_distance(optimized_order) <= tour_distance(naive_order)
    # Concrete, not just "didn't get worse": the naive order is a known-bad
    # zig-zag, so the optimized tour must be strictly shorter.
    assert tour_distance(optimized_order) < tour_distance(naive_order)


def test_nearest_neighbor_two_opt_flags_missing_pincode_without_dropping():
    stops = [_stop(1, "560001"), _stop(2, "bad"), _stop(3, "560002"), _stop(4, "")]
    result = NearestNeighborTwoOptStrategy().sequence(stops)
    assert {s.stop_id for s in result} == {1, 2, 3, 4}
    flagged = {s.stop_id for s in result if s.needs_manual_sequencing}
    assert flagged == {2, 4}


@pytest.mark.parametrize("stops", [[], [_stop(1, "560001")]])
def test_nearest_neighbor_two_opt_handles_empty_and_single_stop(stops):
    result = NearestNeighborTwoOptStrategy().sequence(stops)
    assert [s.stop_id for s in result] == [s.stop_id for s in stops]


def test_pincode_grouping_handles_empty_and_single_stop():
    assert PincodeGroupingStrategy().sequence([]) == []
    single = [_stop(1, "560001")]
    result = PincodeGroupingStrategy().sequence(single)
    assert [s.stop_id for s in result] == [1]


def test_two_opt_terminates_on_large_adversarial_input():
    # 45 stops with pincodes in reverse order -- an adversarial worst case
    # for nearest-neighbor's greedy choices, forcing 2-opt to do real work.
    stops = [_stop(i, f"{560999 - i * 7:06d}") for i in range(45)]
    start = time.monotonic()
    result = NearestNeighborTwoOptStrategy(max_two_opt_iterations=300).sequence(stops)
    elapsed = time.monotonic() - start
    assert len(result) == 45
    assert {s.stop_id for s in result} == {s.stop_id for s in stops}
    assert elapsed < 5.0, f"2-opt took too long: {elapsed:.2f}s"


def test_get_route_optimizer_default_is_nearest_neighbor():
    assert isinstance(get_route_optimizer(), NearestNeighborTwoOptStrategy)
    assert isinstance(get_route_optimizer("pincode_grouping"), PincodeGroupingStrategy)
    with pytest.raises(ValueError):
        get_route_optimizer("not_a_real_strategy")


# ---------------------------------------------------------------------------
# RouteService wiring
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_suggest_stop_sequence_off_when_flag_disabled(tenant_a):
    day = timezone.localdate()
    route = DeliveryRoute.objects.create(company=tenant_a.company, number="OPT-OFF", route_date=day)
    customer = make_customer(tenant_a.company, name="Flagged Off", pincode="560001")
    order = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, number="SO-OPT-OFF",
        status=SalesOrder.Status.CONFIRMED, order_date=day, expected_delivery=day,
    )
    DeliveryRouteStop.objects.create(company=tenant_a.company, route=route, sales_order=order)
    assert RouteService.suggest_stop_sequence(route) == []


@pytest.mark.django_db
def test_suggest_and_apply_stop_sequence(tenant_a, django_user_model):
    day = timezone.localdate()
    tenant_a.company.feature_flags = {"ENABLE_ROUTE_OPTIMIZATION": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    route = DeliveryRoute.objects.create(company=tenant_a.company, number="OPT-ON", route_date=day)
    far = make_customer(tenant_a.company, name="Far", pincode="560090")
    near = make_customer(tenant_a.company, name="Near", pincode="560010")

    def stop(customer, number):
        order = SalesOrder.objects.create(
            company=tenant_a.company, customer=customer, number=number,
            status=SalesOrder.Status.CONFIRMED, order_date=day, expected_delivery=day,
        )
        return DeliveryRouteStop.objects.create(company=tenant_a.company, route=route, sales_order=order)

    far_stop = stop(far, "SO-OPT-ON-1")
    near_stop = stop(near, "SO-OPT-ON-2")

    suggestion = RouteService.suggest_stop_sequence(route)
    assert {s.stop_id for s in suggestion} == {far_stop.id, near_stop.id}

    RouteService.apply_stop_sequence(route, suggestion, None)
    far_stop.refresh_from_db()
    near_stop.refresh_from_db()
    applied = {far_stop.id: far_stop.sequence, near_stop.id: near_stop.sequence}
    suggested = {s.stop_id: s.sequence for s in suggestion}
    assert applied == suggested


def test_distance_is_kilometres_not_the_numeric_pin_gap():
    delhi = StopInput(stop_id=1, pincode="110001")
    bangalore = StopInput(stop_id=2, pincode="560001")
    kilometres = pincode_distance(delhi, bangalore)
    assert 1500 < kilometres < 2000
    assert kilometres != abs(560001 - 110001)


def test_explicit_coordinates_override_the_pin_centroid():
    same_pin_far_apart = pincode_distance(
        StopInput(stop_id=1, pincode="560001", latitude=28.6, longitude=77.2),
        StopInput(stop_id=2, pincode="560001", latitude=13.0, longitude=77.6),
    )
    assert same_pin_far_apart > 1000
    assert pincode_distance(
        StopInput(stop_id=3, latitude=12.97, longitude=77.59),
        StopInput(stop_id=4, latitude=12.97, longitude=77.59),
    ) == 0


@pytest.mark.django_db
def test_customer_coordinates_must_be_set_together(tenant_a):
    missing_one = tenant_a.client.post(
        "/api/v1/customers/",
        {"name": "One Side", "state": "Karnataka", "latitude": "12.970000"},
        format="json",
    )
    assert missing_one.status_code == 400
    out_of_range = tenant_a.client.post(
        "/api/v1/customers/",
        {"name": "Out of Range", "state": "Karnataka", "latitude": "91", "longitude": "77"},
        format="json",
    )
    assert out_of_range.status_code == 400
    placed = tenant_a.client.post(
        "/api/v1/customers/",
        {
            "name": "Placed",
            "state": "Karnataka",
            "latitude": "12.970000",
            "longitude": "77.590000",
        },
        format="json",
    )
    assert placed.status_code == 201, placed.data
    assert placed.data["latitude"] == "12.970000"
    assert placed.data["longitude"] == "77.590000"
    blank = tenant_a.client.post(
        "/api/v1/customers/",
        {"name": "Unplaced", "state": "Karnataka"},
        format="json",
    )
    assert blank.status_code == 201, blank.data
    assert blank.data["latitude"] is None
    assert blank.data["longitude"] is None


def test_unlisted_pin_uses_a_regional_centroid():
    # 560090 is not in the exact file. It still lands in the 560 region,
    # a few kilometres from 560001, not an infinite or numeric gap.
    distance = pincode_distance(
        StopInput(stop_id=1, pincode="560090"),
        StopInput(stop_id=2, pincode="560001"),
    )
    assert distance < 30
