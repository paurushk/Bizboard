"""Pluggable delivery-route stop-sequencing strategies.

`RouteOptimizer.sequence()` is a pure function of `(stops) -> sequenced
stops` -- it does not touch the DB, the request/response cycle, or
`RouteService`. That is deliberate: today it runs inline (see
`RouteService.suggest_stop_sequence`), but if routes routinely grow to
dozens+ stops and inline sequencing shows up as real, *measured* request
latency, this can move into a Celery task with no rewrite -- just call the
same `sequence()` from the task body. Don't guess a stop-count threshold
ahead of that measurement.

Two strategies are provided, both gated behind the existing
`ENABLE_ROUTE_OPTIMIZATION` flag by their caller (`RouteService`):

- `PincodeGroupingStrategy` formalizes the heuristic that
  `sales.route_combine.combine_suggestions()` already uses in production
  (same-day stops that share a customer pincode are worth handling
  together) as a `RouteOptimizer`. It does not change that heuristic's
  logic -- `combine_suggestions()` itself is untouched -- it just packages
  the same "shared pincode -> travel together" idea behind the strategy
  interface, applied to ordering stops within one route rather than to
  suggesting merges across routes.
- `NearestNeighborTwoOptStrategy` is a real, from-scratch single-vehicle
  tour heuristic (nearest-neighbor construction + capped 2-opt local
  search). It is intentionally unconstrained: no vehicle capacity, no time
  windows, no multi-vehicle support. A full constrained VRP solver is out
  of scope here by design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Protocol

from sales.pin_centroids import coordinates_for_stop


@dataclass(frozen=True)
class StopInput:
    """The subset of a `DeliveryRouteStop` (+ its order/customer) a
    strategy needs. Latitude and longitude, when the customer has them,
    win over the PIN centroid lookup.
    """

    stop_id: int
    pincode: str = ""
    delivery_address: str = ""
    sales_order_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class SequencedStop:
    """One stop's place in a suggested route order.

    `needs_manual_sequencing=True` marks a stop the strategy could not
    place with any confidence (no usable pincode). It is never dropped --
    it is appended at the end of the sequence -- but this flag lets a
    caller tell "sequenced normally" apart from "couldn't be placed" and,
    e.g., surface it to the dispatcher differently.
    """

    stop_id: int
    sequence: int
    pincode: str = ""
    needs_manual_sequencing: bool = False


class RouteOptimizer(Protocol):
    def sequence(self, stops: list[StopInput]) -> list[SequencedStop]: ...


def _has_usable_pincode(stop: StopInput) -> bool:
    """A pincode is "usable" if it's a non-empty, all-digit string. Indian
    PINs are 6 digits, but we don't hard-require exactly 6 here -- any
    non-digit value (blank, garbled data-entry, placeholder text) is
    treated the same way: not usable, so the stop is never silently
    dropped, only flagged `needs_manual_sequencing` and placed at the end.
    """
    return (stop.pincode or "").strip().isdigit()


def _split_placeable(stops: list[StopInput]) -> tuple[list[StopInput], list[StopInput]]:
    placeable = [s for s in stops if _has_usable_pincode(s)]
    unplaceable = [s for s in stops if not _has_usable_pincode(s)]
    return placeable, unplaceable


def _append_unplaceable(
    result: list[SequencedStop], unplaceable: list[StopInput], next_sequence: int,
) -> None:
    for stop in unplaceable:
        result.append(
            SequencedStop(
                stop_id=stop.stop_id,
                sequence=next_sequence,
                pincode="",
                needs_manual_sequencing=True,
            )
        )
        next_sequence += 1


class PincodeGroupingStrategy:
    """Same-pincode-stops-travel-together, formalized as a RouteOptimizer.

    Stops are grouped by (stripped) pincode, groups are ordered by pincode
    ascending (mirroring the `sorted(groups.items())` used in
    `route_combine.combine_suggestions()`), and stops within a group keep
    their original relative order. Stops with no usable pincode are
    appended at the end, flagged `needs_manual_sequencing`.
    """

    def sequence(self, stops: list[StopInput]) -> list[SequencedStop]:
        if not stops:
            return []
        placeable, unplaceable = _split_placeable(stops)
        groups: dict[str, list[StopInput]] = {}
        for stop in placeable:
            pin = stop.pincode.strip()
            groups.setdefault(pin, []).append(stop)

        result: list[SequencedStop] = []
        seq = 1
        for pin in sorted(groups):
            for stop in groups[pin]:
                result.append(SequencedStop(stop_id=stop.stop_id, sequence=seq, pincode=pin))
                seq += 1
        _append_unplaceable(result, unplaceable, seq)
        return result


# Distance is pluggable/injectable (see NearestNeighborTwoOptStrategy) so the
# approximation below can be swapped for a real one without touching the
# tour-construction algorithm.
DistanceFn = Callable[[StopInput, StopInput], float]


def haversine_km(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    """Great-circle kilometres. This is road-distance's geographic stand-in:
    no live map API is required, and two nearby PINs no longer look far
    apart just because their numbers differ."""
    radius = 6371.0
    lat1, lon1 = origin
    lat2, lon2 = destination
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    chord = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(chord))


def pincode_distance(a: StopInput, b: StopInput) -> float:
    """Kilometres between two stops.

    Uses the stop's own latitude and longitude when both are set.
    Otherwise uses the Indian PIN centroid file, falling back to the
    longest shared prefix so an unlisted PIN still sits in its region.
    """
    origin = coordinates_for_stop(a)
    destination = coordinates_for_stop(b)
    if origin is None or destination is None:
        return float("inf")
    return haversine_km(origin, destination)


class NearestNeighborTwoOptStrategy:
    """Single-vehicle tour heuristic: nearest-neighbor construction, then
    capped 2-opt local search.

    Unconstrained by design -- no vehicle capacity, no time windows, no
    multi-vehicle support. That's an explicit scope boundary, not an
    oversight: a full constrained VRP solver is not wanted here.

    `distance_fn` defaults to great-circle kilometres from PIN centroids
    or explicit coordinates. It stays injectable so a road-distance
    provider can replace it without touching the algorithm.

    `max_two_opt_iterations` caps total 2-opt swap attempts (not just
    passes) so this stays fast enough to run inline for now, and so it
    provably terminates even on adversarial/large input.
    """

    def __init__(
        self,
        distance_fn: DistanceFn = pincode_distance,
        max_two_opt_iterations: int = 300,
    ):
        self._distance = distance_fn
        self._max_iterations = max_two_opt_iterations

    def sequence(self, stops: list[StopInput]) -> list[SequencedStop]:
        if not stops:
            return []
        placeable = [stop for stop in stops if coordinates_for_stop(stop) is not None]
        unplaceable = [stop for stop in stops if coordinates_for_stop(stop) is None]
        if len(placeable) <= 1:
            tour = placeable
        else:
            tour = self._nearest_neighbor(placeable)
            tour = self._two_opt(tour)

        result: list[SequencedStop] = []
        seq = 1
        for stop in tour:
            result.append(SequencedStop(stop_id=stop.stop_id, sequence=seq, pincode=stop.pincode))
            seq += 1
        _append_unplaceable(result, unplaceable, seq)
        return result

    def _nearest_neighbor(self, stops: list[StopInput]) -> list[StopInput]:
        remaining = list(stops)
        tour = [remaining.pop(0)]
        while remaining:
            last = tour[-1]
            nearest_idx = min(
                range(len(remaining)), key=lambda i: self._distance(last, remaining[i])
            )
            tour.append(remaining.pop(nearest_idx))
        return tour

    def _tour_distance(self, tour: list[StopInput]) -> float:
        return sum(self._distance(tour[i], tour[i + 1]) for i in range(len(tour) - 1))

    def _two_opt(self, tour: list[StopInput]) -> list[StopInput]:
        """Standard 2-opt: for candidate edges (i-1,i) and (j,j+1), evaluate
        the swap by its incremental distance delta (four `_distance` calls)
        rather than reconstructing the whole candidate tour and re-summing
        every edge in it (`_tour_distance`, O(n)) — the two are equivalent
        (`candidate_distance < best_distance` iff `delta < 0`) but the delta
        form is O(1) per candidate instead of O(n), which matters once
        `_max_iterations` candidates are actually being evaluated on a
        route with more than a handful of stops. The candidate list is only
        ever built when a swap is actually accepted, not for every swap
        considered.
        """
        n = len(tour)
        if n < 4:
            return tour
        best = list(tour)
        best_distance = self._tour_distance(best)
        iterations = 0
        improved = True
        while improved and iterations < self._max_iterations:
            improved = False
            for i in range(1, n - 2):
                for j in range(i + 1, n - 1):
                    iterations += 1
                    if iterations >= self._max_iterations:
                        improved = False
                        break
                    removed = self._distance(best[i - 1], best[i]) + self._distance(best[j], best[j + 1])
                    added = self._distance(best[i - 1], best[j]) + self._distance(best[i], best[j + 1])
                    delta = added - removed
                    if delta < -1e-9:
                        best = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                        best_distance += delta
                        improved = True
                if iterations >= self._max_iterations:
                    break
        return best


DEFAULT_STRATEGY_NAME = "nearest_neighbor_2opt"

_STRATEGY_REGISTRY: dict[str, RouteOptimizer] = {
    "nearest_neighbor_2opt": NearestNeighborTwoOptStrategy(),
    "pincode_grouping": PincodeGroupingStrategy(),
}


def get_route_optimizer(name: str | None = None) -> RouteOptimizer:
    """Look up an active strategy by name. Defaults to the new
    NearestNeighborTwoOptStrategy; `"pincode_grouping"` remains available
    as the simpler fallback. Callers should only ever surface one
    strategy's suggestion to the dispatcher at a time.
    """
    key = name or DEFAULT_STRATEGY_NAME
    try:
        return _STRATEGY_REGISTRY[key]
    except KeyError as exc:
        raise ValueError(f"Unknown route optimization strategy: {key!r}") from exc
