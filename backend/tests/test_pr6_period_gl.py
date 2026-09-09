"""PR 6 — R-018/R-019/R-028/R-050 period / GL honesty."""

from datetime import date, datetime
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from django.apps import apps
from django.test import override_settings
from django.utils import timezone

from accounting.models import AccountingPeriod
from accounting.services import BooksHealthService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from manufacturing.models import Bom, WorkOrder
from purchases.models import PurchaseCreditNote
from tests.conftest import make_product, make_supplier


def _backfill_released_at(apps_registry, schema_editor):
    path = Path(__file__).resolve().parents[1] / "manufacturing" / "migrations" / "0010_r028_backfill_released_at.py"
    spec = spec_from_file_location("r028_backfill_released_at", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.forwards(apps_registry, schema_editor)

pytestmark = pytest.mark.django_db


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["accounting_enabled", "gstin", "state"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def _open_period(company, *, name="Sep 2026", start=date(2026, 9, 1), end=date(2026, 9, 30)):
    return AccountingPeriod.objects.create(
        company=company,
        name=name,
        start_date=start,
        end_date=end,
        status=AccountingPeriod.Status.OPEN,
    )


def test_completed_pcn_without_je_blocks_after_cutoff(books):
    """R-019: completed PCN with no JE after the cutoff blocks period close."""
    _open_period(books.company)
    PurchaseCreditNote.objects.create(
        company=books.company,
        supplier=make_supplier(books.company),
        status=PurchaseCreditNote.Status.COMPLETED,
        note_date=date(2026, 9, 5),
        completed_at=timezone.now(),
        grand_total=Decimal("100.00"),
        taxable_total=Decimal("100.00"),
    )
    health = BooksHealthService.control_balances(books.company)
    assert any(a["code"] == "DOCUMENT_MISSING_POSTING" for a in health["alerts"])
    with pytest.raises(BusinessRuleError, match="DOCUMENT_MISSING_POSTING"):
        BooksHealthService.assert_period_close_allowed(books.company, period="2026-09")


def test_legacy_pcn_without_je_warns_not_blocks(books):
    """R-019: completed_at < cutoff is legacy_unposted (warning), not a blocker."""
    _open_period(books.company)
    PurchaseCreditNote.objects.create(
        company=books.company,
        supplier=make_supplier(books.company),
        status=PurchaseCreditNote.Status.COMPLETED,
        note_date=date(2026, 1, 10),
        completed_at=timezone.make_aware(datetime(2026, 1, 10, 12, 0, 0)),
        grand_total=Decimal("50.00"),
        taxable_total=Decimal("50.00"),
    )
    health = BooksHealthService.control_balances(books.company)
    assert any(a["code"] == "legacy_unposted" for a in health["alerts"])
    assert not any(a["code"] == "DOCUMENT_MISSING_POSTING" for a in health["alerts"])
    BooksHealthService.assert_period_close_allowed(books.company, period="2026-09")


@override_settings(ENABLE_MANUFACTURING=True)
def test_null_released_at_after_backfill_does_not_block_all_periods(books):
    """R-028: migration stamps released_at; null no longer blocks every period."""
    fg = make_product(books.company, sku="WIP-R028")
    bom = Bom.objects.create(
        company=books.company, product=fg, name="WIP BOM", status=Bom.Status.ACTIVE,
    )
    wo = WorkOrder.objects.create(
        company=books.company,
        bom=bom,
        qty=Decimal("1"),
        status=WorkOrder.Status.RELEASED,
        released_at=None,
    )
    assert wo.released_at is None
    _backfill_released_at(apps, None)
    wo.refresh_from_db()
    assert wo.released_at == wo.created_at.date()

    _open_period(books.company, name="Apr 2026", start=date(2026, 4, 1), end=date(2026, 4, 30))
    blockers = BooksHealthService.period_close_blockers(books.company, period="2026-04")
    assert not any(b["code"] == "OPEN_WIP" for b in blockers)

    WorkOrder.objects.create(
        company=books.company,
        bom=bom,
        qty=Decimal("1"),
        status=WorkOrder.Status.RELEASED,
        released_at=None,
    )
    blockers = BooksHealthService.period_close_blockers(books.company, period="2026-04")
    assert not any(b["code"] == "OPEN_WIP" for b in blockers)


def test_work_order_release_stamps_released_at_if_null(books):
    from manufacturing.services import release_work_order
    from tests.conftest import add_stock

    fg = make_product(books.company, sku="WIP-STAMP-FG")
    comp = make_product(books.company, sku="WIP-STAMP-CP", purchase_price="10")
    add_stock(books, comp, 10, unit_cost="10")
    from manufacturing.models import BomLine

    bom = Bom.objects.create(
        company=books.company, product=fg, name="Stamp BOM", status=Bom.Status.ACTIVE,
    )
    BomLine.objects.create(bom=bom, component=comp, qty=Decimal("1"))
    wo = WorkOrder.objects.create(
        company=books.company, bom=bom, qty=Decimal("1"), status=WorkOrder.Status.DRAFT,
    )
    assert wo.released_at is None
    release_work_order(wo, books.owner)
    wo.refresh_from_db()
    assert wo.released_at == timezone.now().date()


def test_accounting_close_warns_when_gst_period_open(books):
    """R-050: Close success includes warnings: [{code: gst_period_open}]."""
    period = _open_period(books.company, name="Apr 2026", start=date(2026, 4, 1), end=date(2026, 4, 30))
    resp = books.client.post(f"/api/v1/accounting/periods/{period.id}/close/")
    assert resp.status_code == 200, resp.data
    warnings = resp.data.get("warnings") or []
    assert any(w.get("code") == "gst_period_open" for w in warnings)


@override_settings(ENABLE_GSTR=True)
def test_gst_soft_close_warns_when_accounting_period_open(books):
    """R-050 inverse: GST soft-close returns accounting_period_open. No dual-write."""
    _open_period(books.company, name="Apr 2026", start=date(2026, 4, 1), end=date(2026, 4, 30))
    from reporting.models import GstReturnPeriod

    resp = books.client.post(
        "/api/v1/reports/gst-period/",
        {"period": "2026-04", "action": "soft_close"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    warnings = resp.data.get("warnings") or []
    assert any(w.get("code") == "accounting_period_open" for w in warnings)
    assert AccountingPeriod.objects.get(company=books.company, name="Apr 2026").status == (
        AccountingPeriod.Status.OPEN
    )
    gst = GstReturnPeriod.objects.get(company=books.company, period="2026-04")
    assert gst.status == GstReturnPeriod.Status.SOFT_CLOSED


def test_backfill_missing_postings_dry_run(books):
    from django.core.management import call_command
    from io import StringIO

    PurchaseCreditNote.objects.create(
        company=books.company,
        supplier=make_supplier(books.company),
        status=PurchaseCreditNote.Status.COMPLETED,
        note_date=date(2026, 9, 5),
        completed_at=timezone.now(),
        grand_total=Decimal("10.00"),
        taxable_total=Decimal("10.00"),
    )
    out = StringIO()
    call_command("backfill_missing_postings", "--dry-run", "--company", str(books.company.id), stdout=out)
    assert "would post" in out.getvalue().lower() or "would_post" in out.getvalue()
