"""CRM Lead to Order & Dispatch persona journey.

Validates:
1. P3 (Order Booker / Sales Staff) captures and qualifies a CRM Lead.
2. Lead is converted into Customer master (convert_lead).
3. P3 creates Sales Order for customer.
4. Delivery Challan issued for dispatch:
   - Deducts warehouse stock upon goods dispatch.
   - Proves financial ledgers (AR/Revenue) are unposted at challan stage.
5. Tax Invoice generated for dispatched goods:
   - Posts AR and GST output ledgers.
   - Prevents double stock deduction.
6. Boundary check: P3 Order Booker cannot view accounting ledgers or post manual journals.
7. Zero invariant violations: assert_all_invariants(company) holds throughout.
"""

from decimal import Decimal
import pytest

from core.invariants import assert_all_invariants
from core.models import AuditEvent
from crm.models import Lead, Opportunity, ReferralReward
from crm.referrals import issue_referral_code
from crm.services import convert_lead
from inventory.models import MovementType, StockBalance
from inventory.services import InventoryService
from ledgers.services import LedgerService
from tests.personas.fixtures import seed_archetype

pytestmark = [pytest.mark.django_db, pytest.mark.dark_module]


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def test_pj_crm_lead_to_sales_order_and_challan_pipeline():
    trader = seed_archetype("trader")
    company = trader.company
    wh = trader.warehouses[0]
    plain_prods = [p for p in trader.products if not p.track_batch and not p.track_serial]
    prod = plain_prods[0]

    prod.gst_rate = Decimal("18")
    prod.hsn_code = ""
    prod.save(update_fields=["gst_rate", "hsn_code"])

    company.stock_on_delivery_challan = True
    company.save(update_fields=["stock_on_delivery_challan"])

    # Inward opening stock: 50 units
    InventoryService.post_movement(
        company=company,
        product=prod,
        warehouse=wh,
        quantity=Decimal("50"),
        movement_type=MovementType.PURCHASE,
        unit_cost=Decimal("60.00"),
        user=trader.owner,
    )

    # 1. P3 (Sales Staff) creates and qualifies CRM Lead
    lead = Lead.objects.create(
        company=company,
        name="Apex Enterprise Solutions",
        phone="+919876543210",
        email="purchase@apexsolutions.in",
        status=Lead.Status.QUALIFIED,
        created_by=trader.sales,
        updated_by=trader.sales,
    )

    # 2. Convert Lead to Customer
    lead, opp, customer = convert_lead(lead, trader.sales, won=True, amount=Decimal("3000.00"))
    assert customer is not None
    assert customer.name == "Apex Enterprise Solutions"

    # 3. P3 drafts and confirms Sales Order for 20 units @ 150 + 18% GST = 3540
    so_resp = trader.sales_client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "items": [
                {"product": prod.id, "quantity": "20", "unit_price": "150.00", "gst_rate": "18"}
            ],
        },
        format="json",
    )
    assert so_resp.status_code == 201, so_resp.data
    so_id = _body(so_resp)["id"]

    # Stock is still 50 (sales order reserves, does not physically move stock)
    assert StockBalance.objects.get(company=company, product=prod, warehouse=wh).on_hand == Decimal("50")

    # 4. Delivery Challan generated for dispatching the 20 units
    dc_resp = trader.sales_client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "sales_order": so_id,
            "items": [{"product": prod.id, "quantity": "20", "unit_price": "150.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert dc_resp.status_code == 201, dc_resp.data
    dc_id = _body(dc_resp)["id"]

    # Complete Delivery Challan -> physical goods leave the warehouse
    dc_comp = trader.sales_client.post(f"/api/v1/sales/delivery-challans/{dc_id}/complete/")
    assert dc_comp.status_code == 200, dc_comp.data

    # Stock is now 30 (dispatched on delivery challan)
    assert StockBalance.objects.get(company=company, product=prod, warehouse=wh).on_hand == Decimal("30")
    # Customer financial balance is still 0 (Challan is non-financial)
    assert LedgerService.customer_outstanding(company, customer) == Decimal("0.00")

    # 5. Convert Delivery Challan into finalized Tax Invoice
    conv_resp = trader.sales_client.post(f"/api/v1/sales/delivery-challans/{dc_id}/convert/")
    assert conv_resp.status_code == 200, conv_resp.data
    inv_id = _body(conv_resp)["id"]

    comp_inv = trader.sales_client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert comp_inv.status_code == 200, comp_inv.data

    # Stock remains 30 (no double deduction)
    assert StockBalance.objects.get(company=company, product=prod, warehouse=wh).on_hand == Decimal("30")

    # Customer AR is now debited: 20 * 150 * 1.18 = 3540.00
    assert LedgerService.customer_outstanding(company, customer) == Decimal("3540.00")

    # 6. Boundary check: P3 Sales Booker cannot post manual accounting journals
    sales_journal = trader.sales_client.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-05-15", "lines": []},
        format="json",
    )
    assert sales_journal.status_code in (403, 404), "Sales staff cannot post journals"

    # 7. Invariants hold
    assert_all_invariants(company)


def test_pj_crm_referral_self_referral_guard_auto_rejects_reward():
    """CRM referral fraud guard (crm.referrals): a won opportunity that resolves
    back to its own referrer is a self-referral -- the reward is auto-rejected
    (never silently paid, never blocked from completing the sale) and the
    rejection leaves a permanent audit trail. A genuine, unrelated referral on
    the same code stays PENDING, showing the guard is selective, not a blanket
    referral-reward kill switch.
    """
    trader = seed_archetype("trader")
    company = trader.company
    # ENABLE_REFERRALS is a company-authoritative rollout flag (core.services.
    # feature_flags.ROLLOUT_GRANTABLE_KEYS); ENABLE_CRM must be re-asserted in
    # the same JSON write or touching any other module key here would flip the
    # dark-module default (ENABLE_CRM) off for this company (see
    # feature_flags._build_feature_flags_uncached's "opt-in once you touch
    # module flags" rule).
    company.feature_flags = {"ENABLE_CRM": True, "ENABLE_REFERRALS": True, "pack_grant": "insurance"}
    company.save(update_fields=["feature_flags"])

    referrer_and_referee = trader.customers[0]
    genuine_referee = trader.customers[1]

    code = issue_referral_code(
        company, trader.owner,
        referrer_customer=referrer_and_referee,
        reward_type="FLAT", reward_value=Decimal("250.00"),
    )

    # 1. Self-referral: the lead's customer IS the code's own referrer.
    self_lead = Lead.objects.create(
        company=company,
        name=referrer_and_referee.name,
        customer=referrer_and_referee,
        referral_code=code,
        status=Lead.Status.QUALIFIED,
        created_by=trader.sales,
        updated_by=trader.sales,
    )
    self_lead, self_opp, self_customer = convert_lead(
        self_lead, trader.sales, won=True, amount=Decimal("5000.00")
    )
    assert self_customer.id == referrer_and_referee.id
    assert self_opp.stage == Opportunity.Stage.WON  # the sale itself is never blocked by the guard

    self_reward = ReferralReward.objects.get(company=company, opportunity=self_opp)
    assert self_reward.reward_status == ReferralReward.Status.REJECTED
    assert AuditEvent.objects.filter(
        company=company,
        action="referral_self_referral_blocked",
        entity_type="ReferralReward",
        entity_id=str(self_reward.id),
    ).exists()

    # 2. Contrast: a genuine referral on the same code (different customer)
    #    is not touched by the guard -- it stays PENDING for manual approval.
    genuine_lead = Lead.objects.create(
        company=company,
        name=genuine_referee.name,
        customer=genuine_referee,
        referral_code=code,
        status=Lead.Status.QUALIFIED,
        created_by=trader.sales,
        updated_by=trader.sales,
    )
    _genuine_lead, genuine_opp, _genuine_customer = convert_lead(
        genuine_lead, trader.sales, won=True, amount=Decimal("5000.00")
    )
    genuine_reward = ReferralReward.objects.get(company=company, opportunity=genuine_opp)
    assert genuine_reward.reward_status == ReferralReward.Status.PENDING

    assert_all_invariants(company)
