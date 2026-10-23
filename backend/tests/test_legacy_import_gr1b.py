"""WP-GR1b: Busy / Vyapar / Marg exports import through the Tally commit path with zero recon gap."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from integrations.legacy_import import parse_legacy_file, to_master_rows
from masters.models import Customer, Product, Supplier

pytestmark = pytest.mark.django_db

FIXTURES = {
    "busy": (
        "Name,Group,Mobile No.,GSTIN,State,Op. Bal.,Dr/Cr\n"
        "Asha Traders,Sundry Debtors,9820011111,27AAAPL1234C1ZE,Maharashtra,1500.00,Dr\n"
        "Kiran Supplies,Sundry Creditors,9820022222,,Maharashtra,800.00,Cr\n"
        "HDFC Bank,Bank Accounts,,,,25000.00,Dr\n"
    ),
    "vyapar": (
        "Name,Phone No.,GSTIN,State,Opening Balance,Balance Type\n"
        "Asha Traders,9820011111,27AAAPL1234C1ZE,Maharashtra,1500,To Receive\n"
        "Kiran Supplies,9820022222,,Maharashtra,800,To Pay\n"
    ),
    "marg": (
        "Ledger Name,Group,Mobile,GST No,State,Opening Balance,Dr/Cr\n"
        "ASHA TRADERS,SUNDRY DEBTORS,9820011111,27AAAPL1234C1ZE,Maharashtra,1500,Dr\n"
        "KIRAN SUPPLIES,SUNDRY CREDITORS,9820022222,,Maharashtra,800,Cr\n"
    ),
}
ITEMS = {
    "busy": "Name,Alias,HSN/SAC Code,GST Rate,Purchase Price,Sale Price,Op. Stock (Qty)\nSteel Bolt,SB-1,7318,18,4.50,6.00,100\n",
    "vyapar": "Item Name,Item Code,HSN,Tax Rate,Purchase Price,Sale Price,Opening Stock Quantity\nSteel Bolt,SB-1,7318,18%,4.50,6.00,100\n",
    "marg": "Product Name,Product Code,HSN Code,GST %,Purchase Rate,Sale Rate,Opening Stock\nSteel Bolt,SB-1,7318,18,4.50,6.00,100\n",
}


@pytest.fixture
def granted(tenant_a):
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_LEGACY_IMPORT"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    return tenant_a


@pytest.mark.parametrize("source", ["busy", "vyapar", "marg"])
def test_party_exports_map_to_customers_and_suppliers(source):
    preview = parse_legacy_file(source, FIXTURES[source].encode(), "parties.csv")
    assert preview["errors"] == []
    assert [c["name"].lower() for c in preview["customers"]] == ["asha traders"]
    assert [s["name"].lower() for s in preview["suppliers"]] == ["kiran supplies"]
    assert Decimal(preview["customers"][0]["opening_outstanding"]) == Decimal("1500")
    assert Decimal(preview["suppliers"][0]["opening_outstanding"]) == Decimal("800")
    assert preview["source"] == source


@pytest.mark.parametrize("source", ["busy", "vyapar", "marg"])
def test_item_exports_map_to_products(source):
    preview = parse_legacy_file(source, ITEMS[source].encode(), "items.csv")
    assert preview["errors"] == []
    item = preview["products"][0]
    assert item["name"] == "Steel Bolt" and item["sku"] == "SB-1" and item["hsn_code"] == "7318"
    assert Decimal(item["gst_rate"]) == 18 and Decimal(item["opening_qty"]) == 100


def test_a_file_that_is_not_an_export_is_refused_with_expected_columns():
    rows, errors = to_master_rows("busy", [{"foo": "1", "bar": "2"}])
    assert rows == [] and "does not look like a Busy" in errors[0]["error"]


def test_gated_per_company(tenant_a):
    f = SimpleUploadedFile("parties.csv", FIXTURES["busy"].encode(), content_type="text/csv")
    resp = tenant_a.client.post("/api/v1/integrations/legacy/upload/", {"file": f, "source": "busy"}, format="multipart")
    assert resp.status_code == 404


def test_commit_creates_parties_once_and_totals_tie(granted):
    up = granted.client.post(
        "/api/v1/integrations/legacy/upload/",
        {"file": SimpleUploadedFile("parties.csv", FIXTURES["vyapar"].encode(), content_type="text/csv"),
         "source": "vyapar"},
        format="multipart",
    )
    assert up.status_code == 201, up.content
    run_id = up.json()["data"]["syncRunId"]
    done = granted.client.post("/api/v1/integrations/legacy/commit/", {"sync_run_id": run_id}, format="json")
    assert done.status_code == 200, done.content
    recon = done.data["result"]["reconciliation"]
    assert recon["receivables"]["pass"] and recon["payables"]["pass"], recon
    assert Customer.objects.filter(company=granted.company, name="Asha Traders").count() == 1
    assert Supplier.objects.filter(company=granted.company, name="Kiran Supplies").count() == 1
    again = granted.client.post("/api/v1/integrations/legacy/commit/", {"sync_run_id": run_id}, format="json")
    assert again.status_code == 400  # already committed
    # Re-importing the same file matches the existing parties instead of duplicating them.
    up2 = granted.client.post(
        "/api/v1/integrations/legacy/upload/",
        {"file": SimpleUploadedFile("parties.csv", FIXTURES["vyapar"].encode(), content_type="text/csv"),
         "source": "vyapar"},
        format="multipart",
    )
    granted.client.post("/api/v1/integrations/legacy/commit/", {"sync_run_id": up2.json()["data"]["syncRunId"]},
                        format="json")
    assert Customer.objects.filter(company=granted.company, name="Asha Traders").count() == 1


def test_items_commit_with_opening_stock(granted):
    up = granted.client.post(
        "/api/v1/integrations/legacy/upload/",
        {"file": SimpleUploadedFile("items.csv", ITEMS["marg"].encode(), content_type="text/csv"), "source": "marg"},
        format="multipart",
    )
    run_id = up.json()["data"]["syncRunId"]
    done = granted.client.post("/api/v1/integrations/legacy/commit/", {"sync_run_id": run_id}, format="json")
    assert done.status_code == 200
    assert Product.objects.filter(company=granted.company, name="Steel Bolt").exists()
    assert done.data["result"]["reconciliation"]["stock"]["pass"], done.data["result"]["reconciliation"]
