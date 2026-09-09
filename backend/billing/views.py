"""Owner SaaS billing portal + Razorpay webhook (BB-000671)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService

from .models import Plan
from .serializers import PlanSerializer, SubscriptionSerializer
from .services import apply_razorpay_subscription_status, start_or_update_subscription, subscription_for_company

logger = logging.getLogger("bizboard.billing")

TEST_WEBHOOK_HEADER = "HTTP_X_BIZBOARD_TEST_WEBHOOK"


class PlanListView(APIView):
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        qs = Plan.objects.filter(is_active=True)
        return Response(PlanSerializer(qs, many=True).data)


class SubscriptionDetailView(APIView):
    # B9-021: exposes razorpay_subscription_id / current_period_end — owner-only,
    # consistent with PlanListView / CheckoutView / PortalView.
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        cu = get_company_user(request)
        sub = subscription_for_company(cu.company)
        if sub is None:
            return Response({"subscription": None, "billing_override_active": cu.company.billing_override_active})
        data = SubscriptionSerializer(sub).data
        data["billing_override_active"] = cu.company.billing_override_active
        data["seat_limit"] = sub.plan.seat_limit
        return Response(data)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated, IsOwner]

    def post(self, request):
        cu = get_company_user(request)
        plan_id = request.data.get("plan_id") or request.data.get("planId")
        slug = (request.data.get("plan_slug") or request.data.get("planSlug") or "").strip()
        plan = None
        if plan_id:
            # B9-018: a non-numeric plan_id must be a 400, not an ORM 500.
            try:
                plan_pk = int(str(plan_id).strip())
            except (TypeError, ValueError):
                raise BusinessRuleError("Unknown or inactive plan.")
            plan = Plan.objects.filter(pk=plan_pk, is_active=True).first()
        elif slug:
            plan = Plan.objects.filter(slug=slug, is_active=True).first()
        if plan is None:
            raise BusinessRuleError("Unknown or inactive plan.")
        sub, checkout_order_id = start_or_update_subscription(company=cu.company, plan=plan)
        AuditService.log(
            action="billing.checkout",
            company=cu.company,
            user=request.user,
            entity_type="Subscription",
            entity_id=sub.pk,
            description=f"Started checkout for plan {plan.slug}.",
            metadata={"checkout_order_id": checkout_order_id, "plan": plan.slug},
        )
        return Response(
            {
                "subscription": SubscriptionSerializer(sub).data,
                "checkout_order_id": checkout_order_id,
            },
            status=status.HTTP_201_CREATED,
        )


class PortalView(APIView):
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        cu = get_company_user(request)
        sub = subscription_for_company(cu.company)
        payload = {
            "subscription": SubscriptionSerializer(sub).data if sub else None,
            "plans": PlanSerializer(Plan.objects.filter(is_active=True), many=True).data,
            "billing_override_active": cu.company.billing_override_active,
            "seat_limit": sub.plan.seat_limit if sub else None,
        }
        # Hosted customer portal is not wired; omit rather than always-None.
        portal = (getattr(settings, "RAZORPAY_CUSTOMER_PORTAL_URL", "") or "").strip()
        if portal:
            payload["portal_url"] = portal
        return Response(payload)


class RazorpayWebhookView(APIView):
    """POST /api/v1/billing/razorpay/webhook/

    When ``RAZORPAY_WEBHOOK_SECRET`` is set, ``X-Razorpay-Signature`` is required.
    When the secret is unset, the webhook is accepted only if ``DJANGO_ENV=test``
    (or DEBUG) and header ``X-Bizboard-Test-Webhook: 1`` is present.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        body = request.body or b""
        secret = (getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "") or "").strip()
        if secret:
            signature = request.headers.get("X-Razorpay-Signature") or ""
            expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            if not signature or not hmac.compare_digest(signature, expected):
                return Response({"detail": "Invalid webhook signature."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
            test_header = request.META.get(TEST_WEBHOOK_HEADER) or request.headers.get("X-Bizboard-Test-Webhook")
            if env not in {"test"}:
                return Response(
                    {"detail": "RAZORPAY_WEBHOOK_SECRET is required."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if str(test_header or "").strip() not in {"1", "true", "yes"} and env != "test":
                return Response(
                    {"detail": "Unsigned webhooks require X-Bizboard-Test-Webhook in test/debug."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = request.data if isinstance(request.data, dict) else {}

        entity = _extract_subscription_entity(payload)
        if not entity:
            return Response({"ok": True, "ignored": True})
        rzp_id = str(entity.get("id") or "")
        rzp_status = str(entity.get("status") or "")

        from django.core.cache import cache
        from django.db import IntegrityError

        from accounts.models import Company
        from billing.models import Subscription
        from core.rls import rls_bypass, set_rls_company
        from payments.models import ProcessedWebhookEvent

        event_id = (
            request.headers.get("X-Razorpay-Event-Id")
            or str(payload.get("id") or "")
            or hashlib.sha256(body).hexdigest()
        )
        dedup_key = "bizboard:billing_webhook_seen:" + hashlib.sha256(
            f"{rzp_id}|{rzp_status}|{event_id}".encode()
        ).hexdigest()
        if cache.get(dedup_key):
            return Response({"ok": True, "duplicate": True})

        with rls_bypass():
            sub = Subscription.objects.filter(razorpay_subscription_id=rzp_id).select_related("company").first()
            company = sub.company if sub is not None else None
            if sub is not None and (
                company is None or not Company.objects.filter(pk=company.pk).exists()
            ):
                return Response({"ok": True, "ignored": True}, status=status.HTTP_410_GONE)
            if company is None:
                try:
                    ProcessedWebhookEvent.objects.create(
                        dedup_key=dedup_key, provider="razorpay_subscription", company=None
                    )
                except IntegrityError:
                    cache.set(dedup_key, "1", timeout=24 * 60 * 60)
                    return Response({"ok": True, "duplicate": True})
                cache.set(dedup_key, "1", timeout=24 * 60 * 60)
                return Response({"ok": True, "ignored": True})

        set_rls_company(company.id)
        try:
            ProcessedWebhookEvent.objects.create(
                dedup_key=dedup_key, provider="razorpay_subscription", company=company
            )
        except IntegrityError:
            cache.set(dedup_key, "1", timeout=24 * 60 * 60)
            return Response({"ok": True, "duplicate": True})
        cache.set(dedup_key, "1", timeout=24 * 60 * 60)
        sub = apply_razorpay_subscription_status(
            razorpay_subscription_id=rzp_id,
            rzp_status=rzp_status,
            current_end=entity.get("current_end"),
        )
        if sub is not None:
            AuditService.log(
                action="billing.webhook",
                company=sub.company,
                entity_type="Subscription",
                entity_id=sub.pk,
                description=f"Razorpay subscription {rzp_id} → {sub.status}.",
                metadata={"razorpay_status": rzp_status},
            )
        return Response({"ok": True, "subscription_id": sub.pk if sub else None, "status": sub.status if sub else None})


def _extract_subscription_entity(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None
    nested = (((payload.get("payload") or {}).get("subscription") or {}).get("entity"))
    if isinstance(nested, dict) and nested.get("id"):
        return nested
    if payload.get("id") and payload.get("entity") == "subscription":
        return payload
    return None
