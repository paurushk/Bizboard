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
        created_by=CompanyUser.objects.get(company=company).user,
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
