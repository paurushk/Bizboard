"""9.3 — fail-closed circuit breaker for money-path outbound HTTP."""

from __future__ import annotations

import pytest
from django.core.cache import cache

from core.circuit_breaker import CircuitOpenError, call, reset

pytestmark = pytest.mark.django_db


def test_circuit_opens_after_threshold_and_fail_closes():
    reset("razorpay_subscriptions")
    cache.clear()

    def boom():
        raise RuntimeError("upstream down")

    for _ in range(5):
        with pytest.raises(RuntimeError):
            call("razorpay_subscriptions", boom, failure_threshold=5, cooldown_seconds=30)

    with pytest.raises(CircuitOpenError):
        call("razorpay_subscriptions", boom, failure_threshold=5, cooldown_seconds=30)

    called = {"n": 0}

    def should_not_run():
        called["n"] += 1
        return "ok"

    with pytest.raises(CircuitOpenError):
        call("razorpay_subscriptions", should_not_run, failure_threshold=5, cooldown_seconds=30)
    assert called["n"] == 0


def test_circuit_resets_on_success():
    reset("test_cb")
    n = {"fails": 0}

    def flaky():
        n["fails"] += 1
        if n["fails"] < 3:
            raise RuntimeError("flaky")
        return "ok"

    with pytest.raises(RuntimeError):
        call("test_cb", flaky, failure_threshold=5, cooldown_seconds=30)
    with pytest.raises(RuntimeError):
        call("test_cb", flaky, failure_threshold=5, cooldown_seconds=30)
    assert call("test_cb", flaky, failure_threshold=5, cooldown_seconds=30) == "ok"
    # Counter cleared — five new failures would be required to open.
    def boom():
        raise RuntimeError("down")

    for _ in range(4):
        with pytest.raises(RuntimeError):
            call("test_cb", boom, failure_threshold=5, cooldown_seconds=30)
    # still closed
    with pytest.raises(RuntimeError):
        call("test_cb", boom, failure_threshold=5, cooldown_seconds=30)
    with pytest.raises(CircuitOpenError):
        call("test_cb", boom, failure_threshold=5, cooldown_seconds=30)


def test_cashfree_and_gsp_fail_closed_when_circuit_open():
    from core.exceptions import BusinessRuleError
    from core.services.gsp_adapters import _http_json
    from payments.gateway import CashfreeGateway

    reset("cashfree_collections")
    reset("gsp_einvoice")

    def boom():
        raise RuntimeError("upstream down")

    for name in ("cashfree_collections", "gsp_einvoice"):
        for _ in range(5):
            with pytest.raises(RuntimeError):
                call(name, boom, failure_threshold=5, cooldown_seconds=30)

    with pytest.raises(BusinessRuleError) as exc:
        CashfreeGateway({"app_id": "x", "secret_key": "y"}).create_payment_link(
            amount=__import__("decimal").Decimal("10"),
            description="",
            customer_name="",
            customer_email="",
            customer_phone="",
            reference="",
            callback_url="http://x",
        )
    assert "temporarily unavailable" in str(exc.value).lower()

    with pytest.raises(BusinessRuleError) as gsp_exc:
        _http_json("GET", "https://example.com/gsp", None)
    assert "temporarily unavailable" in str(gsp_exc.value).lower()


def test_payu_fail_closed_when_circuit_open():
    from decimal import Decimal

    from core.exceptions import BusinessRuleError
    from payments.gateway import PayUGateway

    reset("payu_collections")

    def boom():
        raise RuntimeError("upstream down")

    for _ in range(5):
        with pytest.raises(RuntimeError):
            call("payu_collections", boom, failure_threshold=5, cooldown_seconds=30)

    with pytest.raises(BusinessRuleError) as exc:
        PayUGateway(
            {"merchant_key": "key", "merchant_salt": "salt", "api_base": "https://test.payu.in"}
        ).create_payment_link(
            amount=Decimal("10"),
            description="x",
            customer_name="n",
            customer_email="a@b.c",
            customer_phone="9999999999",
            reference="ref-payu-cb",
            callback_url="http://example.test/pay",
        )
    assert "temporarily unavailable" in str(exc.value).lower()


def test_checkout_fail_closed_when_circuit_open(tenant_a):
    from billing.models import Plan
    from core.circuit_breaker import reset as cb_reset
    from django.test import override_settings

    cb_reset("razorpay_subscriptions")
    plan = Plan.objects.create(
        name="Live", slug="live-cb", seat_limit=2, price_paise=100,
        razorpay_plan_id="plan_live",
    )
    with override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="secret"):
        def boom():
            raise RuntimeError("razorpay down")

        for _ in range(5):
            with pytest.raises(Exception):
                call("razorpay_subscriptions", boom, failure_threshold=5, cooldown_seconds=60)
        resp = tenant_a.client.post("/api/v1/billing/checkout/", {"plan_id": plan.id}, format="json")
        assert resp.status_code == 400, resp.data
        assert "temporarily unavailable" in str(resp.data).lower() or "could not create" in str(resp.data).lower()
