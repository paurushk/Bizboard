"""Party custom fields and credit exposure: rules added in the sales invoice review."""

from unittest import mock

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from masters.custom_fields import validate_party_definitions
from masters.serializers import CustomerSerializer
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _def(key, label=None, active=True):
    return {"key": key, "label": label or key.title(), "type": "text", "active": active}


@pytest.mark.parametrize("label", ["PAN", "Credit Limit", "Price List", "Notes", "Phone", "Billing Address"])
def test_more_built_in_party_columns_are_refused(label):
    key = "".join(ch for ch in label.title() if ch.isalnum())
    with pytest.raises(ValidationError) as exc:
        validate_party_definitions([], [_def(key, label)])
    assert "built-in party field" in str(exc.value)


def test_a_definition_saved_before_a_name_was_reserved_can_still_be_saved_again():
    stored = [_def("notes", "Notes")]
    again = validate_party_definitions(stored, [_def("notes", "Notes"), _def("route", "Route")])
    assert {row["key"] for row in again} == {"notes", "route"}


def test_a_new_definition_with_a_reserved_name_is_still_refused_next_to_an_old_one():
    stored = [_def("notes", "Notes")]
    with pytest.raises(ValidationError):
        validate_party_definitions(stored, [_def("notes", "Notes"), _def("pan", "PAN")])


def test_customer_custom_fields_validation_without_a_membership_just_drops_blanks():
    from rest_framework.request import Request

    request = Request(APIRequestFactory().get("/"))
    serializer = CustomerSerializer(context={"request": request})
    assert serializer.validate_custom_fields({"route": "North", "empty": ""}) == {"route": "North"}


def test_customer_list_reads_party_definitions_once_not_per_row(tenant_a):
    tenant_a.company.party_custom_field_defs = [_def("route", "Route")]
    tenant_a.company.save(update_fields=["party_custom_field_defs"])
    customers = [make_customer(tenant_a.company, name=f"Row {i}", state="Karnataka") for i in range(4)]
    with mock.patch("masters.custom_fields.party_defs_for_company", wraps=__import__("masters.custom_fields", fromlist=["x"]).party_defs_for_company) as spy:
        data = CustomerSerializer(customers, many=True, context={}).data
    assert len(data) == 4
    assert spy.call_count == 1


def test_customer_custom_fields_round_trip_through_the_api_and_reject_unknown_keys(tenant_a):
    tenant_a.company.party_custom_field_defs = [_def("route", "Route")]
    tenant_a.company.save(update_fields=["party_custom_field_defs"])
    customer = make_customer(tenant_a.company, name="Route Buyer", state="Karnataka")
    ok = tenant_a.client.patch(f"/api/v1/customers/{customer.id}/", {"custom_fields": {"route": "North"}}, format="json")
    assert ok.status_code == 200, ok.data
    assert ok.data["custom_fields"] == {"route": "North"}
    bad = tenant_a.client.patch(f"/api/v1/customers/{customer.id}/", {"custom_fields": {"nope": "x"}}, format="json")
    assert bad.status_code == 400


def test_credit_exposure_is_the_same_on_the_list_and_the_detail_and_nets_advances(tenant_a):
    product = make_product(tenant_a.company, sku="EXP-1", hsn_code="3004", gst_rate="18")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Exposure Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"},
    ])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    advance = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "50", "mode": "UPI"}, format="json",
    )
    assert advance.status_code == 201, advance.data

    detail = tenant_a.client.get(f"/api/v1/customers/{customer.id}/").data
    listing = tenant_a.client.get("/api/v1/customers/").data
    rows = listing["results"] if isinstance(listing, dict) and "results" in listing else listing
    row = next(r for r in rows if r["id"] == customer.id)
    assert str(detail["credit_exposure"]) == str(row["credit_exposure"])
    total = float(tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/").data["grand_total"])
    assert float(detail["credit_exposure"]) == pytest.approx(total - 50.0)
