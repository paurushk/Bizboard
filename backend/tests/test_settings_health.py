"""SET-18: the Settings health checklist reports what still needs attention, read-only and owner-only."""

from datetime import timedelta

from django.utils import timezone

from accounts.models import CompanyStatutoryLicence
from payments.models import BankAccount

URL = "/api/v1/company/settings-health/"


def _by_id(response):
    return {i["id"]: i for i in response.data["items"]}


def test_a_new_company_has_the_basics_to_do(tenant_a):
    tenant_a.company.gstin = ""
    tenant_a.company.save(update_fields=["gstin"])
    r = tenant_a.client.get(URL)
    assert r.status_code == 200, r.data
    items = _by_id(r)
    assert items["gstin"]["status"] == "todo" and items["gstin"]["path"] == "/settings/gst"
    assert items["bank"]["status"] == "todo"
    assert items["gateway"]["status"] == "todo"
    assert items["licences"]["status"] == "ok"
    assert r.data["needs_attention"] >= 3


def test_tax_profile_item_appears_with_a_gstin_and_clears_when_confirmed(tenant_a):
    from django.utils import timezone

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.tax_profile_confirmed_at = None
    tenant_a.company.save(update_fields=["gstin", "tax_profile_confirmed_at"])
    assert _by_id(tenant_a.client.get(URL))["taxprofile"]["status"] == "warn"
    tenant_a.company.tax_profile_confirmed_at = timezone.now()
    tenant_a.company.save(update_fields=["tax_profile_confirmed_at"])
    assert _by_id(tenant_a.client.get(URL))["taxprofile"]["status"] == "ok"


def test_no_tax_profile_item_without_a_gstin(tenant_a):
    tenant_a.company.gstin = ""
    tenant_a.company.save(update_fields=["gstin"])
    assert "taxprofile" not in _by_id(tenant_a.client.get(URL))


def test_default_bank_account_clears_the_bank_item(tenant_a):
    BankAccount.objects.create(company=tenant_a.company, name="HDFC", is_default=True)
    assert _by_id(tenant_a.client.get(URL))["bank"]["status"] == "ok"


def test_inactive_default_bank_account_does_not_count(tenant_a):
    BankAccount.objects.create(company=tenant_a.company, name="HDFC", is_default=True, is_active=False)
    assert _by_id(tenant_a.client.get(URL))["bank"]["status"] == "todo"


def test_expired_and_expiring_licences_warn(tenant_a):
    today = timezone.localdate()
    base = {"company": tenant_a.company, "is_active": True}
    CompanyStatutoryLicence.objects.create(
        **base, licence_type=CompanyStatutoryLicence.LicenceType.FSSAI, licence_number="A1", valid_upto=today - timedelta(days=1)
    )
    item = _by_id(tenant_a.client.get(URL))["licences"]
    assert item["status"] == "warn" and item["expired"] == 1 and item["count"] == 1


def test_owner_only_and_company_scoped(tenant_a, tenant_b):
    assert tenant_a.staff_client.get(URL).status_code == 403
    BankAccount.objects.create(company=tenant_b.company, name="Other", is_default=True)
    assert _by_id(tenant_a.client.get(URL))["bank"]["status"] == "todo"
