"""Next batch: SO CONFIRMED reservation + stock_on_delivery_challan."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, StockMovement
from sales.models import SalesOrder
from sales.notes_services import SalesNotesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _draft_order(tenant, product, qty="3"):
    customer = make_customer(tenant.company)
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [
                {
                    "product": product.id,
                    "quantity": qty,
                    "unit_price": "100",
                    "gst_rate": "0",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return SalesOrder.objects.get(pk=resp.data["id"]), customer


def test_confirm_reserves_cancel_releases(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    order, _ = _draft_order(tenant_a, product, qty="4")

    confirmed = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/confirm/")
    assert confirmed.status_code == 200, confirmed.data
    assert confirmed.data["status"] == "CONFIRMED"

    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("4")
    assert balance.available == Decimal("6")

    cancelled = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["status"] == "CANCELLED"

    balance.refresh_from_db()
    assert balance.reserved == Decimal("0")
    assert balance.available == Decimal("10")


def test_confirm_insufficient_available_under_block_fails(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "2")
    tenant_a.company.negative_stock_policy = "BLOCK"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    order, _ = _draft_order(tenant_a, product, qty="5")

    resp = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/confirm/")
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == "DRAFT"
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("0")


def test_challan_with_flag_posts_stock_once(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    tenant_a.company.stock_on_delivery_challan = True
    tenant_a.company.save(update_fields=["stock_on_delivery_challan"])
    customer = make_customer(tenant_a.company)

    challan_resp = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [
                {
                    "product": product.id,
                    "quantity": "3",
                    "unit_price": "100",
                    "gst_rate": "0",
                }
            ],
        },
        format="json",
    )
    assert challan_resp.status_code == 201, challan_resp.data
    done = tenant_a.client.post(
        f"/api/v1/sales/delivery-challans/{challan_resp.data['id']}/complete/"
    )
    assert done.status_code == 200, done.data
    assert done.data["stock_posted"] is True

    sales = StockMovement.objects.filter(
        company=tenant_a.company,
        product=product,
        movement_type=MovementType.SALE,
        reference_type="delivery_challan",
        reference_id=str(challan_resp.data["id"]),
    )
    assert sales.count() == 1
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.on_hand == Decimal("7")

    # Convert + complete invoice must not post a second SALE for the same qty.
    inv_resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-challans/{challan_resp.data['id']}/convert/"
    )
    assert inv_resp.status_code == 200, inv_resp.data
    complete = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/")
    assert complete.status_code == 200, complete.data

    assert (
        StockMovement.objects.filter(
            company=tenant_a.company, product=product, movement_type=MovementType.SALE
        ).count()
        == 1
    )
    balance.refresh_from_db()
    assert balance.on_hand == Decimal("7")


def test_convert_confirmed_order_releases_reservation(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    order, _ = _draft_order(tenant_a, product, qty="2")
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("2")

    invoice = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    balance.refresh_from_db()
    # CR-020: reservation is held while converted draft invoice is pending completion
    assert balance.reserved == Decimal("2")
    order.refresh_from_db()
    assert order.converted_invoice_id == invoice.id

    from sales.services import SalesService
    SalesService.complete(invoice, tenant_a.owner)
    balance.refresh_from_db()
    assert balance.reserved == Decimal("0")
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONVERTED


def test_order_gates_block_draft_convert_and_ignore_a_five_percent_margin(tenant_a):
    from core.exceptions import BusinessRuleError
    from sales.models import SalesOrderItem
    from sales.order_gates import apply_order_gates

    customer = make_customer(tenant_a.company, name="Gate Co", credit_limit=Decimal("100"))
    product = make_product(tenant_a.company, sku="GATE-EDGE", purchase_price="95", selling_price="100")
    order = SalesOrder.objects.create(
        company=tenant_a.company,
        customer=customer,
        grand_total=Decimal("30"),
        created_by=tenant_a.owner,
    )
    SalesNotesService._require_confirmation_when_gates_on(order)
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ORDER_GATES"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    with pytest.raises(BusinessRuleError, match="Confirm this sales order"):
        SalesNotesService.convert_sales_order(order, tenant_a.owner)
    with pytest.raises(BusinessRuleError, match="Confirm this sales order"):
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    order.status = SalesOrder.Status.CONFIRMED
    order.save(update_fields=["status"])
    SalesNotesService._require_confirmation_when_gates_on(order)
    item = SalesOrderItem.objects.create(
        company=tenant_a.company,
        sales_order=order,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
    )
    assert apply_order_gates(order, [item]) == []
    item.unit_price = Decimal("96")
    item.save(update_fields=["unit_price"])
    product.purchase_price = Decimal("96")
    product.save(update_fields=["purchase_price"])
    warnings = apply_order_gates(order, [item])
    assert warnings and warnings[0]["product_id"] == product.id
    other = SalesOrder.objects.create(
        company=tenant_a.company,
        customer=customer,
        grand_total=Decimal("80"),
        status=SalesOrder.Status.DRAFT,
        created_by=tenant_a.owner,
    )
    order.grand_total = Decimal("30")
    order.save(update_fields=["grand_total"])
    with pytest.raises(BusinessRuleError, match="Credit limit"):
        apply_order_gates(order, [item])
    other.status = SalesOrder.Status.CANCELLED
    other.save(update_fields=["status"])
    assert apply_order_gates(order, [item]) == warnings


def test_credit_override_is_owner_only_and_copies_onto_that_invoice(tenant_a):
    from accounts.models import CompanyUser
    from core.exceptions import BusinessRuleError
    from sales.models import SalesInvoice, SalesOrderItem
    from sales.order_gates import apply_order_gates, copy_credit_override, invoice_has_credit_override

    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ORDER_GATES"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company, name="Over Co", credit_limit=Decimal("100"))
    product = make_product(tenant_a.company, sku="OVR-1", purchase_price="10", selling_price="100")
    order = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("150"), created_by=tenant_a.owner,
    )
    item = SalesOrderItem.objects.create(
        company=tenant_a.company, sales_order=order, product=product,
        quantity=Decimal("1"), unit_price=Decimal("100"),
    )
    staff = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    with pytest.raises(BusinessRuleError):
        apply_order_gates(order, [item], override_reason="please", acting_user=staff)
    with pytest.raises(BusinessRuleError):
        apply_order_gates(order, [item], override_reason="   ", acting_user=tenant_a.owner)
    with pytest.raises(BusinessRuleError):
        apply_order_gates(order, [item], override_reason="x" * 501, acting_user=tenant_a.owner)
    assert order.credit_overridden_at is None
    apply_order_gates(order, [item], override_reason="  owner approved  ", acting_user=tenant_a.owner)
    order.save()
    order.refresh_from_db()
    owner_member = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)
    assert order.credit_override_reason == "owner approved"
    assert order.credit_overridden_by_id == owner_member.id
    assert order.credit_overridden_at is not None
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("150"),
        status=SalesInvoice.Status.DRAFT, created_by=tenant_a.owner,
    )
    copy_credit_override(order, invoice)
    invoice.refresh_from_db()
    assert invoice_has_credit_override(invoice) is True
    unrelated = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("10"),
        status=SalesInvoice.Status.DRAFT, created_by=tenant_a.owner,
    )
    assert invoice_has_credit_override(unrelated) is False
    unlimited = make_customer(tenant_a.company, name="No Limit", credit_limit=Decimal("0"))
    open_order = SalesOrder.objects.create(
        company=tenant_a.company, customer=unlimited, grand_total=Decimal("9999"), created_by=tenant_a.owner,
    )
    open_item = SalesOrderItem.objects.create(
        company=tenant_a.company, sales_order=open_order, product=product,
        quantity=Decimal("1"), unit_price=Decimal("100"),
    )
    apply_order_gates(open_order, [open_item], acting_user=tenant_a.owner)
    assert open_order.credit_overridden_at is None


def test_owner_membership_excludes_deactivated_and_cross_tenant_owner(tenant_a, tenant_b):
    from accounts.models import CompanyUser
    from sales.order_gates import _owner_membership

    owner_member = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)
    assert _owner_membership(tenant_a.company, tenant_a.owner) == owner_member
    assert _owner_membership(tenant_a.company, owner_member) == owner_member

    tenant_a.owner.is_active = False
    tenant_a.owner.save(update_fields=["is_active"])
    assert _owner_membership(tenant_a.company, tenant_a.owner) is None
    owner_member.refresh_from_db()
    assert _owner_membership(tenant_a.company, owner_member) is None
    tenant_a.owner.is_active = True
    tenant_a.owner.save(update_fields=["is_active"])

    assert _owner_membership(tenant_b.company, tenant_a.owner) is None
    assert _owner_membership(tenant_a.company, tenant_b.owner) is None
    assert _owner_membership(tenant_a.company, None) is None


def test_override_reason_non_string_blocks_instead_of_crashing(tenant_a):
    from core.exceptions import BusinessRuleError
    from sales.models import SalesOrderItem
    from sales.order_gates import apply_order_gates

    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ORDER_GATES"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company, name="Non-String Co", credit_limit=Decimal("50"))
    product = make_product(tenant_a.company, sku="NONSTR-1", purchase_price="10", selling_price="100")
    order = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("100"), created_by=tenant_a.owner,
    )
    item = SalesOrderItem.objects.create(
        company=tenant_a.company, sales_order=order, product=product,
        quantity=Decimal("1"), unit_price=Decimal("100"),
    )
    for bad_reason in (123, {"reason": "ok"}, ["ok"]):
        with pytest.raises(BusinessRuleError, match="Credit limit"):
            apply_order_gates(order, [item], override_reason=bad_reason, acting_user=tenant_a.owner)
    assert order.credit_overridden_at is None


def test_exposure_subtracts_only_ledger_counted_invoices(tenant_a):
    from sales.models import SalesInvoice
    from sales.order_gates import sales_order_exposure

    customer = make_customer(tenant_a.company, name="Part Co", credit_limit=Decimal("1000"))
    posted = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("40"),
        status=SalesInvoice.Status.COMPLETED, created_by=tenant_a.owner,
    )
    confirmed = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("100"),
        status=SalesOrder.Status.CONFIRMED, converted_invoice=posted, created_by=tenant_a.owner,
    )
    draft_invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("25"),
        status=SalesInvoice.Status.DRAFT, created_by=tenant_a.owner,
    )
    SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("25"),
        status=SalesOrder.Status.CONFIRMED, converted_invoice=draft_invoice, created_by=tenant_a.owner,
    )
    current = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, grand_total=Decimal("10"),
        status=SalesOrder.Status.DRAFT, created_by=tenant_a.owner,
    )
    assert sales_order_exposure(tenant_a.company, customer, current) == Decimal("135")
    assert confirmed.converted_invoice_id == posted.id


def test_shared_margin_helper_does_not_warn_at_exactly_five_percent():
    from core.services.margin import margin_below_threshold, margin_ratio

    assert margin_ratio(Decimal("100"), Decimal("95")) == Decimal("0.05")
    assert margin_below_threshold(Decimal("100"), Decimal("95")) is False
    assert margin_below_threshold(Decimal("100"), Decimal("96")) is True
