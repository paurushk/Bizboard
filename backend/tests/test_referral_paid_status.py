"""PAID is a settlement flag. It does not send money."""

from decimal import Decimal

import pytest

from accounts.models import CompanyUser
from core.models import AuditEvent
from crm.models import ReferralReward
from crm.pipeline import capture_lead
from payments.models import CustomerReceipt, SupplierPayment

from .test_growth_os import _flags


def _bill_and_complete(tenant, customer, amount="500"):
    """A completed invoice is not required to mark a reward paid."""
    from masters.models import Product

    from .conftest import create_draft_invoice, make_product

    product = make_product(
        tenant.company, sku=f"REF-SVC-{customer.id}", product_type=Product.ProductType.SERVICE,
    )
    inv = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    from sales.models import SalesInvoice
    from sales.services import SalesService

    invoice = SalesInvoice.objects.get(pk=inv["id"])
    SalesService.complete(invoice, tenant.owner)
    return invoice


@pytest.mark.django_db
def test_mark_paid_records_status_and_does_not_move_money(tenant_a):
    _flags(tenant_a.company)
    from .conftest import make_customer

    customer = make_customer(tenant_a.company)
    _bill_and_complete(tenant_a, customer)
    issued = tenant_a.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": customer.id, "reward_type": "FLAT", "reward_value": "40"},
        format="json",
    )
    assert issued.status_code == 201, issued.data
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Referred", phone="9000000199",
        referral_code=issued.data["code"],
    )
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/",
        {"won": True, "amount": "100"},
        format="json",
    )
    reward = ReferralReward.objects.get(opportunity_id=converted.data["opportunity"]["id"])
    too_soon = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert too_soon.status_code == 400
    denied = tenant_a.staff_client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert denied.status_code == 403

    tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")
    receipts_before = CustomerReceipt.objects.count()
    payments_before = SupplierPayment.objects.count()
    paid = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert paid.status_code == 200, paid.data
    assert paid.data["reward_status"] == ReferralReward.Status.PAID
    assert paid.data["paid_at"]
    reward.refresh_from_db()
    assert reward.paid_at is not None
    assert CustomerReceipt.objects.count() == receipts_before
    assert SupplierPayment.objects.count() == payments_before
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="referral_reward_marked_paid", entity_id=str(reward.pk),
    ).exists()

    # A second mark-paid is a no-op. It must not draft a credit note.
    again = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert again.status_code == 200, again.data
    assert again.data["reward_status"] == ReferralReward.Status.PAID
    assert CustomerReceipt.objects.count() == receipts_before
    assert SupplierPayment.objects.count() == payments_before
    still_paid = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/reject/")
    assert still_paid.status_code == 400

    board = tenant_a.client.get("/api/v1/crm/referrals/codes/leaderboard/")
    assert Decimal(board.data[0]["approved_total"]) == Decimal("40")


def _won_reward(tenant, phone):
    from .conftest import make_customer

    customer = make_customer(tenant.company, name=f"Referrer {phone}")
    issued = tenant.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": customer.id, "reward_type": "FLAT", "reward_value": "15"},
        format="json",
    )
    assert issued.status_code == 201, issued.data
    lead = capture_lead(
        tenant.company, tenant.owner, name="Buyer", phone=phone,
        referral_code=issued.data["code"],
    )
    converted = tenant.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/",
        {"won": True, "amount": "50"},
        format="json",
    )
    assert converted.status_code == 200, converted.data
    return ReferralReward.objects.get(opportunity_id=converted.data["opportunity"]["id"])


@pytest.mark.django_db
def test_paid_is_owner_or_manager_only_and_stays_out_of_other_companies(tenant_a, tenant_b):
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    reward = _won_reward(tenant_a, "9000000201")
    empty = tenant_a.client.get("/api/v1/crm/referrals/codes/leaderboard/")
    assert empty.data == []

    rejected = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/reject/")
    assert rejected.status_code == 200
    still_rejected = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert still_rejected.status_code == 400

    second = _won_reward(tenant_a, "9000000202")
    _bill_and_complete(tenant_a, second.referral_code.referrer_customer)
    tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{second.id}/approve/")
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.role = CompanyUser.Role.MANAGER
    membership.can_create_sales = True
    membership.save(update_fields=["role", "can_create_sales"])
    paid = tenant_a.staff_client.post(f"/api/v1/crm/referrals/rewards/{second.id}/mark-paid/")
    assert paid.status_code == 200, paid.data
    assert paid.data["reward_status"] == ReferralReward.Status.PAID
    approved_again = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{second.id}/approve/")
    assert approved_again.status_code == 400
    assert tenant_b.client.post(f"/api/v1/crm/referrals/rewards/{second.id}/mark-paid/").status_code == 404
    board = tenant_a.client.get("/api/v1/crm/referrals/codes/leaderboard/")
    assert Decimal(board.data[0]["approved_total"]) == Decimal("15")
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    assert SupplierPayment.objects.filter(company=tenant_a.company).count() == 0
