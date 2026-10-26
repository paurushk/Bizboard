"""seed_load_tenant: environment gate, service path, and suppressed PDF enqueue."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from django.db.models import Sum
from django.utils import timezone

from accounts.management.commands.seed_load_tenant import mix_bucket
from accounts.models import Company, CompanyUser
from inventory.models import StockBalance
from masters.models import Customer
from sales.models import SalesInvoice

pytestmark = pytest.mark.django_db


def test_mix_bucket_is_70_25_5_over_a_block_of_20():
    buckets = [mix_bucket(i) for i in range(20)]
    assert buckets.count("b2c") == 14
    assert buckets.count("b2b") == 5
    assert buckets.count("return") == 1


@override_settings(DJANGO_ENV="production")
def test_refuses_production():
    with pytest.raises(CommandError, match="refuses"):
        call_command("seed_load_tenant", password="x", stdout=StringIO())


@override_settings(DJANGO_ENV="development", DEBUG=True)
def test_refuses_development_even_with_debug():
    with pytest.raises(CommandError, match="staging or test"):
        call_command("seed_load_tenant", password="x", stdout=StringIO())


@override_settings(DJANGO_ENV="test")
def test_service_path_completes_a_block_without_queueing_pdfs():
    out = StringIO()
    with patch("sales.handlers.safe_delay") as delay:
        call_command(
            "seed_load_tenant",
            invoices=20,
            products=4,
            customers=3,
            password="LoadPass123!",
            stdout=out,
        )
        delay.assert_not_called()
    company = Company.objects.get(name="Load Tenant")
    seeded = SalesInvoice.objects.filter(company=company, notes__startswith="SEED_LOAD:")
    assert seeded.count() == 20
    assert seeded.filter(pdf_status=SalesInvoice.PdfStatus.NONE).count() == 20
    returned = SalesInvoice.objects.get(company=company, notes="SEED_LOAD:000019")
    assert returned.status == SalesInvoice.Status.RETURNED
    b2b = SalesInvoice.objects.get(company=company, notes="SEED_LOAD:000014")
    assert b2b.items.count() >= 5
    call_command(
        "seed_load_tenant",
        invoices=20,
        products=4,
        customers=3,
        password="LoadPass123!",
        stdout=StringIO(),
    )
    assert SalesInvoice.objects.filter(company=company, notes__startswith="SEED_LOAD:").count() == 20


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
@override_settings(DJANGO_ENV="test")
def test_resumes_a_leftover_draft_and_refills_drained_stock():
    call_command(
        "seed_load_tenant",
        invoices=1,
        products=1,
        customers=1,
        password="LoadPass123!",
        stdout=StringIO(),
    )
    company = Company.objects.get(name="Load Tenant")
    StockBalance.objects.filter(company=company).update(on_hand=0, reserved=0)
    SalesInvoice.objects.create(
        company=company,
        customer=Customer.objects.filter(company=company).first(),
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        invoice_date=timezone.localdate(),
        status=SalesInvoice.Status.DRAFT,
        notes="SEED_LOAD:000001",
        created_by=CompanyUser.objects.get(company=company, role=CompanyUser.Role.OWNER).user,
    )
    call_command(
        "seed_load_tenant",
        invoices=2,
        products=1,
        customers=1,
        password="LoadPass123!",
        stdout=StringIO(),
    )
    resumed = SalesInvoice.objects.get(company=company, notes="SEED_LOAD:000001")
    assert resumed.status == SalesInvoice.Status.COMPLETED
    on_hand = StockBalance.objects.filter(company=company).aggregate(total=Sum("on_hand"))["total"]
    assert on_hand > 0


@override_settings(DJANGO_ENV="test")
def test_bulk_fallback_is_refused():
    with pytest.raises(CommandError, match="bulk-fallback"):
        call_command(
            "seed_load_tenant",
            invoices=1,
            products=1,
            customers=1,
            password="x",
            bulk_fallback=True,
            stdout=StringIO(),
        )


@override_settings(DJANGO_ENV="test")
def test_span_days_spreads_a_small_run_over_the_whole_year():
    """QOS-0016's browser budget seeds a few hundred invoices; they must still cover twelve months."""
    call_command(
        "seed_load_tenant", invoices=20, products=4, customers=3, span_days=360,
        password="LoadPass123!", stdout=StringIO(),
    )
    company = Company.objects.get(name="Load Tenant")
    dates = sorted(
        SalesInvoice.objects.filter(company=company, notes__startswith="SEED_LOAD:").values_list("invoice_date", flat=True)
    )
    today = timezone.localdate()
    assert (today - dates[0]).days >= 300  # reaches back about a year, not just 20 days
    assert dates[-1] == today


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
@override_settings(DJANGO_ENV="test")
def test_load_tenant_has_a_sales_staff_login_outside_the_two_step_rule():
    """Owners must enrol in two-step where MFA is enforced, so unattended load runs sign in as
    sales staff (2026-10-23: every seeded owner hit mfaEnrollmentRequired on staging)."""
    from accounts.management.commands.seed_load_tenant import LOAD_STAFF_EMAIL
    from accounts.mfa_service import user_has_money_role

    out = StringIO()
    with patch("sales.handlers.safe_delay"):
        call_command("seed_load_tenant", invoices=2, products=2, customers=2, password="LoadPass123!", stdout=out)
    staff = CompanyUser.objects.get(user__email=LOAD_STAFF_EMAIL, company__name="Load Tenant")
    assert staff.role == CompanyUser.Role.SALES_STAFF and staff.can_create_sales and not staff.can_post_journals
    assert staff.can_view_financial_reports and staff.can_export  # dashboard + GST worksheets
    assert staff.user.check_password("LoadPass123!")
    assert user_has_money_role(staff.user) is False
    assert f"staff_email={LOAD_STAFF_EMAIL}" in out.getvalue()
    # A second run keeps one membership and resets the password.
    with patch("sales.handlers.safe_delay"):
        call_command("seed_load_tenant", invoices=2, products=2, customers=2, password="Other123!x", stdout=StringIO())
    assert CompanyUser.objects.filter(user__email=LOAD_STAFF_EMAIL).count() == 1
    staff.user.refresh_from_db()
    assert staff.user.check_password("Other123!x")


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
@override_settings(DJANGO_ENV="test")
def test_load_tenant_has_one_staff_login_per_virtual_user():
    """D-10 (2026-10-24): the per-user API limit makes one login a bottleneck, so the soak gets
    one sales-staff login per k6 virtual user, all with the same password and no two-step."""
    from accounts.management.commands.seed_load_tenant import load_staff_email
    from accounts.mfa_service import user_has_money_role

    out = StringIO()
    with patch("sales.handlers.safe_delay"):
        call_command(
            "seed_load_tenant", invoices=2, products=2, customers=2, password="LoadPass123!", staff=3, stdout=out,
        )
    emails = [load_staff_email(i) for i in (1, 2, 3)]
    assert emails[1] == "load-staff-02@bizboard.local"
    staff = CompanyUser.objects.filter(user__email__in=emails, company__name="Load Tenant")
    assert staff.count() == 3
    assert all(cu.role == CompanyUser.Role.SALES_STAFF and cu.user.check_password("LoadPass123!") for cu in staff)
    assert not any(user_has_money_role(cu.user) for cu in staff)
    assert f"staff_emails={','.join(emails)}" in out.getvalue()


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
@override_settings(DJANGO_ENV="test")
def test_a_second_draft_pool_on_the_same_tenant_tops_up_stock():
    """seed_draft_pool used to fail with 'Opening stock has already been recorded' on any company
    that already had opening stock, so a pool could not be refilled for a second run."""
    with patch("sales.handlers.safe_delay"):
        call_command("seed_load_tenant", invoices=2, products=2, customers=2, password="LoadPass123!", stdout=StringIO())
    first, second = StringIO(), StringIO()
    call_command("seed_draft_pool", count=3, company="Load Tenant", stdout=first, stderr=StringIO())
    call_command("seed_draft_pool", count=3, company="Load Tenant", stdout=second, stderr=StringIO())
    ids = first.getvalue().strip().split(",") + second.getvalue().strip().split(",")
    assert len(set(ids)) == 6
    assert SalesInvoice.objects.filter(pk__in=ids, status=SalesInvoice.Status.DRAFT).count() == 6
