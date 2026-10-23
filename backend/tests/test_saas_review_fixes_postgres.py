"""Postgres-only regression tests from the 2026-10-23 review: bugs that RLS hides on SQLite.

Each runs the code under test as the restricted app role (NOSUPERUSER NOBYPASSRLS), as production
does, after building data as the superuser.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.test import override_settings

from tests.rls_helpers import app_role, needs_pg

pytestmark = [needs_pg, pytest.mark.django_db(transaction=True)]


def _bypass_on() -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.rls_bypass', true)")
        return (cur.fetchone()[0] or "") == "1"


def test_rls_bypass_nests_without_switching_the_outer_one_off():
    from core.rls import rls_bypass

    with override_settings(POSTGRES_RLS_ENABLED=True):
        with rls_bypass():
            with rls_bypass():
                assert _bypass_on()
            assert _bypass_on()  # the inner block used to clear it here
        assert not _bypass_on()


def test_staff_admin_lists_show_rows_under_rls():
    """The TDS-claim and ownership-transfer admins built a lazy queryset inside a bypass that had
    ended before the list ran, so on Postgres the list was empty and the change page a 404."""
    from django.test import Client

    from accounts.models import OwnershipTransfer, User
    from billing.models import SaasTdsClaim
    from billing.platform_gst import issue_platform_gst_invoice
    from core.rls import rls_bypass
    from core.services.files import FileService
    from tests.conftest import make_tenant

    tenant = make_tenant("rvwpg1")
    admin = User.objects.create_superuser(email="pg-root@bizboard.example", password="x-Strong-pass-1")
    with rls_bypass():
        inv = issue_platform_gst_invoice(tenant.company, provider="razorpay", capture_id="pay_pg1", amount="1180")
        from django.core.files.uploadedfile import SimpleUploadedFile

        from core.models import FileAsset

        cert = FileService.store_upload(company=tenant.company, uploaded_file=SimpleUploadedFile(
            "f16a.pdf", b"%PDF-1.4", content_type="application/pdf"), kind=FileAsset.Kind.ATTACHMENT, user=tenant.owner)
        claim = SaasTdsClaim.objects.create(company=tenant.company, section="194J-2", rate=Decimal("2"),
                                            taxable_total=inv.taxable_amount, amount=Decimal("20.00"),
                                            quarter="2026-27 Q3", certificate=cert)
        from datetime import timedelta

        from django.utils import timezone

        transfer = OwnershipTransfer.objects.create(company=tenant.company, kind=OwnershipTransfer.Kind.STAFF_RECOVERY,
                                                    recovery_email="r@x.in", expires_at=timezone.now() + timedelta(days=14))
    client = Client()
    client.force_login(admin)
    with override_settings(POSTGRES_RLS_ENABLED=True), app_role():
        listing = client.get("/admin/billing/saastdsclaim/")
        if listing.status_code == 404:
            pytest.skip("Django admin is not mounted in this settings module")
        assert listing.status_code == 200 and b"2026-27 Q3" in listing.content
        assert client.get(f"/admin/billing/saastdsclaim/{claim.pk}/change/").status_code == 200
        assert client.get(f"/admin/accounts/ownershiptransfer/{transfer.pk}/change/").status_code == 200


def test_ownership_link_works_while_working_in_another_company():
    """The member opens the emailed link while their active company is another one: the request's
    tenant is not the transfer's, and under FORCE RLS the lookup used to find nothing."""
    from accounts.models import CompanyUser
    from accounts.ownership import accept_transfer, start_transfer
    from core.rls import company_scope, rls_bypass
    from tests.conftest import make_tenant

    a, b = make_tenant("rvwpg2"), make_tenant("rvwpg3")
    with rls_bypass():
        CompanyUser.objects.create(company=b.company, user=a.staff, role=CompanyUser.Role.SALES_STAFF)
        _t, token = start_transfer(company=b.company, from_user=b.owner, to_user_id=a.staff.pk)
    from unittest import mock

    # Emails are stubbed: in eager test mode the email task's postrun hook clears the tenant GUC on
    # this connection mid-request (a worker runs it elsewhere in production).
    with override_settings(POSTGRES_RLS_ENABLED=True), app_role(), company_scope(a.company.pk),             mock.patch("accounts.ownership._email"):
        accept_transfer(token=token, user=a.staff)
    with rls_bypass():
        assert CompanyUser.objects.get(company=b.company, user=a.staff).role == CompanyUser.Role.OWNER
