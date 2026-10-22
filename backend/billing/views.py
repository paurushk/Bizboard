"""Owner SaaS billing portal + Razorpay webhook (BB-000671)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService

from .models import DeadLetterEvent, Plan
from .serializers import PlanSerializer, SubscriptionSerializer
from .ops import suspend_for_churn, trial_ending_notice, upgrade_prompt
from .services import (
    apply_razorpay_subscription_status,
    park_dead_letter,
    replay_dead_letter,
    start_or_update_subscription,
    subscription_for_company,
)

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
        from billing.quotas import usage_snapshot

        data["quotas"] = usage_snapshot(cu.company, sub=sub)
        data["upgrade_prompt"] = upgrade_prompt(cu.company)
        data["trial_notice"] = trial_ending_notice(cu.company)
        return Response(data)

    def post(self, request):
        """Owner suspends the subscription and records a churn reason.

        The most destructive action on this screen, so it asks for: a reason, the company name typed
        out, and the owner's password (plus a two-step code when that is on). It is refused if the
        subscription is already suspended, and it is written to the audit trail.
        """
        from django.db import transaction

        from core.services.audit import AuditService

        from .reauth import require_reauth

        cu = get_company_user(request)
        if request.data.get("action") != "suspend":
            raise BusinessRuleError("Unknown billing action.")
        company = cu.company
        reason = str(request.data.get("churn_reason") or request.data.get("churnReason") or "").strip()
        if not reason:
            raise BusinessRuleError("A churn reason is required to suspend.", code="CHURN_REASON_REQUIRED")
        typed = str(request.data.get("confirm_company_name") or request.data.get("confirmCompanyName") or "")
        if " ".join(typed.split()).casefold() != " ".join((company.name or "").split()).casefold():
            raise BusinessRuleError("Type the company name exactly as shown to confirm.", code="COMPANY_NAME_MISMATCH")
        existing = subscription_for_company(company)
        if existing is not None and existing.status == existing.Status.SUSPENDED:
            raise BusinessRuleError("This workspace is already suspended.", code="ALREADY_SUSPENDED")
        require_reauth(request)
        with transaction.atomic():
            sub, win_back_name = suspend_for_churn(company, request.user, reason=reason)
            AuditService.log(
                company=company,
                user=request.user,
                action="billing.suspend",
                entity_type="Subscription",
                entity_id=sub.pk,
                description=reason[:255],
            )
        data = SubscriptionSerializer(sub).data
        data["win_back_name"] = win_back_name
        return Response(data)


class VendorTenantsView(APIView):
    """P13 reads redacted snapshots stored in the vendor company."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        from .models import VendorTenantSnapshot

        cu = get_company_user(request)
        rows = VendorTenantSnapshot.objects.filter(company=cu.company).order_by("source_company_name")
        return Response([
            {
                "source_company_id": row.source_company_id,
                "source_company_name": row.source_company_name,
                "setup_completed_at": row.setup_completed_at,
                "first_invoice_at": row.first_invoice_at,
                "last_invoice_at": row.last_invoice_at,
                "last_login_at": row.last_login_at,
                "seats_used": row.seats_used,
                "seats_limit": row.seats_limit,
                "documents_used": row.documents_used,
                "documents_limit": row.documents_limit,
                "churn_reason": row.churn_reason,
            }
            for row in rows
        ])


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
        checkout_url = getattr(sub, "_checkout_url", "") or ""
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
                "checkout_url": checkout_url or None,
                # WP-BL3: the one-time prorated charge for an upgrade (None otherwise).
                "proration_url": getattr(sub, "_proration_url", "") or None,
            },
            status=status.HTTP_201_CREATED,
        )


def _effective_seat_limit(sub):
    from billing.plan_change import effective_plan

    plan = effective_plan(sub)
    return plan.seat_limit if plan else None


class PortalView(APIView):
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        cu = get_company_user(request)
        sub = subscription_for_company(cu.company)
        payload = {
            "subscription": SubscriptionSerializer(sub).data if sub else None,
            "plans": PlanSerializer(Plan.objects.filter(is_active=True), many=True).data,
            "billing_override_active": cu.company.billing_override_active,
            "seat_limit": _effective_seat_limit(sub),
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
    and header ``X-Bizboard-Test-Webhook: 1`` is present.
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
            if str(test_header or "").strip() not in {"1", "true", "yes"}:
                return Response(
                    {"detail": "Unsigned webhooks require X-Bizboard-Test-Webhook in test."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = request.data if isinstance(request.data, dict) else {}

        event_name = str(payload.get("event") or "") if isinstance(payload, dict) else ""
        if event_name.startswith("payment_link."):
            from billing.plan_change import handle_payment_link_event

            return Response(handle_payment_link_event(payload))  # WP-BL3 prorated upgrade charge
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
        from core.tracing import trace_span
        from payments.models import ProcessedWebhookEvent

        # WP-BL2: a charge must be invoiced even when it arrives after a newer status event. The
        # ordering check only protects status transitions, so an older charge skips the status
        # update below but still issues its GST invoice.
        charge = _extract_charge(payload)
        out_of_order = False
        created_at = _webhook_created_at(payload)
        if created_at is not None:
            last_key = f"billing:wh:lastts:{rzp_id}"
            last = cache.get(last_key)
            if last is not None and int(created_at) < int(last):
                if charge is None:
                    return Response({"ok": True, "ignored": True, "reason": "out_of_order"})
                out_of_order = True
            else:
                cache.set(last_key, int(created_at), timeout=7 * 24 * 60 * 60)

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
            sub = (
                Subscription.objects.filter(razorpay_subscription_id=rzp_id).select_related("company").first()
                or Subscription.objects.filter(pending_razorpay_subscription_id=rzp_id).select_related("company").first()
            )
            company = sub.company if sub is not None else None
            if sub is not None and (
                company is None or not Company.objects.filter(pk=company.pk).exists()
            ):
                return Response({"ok": True, "ignored": True}, status=status.HTTP_410_GONE)
            if company is None:
                # BUG-BIL-002: an event that matched no local subscription must
                # not be deduped. A row created a moment later has to accept
                # Razorpay's retry.
                return Response({"ok": True, "ignored": True, "reason": "unknown_subscription"})

        set_rls_company(company.id)
        try:
            ProcessedWebhookEvent.objects.create(
                dedup_key=dedup_key, provider="razorpay_subscription", company=company
            )
        except IntegrityError:
            cache.set(dedup_key, "1", timeout=24 * 60 * 60)
            return Response({"ok": True, "duplicate": True})
        cache.set(dedup_key, "1", timeout=24 * 60 * 60)
        stale = _reject_stale_webhook(payload)
        if stale is not None:
            # BB-000671 gap fix: a delayed-but-legitimate retry (worker outage,
            # queue backlog) must not be silently dropped with no recovery
            # path — park it like every other post-signature failure so an
            # owner/operator can replay it once the status is confirmed still
            # relevant, instead of the subscription status change being lost.
            parked = park_dead_letter(
                provider="razorpay_subscription",
                event_id=str(event_id),
                payload=payload if isinstance(payload, dict) else {},
                error="Stale webhook: age exceeds BILLING_WEBHOOK_MAX_AGE_SECONDS.",
                company=company,
            )
            AuditService.log(
                action="billing.webhook_dlq",
                company=company,
                entity_type="DeadLetterEvent",
                entity_id=parked.pk,
                description=f"Parked stale Razorpay webhook {event_id}.",
                metadata={"reason": "stale"},
            )
            logger.warning("Razorpay subscription webhook stale; parked in DLQ")
            return Response({"ok": True, "parked": True, "dead_letter_id": parked.pk})
        if charge is not None:
            _invoice_charge(company, charge)
        if out_of_order:
            return Response({"ok": True, "ignored": True, "reason": "out_of_order", "invoiced": True})
        try:
            with trace_span("billing.razorpay_webhook", company_id=company.id, event_id=event_id):
                sub = apply_razorpay_subscription_status(
                    razorpay_subscription_id=rzp_id,
                    rzp_status=rzp_status,
                    current_end=entity.get("current_end"),
                )
        except Exception as exc:  # noqa: BLE001 — park, do not 500 after signature verified
            parked = park_dead_letter(
                provider="razorpay_subscription",
                event_id=str(event_id),
                payload=payload if isinstance(payload, dict) else {},
                error=str(exc),
                company=company,
            )
            AuditService.log(
                action="billing.webhook_dlq",
                company=company,
                entity_type="DeadLetterEvent",
                entity_id=parked.pk,
                description=f"Parked Razorpay webhook {event_id}.",
                metadata={"error": str(exc)[:500]},
            )
            logger.exception("Razorpay subscription webhook parked in DLQ")
            return Response({"ok": True, "parked": True, "dead_letter_id": parked.pk})
        if sub is not None:
            from billing.autopay import MANDATE_EVENTS, record_mandate_event

            record_mandate_event(sub, payload)  # WP-BL4 mandate state and payment method
            if event_name.startswith("subscription.") and event_name not in MANDATE_EVENTS:
                parked = park_dead_letter(
                    provider="razorpay_subscription", event_id=str(event_id),
                    payload=payload if isinstance(payload, dict) else {},
                    error=f"Unhandled event {event_name}", company=company,
                )
                logger.warning("Razorpay event %s not handled; parked %s", event_name, parked.pk)
            AuditService.log(
                action="billing.webhook",
                company=sub.company,
                entity_type="Subscription",
                entity_id=sub.pk,
                description=f"Razorpay subscription {rzp_id} → {sub.status}.",
                metadata={"razorpay_status": rzp_status},
            )
        return Response({"ok": True, "subscription_id": sub.pk if sub else None, "status": sub.status if sub else None})


def _extract_charge(payload: dict) -> dict | None:
    """WP-BL2: the captured payment of a ``subscription.charged`` event, else None."""
    if not isinstance(payload, dict) or payload.get("event") != "subscription.charged":
        return None
    payment = (((payload.get("payload") or {}).get("payment") or {}).get("entity")) or {}
    if not isinstance(payment, dict) or not payment.get("id"):
        return None
    if str(payment.get("status") or "captured") not in ("captured", "authorized"):
        return None
    try:
        paise = int(payment.get("amount") or 0)
    except (TypeError, ValueError):
        return None
    if paise <= 0:
        return None
    return {"payment_id": str(payment["id"]), "amount": Decimal(paise) / Decimal(100)}


def _invoice_charge(company, charge: dict) -> None:
    """Issue the GST invoice for one charge. A failure is logged, not raised: the daily recon
    (``billing.recon``) issues any invoice a charge event did not."""
    from billing.platform_gst import issue_platform_gst_invoice

    try:
        invoice = issue_platform_gst_invoice(
            company, provider="razorpay", capture_id=charge["payment_id"], amount=charge["amount"],
        )
    except Exception:  # noqa: BLE001
        logger.exception("Platform GST invoice for Razorpay payment %s failed; recon will retry", charge["payment_id"])
        return
    if invoice is None:
        return
    from billing.tds_claims import apply_renewal_credit

    try:
        apply_renewal_credit(company, invoice)  # WP-BL1: verified TDS credit comes off this renewal
    except Exception:  # noqa: BLE001
        logger.exception("TDS credit on renewal %s failed; the daily task retries", invoice.pk)


def _webhook_created_at(payload: dict) -> int | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("created_at")
    if raw is None:
        nested = (((payload.get("payload") or {}).get("subscription") or {}).get("entity")) or {}
        raw = nested.get("created_at") if isinstance(nested, dict) else None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _reject_stale_webhook(payload: dict):
    import time

    max_age = int(getattr(settings, "BILLING_WEBHOOK_MAX_AGE_SECONDS", 0) or 0)
    if max_age <= 0:
        return None
    created_at = _webhook_created_at(payload)
    if created_at is None:
        return None
    now = int(time.time())
    if now - created_at > max_age or created_at - now > 60:
        return Response({"detail": "Stale webhook."}, status=status.HTTP_400_BAD_REQUEST)
    return None


def _extract_subscription_entity(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None
    nested = (((payload.get("payload") or {}).get("subscription") or {}).get("entity"))
    if isinstance(nested, dict) and nested.get("id"):
        return nested
    if payload.get("id") and payload.get("entity") == "subscription":
        return payload
    return None


class DeadLetterListView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        cu = get_company_user(request)
        qs = DeadLetterEvent.objects.filter(company=cu.company).order_by("-id")[:100]
        return Response(
            [
                {
                    "id": row.pk,
                    "provider": row.provider,
                    "event_id": row.event_id,
                    "status": row.status,
                    "error": row.error,
                    "attempts": row.attempts,
                    "created_at": row.created_at,
                }
                for row in qs
            ]
        )


class DeadLetterReplayView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request, pk: int):
        cu = get_company_user(request)
        event = DeadLetterEvent.objects.filter(pk=pk, company=cu.company).first()
        if event is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        replayed = replay_dead_letter(event, user=request.user)
        return Response({"ok": True, "status": replayed.status, "id": replayed.pk})


class PlatformInvoiceListView(APIView):
    """GET /api/v1/billing/invoices/ — WP-BL2: Bizboard's GST invoices and credit notes to the
    owner's company, newest first."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        from .models import PlatformGstInvoice
        from .serializers import PlatformGstInvoiceSerializer

        cu = get_company_user(request)
        rows = (
            PlatformGstInvoice.objects.filter(company=cu.company)
            .select_related("original")
            .order_by("-created_at", "-pk")[:200]
        )
        return Response(PlatformGstInvoiceSerializer(rows, many=True).data)


class PlatformInvoicePdfView(APIView):
    """GET /api/v1/billing/invoices/<pk>/pdf/ — WP-BL2: PDF of one Bizboard invoice or credit note."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request, pk: int):
        from django.http import HttpResponse

        from .models import PlatformGstInvoice
        from .platform_invoice_pdf import render_platform_invoice_pdf

        cu = get_company_user(request)
        row = PlatformGstInvoice.objects.filter(company=cu.company, pk=pk).select_related("original").first()
        if row is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        resp = HttpResponse(render_platform_invoice_pdf(row), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{row.number or row.pk}.pdf"'
        resp["Cache-Control"] = "private, no-store"
        return resp


class SaasTdsClaimView(APIView):
    """GET/POST /api/v1/billing/tds-claims/ — WP-BL1: claim back TDS deducted on Bizboard's fees.

    POST ``{"invoice_ids": [..], "section": "194J-2", "certificate_id": <uploaded Form 16A file>}``.
    """

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        from .models import SaasTdsClaim
        from .serializers import SaasTdsClaimSerializer
        from .tds_claims import sections

        cu = get_company_user(request)
        rows = SaasTdsClaim.objects.filter(company=cu.company).prefetch_related("invoices")[:100]
        return Response({
            "claims": SaasTdsClaimSerializer(rows, many=True).data,
            "sections": [{**s, "rate": str(s["rate"])} for s in sections()],
        })

    def post(self, request):
        from .serializers import SaasTdsClaimSerializer
        from .tds_claims import submit_claim

        cu = get_company_user(request)
        claim = submit_claim(
            company=cu.company,
            user=request.user,
            invoice_ids=request.data.get("invoice_ids") or [],
            section_code=str(request.data.get("section") or ""),
            certificate_id=int(request.data.get("certificate_id") or 0),
            settle_by=str(request.data.get("settle_by") or ""),
        )
        AuditService.log(
            action="billing.tds_claim", company=cu.company, user=request.user,
            entity_type="SaasTdsClaim", entity_id=claim.pk,
            description=f"TDS claim {claim.amount} for {claim.quarter} submitted ({claim.settle_by.lower()}).",
        )
        return Response(SaasTdsClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class SaasTdsClaimRefundView(APIView):
    """POST /api/v1/billing/tds-claims/<pk>/refund/ — WP-BL1 (Q5): refund the credit still left on a
    claim instead of taking it off the next renewal."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request, pk: int):
        from .models import SaasTdsClaim
        from .serializers import SaasTdsClaimSerializer
        from .tds_claims import request_refund

        cu = get_company_user(request)
        claim = SaasTdsClaim.objects.filter(company=cu.company, pk=pk).first()
        if claim is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        claim = request_refund(claim, user=request.user)
        AuditService.log(
            action="billing.tds_claim_refund", company=cu.company, user=request.user,
            entity_type="SaasTdsClaim", entity_id=claim.pk,
            description=f"Owner asked for TDS claim {claim.pk} to be refunded instead of credited.",
        )
        return Response(SaasTdsClaimSerializer(claim).data)


class OnboardingChecklistView(APIView):
    """GET /api/v1/billing/onboarding/ — WP-GR2: the home-screen checklist (any member).
    POST /api/v1/billing/onboarding/dismiss/ — the owner hides it."""

    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        from .onboarding import checklist

        return Response(checklist(get_company_user(request).company))


class OnboardingDismissView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        from .onboarding import checklist, dismiss

        cu = get_company_user(request)
        dismiss(cu.company)
        return Response(checklist(cu.company))
