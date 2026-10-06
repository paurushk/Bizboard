from datetime import timedelta
import pytest
from decimal import Decimal

from django.utils import timezone

from planwave.services import decide_approval


def test_party_bank_account_is_sealed_and_revealed(tenant_a):
    from masters.models import Customer
    from planwave.crypto import open_secret
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Banked")
    customer.party_bank_account = "123456789012"
    customer.save(update_fields=["party_bank_account"])
    stored = Customer.all_objects.get(pk=customer.pk).party_bank_account
    assert stored.startswith("gcm1.")
    assert open_secret(stored) == "123456789012"
    shown = tenant_a.client.get(f"/api/v1/customers/{customer.pk}/")
    assert shown.status_code == 200
    assert shown.data["party_bank_account"] == "123456789012"


def test_partial_receipt_records_the_shortage(tenant_a):
    from inventory.models import StockTransfer, StockTransferLine, Warehouse
    from inventory.services import InventoryService, StockTransferService
    from tests.conftest import add_stock, make_product

    product = make_product(tenant_a.company, sku="TR-SHORT")
    add_stock(tenant_a, product, "10")
    source = InventoryService.default_warehouse(tenant_a.company)
    dest = Warehouse.objects.create(company=tenant_a.company, name="Shop", code="SHOP")
    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=dest,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    line = StockTransferLine.objects.create(
        transfer=transfer, company=tenant_a.company, product=product, quantity=Decimal("4"),
    )
    StockTransferService.dispatch(transfer, tenant_a.owner)
    StockTransferService.receive(
        transfer, tenant_a.owner,
        receipts=[{"line": line.pk, "quantity": "3", "reason": "One carton damaged"}],
    )
    line.refresh_from_db()
    assert line.shortage_qty == Decimal("1.000")
    assert "damaged" in line.shortage_reason
    assert InventoryService.available_quantity(tenant_a.company, product, dest) == Decimal("3")


def test_completed_invoice_cancel_waits_for_a_second_owner(tenant_a):
    from accounts.models import CompanyUser, User
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    second = User.objects.create_user(email="cancel-owner@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(company=tenant_a.company, user=second, role=CompanyUser.Role.OWNER)
    product = make_product(tenant_a.company, sku="CAN-1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Cancel Me")
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/", {}, format="json")
    assert done.status_code == 200, done.data
    from planwave.models import ApprovalRequest
    from sales.models import SalesInvoice

    waiting = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/cancel/", {"reason": "wrong"}, format="json",
    )
    assert waiting.status_code == 202, waiting.data
    # While it waits, nothing has happened to the invoice.
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.COMPLETED
    approval_id = waiting.data["approval_id"]
    # Asking again reuses the open request instead of piling up new ones.
    again = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/cancel/", {"reason": "wrong"}, format="json",
    )
    assert again.status_code == 202 and again.data["approval_id"] == approval_id
    # The requester cannot approve their own request.
    own = ApprovalRequest.objects.get(pk=approval_id)
    with pytest.raises(Exception):
        decide_approval(own, approver=tenant_a.owner, accept=True)
    decide_approval(ApprovalRequest.objects.get(pk=approval_id), approver=second, accept=True)

    done_cancel = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/cancel/",
        {"reason": "wrong", "approval_id": approval_id}, format="json",
    )
    assert done_cancel.status_code == 200, done_cancel.data
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.CANCELLED
    # The approval is spent: it cannot cancel anything else.
    assert ApprovalRequest.objects.get(pk=approval_id).token_used_at is not None


def test_missed_audit_seal_notifies_the_owner(tenant_a):
    from django.core.cache import cache

    from core.models import Notification
    from core.tasks import SEAL_HEARTBEAT_KEY, alert_missed_seal

    cache.set(SEAL_HEARTBEAT_KEY, timezone.now() - timedelta(hours=30), timeout=14 * 24 * 60 * 60)
    alert_missed_seal(company=tenant_a.company, hours_late=30)
    assert Notification.objects.filter(company=tenant_a.company, subject="Audit seal missed").exists()


def test_tally_commit_stays_off(tenant_a):
    resp = tenant_a.client.post("/api/v1/plan/tally-commit/", {}, format="json")
    assert resp.status_code == 200
    assert resp.data["imported"] is False
