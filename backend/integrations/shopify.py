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
    matches = []
    for conn in connections:
        meta = conn.metadata or {}
        stored = str(getattr(conn, "shop_domain", "") or meta.get("shop_domain") or "").strip().lower()
        if stored == domain:
            matches.append(conn)
    if len(matches) != 1:
        return None
    return matches[0]


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


def _shopify_time(value):
    from datetime import timezone as dt_timezone

    from django.utils.dateparse import parse_datetime
    from django.utils import timezone

    parsed = parse_datetime(str(value or "").strip())
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


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
    incoming = _shopify_time(payload.get("updated_at"))
    if incoming is None:
        return {"status": "skipped", "applied": False, "error": "Stock sync needs updated_at. No stock was changed."}
    item_key = str(payload.get("inventory_item_id") or sku)
    with transaction.atomic():
        locked = IntegrationConnection.objects.select_for_update().get(pk=conn.pk)
        meta = dict(locked.metadata or {})
        applied_map = dict(meta.get("shopify_applied_at") or {})
        pending_map = dict(meta.get("shopify_pending") or {})
        previous = _shopify_time(applied_map.get(item_key))
        if previous is not None and incoming <= previous:
            return {"status": "skipped", "applied": True, "delta": "0", "reason": "stale"}
        pending = pending_map.get(item_key) or {}
        pending_time = _shopify_time(pending.get("updated_at"))
        if pending_time is not None and incoming <= pending_time:
            return {"status": "skipped", "applied": True, "delta": "0", "reason": "stale_pending"}
        balance = (
            StockBalance.objects.select_for_update()
            .filter(company=locked.company, product=product, warehouse=warehouse)
            .first()
        )
        on_hand = balance.on_hand if balance else Decimal("0")
        delta = Decimal(str(payload["available"])) - Decimal(on_hand)
        stamp = incoming.isoformat()
        if delta == 0:
            applied_map[item_key] = stamp
            pending_map.pop(item_key, None)
            meta["shopify_applied_at"] = applied_map
            meta["shopify_pending"] = pending_map
            locked.metadata = meta
            locked.save(update_fields=["metadata", "updated_at"])
            return {"status": "accepted", "applied": True, "delta": "0"}
        band = max(Decimal("1"), (Decimal("0.25") * Decimal(on_hand)).quantize(Decimal("0.001")))
        if abs(delta) <= band:
            InventoryService.post_movement(
                company=locked.company,
                product=product,
                warehouse=warehouse,
                movement_type=MovementType.ADJUSTMENT,
                quantity=delta,
                reason="Shopify inventory_levels/update",
                reference_type="shopify",
                reference_id=item_key,
            )
            applied_map[item_key] = stamp
            pending_map.pop(item_key, None)
            meta["shopify_applied_at"] = applied_map
            meta["shopify_pending"] = pending_map
            locked.metadata = meta
            locked.save(update_fields=["metadata", "updated_at"])
            return {"status": "accepted", "applied": True, "delta": str(delta)}
        pending_map[item_key] = {
            "available": str(payload["available"]),
            "updated_at": stamp,
            "delta": str(delta),
            "on_hand_before": str(on_hand),
            "sku": sku,
        }
        meta["shopify_pending"] = pending_map
        locked.metadata = meta
        locked.save(update_fields=["metadata", "updated_at"])
        return {"status": "held", "applied": True, "delta": str(delta)}


def apply_pending_stock(conn, item_key, user=None) -> dict:
    """Post one held Shopify delta. Large deltas stay held until this call."""
    from core.exceptions import BusinessRuleError
    from inventory.models import MovementType, Warehouse
    from inventory.services import InventoryService
    from masters.models import Product

    item_key = str(item_key or "").strip()
    if not item_key:
        raise BusinessRuleError("A pending item key is required.")
    with transaction.atomic():
        locked = IntegrationConnection.objects.select_for_update().get(
            pk=conn.pk, company_id=conn.company_id,
        )
        meta = dict(locked.metadata or {})
        pending_map = dict(meta.get("shopify_pending") or {})
        row = pending_map.get(item_key)
        if not row:
            raise BusinessRuleError("That Shopify stock change is not waiting for review.")
        warehouse = Warehouse.objects.filter(
            company=locked.company, pk=meta.get("warehouse_id"),
        ).first()
        product = Product.objects.filter(company=locked.company, sku=row.get("sku") or "").first()
        if warehouse is None or product is None:
            raise BusinessRuleError("The held Shopify change is missing a godown or a product.")
        delta = Decimal(str(row.get("delta") or "0"))
        if row.get("available") not in (None, ""):
            # The stored delta was measured when the webhook arrived. A sale or receipt since then
            # would leave on-hand at neither Shopify's number nor the right one, so measure again
            # against what is on hand now.
            from inventory.models import StockBalance

            balance = (
                StockBalance.objects.select_for_update()
                .filter(company=locked.company, product=product, warehouse=warehouse)
                .first()
            )
            on_hand_now = Decimal(str(balance.on_hand)) if balance else Decimal("0")
            delta = Decimal(str(row["available"])) - on_hand_now
        if delta == 0:
            pending_map.pop(item_key, None)
            meta["shopify_pending"] = pending_map
            locked.metadata = meta
            locked.save(update_fields=["metadata", "updated_at"])
            return {"status": "applied", "item_key": item_key, "delta": "0", "pending_count": len(pending_map)}
        InventoryService.post_movement(
            company=locked.company,
            product=product,
            warehouse=warehouse,
            movement_type=MovementType.ADJUSTMENT,
            quantity=delta,
            reason="Shopify pending stock approved",
            reference_type="shopify",
            reference_id=item_key,
            user=user,
        )
        pending_map.pop(item_key, None)
        applied_map = dict(meta.get("shopify_applied_at") or {})
        applied_map[item_key] = row.get("updated_at")
        meta["shopify_pending"] = pending_map
        meta["shopify_applied_at"] = applied_map
        locked.metadata = meta
        locked.updated_by = user
        locked.save(update_fields=["metadata", "updated_by", "updated_at"])
    return {"status": "applied", "item_key": item_key, "delta": str(delta), "pending_count": len(pending_map)}


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


def notify_shopify_gaps():
    """Tell each owner about a shared shop domain or a held stock delta.

    Does not post stock. A large delta stays in connection metadata until an
    operator posts an inventory adjustment by hand.
    """
    rows = list(IntegrationConnection.objects.filter(
        provider="SHOPIFY", status=IntegrationConnection.Status.ACTIVE,
    ))
    by_domain: dict[str, list] = {}
    for conn in rows:
        meta = conn.metadata or {}
        domain = str(conn.shop_domain or meta.get("shop_domain") or "").strip().lower()
        if domain:
            by_domain.setdefault(domain, []).append(conn)
    for domain, conns in by_domain.items():
        if len(conns) < 2:
            continue
        company_ids = sorted({c.company_id for c in conns})
        logger.error("SHOPIFY_DOMAIN_CLASH domain=%s companies=%s", domain, company_ids)
        for conn in conns:
            _shopify_notice(
                conn.company,
                "SHOPIFY_DOMAIN_CLASH",
                f"Shopify domain {domain} is active on more than one company. "
                "Stock updates are rejected until one connection is deactivated.",
            )
    for conn in rows:
        pending = (conn.metadata or {}).get("shopify_pending") or {}
        if not pending:
            continue
        _shopify_notice(
            conn.company,
            "SHOPIFY_STOCK_HELD",
            f"{len(pending)} Shopify stock change(s) are held and were not posted.",
        )


def _shopify_notice(company, code, body):
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService

    owners = CompanyUser.objects.filter(
        company=company, role=CompanyUser.Role.OWNER, is_active=True,
    ).select_related("user")
    for membership in owners:
        NotificationService.send(
            company=company,
            channel=Notification.Channel.IN_APP,
            recipient=membership.user.email or str(membership.user_id),
            subject=code,
            body=body,
            user=membership.user,
        )
