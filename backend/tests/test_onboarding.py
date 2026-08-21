import pytest
from django.apps import apps
from django.test import override_settings
from django.utils import timezone
import importlib.util
from pathlib import Path

from accounts.models import Company
from accounts.onboarding import derive_onboarding, should_force_setup
from sales.models import SalesInvoice
from tests.conftest import add_stock, make_customer, make_product


pytestmark = pytest.mark.django_db


def _load_backfill():
    path = Path(__file__).resolve().parents[1] / "accounts" / "migrations" / "0028_onboarding_fields.py"
    spec = importlib.util.spec_from_file_location("onboarding_backfill_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.backfill_onboarding


def test_derive_completed_when_completed_invoice_exists(tenant_a):
    customer = make_customer(tenant_a.company)
    SalesInvoice.objects.create(
        company=tenant_a.company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
    )

    derived = derive_onboarding(tenant_a.company)

    assert derived["status"] == "COMPLETED"
    assert derived["activation_done"] is True
    assert derived["step"] is None


def test_dismissed_company_with_address_is_not_forced_into_setup(tenant_a):
    tenant_a.company.address = "1 Existing Shop Road"
    tenant_a.company.onboarding_dismissed_at = timezone.now()
    tenant_a.company.save(update_fields=["address", "onboarding_dismissed_at"])

    assert derive_onboarding(tenant_a.company)["status"] == "DISMISSED"
    assert should_force_setup(
        company=tenant_a.company,
        is_owner=True,
        wizard_enabled=True,
    ) is False


def test_owner_can_dismiss_onboarding(tenant_a):
    response = tenant_a.client.patch(
        "/api/v1/company/",
        {"dismiss_onboarding": True},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["onboarding"]["status"] == "DISMISSED"
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.onboarding_dismissed_at is not None


def test_regular_tax_confirmation_requires_valid_gstin(tenant_a):
    rejected = tenant_a.client.patch(
        "/api/v1/company/",
        {
            "registration_type": Company.RegistrationType.REGULAR,
            "confirm_tax_profile": True,
        },
        format="json",
    )
    assert rejected.status_code == 400
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.tax_profile_confirmed_at is None

    confirmed = tenant_a.client.patch(
        "/api/v1/company/",
        {
            "registration_type": Company.RegistrationType.REGULAR,
            "gstin": "29ABCDE1234F1ZW",
            "confirm_tax_profile": True,
        },
        format="json",
    )
    assert confirmed.status_code == 200, confirmed.data
    assert confirmed.data["onboarding"]["tax_done"] is True


def test_composition_cannot_complete_gst_tax_invoice(tenant_a):
    tenant_a.company.registration_type = Company.RegistrationType.COMPOSITION
    tenant_a.company.gstin = ""
    tenant_a.company.save(update_fields=["registration_type", "gstin"])
    product = make_product(tenant_a.company, sku="COMP-GST", hsn_code="8471")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": SalesInvoice.InvoiceType.GST,
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "18",
                }
            ],
        },
        format="json",
    )
    assert created.status_code == 201, created.data

    completed = tenant_a.client.post(
        f"/api/v1/sales/invoices/{created.data['id']}/complete/"
    )

    assert completed.status_code == 400
    assert "composition dealers cannot issue" in str(completed.data).lower()


@override_settings(ENABLE_SETUP_WIZARD=True)
def test_setup_wizard_feature_flag_is_exposed(tenant_a):
    response = tenant_a.client.get("/api/v1/feature-flags/")

    assert response.status_code == 200
    assert response.data["ENABLE_SETUP_WIZARD"] is True


def test_payments_optional_does_not_block_catalog_step(tenant_a):
    tenant_a.company.tax_profile_confirmed_at = timezone.now()
    tenant_a.company.address = "12 Shop Street"
    tenant_a.company.save(update_fields=["tax_profile_confirmed_at", "address"])
    make_product(tenant_a.company, sku="PAY-OPT")

    derived = derive_onboarding(tenant_a.company)
    assert derived["status"] == "IN_PROGRESS"
    assert derived["step"] == "first_bill"
    assert derived["ui_step"] == "first_bill"


def test_backfill_dismisses_existing_progress_companies(tenant_a):
    tenant_a.company.address = "Legacy address"
    tenant_a.company.onboarding_dismissed_at = None
    tenant_a.company.tax_profile_confirmed_at = None
    tenant_a.company.save(
        update_fields=["address", "onboarding_dismissed_at", "tax_profile_confirmed_at"]
    )

    backfill_onboarding = _load_backfill()
    backfill_onboarding(apps, None)
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.onboarding_dismissed_at is not None
    assert should_force_setup(
        company=tenant_a.company, is_owner=True, wizard_enabled=True
    ) is False
