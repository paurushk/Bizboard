"""One contract covers several products and does not carry a serial."""

from datetime import date

import pytest

from contracts.models import ContractProduct

from .test_growth_os import _flags
from .conftest import make_customer, make_product


@pytest.mark.django_db
def test_contract_accepts_several_products_and_rejects_a_serial(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    first = make_product(tenant_a.company, sku="CON-A")
    second = make_product(tenant_a.company, sku="CON-B", name="Second")
    created = tenant_a.client.post(
        "/api/v1/contracts/",
        {
            "customer": customer.id,
            "products": [first.id, second.id],
            "contract_type": "AMC",
            "start_date": date(2026, 1, 1).isoformat(),
            "end_date": date(2026, 12, 31).isoformat(),
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["products"] == [first.id, second.id]
    assert created.data["product"] == first.id
    assert ContractProduct.objects.filter(contract_id=created.data["id"]).count() == 2
    assert "serial" not in {field.name for field in ContractProduct._meta.fields}

    rejected = tenant_a.client.post(
        "/api/v1/contracts/",
        {
            "customer": customer.id,
            "products": [first.id],
            "serial": "SN-1",
            "contract_type": "WARRANTY",
            "start_date": "2026-01-01",
            "end_date": "2026-06-01",
        },
        format="json",
    )
    assert rejected.status_code == 400


@pytest.mark.django_db
def test_product_list_replaces_dedupes_and_stays_inside_the_company(tenant_a, tenant_b):
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    customer = make_customer(tenant_a.company)
    first = make_product(tenant_a.company, sku="CON-C")
    second = make_product(tenant_a.company, sku="CON-D", name="Fourth")
    foreign = make_product(tenant_b.company, sku="CON-X", name="Foreign")
    created = tenant_a.client.post(
        "/api/v1/contracts/",
        {
            "customer": customer.id,
            "products": [first.id],
            "contract_type": "WARRANTY",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    contract_id = created.data["id"]

    replaced = tenant_a.client.patch(
        f"/api/v1/contracts/{contract_id}/",
        {"products": [second.id, second.id, first.id]},
        format="json",
    )
    assert replaced.status_code == 200, replaced.data
    assert replaced.data["products"] == [first.id, second.id]
    assert replaced.data["product"] == second.id
    assert ContractProduct.objects.filter(contract_id=contract_id).count() == 2

    kept = tenant_a.client.patch(
        f"/api/v1/contracts/{contract_id}/",
        {"notes": "still covered"},
        format="json",
    )
    assert kept.status_code == 200
    assert kept.data["products"] == [first.id, second.id]

    cleared = tenant_a.client.patch(
        f"/api/v1/contracts/{contract_id}/",
        {"products": []},
        format="json",
    )
    assert cleared.status_code == 200, cleared.data
    assert cleared.data["products"] == []
    assert cleared.data["product"] is None
    assert ContractProduct.objects.filter(contract_id=contract_id).count() == 0

    rejected = tenant_a.client.patch(
        f"/api/v1/contracts/{contract_id}/",
        {"products": [foreign.id]},
        format="json",
    )
    assert rejected.status_code == 400
    assert ContractProduct.objects.filter(contract_id=contract_id).count() == 0
