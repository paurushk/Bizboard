"""Wave 1 slices: audit IP and before/after, missed seal alert, session version."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.views import _tokens_for_user
from core.models import AuditEvent, Notification
from core.tasks import SEAL_HEARTBEAT_KEY, alert_missed_seal, seal_gap_seconds

pytestmark = pytest.mark.django_db


def test_posting_event_names_imply_the_prior_status():
    from core.services.audit import before_status_for_event

    assert before_status_for_event("sales_invoice.completed") == "DRAFT"
    assert before_status_for_event("journal.posted") == "DRAFT"
    assert before_status_for_event("sales_invoice.cancelled") == "COMPLETED"
    assert before_status_for_event("journal.reversed") == "POSTED"
    assert before_status_for_event("customer_receipt.created") == ""


def test_purchase_complete_audit_has_ip_and_before_status(tenant_a):
    from tests.conftest import create_draft_purchase, make_product, make_supplier

    product = make_product(tenant_a.company, sku="AUD-IP")
    supplier = make_supplier(tenant_a.company)
    draft = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "10.00", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(
        f"/api/v1/purchases/invoices/{draft['id']}/complete/",
        REMOTE_ADDR="203.0.113.10",
    )
    assert resp.status_code == 200, resp.data
    event = AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="PurchaseInvoice", entity_id=str(draft["id"]),
        description__icontains="purchase_invoice.completed",
    ).latest("id")
    assert event.metadata.get("ip") == "203.0.113.10"
    assert event.metadata.get("before", {}).get("status") == "DRAFT"
    assert event.metadata.get("after", {}).get("status")


def test_seal_gap_alerts_the_owner_and_a_fresh_run_does_not(tenant_a):
    now = timezone.now()
    assert seal_gap_seconds(None, now) is None
    assert seal_gap_seconds(now - timedelta(hours=2), now) < 26 * 3600
    stale = seal_gap_seconds(now - timedelta(hours=30), now)
    assert stale > 26 * 3600
    alert_missed_seal(company=tenant_a.company, hours_late=stale / 3600)
    assert Notification.objects.filter(
        company=tenant_a.company, subject="Audit seal missed",
    ).exists()
    cache.set(SEAL_HEARTBEAT_KEY, now, timeout=60)
    assert cache.get(SEAL_HEARTBEAT_KEY) == now


def test_deactivated_user_access_token_is_rejected(tenant_a):
    from accounts.models import CompanyUser

    staff = tenant_a.staff
    membership = CompanyUser.objects.get(company=tenant_a.company, user=staff)
    tokens = _tokens_for_user(staff)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    ok = client.get("/api/v1/auth/me/")
    assert ok.status_code == 200, ok.content

    membership.is_active = False
    membership.save(update_fields=["is_active"])
    from accounts.views import _revoke_sessions_if_last_active_membership

    _revoke_sessions_if_last_active_membership(staff)
    staff.refresh_from_db()
    assert staff.session_version == 1
    denied = APIClient()
    denied.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    again = denied.get("/api/v1/auth/me/")
    assert again.status_code == 401
