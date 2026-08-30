"""Wave 22 Sprint F2 — FIFO/serial/challan/PR/CRM/price_role fixes."""



from decimal import Decimal



import pytest



from core.exceptions import BusinessRuleError

from crm.models import Lead, Opportunity

from crm.services import convert_lead

from inventory.models import InventoryCostLayer, MovementType, SerialNumber, StockMovement

from inventory.services import InventoryService

from masters.models import PriceList, PriceListItem

from masters.pricing import resolve_unit_price

from purchases.models import PurchaseReturn

from sales.models import DeliveryChallan, SalesInvoice

from sales.services import SalesService

from tests.conftest import (

    add_stock,

    create_draft_invoice,

    create_draft_purchase,

    make_customer,

    make_product,

    make_supplier,

)



pytestmark = pytest.mark.django_db





def test_bb_000717_challan_cancel_restores_peels_and_serials(tenant_a):

    company = tenant_a.company

    company.inventory_valuation_method = "FIFO"

    company.stock_on_delivery_challan = True

    company.save(update_fields=["inventory_valuation_method", "stock_on_delivery_challan"])

    product = make_product(company, sku="CH-SN", track_serial=True)

    wh = InventoryService.default_warehouse(company)

    InventoryService.post_movement(

        company=company, product=product, warehouse=wh,

        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="25", user=tenant_a.owner,

    )

    SerialNumber.objects.create(

        company=company, product=product, warehouse=wh,

        serial_number="CH-SN-1", status=SerialNumber.Status.AVAILABLE,

    )

    layer = InventoryCostLayer.objects.get(company=company, product=product)

    customer = make_customer(company)

    create = tenant_a.client.post(

        "/api/v1/sales/delivery-challans/",

        {

            "customer": customer.id,

            "items": [

                {

                    "product": product.id,

                    "quantity": "1",

                    "unit_price": "100",

                    "gst_rate": "0",

                    "serial_numbers": ["CH-SN-1"],

                }

            ],

        },

        format="json",

    )

    assert create.status_code == 201, create.data

    challan_id = create.data["id"]

    assert tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_id}/complete/").status_code == 200

    sale = StockMovement.objects.get(

        company=company, product=product, movement_type=MovementType.SALE,

        reference_type="delivery_challan", reference_id=str(challan_id),

    )

    assert sale.layer_peels

    layer.refresh_from_db()

    assert layer.qty_remaining == Decimal("0")

    assert SerialNumber.objects.get(serial_number="CH-SN-1").status == SerialNumber.Status.SOLD



    cancel = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_id}/cancel/")

    assert cancel.status_code == 200, cancel.data

    layer.refresh_from_db()

    assert layer.qty_remaining == Decimal("1")

    assert SerialNumber.objects.get(serial_number="CH-SN-1").status == SerialNumber.Status.AVAILABLE

    assert not InventoryCostLayer.objects.filter(

        company=company, product=product, source_movement__reference_type="delivery_challan_cancel"

    ).exists()

    assert DeliveryChallan.objects.get(pk=challan_id).status == DeliveryChallan.Status.CANCELLED





def test_bb_000722_purchase_return_requires_and_scraps_serials(tenant_a):

    company = tenant_a.company

    product = make_product(company, sku="PR-SN", track_serial=True, purchase_price="50")

    supplier = make_supplier(company)

    inv = create_draft_purchase(

        tenant_a,

        supplier,

        [{"product": product.id, "quantity": "1", "unit_price": "50", "serial_numbers": ["PR-SN-1"]}],

        purchase_type="NON_GST",

    )

    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{inv['id']}/complete/").status_code == 200

    assert SerialNumber.objects.get(serial_number="PR-SN-1").status == SerialNumber.Status.AVAILABLE



    bad = tenant_a.client.post(

        "/api/v1/purchases/returns/",

        {

            "supplier": supplier.id,

            "purchase_invoice": inv["id"],

            "items": [{"product": product.id, "quantity": "1", "unit_price": "50"}],

        },

        format="json",

    )

    assert bad.status_code == 400, bad.data



    good = tenant_a.client.post(

        "/api/v1/purchases/returns/",

        {

            "supplier": supplier.id,

            "purchase_invoice": inv["id"],

            "items": [

                {

                    "product": product.id,

                    "quantity": "1",

                    "unit_price": "50",

                    "serial_numbers": ["PR-SN-1"],

                }

            ],

        },

        format="json",

    )

    assert good.status_code == 201, good.data

    ret_id = good.data["id"]

    assert PurchaseReturn.objects.get(pk=ret_id).items.first().serial_numbers == ["PR-SN-1"]

    assert tenant_a.client.post(f"/api/v1/purchases/returns/{ret_id}/complete/").status_code == 200

    # A SELLABLE purchase return sends the unit back to the supplier — it is
    # RETURNED, not SCRAPPED (only condition=DAMAGED scraps). See
    # PurchaseService.complete_return.
    assert SerialNumber.objects.get(serial_number="PR-SN-1").status == SerialNumber.Status.RETURNED





def test_bb_000731_convert_lead_idempotent(tenant_a):

    lead = Lead.objects.create(

        company=tenant_a.company, name="Dup Convert", status=Lead.Status.NEW,

        created_by=tenant_a.owner, updated_by=tenant_a.owner,

    )

    lead1, opp1, cust1 = convert_lead(lead, tenant_a.owner)

    lead2, opp2, cust2 = convert_lead(lead, tenant_a.owner)

    assert lead1.pk == lead2.pk

    assert opp1.pk == opp2.pk

    assert cust1.pk == cust2.pk

    assert Opportunity.objects.filter(lead=lead).count() == 1

    assert Lead.objects.get(pk=lead.pk).status == Lead.Status.QUALIFIED





def test_bb_000728_price_role_owner_override(tenant_a):

    company = tenant_a.company

    pl = PriceList.objects.create(company=company, name="List A")

    product = make_product(company, sku="PL-1", selling_price="100")

    PriceListItem.objects.create(

        company=company, price_list=pl, product=product, unit_price=Decimal("90")

    )

    customer = make_customer(company)

    customer.price_list = pl

    customer.save(update_fields=["price_list"])



    assert resolve_unit_price(

        customer=customer, product=product, requested_price="80", role="SALES_STAFF"

    ) == Decimal("90")

    assert resolve_unit_price(

        customer=customer, product=product, requested_price="80", role="OWNER"

    ) == Decimal("80")



    inv = create_draft_invoice(

        tenant_a,

        customer,

        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}],

        invoice_type="NON_GST",

    )

    line = SalesInvoice.objects.get(pk=inv["id"]).items.get()

    assert line.unit_price == Decimal("80")





def test_bb_000721_forbid_qty_amend_on_serial_completed(tenant_a):

    product = make_product(tenant_a.company, sku="H9-SN", track_serial=True)

    add_stock(tenant_a, product, "2")

    SerialNumber.objects.create(

        company=tenant_a.company, product=product,

        warehouse=InventoryService.default_warehouse(tenant_a.company),

        serial_number="H9-1", status=SerialNumber.Status.AVAILABLE,

    )

    customer = make_customer(tenant_a.company)

    inv = create_draft_invoice(

        tenant_a,

        customer,

        [

            {

                "product": product.id,

                "quantity": "1",

                "unit_price": "100",

                "gst_rate": "0",

                "serial_numbers": ["H9-1"],

            }

        ],

        invoice_type="NON_GST",

    )

    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    invoice = SalesInvoice.objects.get(pk=inv["id"])

    with pytest.raises(BusinessRuleError, match="batch/serial"):

        SalesService.set_items(

            invoice,

            [

                {

                    "product": product,

                    "quantity": "2",

                    "unit_price": "100",

                    "gst_rate": "0",

                    "serial_numbers": ["H9-1", "H9-2"],

                }

            ],

            tenant_a.owner,

        )


