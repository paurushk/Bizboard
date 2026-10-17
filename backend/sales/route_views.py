from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.permissions import CanCancelDocuments, CanCreateSales, CanViewSalesSurfaces, HasCompany
from core.viewsets import CompanyScopedViewSet

from .challan_return import ChallanReturnService
from .models import DeliveryChallanReturn, DeliveryRoute, DeliveryRouteStop
from .route_optimization import SequencedStop
from .route_serializers import DeliveryChallanReturnSerializer, DeliveryRouteSerializer, SequencedStopSerializer
from .route_planning import planning_candidates, viewer_for
from .route_service import RouteService


def _stop_cap(raw):
    """Positive whole number, or None when the caller omitted the cap."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise BusinessRuleError("stop_cap must be a positive integer.")
    if isinstance(raw, int):
        cap = raw
    elif isinstance(raw, float):
        if not raw.is_integer():
            raise BusinessRuleError("stop_cap must be a positive integer.")
        cap = int(raw)
    else:
        text = str(raw).strip()
        if not text.isdecimal():
            raise BusinessRuleError("stop_cap must be a positive integer.")
        cap = int(text)
    if cap < 1:
        raise BusinessRuleError("stop_cap must be a positive integer.")
    return cap


def _capped_stops(stops, cap):
    sequenced = list(stops)[:cap]
    left_out = list(stops)[cap:]

    def stop_id(stop):
        return stop["stop_id"] if isinstance(stop, dict) else stop.stop_id

    def pincode(stop):
        if isinstance(stop, dict):
            return stop.get("pincode") or ""
        return stop.pincode or ""

    return {
        "sequenced": SequencedStopSerializer(sequenced, many=True).data
        if sequenced and not isinstance(sequenced[0], dict)
        else sequenced,
        "unassigned": [
            {"stop_id": stop_id(stop), "pincode": pincode(stop), "reason": "over_stop_cap"}
            for stop in left_out
        ],
    }


class DeliveryRouteViewSet(CompanyScopedViewSet):
    queryset = DeliveryRoute.objects.select_related("cash_handover").prefetch_related(
        "stops__sales_order__customer", "stops__sales_order__items__product", "stops__acknowledgements__created_by"
    )
    serializer_class = DeliveryRouteSerializer
    audit_entity = "DeliveryRoute"

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "add_orders", "remove_stop",
                      "set_stop_status", "start", "complete", "suggest_sequence", "apply_sequence",
                      "issue_otp", "verify_handover", "link_receipt"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    def get_queryset(self):
        from datetime import date as _date

        from django.db.models import Q

        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            wanted = [part.strip().upper() for part in str(params["status"]).split(",") if part.strip()]
            unknown = [part for part in wanted if part not in DeliveryRoute.Status.values]
            if unknown:
                raise BusinessRuleError(f"Unknown route status: {', '.join(unknown)}.")
            qs = qs.filter(status__in=wanted)
        for key, lookup in (("date", "route_date"), ("date_from", "route_date__gte"), ("date_to", "route_date__lte")):
            raw = params.get(key)
            if raw:
                try:
                    qs = qs.filter(**{lookup: _date.fromisoformat(str(raw)[:10])})
                except ValueError:
                    raise BusinessRuleError(f"{key} must be an ISO date (YYYY-MM-DD).")
        vehicle = (params.get("vehicle") or "").strip()[:32]
        if vehicle:
            qs = qs.filter(vehicle_number__icontains=vehicle)
        driver = (params.get("driver") or "").strip()[:128]
        if driver:
            qs = qs.filter(Q(driver_name__icontains=driver) | Q(driver__name__icontains=driver))
        term = (params.get("q") or "").strip()[:100]
        if term:
            qs = qs.filter(
                Q(number__icontains=term) | Q(vehicle_number__icontains=term) | Q(driver_name__icontains=term)
            )
        return qs

    def perform_create(self, serializer):
        raw_ids = self.request.data.get("order_ids") or self.request.data.get("orderIds") or []
        try:
            order_ids = [int(x) for x in raw_ids]
        except (TypeError, ValueError) as exc:
            raise BusinessRuleError("order_ids must be a list of integers.") from exc
        with transaction.atomic():
            super().perform_create(serializer)
            # The number is given at creation so the route can be found, printed and phoned about
            # from the start (RT-15), not only after it is started.
            RouteService._ensure_number(serializer.instance)
            if order_ids:
                RouteService.add_orders(
                    serializer.instance,
                    order_ids,
                    self.request.user,
                    acknowledgements=self.request.data.get("acknowledgements"),
                    viewer=viewer_for(self.request),
                )

    def perform_destroy(self, instance):
        if instance.status != DeliveryRoute.Status.PLANNED:
            raise BusinessRuleError("Only PLANNED routes can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"], url_path="add-orders")
    def add_orders(self, request, pk=None):
        ids = request.data.get("order_ids") or request.data.get("orderIds") or []
        try:
            order_ids = [int(x) for x in ids]
        except (TypeError, ValueError) as exc:
            raise BusinessRuleError("order_ids must be a list of integers.") from exc
        RouteService.add_orders(
            self.get_object(),
            order_ids,
            request.user,
            acknowledgements=request.data.get("acknowledgements"),
            viewer=viewer_for(request),
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="remove-stop")
    def remove_stop(self, request, pk=None):
        stop_id = request.data.get("stop_id") or request.data.get("stopId")
        route = self.get_object()
        stop = DeliveryRouteStop.objects.filter(pk=stop_id, route=route).first()
        if stop is None:
            raise BusinessRuleError("Stop was not found on this route.")
        RouteService.remove_stop(route, stop, request.user)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="set-stop-status")
    def set_stop_status(self, request, pk=None):
        stop_id = request.data.get("stop_id") or request.data.get("stopId")
        status = request.data.get("status")
        route = self.get_object()
        stop = DeliveryRouteStop.objects.filter(pk=stop_id, route=route).first()
        if stop is None:
            raise BusinessRuleError("Stop was not found on this route.")
        from core.models import FileAsset
        from payments.models import CustomerReceipt

        photo = None
        photo_id = request.data.get("pod_photo") or request.data.get("podPhoto")
        if photo_id:
            photo = FileAsset.objects.filter(pk=photo_id, company=route.company).first()
            if photo is None:
                raise BusinessRuleError("Proof photo was not found.")
        receipt = None
        receipt_id = request.data.get("customer_receipt") or request.data.get("customerReceipt")
        if receipt_id:
            receipt = CustomerReceipt.objects.filter(pk=receipt_id, company=route.company).first()
            if receipt is None:
                raise BusinessRuleError("Receipt was not found.")
        RouteService.set_stop_status(
            route,
            stop,
            status,
            request.user,
            completion_source=request.data.get("completion_source") or request.data.get("completionSource") or "",
            otp_code=request.data.get("otp_code") or request.data.get("otp") or "",
            pod_note=request.data.get("pod_note") or request.data.get("podNote") or "",
            received_by_name=request.data.get("received_by_name") or request.data.get("receivedByName") or "",
            pod_photo=photo,
            customer_receipt=receipt,
            collected_cash=request.data.get("collected_cash", request.data.get("collectedCash", None))
            if ("collected_cash" in request.data or "collectedCash" in request.data)
            else None,
            collected_upi=request.data.get("collected_upi", request.data.get("collectedUpi", None))
            if ("collected_upi" in request.data or "collectedUpi" in request.data)
            else None,
            upi_reference=request.data.get("upi_reference", request.data.get("upiReference", None))
            if ("upi_reference" in request.data or "upiReference" in request.data)
            else None,
            reason=request.data.get("reason") or "",
            returned_lines=request.data.get("returned_lines", request.data.get("returnedLines", None)),
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        route = RouteService.cancel_route(
            self.get_object(), request.user, reason=request.data.get("reason") or ""
        )
        return Response(self.get_serializer(route).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        route = RouteService.start_route(
            self.get_object(),
            request.user,
            acknowledgements=request.data.get("acknowledgements"),
            viewer=viewer_for(request),
        )
        return Response(self.get_serializer(route).data)

    @action(detail=True, methods=["get"])
    def preflight(self, request, pk=None):
        """Every stop's facts and risks as they stand now, and whether the route may start."""
        route = self.get_object()
        return Response(RouteService.preflight(route, viewer_for(request)))

    @action(detail=False, methods=["get"])
    def candidates(self, request):
        """Orders a dispatcher can choose from, with what they need to know about each (paged).

        By default only orders that can go out: confirmed, partly processed or shipped, and not
        already on a live route or delivered. ``show_unavailable=1`` also lists those, as blocked
        rows, and ``include_drafts=1`` adds unconfirmed orders (blocked unless an owner accepts them).
        """
        return Response(planning_candidates(self.company, request.query_params, viewer_for(request)))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        cost = request.data.get("actual_logistics_cost", request.data.get("actualLogisticsCost"))
        route = RouteService.complete_route(
            self.get_object(), request.user, actual_logistics_cost=cost,
        )
        return Response(self.get_serializer(route).data)

    @action(detail=True, methods=["post"], url_path="issue-otp")
    def issue_otp(self, request, pk=None):
        stop_id = request.data.get("stop_id") or request.data.get("stopId")
        route = self.get_object()
        stop = DeliveryRouteStop.objects.filter(pk=stop_id, route=route).first()
        if stop is None:
            raise BusinessRuleError("Stop was not found on this route.")
        RouteService.issue_delivery_otp(route, stop, request.user)
        return Response({"sent": True})

    @action(detail=True, methods=["post"], url_path="verify-handover")
    def verify_handover(self, request, pk=None):
        route = self.get_object()
        if "cash_counted" not in request.data or "upi_counted" not in request.data:
            raise BusinessRuleError("Counted cash and counted UPI are required.")
        RouteService.verify_cashier_handover(
            route,
            request.user,
            cash_counted=request.data.get("cash_counted"),
            upi_counted=request.data.get("upi_counted"),
            variance_note=request.data.get("variance_note") or "",
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="link-receipt")
    def link_receipt(self, request, pk=None):
        from payments.models import CustomerReceipt

        route = self.get_object()
        stop_id = request.data.get("stop_id") or request.data.get("stopId")
        receipt_id = request.data.get("receipt_id") or request.data.get("receiptId")
        stop = DeliveryRouteStop.objects.filter(pk=stop_id, route=route).first()
        if stop is None:
            raise BusinessRuleError("Stop was not found on this route.")
        receipt = CustomerReceipt.objects.filter(pk=receipt_id, company=route.company).first()
        if receipt is None:
            raise BusinessRuleError("Receipt was not found.")
        RouteService.link_receipt(route, stop, receipt, request.user, reason=request.data.get("reason") or "")
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=False, methods=["get"], url_path="completion-baseline")
    def completion_baseline(self, request):
        from django.db.models import Count, Q

        counts = DeliveryRouteStop.objects.filter(route__company=self.company).aggregate(
            phone=Count("id", filter=Q(completion_source="PHONE")),
            office=Count("id", filter=Q(completion_source="OFFICE")),
            total=Count("id"),
        )
        return Response(counts)

    @action(detail=True, methods=["post"], url_path="suggest-sequence")
    def suggest_sequence(self, request, pk=None):
        from django.core.cache import cache

        route = self.get_object()
        from core.services.feature_flags import flag_enabled

        if not flag_enabled(route.company, "ENABLE_ROUTE_OPTIMIZATION"):
            raise Http404()
        strategy_name = request.data.get("strategy_name") or request.data.get("strategy") or None
        cap = _stop_cap(request.data.get("stop_cap", request.data.get("stopCap", None)))
        elapsed = cache.get(f"route-seq-ms:{route.company_id}") or 0
        if str(request.data.get("use_cached") or request.data.get("useCached") or "") == "1":
            cached = cache.get(f"route-seq-result:{route.id}")
            if cached is not None:
                if cap is None:
                    return Response(cached)
                return Response(_capped_stops(cached, cap))
        defer = str(request.data.get("defer") or "") == "1"
        if defer and elapsed > 1500 and cap is None:
            from sales.tasks import suggest_route_sequence_task

            suggest_route_sequence_task.delay(route.id, strategy_name or "", route.company_id)
            return Response({"status": "queued"}, status=202)
        try:
            suggestion = RouteService.suggest_stop_sequence(route, strategy_name=strategy_name)
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        if cap is None:
            return Response(SequencedStopSerializer(suggestion, many=True).data)
        return Response(_capped_stops(suggestion, cap))

    @action(detail=True, methods=["post"], url_path="apply-sequence")
    def apply_sequence(self, request, pk=None):
        raw = request.data.get("sequence")
        if raw is None:
            raw = request.data.get("stops")
        if not isinstance(raw, list) or not raw:
            raise BusinessRuleError("sequence must be a non-empty list of {stop_id, sequence} pairs.")
        sequenced_stops = []
        for item in raw:
            if not isinstance(item, dict):
                raise BusinessRuleError("Each sequence entry must be an object with stop_id and sequence.")
            try:
                stop_id = int(item.get("stop_id"))
                sequence = int(item.get("sequence"))
            except (TypeError, ValueError) as exc:
                raise BusinessRuleError("Each sequence entry needs an integer stop_id and sequence.") from exc
            sequenced_stops.append(
                SequencedStop(
                    stop_id=stop_id,
                    sequence=sequence,
                    pincode=item.get("pincode") or "",
                    needs_manual_sequencing=bool(item.get("needs_manual_sequencing")),
                )
            )
        route = self.get_object()
        RouteService.apply_stop_sequence(route, sequenced_stops, request.user)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["get"])
    def manifest(self, request, pk=None):
        import io

        from .pdf import render_route_manifest

        route = self.get_object()
        content = render_route_manifest(route)
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=f"{route.number or f'route-{route.pk}'}_manifest.pdf",
            content_type="application/pdf",
        )


class PodSlipView(APIView):
    """GET .../stops/<id>/pod.pdf — registered outside the router so the dot is not redirected."""

    permission_classes = [IsAuthenticated, HasCompany, CanViewSalesSurfaces]

    def get(self, request, pk=None, stop_id=None):
        from django.http import HttpResponse

        from core.permissions import get_company_user

        from .pod_slip import render_pod_pdf

        company = get_company_user(request).company
        stop = DeliveryRouteStop.objects.filter(route_id=pk, route__company=company, pk=stop_id).select_related(
            "route", "sales_order__customer", "pod_photo",
        ).prefetch_related("sales_order__items__product").first()
        if stop is None:
            from django.http import Http404

            raise Http404()
        body = render_pod_pdf(stop)
        response = HttpResponse(body, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="pod-{stop_id}.pdf"'
        return response


class DeliveryChallanReturnViewSet(CompanyScopedViewSet):
    queryset = DeliveryChallanReturn.objects.select_related("customer", "challan").prefetch_related("items__product")
    serializer_class = DeliveryChallanReturnSerializer
    audit_entity = "DeliveryChallanReturn"

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            wanted = [p.strip().upper() for p in str(params["status"]).split(",") if p.strip()]
            unknown = [p for p in wanted if p not in DeliveryChallanReturn.Status.values]
            if unknown:
                raise BusinessRuleError(f"Unknown return status: {', '.join(unknown)}.")
            qs = qs.filter(status__in=wanted)
        if str(params.get("from_route") or "").lower() in ("1", "true", "yes"):
            # Returns opened by a failed or refused delivery: the godown's "goods to check in" list.
            qs = qs.filter(reason__startswith="Stop ")
        return qs

    def perform_destroy(self, instance):
        if instance.status != DeliveryChallanReturn.Status.DRAFT:
            raise BusinessRuleError("Only draft challan returns can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        obj = ChallanReturnService.complete(self.get_object(), request.user)
        return Response(self.get_serializer(obj).data)
