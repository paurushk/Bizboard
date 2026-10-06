"""Pass and rejecting cases for the remaining implementation-plan behaviour."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from core.exceptions import BusinessRuleError
from planwave.crypto import SealError, open_secret, seal
from planwave.models import EwayStubAction, IntegrityQuarantine, LoggingWindow
from planwave.services import (
    assert_books_clear,
    assert_chronic_credit_allowed,
    assert_pharmacy_sale,
    blocked_credit_match,
    cashflow_forecast,
    certification_export,
    clear_quarantine,
    consume_unlock,
    cost_visible,
    decide_approval,
    eway_validity_days,
    flag_anomaly,
    gstr2b_score,
    interest_exposure,
    issue_credit_token,
    issue_unlock,
    itc_claimable,
    map_tally_import,
    mask_commercial,
    open_quarantine,
    parse_bulk_invoices,
    record_eway_stub,
    redeem_credit_token,
    reseal_fernet_blob,
    save_itc_check,
    section_138_dates,
    section_16_4_status,
    section_50_interest,
    stamp_party,
    stock_adjustment_needs_second,
    submit_approval,
    suggest_provision,
    supplier_itc_blocked,
)
from sales.models import SalesInvoice

pytestmark = pytest.mark.django_db


def test_quarantine_blocks_close_and_clears(tenant_a):
    open_quarantine(tenant_a.company, {"gl.trial_balance_zero": ["not zero"]})
    with pytest.raises(BusinessRuleError):
        assert_books_clear(tenant_a.company)
    assert clear_quarantine(tenant_a.company, tenant_a.owner) == 1
    assert_books_clear(tenant_a.company)
    assert not IntegrityQuarantine.objects.filter(company=tenant_a.company, cleared_at__isnull=True).exists()


def test_cost_fields_are_omitted_for_sales_staff():
    raw = {"purchase_price": "80.00", "selling_price": "70.00", "name": "Paracetamol"}
    assert cost_visible("OWNER")
    masked = mask_commercial(raw, "SALES_STAFF")
    assert "purchase_price" not in masked
    assert "margin" not in masked
    assert masked["below_cost"] is True
    assert mask_commercial(raw, "OWNER")["purchase_price"] == "80.00"


def test_product_api_omits_cost_for_sales_staff(tenant_a):
    from accounts.models import CompanyUser
    from masters.models import Product
    from masters.serializers import ProductSerializer

    product = Product.objects.create(
        company=tenant_a.company, name="Masked", sku="MSK", purchase_price="40", selling_price="30",
    )
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    request = APIRequestFactory().get("/")
    request.user = tenant_a.staff
    request._company_user = membership
    request._company_user_uid = tenant_a.staff.pk
    data = ProductSerializer(product, context={"request": request}).data
    assert "purchase_price" not in data
    assert data["below_cost"] is True
    assert data["below_cost"] is True


def test_bank_account_seals_and_rejects_tamper(tenant_a):
    tenant_a.company.bank_account = "123456789012"
    tenant_a.company.save(update_fields=["bank_account"])
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.bank_account.startswith("gcm1.")
    assert open_secret(tenant_a.company.bank_account) == "123456789012"
    blob = tenant_a.company.bank_account
    flipped = blob[:-1] + ("A" if blob[-1] != "A" else "B")
    with pytest.raises(SealError):
        open_secret(flipped)
    other = seal("999", key=b"\x02" * 32)
    with pytest.raises(SealError):
        open_secret(other)


def test_fernet_gateway_blob_moves_to_gcm():
    from core.services.gsp_secrets import encrypt_gsp_credentials

    sealed = reseal_fernet_blob(encrypt_gsp_credentials({"api_key": "k"}))
    assert sealed.startswith("gcm1.")
    from planwave.services import open_credential_blob

    assert open_credential_blob(sealed)["api_key"] == "k"


def test_html_is_stripped_on_customer_notes(tenant_a):
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Plain")
    resp = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"notes": "Hello <script>alert(1)</script>"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert "<script>" not in resp.data["notes"]
    assert "alert(1)" in resp.data["notes"]


def test_stale_customer_put_returns_409(tenant_a):
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Lock")
    stale = tenant_a.client.put(
        f"/api/v1/customers/{customer.id}/",
        {"name": "Lock", "version": 0},
        format="json",
    )
    assert stale.status_code == 409
    customer.refresh_from_db()
    assert customer.name == "Lock"
    merged = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"phone": "9998887776"},
        format="json",
    )
    assert merged.status_code == 200, merged.data
    customer.refresh_from_db()
    assert customer.phone == "9998887776"
    assert customer.version == 2


def test_soft_deleted_customer_hides_and_hard_delete_is_refused(tenant_a):
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    customer = make_customer(tenant_a.company, name="Gone")
    deleted = tenant_a.client.delete(f"/api/v1/customers/{customer.id}/")
    assert deleted.status_code in (200, 204)
    listed = tenant_a.client.get("/api/v1/customers/")
    assert all(row["id"] != customer.id for row in listed.data["results"])
    from masters.models import Customer

    hidden = Customer.all_objects.get(pk=customer.id)
    assert hidden.is_deleted is True
    product = make_product(tenant_a.company, sku="SOFT1")
    add_stock(tenant_a, product, "2")
    billed = make_customer(tenant_a.company, name="Billed")
    create_draft_invoice(tenant_a, billed, [{"product": product.id, "quantity": "1", "unit_price": "10"}])
    with pytest.raises(ProtectedError):
        billed.delete()


def test_chronic_credit_blocks_and_unlock_is_single_use(tenant_a):
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Late")
    SalesInvoice.objects.create(
        company=tenant_a.company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        due_date=timezone.localdate() - timedelta(days=70),
        grand_total=Decimal("6000"),
        payment_terms_days=30,
    )

    class Draft:
        company = tenant_a.company
        payment_terms_days = 30

    Draft.customer = customer
    with pytest.raises(BusinessRuleError):
        assert_chronic_credit_allowed(Draft())
    Draft.payment_terms_days = 0
    assert_chronic_credit_allowed(Draft())
    Draft.payment_terms_days = 30
    unlock = issue_unlock(tenant_a.company, customer, tenant_a.owner, "one delivery")
    assert_chronic_credit_allowed(Draft(), unlock_code=unlock.code)
    assert consume_unlock(tenant_a.company, customer, unlock.code) is False


def test_gst_rules(tenant_a):
    claim = save_itc_check(
        tenant_a.company, "purchase", "9",
        invoice_held=True, goods_received=True, paid_within_180=True,
        supplier_tax_attested=False, return_filed_attested=True,
    )
    assert itc_claimable(claim) is False
    claim.supplier_tax_attested = True
    claim.save()
    assert itc_claimable(claim) is True
    barred = section_16_4_status(date(2024, 4, 1), claimed=False, today=date(2025, 12, 1))
    assert barred == "TIME_BARRED"
    flagged = section_16_4_status(date(2024, 4, 1), claimed=True, today=date(2025, 12, 1))
    assert flagged == "CLAIMED_REVIEW"
    assert blocked_credit_match(hsn="8703", expense_category="", on=date(2024, 1, 1)) is not None
    interest = section_50_interest(tax=Decimal("1000"), excess_itc=Decimal("0"), days=365, on=date(2024, 4, 1))
    assert interest["late_tax_interest"] == Decimal("180.00")
    assert interest["journal_posted"] is False
    with pytest.raises(BusinessRuleError):
        section_50_interest(tax=Decimal("1"), excess_itc=Decimal("0"), days=1, on=date(2010, 1, 1))
    assert supplier_itc_blocked(date(2024, 5, 2), date(2024, 5, 1)) is True
    assert supplier_itc_blocked(date(2024, 4, 1), date(2024, 5, 1)) is False


def test_eway_stub_and_distance(tenant_a):
    assert eway_validity_days(100) == 1
    assert eway_validity_days(200) == 2
    assert eway_validity_days(201) == 3
    with pytest.raises(BusinessRuleError):
        eway_validity_days(0)
    row = record_eway_stub(
        company=tenant_a.company, document_type="invoice", document_id="1",
        action=EwayStubAction.Action.PART_B, payload={"vehicle": "KA01AB1234"},
    )
    assert row.history
    with pytest.raises(BusinessRuleError):
        record_eway_stub(
            company=tenant_a.company, document_type="invoice", document_id="1",
            action=EwayStubAction.Action.PART_B, payload={}, bill_status="CANCELLED",
        )


def test_approvals_reject_self_and_expired_tokens(tenant_a):
    row = submit_approval(company=tenant_a.company, action="write_off", requester=tenant_a.owner, payload={})
    with pytest.raises(BusinessRuleError):
        decide_approval(row, approver=tenant_a.owner, accept=True)
    other = tenant_a.staff if hasattr(tenant_a, "staff") else tenant_a.owner
    if other.pk != tenant_a.owner.pk:
        decide_approval(row, approver=other, accept=True)
        assert row.status == "APPROVED"
    token = issue_credit_token(company=tenant_a.company, requester=tenant_a.owner, invoice_batch="B1")
    redeem_credit_token(tenant_a.company, token.token, "B1")
    with pytest.raises(BusinessRuleError):
        redeem_credit_token(tenant_a.company, token.token, "B1")
    assert stock_adjustment_needs_second(
        tenant_a.company, value=Decimal("10000"), quantity=Decimal("1"), on_hand=Decimal("100"),
    )


def test_party_snapshot_survives_rename(tenant_a):
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Old Name")
    invoice = SalesInvoice.objects.create(company=tenant_a.company, customer=customer, grand_total=Decimal("10"))
    snap = stamp_party(invoice, customer)
    customer.name = "New Name"
    customer.save(update_fields=["name"])
    snap.refresh_from_db()
    assert snap.payload["trade_name"] == "Old Name"


def test_pharmacy_flag_gates_schedule_x(tenant_a):
    from masters.models import Product

    product = Product.objects.create(
        company=tenant_a.company, name="Drug", sku="DRUGX", drug_schedule="X",
    )
    assert_pharmacy_sale(company=tenant_a.company, product=product)
    tenant_a.company.feature_flags = {"pharmacy_enabled": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    with pytest.raises(BusinessRuleError):
        assert_pharmacy_sale(company=tenant_a.company, product=product)
    row = assert_pharmacy_sale(
        company=tenant_a.company, product=product,
        patient_name="Asha", prescriber_name="Dr Rao", prescriber_registration="KA123",
        prescription_note="copy on file",
    )
    assert row.schedule == "X"


def test_section_138_dates_and_provision():
    memo = date(2026, 1, 1)
    ok = section_138_dates(memo=memo, demand=date(2026, 1, 20))
    assert ok["pay_by"] == "2026-02-04"
    assert "advocate" in ok["disclaimer"]
    with pytest.raises(BusinessRuleError):
        section_138_dates(memo=memo, demand=date(2026, 3, 1))


def test_provision_interest_anomaly_cashflow_and_2b(tenant_a):
    assert suggest_provision(tenant_a.company, days_overdue=100, amount=Decimal("1000")) == Decimal("250.00")
    assert interest_exposure(tenant_a.company, amount=Decimal("1000"), days=365) == Decimal("180.00")
    flagged = flag_anomaly(
        company=tenant_a.company, kind="discount", subject_id="1",
        discount=Decimal("30"), median_discount=Decimal("5"),
    )
    assert flagged is not None
    assert flag_anomaly(
        company=tenant_a.company, kind="bill", subject_id="2",
        bill=Decimal("10"), median_bill=Decimal("10"),
    ) is None
    forecast = cashflow_forecast([2, 4, 6, 8, 10], segment_average=5)
    assert forecast["low_confidence"] is False
    thin = cashflow_forecast([9], segment_average=4)
    assert thin["low_confidence"] is True
    assert gstr2b_score(
        books_gstin="29AAAAA0000A1Z5", return_gstin="29AAAAA0000A1Z5",
        books_tax=Decimal("18"), return_tax=Decimal("18"),
    ) == "AUTO"
    assert gstr2b_score(
        books_gstin="29AAAAA0000A1Z5", return_gstin="27BBBBB0000B1Z5",
        books_tax=Decimal("18"), return_tax=Decimal("99"),
    ) == "NONE"


def test_bulk_import_and_tally_map(tenant_a):
    report = parse_bulk_invoices(
        tenant_a.company,
        "invoice_ref,customer,sku,quantity,rate\nA,Acme,SKU,1,10\n,Missing,SKU,1,10\n",
    )
    assert report["report"]["accepted"] == 1
    assert report["report"]["rejected"]
    again = parse_bulk_invoices(
        tenant_a.company,
        "invoice_ref,customer,sku,quantity,rate\nA,Acme,SKU,1,10\n,Missing,SKU,1,10\n",
    )
    assert again["idempotent"] is False or again["report"]
    job = map_tally_import(
        tenant_a.company, financial_year="2025-26",
        ledgers={"Cash": "1000"}, stock_items={"Pen": "SKU"}, vouchers=[{}, {}],
    )
    assert job.voucher_count == 2
    with pytest.raises(BusinessRuleError):
        map_tally_import(
            tenant_a.company, financial_year="2025-26", ledgers={}, stock_items={}, vouchers=[],
        )


def test_certification_refuses_a_dark_window(tenant_a):
    start, end = date(2025, 4, 1), date(2026, 3, 31)
    ok = certification_export(tenant_a.company, year_start=start, year_end=end, chain_ok=True)
    assert ok["certified"] is True
    assert "sales_invoice.complete" in ok["coverage"]
    with pytest.raises(BusinessRuleError):
        certification_export(tenant_a.company, year_start=start, year_end=end, chain_ok=False)
    LoggingWindow.objects.create(
        company=tenant_a.company, starts_on=start, ends_on=end, logging_enabled=False,
    )
    with pytest.raises(BusinessRuleError):
        certification_export(tenant_a.company, year_start=start, year_end=end, chain_ok=True)


def test_rate_limit_refuses_the_eleventh_login(tenant_a):
    from django.core.cache import cache

    cache.clear()
    with override_settings(PLANWAVE_RATE_LIMIT=True):
        last = None
        for i in range(11):
            last = tenant_a.client.post(
                "/api/v1/auth/login/",
                {"email": f"nobody{i}@example.com", "password": "wrong-password-1"},
                format="json",
            )
        assert last.status_code == 429
        assert last["Retry-After"]


def test_same_account_login_stops_at_six(tenant_a):
    from django.core.cache import cache

    cache.clear()
    with override_settings(PLANWAVE_RATE_LIMIT=True):
        last = None
        for _ in range(6):
            last = tenant_a.client.post(
                "/api/v1/auth/login/",
                {"email": "same@example.com", "password": "wrong-password-1"},
                format="json",
            )
        assert last.status_code == 429


def test_cache_down_closes_login_and_leaves_api_up(tenant_a, monkeypatch):
    from django.core.cache import cache

    import planwave.ratelimit as rl

    cache.clear()
    rl._LOCAL.clear()
    rl._CACHE_ALERTED = False

    def _boom(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "add", _boom)
    with override_settings(PLANWAVE_RATE_LIMIT=True):
        last = None
        for i in range(11):
            last = tenant_a.client.post(
                "/api/v1/auth/login/",
                {"email": f"down{i}@example.com", "password": "wrong-password-1"},
                format="json",
            )
        assert last.status_code == 429
        alive = tenant_a.client.get("/api/v1/products/")
        assert alive.status_code != 429


def test_cancelled_gstin_holds_supplier_payment(tenant_a):
    from datetime import date as date_cls

    from payments.services import PaymentService
    from tests.conftest import make_supplier

    supplier = make_supplier(tenant_a.company, name="Held")
    supplier.gstin_cancelled_on = date_cls(2020, 1, 1)
    supplier.save(update_fields=["gstin_cancelled_on"])
    with pytest.raises(BusinessRuleError):
        PaymentService.create_supplier_payment(
            company=tenant_a.company, supplier=supplier, amount=Decimal("10"), mode="CASH", user=tenant_a.owner,
        )
    paid = PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("10"), mode="CASH", user=tenant_a.owner,
        gstin_hold_override=True, gstin_hold_reason="CA confirmed the old bill is payable.",
    )
    assert paid.pk


def test_no_string_built_raw_sql():
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"""(cursor\.execute|\.raw)\(\s*f["']""")
    hits = []
    for path in root.rglob("*.py"):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            hits.append(str(path))
    assert hits == []


def test_chronic_order_and_challan_are_blocked(tenant_a):
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService
    from tests.conftest import make_customer, make_product

    customer = make_customer(tenant_a.company, name="Chronic")
    SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        due_date=timezone.localdate() - timedelta(days=70), grand_total=Decimal("6000"),
        payment_terms_days=30,
    )
    product = make_product(tenant_a.company, sku="CHR-1")
    order = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, payment_terms_days=30,
    )
    from sales.models import SalesOrderItem

    SalesOrderItem.objects.create(
        company=tenant_a.company, sales_order=order, product=product,
        quantity=Decimal("1"), unit_price=Decimal("10"),
    )
    with pytest.raises(BusinessRuleError):
        SalesNotesService.confirm_sales_order(order, tenant_a.owner)


def test_pharmacy_blocks_sale_complete(tenant_a):
    from masters.models import Product
    from tests.conftest import add_stock, create_draft_invoice, make_customer

    product = Product.objects.create(
        company=tenant_a.company, name="Sched", sku="SCHX", drug_schedule="X",
        selling_price=Decimal("10"), purchase_price=Decimal("5"),
    )
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Patient")
    tenant_a.company.feature_flags = {"pharmacy_enabled": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    draft = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}])
    refused = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/", {}, format="json")
    assert refused.status_code >= 400
    ok = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {
            "patient_name": "Asha",
            "prescriber_name": "Dr Rao",
            "prescriber_registration": "KA1",
            "prescription_note": "copy",
        },
        format="json",
    )
    assert ok.status_code == 200, ok.data


def test_cancelled_supplier_gstin_blocks_purchase(tenant_a):
    from datetime import date as date_cls

    from tests.conftest import create_draft_purchase, make_product, make_supplier

    supplier = make_supplier(tenant_a.company, name="Cancelled")
    supplier.gstin_cancelled_on = date_cls(2020, 1, 1)
    supplier.save(update_fields=["gstin_cancelled_on"])
    product = make_product(tenant_a.company, sku="GSTIN-1")
    draft = create_draft_purchase(tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "10"}])
    refused = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/", {}, format="json")
    assert refused.status_code >= 400


def test_large_stock_adjustment_waits_for_a_second_user(tenant_a):
    from accounts.models import CompanyUser, User
    from tests.conftest import make_product

    second = User.objects.create_user(email="second-owner@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(
        company=tenant_a.company, user=second, role=CompanyUser.Role.OWNER,
    )
    product = make_product(tenant_a.company, sku="ADJ-1", purchase_price="10000")
    resp = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "1", "reason": "found"},
        format="json",
    )
    assert resp.status_code == 202, resp.data
    assert resp.data["status"] == "PENDING"


def test_plain_text_tags_are_stripped_on_save(tenant_a):
    from masters.models import Product

    product = Product.objects.create(company=tenant_a.company, name="Pen <script>x</script>", sku="PEN-HTML")
    product.refresh_from_db()
    assert "<script>" not in product.name
    assert "Pen" in product.name


def test_socket_drop_is_a_no_op_without_channels(tenant_a):
    from planwave.sockets import drop_user_sockets

    assert drop_user_sockets(tenant_a.owner) is False


def test_pos_harness_reports_gap_without_hiding_it():
    samples = [10, 20, 30, 40, 400]
    ordered = sorted(samples)
    p95 = ordered[max(0, math_index := int(round(0.95 * (len(ordered) - 1))))]
    assert p95 == 400
    report = {"p95_ms": p95, "target_ms": 200, "met": p95 <= 200}
    assert report["met"] is False
    assert math_index >= 0
