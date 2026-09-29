"""Security hardening test: Dedicated IP rate-limiting bucket on /pay/:token."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from django.core.cache import cache

from payments.models import PaymentLink
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def test_public_pay_token_endpoint_is_rate_limited(tenant_a):
    """Calling /api/v1/payments/public/pay/<token>/ repeatedly exhausts the public_pay bucket

    and returns 429 Too Many Requests once the budget (20/min) is reached.
    """
    cache.clear()
    company = tenant_a.company
    customer = make_customer(company, state="Karnataka")

    # Create active payment link directly
    link = PaymentLink.objects.create(
        company=company,
        customer=customer,
        token="paytok_ratelimit_bucket_test",
        amount=Decimal("100.00"),
        expires_at=timezone.now() + timedelta(days=2),
    )

    client = APIClient()
    url = f"/api/v1/public/pay/{link.token}/"

    # Make 20 allowed requests within rate budget (20/min)
    statuses = [client.get(url).status_code for _ in range(20)]
    assert all(code == status.HTTP_200_OK for code in statuses), f"Expected 200s, got {statuses}"

    # 21st request from same IP must trigger 429 Too Many Requests
    resp_21 = client.get(url)
    assert resp_21.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "throttled" in str(resp_21.data).lower()
