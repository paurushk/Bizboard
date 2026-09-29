"""Shopify v1 webhook receiver. One store per company, HMAC before any write."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from decimal import Decimal

from django.db import transaction
from django.utils.encoding import force_bytes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.rls import rls_bypass, set_rls_company
from core.services.gsp_secrets import decrypt_gsp_credentials

from .models import IntegrationConnection, IntegrationSyncRun

logger = logging.getLogger(__name__)


def _shop_connection(shop_domain: str):
    domain = (shop_domain or "").strip().lower()
    if not domain:
        return None
    with rls_bypass():
        connections = list(IntegrationConnection.objects.filter(
            provider="SHOPIFY", status=IntegrationConnection.Status.ACTIVE,
        ))
    for conn in connections:
        meta = conn.metadata or {}
        if str(meta.get("shop_domain") or "").strip().lower() == domain:
            return conn
    return None


def _apply_shopify_event(conn, topic: str, payload: dict) -> dict:
    topic = (topic or "").strip().lower()
    if topic in ("orders/create", "orders/updated"):
        return _import_order(conn, payload)
    if topic == "inventory_levels/update":
        return _sync_stock(conn, payload)
    return {"status": "accepted", "applied": False}


def _import_order(conn, payload: dict) -> dict:
    from inventory.models import Warehouse
    from masters.models import Customer, Product
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService

    meta = conn.metadata or {}
    warehouse = Warehouse.objects.filter(company=conn.company, pk=meta.get("warehouse_id")).first()
    customer = Customer.objects.filter(company=conn.company, pk=meta.get("customer_id")).first()
    if warehouse is None or customer is None:
        return {
            "status": "skipped",
            "applied": False,
            "error": "Set a godown and a customer on the Shopify connection before orders become drafts.",
        }
    shopify_id = str(payload.get("id") or "").strip()
    marker = f"shopify:{shopify_id}" if shopify_id else ""
    from django.db.models import Q

    def _already_imported():
        if not marker:
            return False
        # Whole-token match. notes__contains would treat shopify:123 as shopify:1234.
        return SalesOrder.objects.filter(company=conn.company).filter(
            Q(notes=marker) | Q(notes__startswith=marker + " ") | Q(notes__startswith=marker + "\n")
        ).exists()
    missing = []
    items = []
    for line in payload.get("line_items") or []:
        sku = str(line.get("sku") or "").strip()
        product = Product.objects.filter(company=conn.company, sku=sku).first() if sku else None
        if product is None:
            missing.append(sku or "(blank)")
            continue
        items.append({
            "product": product.pk,
            "quantity": line.get("quantity") or 0,
            "unit_price": line.get("price") or product.selling_price,
            "gst_rate": product.gst_rate,
        })
    if missing or not items:
        return {
            "status": "skipped",
            "applied": False,
            "error": f"Unmapped SKUs: {', '.join(missing) or 'none'}. No order was created.",
        }
    with transaction.atomic():
        IntegrationConnection.objects.select_for_update().get(pk=conn.pk)
        if _already_imported():
            return {"status": "duplicate", "applied": False}
        order = SalesOrder.objects.create(
            company=conn.company,
            customer=customer,
            warehouse=warehouse,
            sales_channel="ONLINE",
            notes=marker,
            delivery_address=str((payload.get("shipping_address") or {}).get("address1") or ""),
        )
        SalesNotesService.set_order_items(order, items, None)
    return {"status": "accepted", "applied": True, "sales_order_id": order.id}


def _sync_stock(conn, payload: dict) -> dict:
    from inventory.models import MovementType, StockBalance, Warehouse
    from inventory.services import InventoryService
    from masters.models import Product

    sku = str(payload.get("sku") or "").strip()
    if not sku:
        item_id = str(payload.get("inventory_item_id") or "").strip()
        mapped = (conn.metadata or {}).get("inventory_item_skus") or {}
        if item_id and isinstance(mapped, dict):
            sku = str(mapped.get(item_id) or "").strip()
    location_id = str(payload.get("location_id") or "").strip()
    expected_location = str((conn.metadata or {}).get("shopify_location_id") or "").strip()
    if location_id and expected_location and location_id != expected_location:
        return {
            "status": "skipped",
            "applied": False,
            "error": "Inventory update is for a different Shopify location.",
        }
    warehouse = Warehouse.objects.filter(
        company=conn.company, pk=(conn.metadata or {}).get("warehouse_id"),
    ).first()
    if not sku or warehouse is None or "available" not in payload:
        return {
            "status": "skipped",
            "applied": False,
            "error": "Stock sync needs a SKU, a godown on the connection, and an available quantity.",
        }
    product = Product.objects.filter(company=conn.company, sku=sku).first()
    if product is None:
        return {"status": "skipped", "applied": False, "error": f"SKU {sku} is not in this company. No stock was changed."}
    # Lock the balance row (if any) before reading on_hand, and hold that lock
    # through post_movement, so a concurrent webhook/sale/GRN for the same
    # product+warehouse can't slip in between the read and the delta being
    # applied — it blocks on the lock and re-reads the now-current balance.
    with transaction.atomic():
        balance = (
            StockBalance.objects.select_for_update()
            .filter(company=conn.company, product=product, warehouse=warehouse)
            .first()
        )
        on_hand = balance.on_hand if balance else Decimal("0")
        delta = Decimal(str(payload["available"])) - Decimal(on_hand)
        if delta == 0:
            return {"status": "accepted", "applied": True, "delta": "0"}
        InventoryService.post_movement(
            company=conn.company,
            product=product,
            warehouse=warehouse,
            movement_type=MovementType.ADJUSTMENT,
            quantity=delta,
            reason="Shopify inventory_levels/update",
            reference_type="shopify",
            reference_id=str(payload.get("inventory_item_id") or sku),
        )
    return {"status": "accepted", "applied": True, "delta": str(delta)}


class ShopifyWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        # QOS-0002: every inbound webhook route must fail closed on an
        # unsigned/unauthenticated POST with 400/401/403, never 404 -- a 404
        # here would let a caller distinguish "no such shop" from "bad
        # signature" and enumerate configured shop domains.
        shop = request.headers.get("X-Shopify-Shop-Domain") or ""
        if not shop:
            return Response({"detail": "Invalid signature."}, status=401)
        conn = _shop_connection(shop)
        if conn is None:
            return Response({"detail": "Invalid signature."}, status=401)
        set_rls_company(conn.company_id)
        secret = ""
        if conn.encrypted_secrets:
            creds = decrypt_gsp_credentials(conn.encrypted_secrets) or {}
            secret = str(creds.get("webhook_secret") or "")
        digest = request.headers.get("X-Shopify-Hmac-Sha256") or ""
        body = request.body or b""
        expected = base64.b64encode(hmac.new(force_bytes(secret), body, hashlib.sha256).digest()).decode()
        if not secret or not hmac.compare_digest(expected, digest):
            return Response({"detail": "Invalid signature."}, status=401)
        delivery = request.headers.get("X-Shopify-Webhook-Id") or ""
        if delivery and IntegrationSyncRun.objects.filter(
            company=conn.company,
            kind="SHOPIFY_WEBHOOK",
            status=IntegrationSyncRun.Status.COMMITTED,
            result__delivery_id=delivery,
        ).exists():
            return Response({"status": "duplicate"})
        topic = request.headers.get("X-Shopify-Topic") or ""
        payload = request.data if isinstance(request.data, dict) else {}
        try:
            outcome = _apply_shopify_event(conn, topic, payload)
        except Exception:
            logger.exception(
                "Shopify webhook failed to apply: company=%s topic=%s delivery=%s",
                conn.company_id, topic, delivery,
            )
            IntegrationSyncRun.objects.create(
                company=conn.company,
                kind="SHOPIFY_WEBHOOK",
                status=IntegrationSyncRun.Status.FAILED,
                result={"delivery_id": delivery, "topic": topic, "status": "error", "applied": False},
                created_by=None,
            )
            return Response({"detail": "Could not apply the webhook."}, status=500)
        IntegrationSyncRun.objects.create(
            company=conn.company,
            kind="SHOPIFY_WEBHOOK",
            status=IntegrationSyncRun.Status.COMMITTED if outcome.get("applied") else IntegrationSyncRun.Status.FAILED,
            result={"delivery_id": delivery, "topic": topic, **outcome},
            created_by=None,
        )
        return Response(outcome)
