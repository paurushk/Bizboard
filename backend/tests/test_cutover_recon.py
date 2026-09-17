"""6.4 / 6.5 — cutover recon command prints counts and runs invariants."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from tests.conftest import make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_cutover_recon_prints_counts(tenant_a, capsys):
    make_product(tenant_a.company)
    make_customer(tenant_a.company)
    make_supplier(tenant_a.company)
    call_command("cutover_recon", company_id=tenant_a.company.pk)
    out = capsys.readouterr().out
    assert "products=1" in out
    assert "customers=1" in out
    assert "suppliers=1" in out
    assert "ok" in out.lower() or "company=" in out
