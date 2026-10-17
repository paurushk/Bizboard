"""QOS-0127: the GSTR-9 filing date endpoint and the Sec 34(2) note deadline helper."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from reporting.annual_filing import fy_start_year_of, note_deadline
from reporting.models import AnnualReturnFiling

pytestmark = pytest.mark.django_db

URL = "/api/v1/reports/gstr9/filing-date/"


def _client(tenant, role, email, **caps):
    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=email)
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **caps)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_fy_start_year_rolls_over_in_april():
    assert fy_start_year_of(date(2026, 3, 31)) == 2025
    assert fy_start_year_of(date(2026, 4, 1)) == 2026


def test_deadline_defaults_to_30_november_and_takes_the_earlier_filing_date(tenant_a):
    assert note_deadline(tenant_a.company, date(2026, 2, 10)) == date(2026, 11, 30)
    AnnualReturnFiling.objects.create(company=tenant_a.company, fy_start_year=2025, filed_on=date(2026, 9, 1))
    assert note_deadline(tenant_a.company, date(2026, 2, 10)) == date(2026, 9, 1)
    # A different financial year is untouched.
    assert note_deadline(tenant_a.company, date(2026, 6, 1)) == date(2027, 11, 30)


def test_a_filing_date_after_30_november_does_not_extend_the_limit(tenant_a):
    AnnualReturnFiling.objects.create(company=tenant_a.company, fy_start_year=2025, filed_on=date(2027, 1, 10))
    assert note_deadline(tenant_a.company, date(2026, 2, 10)) == date(2026, 11, 30)


@pytest.mark.parametrize("fy", [None, "", "abc", "1999-00", "2200-01"])
def test_bad_financial_year_is_rejected(tenant_a, fy):
    params = {"fy": fy} if fy is not None else {}
    assert tenant_a.client.get(URL, params).status_code == 400
    assert tenant_a.client.put(URL, {"fy": fy, "filed_on": "2026-10-15"}, format="json").status_code == 400


def test_bad_filing_date_is_rejected(tenant_a):
    for bad in ("15/10/2026", "not-a-date", "2026-02-30"):
        assert tenant_a.client.put(URL, {"fy": "2025-26", "filed_on": bad}, format="json").status_code == 400
    assert not AnnualReturnFiling.objects.filter(company=tenant_a.company).exists()


def test_saving_twice_updates_one_row(tenant_a):
    for day in ("2026-10-15", "2026-10-20"):
        resp = tenant_a.client.put(URL, {"fy": "2025-26", "filed_on": day}, format="json")
        assert resp.status_code == 200 and resp.data["fy"] == "2025-26"
    rows = AnnualReturnFiling.objects.filter(company=tenant_a.company)
    assert rows.count() == 1 and rows.get().filed_on == date(2026, 10, 20)


@pytest.mark.parametrize("role", [CompanyUser.Role.MANAGER, CompanyUser.Role.ACCOUNTANT])
def test_manager_and_accountant_can_record_the_date(tenant_a, role):
    client = _client(tenant_a, role, f"{role.lower()}-ar@alpha.test", can_view_financial_reports=True)
    resp = client.put(URL, {"fy": "2025-26", "filed_on": "2026-10-15"}, format="json")
    assert resp.status_code == 200 and resp.data["filed_on"] == "2026-10-15"


def test_viewer_can_read_but_not_write(tenant_a):
    AnnualReturnFiling.objects.create(company=tenant_a.company, fy_start_year=2025, filed_on=date(2026, 10, 15))
    viewer = _client(tenant_a, CompanyUser.Role.VIEWER, "viewer-ar@alpha.test", can_view_financial_reports=True)
    resp = viewer.put(URL, {"fy": "2025-26", "filed_on": "2026-10-01"}, format="json")
    assert resp.status_code in (400, 403)
    assert AnnualReturnFiling.objects.get(company=tenant_a.company).filed_on == date(2026, 10, 15)
    read = viewer.get(URL, {"fy": "2025-26"})
    assert read.status_code == 200 and read.data["filed_on"] == "2026-10-15"


def test_a_user_without_the_reports_permission_is_refused(tenant_a):
    plain = _client(tenant_a, CompanyUser.Role.ACCOUNTANT, "plain-ar@alpha.test", can_view_financial_reports=False)
    assert plain.get(URL, {"fy": "2025-26"}).status_code == 403
    assert plain.put(URL, {"fy": "2025-26", "filed_on": "2026-10-15"}, format="json").status_code == 403


def test_anonymous_is_refused():
    assert APIClient().get(URL, {"fy": "2025-26"}).status_code in (401, 403)


def test_companies_do_not_see_each_others_dates(tenant_a, tenant_b):
    tenant_a.client.put(URL, {"fy": "2025-26", "filed_on": "2026-10-15"}, format="json")
    other = tenant_b.client.get(URL, {"fy": "2025-26"})
    assert other.status_code == 200 and other.data["filed_on"] is None
    assert other.data["note_deadline"] == "2026-11-30"
    assert note_deadline(tenant_b.company, date(2026, 2, 10)) == date(2026, 11, 30)
