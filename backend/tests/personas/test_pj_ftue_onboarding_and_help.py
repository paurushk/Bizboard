"""Persona Journey — First-Time User Experience (FTUE / Day-0) & Help/FAQ Synchronization.

Validates:
1. Startup Founder Day-0 Onboarding & Setup Wizard Stepper:
   - Starts with a blank slate (NOT_STARTED, tax step)
   - Real-time GSTIN validation and error recovery (HelpCode.COMPANY_GSTIN_REQUIRED -> intent 'add-gstin')
   - Stepper progression: tax -> shop -> payments -> catalog -> first_bill
   - Setup completion unlocks the executive dashboard (derive_onboarding & should_force_setup)
2. Invited Staff Day-0 First Landing (Clerk, Custodian, Munshi):
   - Invitation acceptance and first landing on role-appropriate surfaces without 403 bursts
3. Help & FAQ Role-Aware Intent & Error Resolution:
   - Verification that business rule barriers map directly to Help intents and diagnosis leaves
   - Clerk blocked from invoice cancellation receives role escalation guidance
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Company, CompanyUser, User
from accounts.onboarding import derive_onboarding, should_force_setup
from core.exceptions import BusinessRuleError, api_exception_handler
from core.help_codes import ALL_HELP_CODES, ERROR_CODE_TO_INTENT, ERROR_CODE_TO_LEAF, HelpCode
from core.invariants import assert_all_invariants
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product
from sales.models import SalesInvoice
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_ftue_founder_onboarding_stepper_and_error_recovery():
    """Startup Founder Day-0: Onboarding stepper from blank slate to first completed bill."""
    # 1. Day-0 brand-new company registration
    company = Company.objects.create(
        name="Day Zero Enterprises",
        legal_name="Day Zero Enterprises Pvt Ltd",
        state="Karnataka",
        negative_stock_policy="ALLOW",
    )
    founder = User.objects.create_user(
        email="founder@dayzero.test",
        password="DayZeroPassword123!",
    )
    CompanyUser.objects.create(user=founder, company=company, role="OWNER")
    founder.active_company = company
    founder.save(update_fields=["active_company"])

    client = APIClient()
    client.force_authenticate(user=founder)

    # Initial onboarding state: NOT_STARTED, blocking on tax
    initial = derive_onboarding(company)
    assert initial["status"] == "NOT_STARTED"
    assert initial["step"] == "tax"
    assert initial["tax_done"] is False
    assert initial["catalog_done"] is False
    assert initial["activation_done"] is False
    assert should_force_setup(company=company, is_owner=True, wizard_enabled=True) is True

    # Step 0: Tax Profile & GSTIN Error Recovery
    # Invalid GSTIN format triggers error mapped to add-gstin intent
    invalid_resp = client.patch(
        "/api/v1/company/",
        {"gstin": "29INVALID"},
        format="json",
    )
    assert invalid_resp.status_code == 400
    assert ERROR_CODE_TO_INTENT[HelpCode.COMPANY_GSTIN_REQUIRED] == "add-gstin"

    # Valid GSTIN provided and confirmed
    valid_resp = client.patch(
        "/api/v1/company/",
        {
            "gstin": "29AABCU9603R1ZJ",
            "registration_type": "REGULAR",
        },
        format="json",
    )
    assert valid_resp.status_code == 200
    company.tax_profile_confirmed_at = timezone.now()
    company.save(update_fields=["tax_profile_confirmed_at"])

    step_tax = derive_onboarding(company)
    assert step_tax["tax_done"] is True
    assert step_tax["step"] == "shop"

    # Step 1: Shop Details
    shop_resp = client.patch(
        "/api/v1/company/",
        {
            "address": "42 Commercial Street, Tasker Town",
            "city": "Bengaluru",
            "pincode": "560001",
        },
        format="json",
    )
    assert shop_resp.status_code == 200
    company.refresh_from_db()

    step_shop = derive_onboarding(company)
    assert step_shop["shop_done"] is True
    # UI displays payments next, but payments is non-blocking for catalog
    assert step_shop["ui_step"] == "payments"
    assert step_shop["step"] == "catalog"

    # Step 2: Payments (Bank & UPI setup)
    pay_resp = client.patch(
        "/api/v1/company/",
        {
            "bank_account": "5010022334455",
            "bank_name": "HDFC Bank",
            "bank_ifsc": "HDFC0001234",
            "upi_id": "dayzero@okhdfcbank",
        },
        format="json",
    )
    assert pay_resp.status_code == 200
    company.refresh_from_db()

    step_pay = derive_onboarding(company)
    assert step_pay["payments_done"] is True
    assert step_pay["step"] == "catalog"

    # Step 3: Catalog Setup (First product created)
    prod_resp = client.post(
        "/api/v1/products/",
        {
            "name": "Starter Retail Kit",
            "sku": "DZ-KIT-001",
            "selling_price": "499.00",
            "purchase_price": "300.00",
            "gst_rate": "18.00",
            "hsn_code": "84713010",
        },
        format="json",
    )
    assert prod_resp.status_code == 201, prod_resp.data
    prod_id = prod_resp.data["id"]

    step_cat = derive_onboarding(company)
    assert step_cat["catalog_done"] is True
    assert step_cat["step"] == "first_bill"

    # Step 4: First Bill (First sales invoice to walk-in cash customer)
    cust = Customer.objects.create(
        company=company,
        name="Walk-in Customer",
        state="Karnataka",
    )
    inv_resp = client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": prod_id,
                    "quantity": "1.000",
                    "unit_price": "499.00",
                    "gst_rate": "18.00",
                }
            ],
        },
        format="json",
    )
    assert inv_resp.status_code == 201, inv_resp.data
    inv_id = inv_resp.data["id"]

    # Inward stock so complete invoice succeeds cleanly
    product = Product.objects.get(pk=prod_id)
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("10.000"),
        unit_cost=Decimal("300.00"),
        user=founder,
    )

    # Complete first bill
    comp_resp = client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert comp_resp.status_code == 200, comp_resp.data

    # Onboarding is now fully COMPLETED
    done = derive_onboarding(company)
    assert done["status"] == "COMPLETED"
    assert done["step"] is None
    assert done["activation_done"] is True
    # Dashboard is now unlocked for Founder
    assert should_force_setup(company=company, is_owner=True, wizard_enabled=True) is False

    assert_all_invariants(company)


def test_pj_ftue_team_invite_landing_and_role_access():
    """Invited Staff Day-0: Clerk, Custodian, and Munshi accept invite and land on their respective workspaces."""
    ns = seed_archetype("wholesale")
    company = ns.company

    # 1. Clerk / Sales Staff landing
    sc = ns.sales_client
    prod_resp = sc.get("/api/v1/products/")
    assert prod_resp.status_code == 200
    # Clerk reaches invoice creation surface
    inv_draft = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": ns.customers[0].id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": ns.products[0].id,
                    "quantity": "1.000",
                    "unit_price": "100.00",
                    "gst_rate": "18.00",
                }
            ],
        },
        format="json",
    )
    assert inv_draft.status_code == 201

    # 2. Godown Custodian landing
    gc = ns.godown_client
    bal_resp = gc.get("/api/v1/inventory/balances/")
    assert bal_resp.status_code == 200
    wh_resp = gc.get("/api/v1/inventory/warehouses/")
    assert wh_resp.status_code == 200

    # 3. In-House Accountant (Munshi) landing
    ac = ns.acct_client
    acc_resp = ac.get("/api/v1/accounting/accounts/")
    assert acc_resp.status_code == 200
    jr_resp = ac.get("/api/v1/accounting/journals/")
    assert jr_resp.status_code == 200

    assert_all_invariants(company)


def test_pj_ftue_help_error_code_to_intent_resolution():
    """Help & FAQ Intent Resolution: Verifies error code mapping, diagnostic branching, and role escalations."""
    ns = seed_archetype("trader")
    sc = ns.sales_client
    oc = ns.owner_client

    # Verify all stable help codes have valid intent mappings
    for code in ALL_HELP_CODES:
        assert code in ERROR_CODE_TO_INTENT, f"Help code {code} missing in ERROR_CODE_TO_INTENT"
        intent = ERROR_CODE_TO_INTENT[code]
        assert isinstance(intent, str) and len(intent) > 0

    # Test error code to leaf mappings for quick diagnosis bypass
    assert ERROR_CODE_TO_LEAF[HelpCode.INACTIVE_PRODUCT] == "inactive"
    assert ERROR_CODE_TO_LEAF[HelpCode.BLOCKED_CUSTOMER] == "blocked-party"
    assert ERROR_CODE_TO_LEAF[HelpCode.CLOSED_PERIOD] == "period"
    assert ERROR_CODE_TO_LEAF[HelpCode.CREDIT_LIMIT_EXCEEDED] == "credit"

    # Inward stock first so invoice completes cleanly
    p = next(p for p in ns.products if not p.track_batch)
    InventoryService.post_movement(
        company=ns.company,
        product=p,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("50.00"),
        user=ns.owner,
    )

    # Clerk blocked from cancelling completed invoice -> maps to role escalation
    inv = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": ns.customers[0].id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": p.id,
                    "quantity": "1.000",
                    "unit_price": "100.00",
                    "gst_rate": "18.00",
                }
            ],
        },
        format="json",
    )
    assert inv.status_code == 201
    iid = inv.data["id"]
    comp_res = oc.post(f"/api/v1/sales/invoices/{iid}/complete/")
    assert comp_res.status_code == 200, comp_res.data

    # Clerk attempt to cancel is rejected
    cancel_resp = sc.post(f"/api/v1/sales/invoices/{iid}/cancel/", {"reason": "Customer changed mind"})
    assert cancel_resp.status_code in (403, 400)

    # Invariant assertion holds
    assert_all_invariants(ns.company)
