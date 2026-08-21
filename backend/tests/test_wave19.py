"""Wave 19: SO/PO cess, GSTR-9 table 18, AT depth, statutory list, RLS helper."""

from decimal import Decimal
from pathlib import Path

import pytest

from core.rls import set_rls_company
from reporting.gst_returns import build_gstr1, build_gstr9
from tests.conftest import make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]


def test_sales_order_cess_total(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "18",
                    "cess_rate": "1",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    detail = tenant_a.client.get(f"/api/v1/sales/orders/{resp.data['id']}/").json()["data"]
    assert Decimal(str(detail.get("cessTotal") or detail.get("cess_total") or 0)) == Decimal("1.00")


def test_purchase_order_cess_total(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    supplier = make_supplier(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/purchases/orders/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "18",
                    "cess_rate": "1",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    detail = tenant_a.client.get(f"/api/v1/purchases/orders/{resp.data['id']}/").json()["data"]
    assert Decimal(str(detail.get("cessTotal") or detail.get("cess_total") or 0)) == Decimal("1.00")


def test_gstr9_table_18_inward_hsn(tenant_a):
    payload = build_gstr9(tenant_a.company, "2025-26")
    assert payload["tables"]["18"]["aid_kind"] == "hsn_inward"
    assert "rows" in payload["tables"]["18"]
    assert "hsn_inward_stub" not in str(payload)
    assert "17/18 are stubs" not in payload["disclaimer"]


def test_gstr1_at_has_rate_and_pos(tenant_a):
    from datetime import date

    from payments.models import CustomerReceipt, ReceiptStatus

    customer = make_customer(tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka")
    CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("250.00"),
        receipt_date=date(2026, 4, 10),
        status=ReceiptStatus.POSTED,
        mode="CASH",
    )
    payload = build_gstr1(tenant_a.company, "2026-04")
    assert payload["at"]
    row = payload["at"][0]
    assert row["place_of_supply"] == "29"
    assert row["rate"] == "0.00"
    assert row["tax_status"] == "rate_unknown"
    assert row.get("aid_kind") == "unallocated_receipt"


def test_statutory_events_list_200(tenant_a):
    resp = tenant_a.client.get("/api/v1/statutory-events/")
    assert resp.status_code == 200


def test_set_rls_company_noop_on_sqlite(tenant_a, settings):
    settings.POSTGRES_RLS_ENABLED = True
    set_rls_company(tenant_a.company.id)


def test_celery_rls_prerun_accepts_positional_ids(tenant_a, settings):
    settings.POSTGRES_RLS_ENABLED = True
    from config.celery import set_rls_company_for_task

    def run(invoice_id):  # noqa: ARG001 — signature probe only
        return None

    task = type("TaskProbe", (), {"run": staticmethod(run)})()
    set_rls_company_for_task(task=task, args=(999999,), kwargs={})
    set_rls_company_for_task(task=task, args=(), kwargs={"company_id": tenant_a.company.id})


def test_rls_migration_covers_tenant_tables():
    sql = (ROOT / "backend/core/migrations/0008_wave19_rls_all_tenant_tables.py").read_text(
        encoding="utf-8"
    )
    assert "sales_salescreditnote" in sql
    assert "inventory_stockmovement" in sql
