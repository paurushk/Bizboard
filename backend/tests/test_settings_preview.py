"""SET-22: dry-run previews of high-impact settings: they change nothing and say what would be touched."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from payments.models import CustomerReceipt, PaymentMode
from tests.conftest import make_customer

URL = "/api/v1/company/settings-preview/"


def _lines(resp):
    assert resp.status_code == 200, resp.data
    return {line["key"]: line["params"] for line in resp.data["lines"]}


def test_series_preview_lists_the_next_five_numbers_and_changes_nothing(tenant_a):
    before = tenant_a.client.get("/api/v1/company/number-series/").data["items"]
    r = tenant_a.client.post(
        URL, {"area": "series", "proposed": {"items": [{"doc_type": "QUOTATION", "prefix": "EST", "next_number": 7, "padding": 4}]}}, format="json"
    )
    assert _lines(r)["series_next"]["numbers"] == "EST-0007, EST-0008, EST-0009, EST-0010, EST-0011"
    assert tenant_a.client.get("/api/v1/company/number-series/").data["items"] == before


def test_a_bad_prefix_is_refused_in_the_preview_too(tenant_a):
    r = tenant_a.client.post(URL, {"area": "series", "proposed": {"items": [{"doc_type": "QUOTATION", "prefix": "bad prefix!"}]}}, format="json")
    assert r.status_code == 400


def _draft(tenant, number):
    from sales.models import SalesInvoice

    SalesInvoice.objects.create(
        company=tenant.company,
        customer=make_customer(tenant.company, name=f"C-{number}"),
        number=number,
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        status=SalesInvoice.Status.DRAFT,
    )


def test_registration_change_reports_the_open_drafts(tenant_a):
    _draft(tenant_a, "D-1")
    _draft(tenant_a, "D-2")
    tenant_a.company.registration_type = "REGULAR"
    tenant_a.company.save(update_fields=["registration_type"])
    r = tenant_a.client.post(URL, {"area": "gst_registration", "proposed": {"registration_type": "UNREGISTERED"}}, format="json")
    lines = _lines(r)
    assert lines["registration_change"] == {"old": "REGULAR", "new": "UNREGISTERED"}
    assert "registration_no_tax" in lines and lines["drafts_affected"]["count"] == 2
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.registration_type == "REGULAR"


def test_a_new_gstin_is_flagged_as_starting_its_own_series(tenant_a):
    r = tenant_a.client.post(URL, {"area": "gst_registration", "proposed": {"gstin": "29ABCDE1234F1ZW"}}, format="json")
    assert _lines(r)["gstin_new_series"]["gstin"] == "29ABCDE1234F1ZW"


def test_stock_rule_preview_reports_each_change(tenant_a):
    _draft(tenant_a, "D-9")
    tenant_a.company.negative_stock_policy = "BLOCK"
    tenant_a.company.valuation_business_date_order = False
    tenant_a.company.save(update_fields=["negative_stock_policy", "valuation_business_date_order"])
    r = tenant_a.client.post(
        URL,
        {"area": "stock_rules", "proposed": {"negative_stock_policy": "WARN", "valuation_business_date_order": True}},
        format="json",
    )
    lines = _lines(r)
    assert "stock_policy_warn" in lines and lines["valuation_order"] == {"on": True}
    assert lines["drafts_affected"]["count"] == 1


def test_269st_preview_counts_days_that_would_have_been_refused(tenant_a):
    customer = make_customer(tenant_a.company)
    today = timezone.localdate()
    for amount in ("150000", "60000"):
        CustomerReceipt.objects.create(
            company=tenant_a.company, customer=customer, amount=Decimal(amount), mode=PaymentMode.CASH, receipt_date=today
        )
    CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("250000"), mode=PaymentMode.BANK, receipt_date=today
    )
    CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("500000"), mode=PaymentMode.CASH,
        receipt_date=today - timedelta(days=200),
    )
    r = tenant_a.client.post(URL, {"area": "cash_269st", "proposed": {"cash_269st_mode": "block"}}, format="json")
    assert _lines(r)["cash_days_over_limit"] == {"count": 1, "blocked": True}
    off = tenant_a.client.post(URL, {"area": "cash_269st", "proposed": {"cash_269st_mode": "off"}}, format="json")
    assert "cash_days_over_limit" not in _lines(off)


def test_owner_only_unknown_area_and_missing_values_are_refused(tenant_a):
    assert tenant_a.staff_client.post(URL, {"area": "series", "proposed": {}}, format="json").status_code == 403
    assert tenant_a.client.post(URL, {"area": "nope", "proposed": {}}, format="json").status_code == 400
    assert tenant_a.client.post(URL, {"area": "series"}, format="json").status_code == 400
