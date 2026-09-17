"""14.5 — post-deploy smoke helpers against the Django test client."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _smoke_mod():
    path = Path(__file__).resolve().parents[2] / "scripts" / "post_deploy_smoke.py"
    spec = importlib.util.spec_from_file_location("post_deploy_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_post_deploy_smoke_health_login_complete_invariants(tenant_a):
    smoke = _smoke_mod()

    def get(path):
        resp = tenant_a.client.get(path)
        return resp.status_code, resp.data

    smoke.check_health(get)
    smoke.check_ready(get)

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    smoke.check_invariants(get)

    unauth = APIClient()
    login = unauth.post(
        "/api/v1/auth/login/",
        {"email": tenant_a.owner.email, "password": "StrongPass123!"},
        format="json",
    )
    assert login.status_code == 200, login.data
    smoke.check_login(
        lambda path, body: (login.status_code, login.data),
        tenant_a.owner.email,
        "StrongPass123!",
    )
