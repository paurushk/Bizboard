"""W0-08 ops integrity + B-04 GST Complete guardrails."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from django.db import IntegrityError

from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from masters.models import Product
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db

REPO = Path(__file__).resolve().parents[2]


def test_dockerfile_drops_to_non_root_app_user():
    dockerfile = (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
    entry = (REPO / "backend" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "useradd --system" in dockerfile
    assert "setpriv --reuid=app" in entry
    assert "gunicorn" in dockerfile


def test_cd_workflow_requires_ci_green_and_digest_pin():
    cd = (REPO / ".github" / "workflows" / "cd.yml").read_text(encoding="utf-8")
    assert "confirm_ci_green" in cd
    assert "pin_image_digests.sh" in cd
    assert "sha256:" in cd


def test_opening_stock_duplicate_raises(tenant_a):
    product = make_product(tenant_a.company, sku="OPEN-DUP")
    add_stock(tenant_a, product, "5")
    with pytest.raises((IntegrityError, Exception)):
        StockMovement.objects.create(
            company=tenant_a.company,
            warehouse=InventoryService.default_warehouse(tenant_a.company),
            product=product,
            movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal("1"),
            unit_cost=Decimal("10"),
        )


def test_void_product_import_keeps_preexisting(tenant_a):
    from tests.test_imports import _upload

    existing = make_product(tenant_a.company, name="Keep Me", sku="KEEP-1", selling_price="10")
    csv_content = (
        b"name,sku,gst_rate,selling_price,opening_stock,unit_cost\n"
        b"Keep Me Updated,KEEP-1,18,12,0,5\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    void = tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    assert void.status_code == 200, void.data
    existing.refresh_from_db()
    assert existing.status == Product.Status.ACTIVE
    assert existing.sku == "KEEP-1"


def test_blank_pos_complete_requires_confirm(tenant_a):
    tenant_a.company.assume_local_state_for_blank_party = True
    tenant_a.company.save(update_fields=["assume_local_state_for_blank_party"])
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="", gstin="")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert blocked.status_code == 400
    ok = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/",
        {"confirm_blank_pos": True},
        format="json",
    )
    assert ok.status_code == 200, ok.data


def test_urd_purchase_without_rcm_confirm_blocked(tenant_a):
    from tests.conftest import create_draft_purchase

    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company, gstin="", taxpayer_type="")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert resp.status_code == 400
