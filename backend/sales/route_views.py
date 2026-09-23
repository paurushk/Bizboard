from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.permissions import CanCreateSales, CanViewSalesSurfaces, HasCompany
from core.viewsets import CompanyScopedViewSet

from .challan_return import ChallanReturnService
from .models import DeliveryChallanReturn, DeliveryRoute, DeliveryRouteStop
from .route_serializers import DeliveryChallanReturnSerializer, DeliveryRouteSerializer
from .route_service import RouteService


class DeliveryRouteViewSet(CompanyScopedViewSet):
    queryset = DeliveryRoute.objects.prefetch_related(
        "stops__sales_order__customer", "stops__sales_order__items__product"
    )
    serializer_class = DeliveryRouteSerializer
    audit_entity = "DeliveryRoute"

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action in ("create", "update", "partial_update", "destroy", "add_orders", "remove_stop",
                      "set_stop_status", "start", "complete"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("date"):
            qs = qs.filter(route_date=self.request.query_params["date"])
        return qs

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
        RouteService.add_orders(self.get_object(), order_ids, request.user)
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
        RouteService.set_stop_status(route, stop, status, request.user)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        route = RouteService.start_route(self.get_object(), request.user)
        return Response(self.get_serializer(route).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        cost = request.data.get("actual_logistics_cost", request.data.get("actualLogisticsCost"))
        route = RouteService.complete_route(
            self.get_object(), request.user, actual_logistics_cost=cost,
        )
        return Response(self.get_serializer(route).data)

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


class DeliveryChallanReturnViewSet(CompanyScopedViewSet):
    queryset = DeliveryChallanReturn.objects.select_related("customer", "challan").prefetch_related("items__product")
    serializer_class = DeliveryChallanReturnSerializer
    audit_entity = "DeliveryChallanReturn"

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    def perform_destroy(self, instance):
        if instance.status != DeliveryChallanReturn.Status.DRAFT:
            raise BusinessRuleError("Only draft challan returns can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        obj = ChallanReturnService.complete(self.get_object(), request.user)
        return Response(self.get_serializer(obj).data)
