"""Next-batch coverage: SMTP fail-closed, purchase CN link, GSP factory."""

from decimal import Decimal

import pytest
from django.test import override_settings

from core.exceptions import BusinessRuleError
from core.models import Notification
from core.services.gsp_adapters import LiveIrpAdapter, SandboxIrpAdapter, get_irp_adapter
from core.services.notifications import NotificationService
from core.tasks import send_email_notification
from purchases.models import PurchaseCreditNote
from purchases.notes_services import PurchaseNotesService
from tests.conftest import make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_email_console_blocked_in_production(tenant_a):
    n = Notification.objects.create(
        company=tenant_a.company,
        channel=Notification.Channel.EMAIL,
        recipient="a@example.com",
        subject="t",
        body="b",
    )
    with override_settings(
        DJANGO_ENV="production",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    ):
        send_email_notification(n.id)
    n.refresh_from_db()
    assert n.status == Notification.Status.FAILED
    assert "SMTP" in n.error or "console" in n.error.lower()


def test_notification_service_fails_closed_production(tenant_a):
    with override_settings(
        DJANGO_ENV="production",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    ):
        n = NotificationService.send(
            company=tenant_a.company,
            channel=Notification.Channel.EMAIL,
            recipient="a@example.com",
            subject="t",
            body="b",
            user=tenant_a.owner,
        )
    assert n.status == Notification.Status.FAILED


def test_gst_purchase_cn_requires_invoice(tenant_a):
    company = tenant_a.company
    company.gstin = "29AAAAA0000A1ZY"
    company.registration_type = "REGULAR"
    company.save(update_fields=["gstin", "registration_type"])
    supplier = make_supplier(company)
    product = make_product(company)
    note = PurchaseCreditNote.objects.create(
        company=company,
        supplier=supplier,
        purchase_invoice=None,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    PurchaseNotesService.set_credit_note_items(
        note,
        [
            {
                "product": product,
                "quantity": Decimal("1"),
                "unit_price": Decimal("100"),
                "gst_rate": Decimal("18"),
            }
        ],
        tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="link purchase credit notes"):
        PurchaseNotesService.complete_credit_note(note, tenant_a.owner)


def test_gsp_factory_sandbox_by_default(tenant_a):
    company = tenant_a.company
    company.gsp_provider = "sandbox"
    assert isinstance(get_irp_adapter(company), SandboxIrpAdapter)


@override_settings(GSP_LIVE_ENABLED=True, GSP_CERTIFIED=True, GSP_LIVE_BASE_URL="")
def test_gsp_live_without_creds_raises(tenant_a):
    company = tenant_a.company
    company.gsp_provider = "cleartax"
    company.gsp_credentials_encrypted = ""
    adapter = get_irp_adapter(company)
    assert isinstance(adapter, LiveIrpAdapter)
    with pytest.raises(BusinessRuleError, match="not configured"):
        adapter.submit({})
