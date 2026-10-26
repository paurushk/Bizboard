"""BB-134: `seed_demo --with-activity` gives a demo company believable trading, idempotently."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from accounts.models import Company
from sales.models import SalesInvoice, SalesReturn

pytestmark = pytest.mark.django_db


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="seed_demo opens stock directly through the ORM-backed seed")
@override_settings(DEBUG=True, DJANGO_ENV="test")
def test_demo_activity_fills_dashboard_outstanding_and_returns():
    with patch("sales.handlers.safe_delay"):
        call_command("seed_demo", with_activity=True, stdout=StringIO())
        call_command("seed_demo", with_activity=True, stdout=StringIO())  # re-run adds nothing
    company = Company.objects.get(name="Demo Traders")
    demo = SalesInvoice.objects.filter(company=company, notes__startswith="DEMO:")
    assert demo.count() == 24
    assert demo.exclude(status__in=[SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED]).count() == 0
    assert demo.values("customer").distinct().count() == 3
    assert demo.filter(customer__state="Maharashtra").exists()  # inter-state (IGST) bills for GSTR-1
    from django.db.models import Sum

    from payments.models import PaymentAllocation

    paid = {row["sales_invoice"]: row["total"] for row in PaymentAllocation.objects.filter(
        company=company, sales_invoice__in=demo).values("sales_invoice").annotate(total=Sum("amount"))}
    fully = [inv for inv in demo if paid.get(inv.pk, Decimal("0")) >= inv.grand_total]
    partly = [inv for inv in demo if Decimal("0") < paid.get(inv.pk, Decimal("0")) < inv.grand_total]
    unpaid = [inv for inv in demo if inv.pk not in paid]
    assert fully and partly and unpaid  # paid, part-paid and outstanding bills for aging
    assert SalesReturn.objects.filter(company=company, status=SalesReturn.Status.COMPLETED).count() == 1
    dates = sorted(demo.values_list("invoice_date", flat=True))
    assert (dates[-1] - dates[0]).days >= 60  # spread over about three months


@override_settings(DEBUG=False, DJANGO_ENV="production")
def test_demo_seed_still_refuses_production():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("seed_demo", with_activity=True, stdout=StringIO())
