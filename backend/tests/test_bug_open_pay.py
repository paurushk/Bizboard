"""Open payments, stocktake, erasure, and RLS defects."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from pypdf import PdfReader

from accounts.erasure import erase_company
from accounts.models import Company
from config.settings import _assert_postgres_rls_required
from core.exceptions import BusinessRuleError
from core.models import Notification
from payments.models import ChequeStatus, CustomerReceipt, ReceiptStatus
from payments.services import PaymentService

pytestmark = pytest.mark.django_db


def _pdf_text(asset) -> str:
    asset.file.open("rb")
    content = asset.file.read()
    asset.file.close()
    assert content.startswith(b"%PDF")
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def test_bug_pay_001_bounce_levies_fee_and_stores_section_138_notice(tenant_a):
    from accounting.models import JournalEntry, JournalLine
    from accounting.services import seed_chart_of_accounts
    from sales.models import SalesInvoice
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    product = make_product(company, sku="PAY001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(company, name="Cheque Party", state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert completed.status_code == 200, completed.data
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    receipt = PaymentService.create_receipt(
        company=company,
        customer=customer,
        amount=Decimal("100.00"),
        mode="CHEQUE",
        cheque_number="445566",
        cheque_bank_name="HDFC",
        user=tenant_a.owner,
        settlement_discount=Decimal("5.00"),
    )
    alloc = PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=invoice, amount=Decimal("100.00"), user=tenant_a.owner,
    )
    bounced = PaymentService.set_cheque_status(
        receipt=receipt,
        cheque_status=ChequeStatus.BOUNCED,
        user=tenant_a.owner,
        bank_charge=Decimal("100.005"),
    )
    bounced.refresh_from_db()
    assert bounced.cheque_status == ChequeStatus.BOUNCED
    assert bounced.status == ReceiptStatus.VOIDED
    assert bounced.dishonour_fee == Decimal("100.01")
    text = _pdf_text(bounced.section_138_notice)
    assert "Section 138" in text
    assert "Cheque Party" in text
    assert "445566" in text
    assert "not a court filing" in text
    assert "criminal" not in text.lower()
    assert JournalLine.objects.filter(
        company=company, account__code="1200", debit=Decimal("100.01"), customer=customer,
    ).exists()
    alloc_entry = JournalEntry.objects.get(
        company=company, source_type="PAYMENT_ALLOCATION", source_id=alloc.id, purpose="ALLOCATE_RECEIPT",
    )
    assert alloc_entry.status == JournalEntry.Status.REVERSED


def test_bug_pay_001_fee_post_is_atomic(tenant_a):
    from accounting.services import seed_chart_of_accounts
    from tests.conftest import make_customer

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    customer = make_customer(company, name="Atomic Party")
    receipt = PaymentService.create_receipt(
        company=company,
        customer=customer,
        amount=Decimal("40.00"),
        mode="CHEQUE",
        cheque_number="100200",
        cheque_bank_name="SBI",
        user=tenant_a.owner,
    )
    with patch("accounting.services.PostingService.post", side_effect=BusinessRuleError("fee failed")):
        with pytest.raises(BusinessRuleError):
            PaymentService.set_cheque_status(
                receipt=receipt,
                cheque_status=ChequeStatus.BOUNCED,
                user=tenant_a.owner,
                bank_charge=Decimal("15.00"),
            )
    receipt.refresh_from_db()
    assert receipt.cheque_status == ChequeStatus.PENDING_CLEARANCE
    assert receipt.status == ReceiptStatus.POSTED
    assert receipt.section_138_notice_id is None
    assert receipt.dishonour_fee == Decimal("0.00")


def _aa_consent(company, consent_id="consent-open-pay", status="ACTIVE"):
    from banking.models import AaConsent

    return AaConsent.objects.create(company=company, consent_id=consent_id, status=status)


def _receipt(company, customer, *, amount, utr="", name_unused=None):
    return CustomerReceipt.objects.create(
        company=company,
        customer=customer,
        amount=amount,
        receipt_date=date.today(),
        status=ReceiptStatus.POSTED,
        utr=utr,
    )


def test_bug_pay_006_substring_utr_does_not_bind(tenant_a):
    from banking.models import AaTransaction
    from banking.services import match_aa_to_receipts
    from tests.conftest import make_customer

    company = tenant_a.company
    short_party = make_customer(company, name="Short Party")
    other = make_customer(company, name="Other Party")
    exact_party = make_customer(company, name="Exact Party")
    short = _receipt(company, short_party, amount=Decimal("100.00"), utr="928374100")
    _receipt(company, other, amount=Decimal("100.00"), utr="111111111111")
    exact = _receipt(company, exact_party, amount=Decimal("250.00"), utr="HDFC00928374100")
    consent = _aa_consent(company)
    buried = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY006-BURIED",
        amount=Decimal("100.00"), txn_date=date.today(),
        raw={"narration": "NEFT CR HDFC00928374100999 EXTRA"},
    )
    equal = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY006-EQUAL",
        amount=Decimal("250.00"), txn_date=date.today(),
        raw={"narration": "UPI CR HDFC00928374100 EXACT"},
    )
    match_aa_to_receipts(company=company)
    buried.refresh_from_db()
    equal.refresh_from_db()
    assert buried.matched_payment_id != short.id
    assert buried.matched_payment_id is None
    assert equal.matched_payment_id == exact.id


def test_bug_pay_007_second_attach_to_same_receipt_is_refused(tenant_a):
    from banking.models import AaTransaction
    from banking.services import match_aa_to_receipts
    from tests.conftest import make_customer

    company = tenant_a.company
    customer = make_customer(company, name="One Receipt")
    receipt = _receipt(company, customer, amount=Decimal("880.00"), utr="UTIB001122334455")
    consent = _aa_consent(company, "consent-pay-007")
    first = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY007-1",
        amount=Decimal("880.00"), txn_date=date.today(),
        raw={"narration": "NEFT CR UTIB001122334455"},
    )
    second = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY007-2",
        amount=Decimal("880.00"), txn_date=date.today(),
        raw={"narration": "IMPS CR UTIB001122334455"},
    )
    match_aa_to_receipts(company=company)
    first.refresh_from_db()
    second.refresh_from_db()
    assert AaTransaction.objects.filter(matched_payment=receipt).count() == 1
    assert {first.matched_payment_id, second.matched_payment_id} == {receipt.id, None}


def test_bug_pay_008_reingest_does_not_overwrite_a_matched_row(tenant_a, settings):
    from banking.models import AaConsent, AaTransaction

    settings.ENABLE_ACCOUNT_AGGREGATOR = True
    company = tenant_a.company
    company.feature_flags = {"ENABLE_ACCOUNT_AGGREGATOR": True}
    company.save(update_fields=["feature_flags"])
    from tests.conftest import make_customer

    customer = make_customer(company, name="Reingest Party")
    receipt = _receipt(company, customer, amount=Decimal("500.00"), utr="YESB009900112233")
    feed = {
        "consent_id": "consent-pay-008",
        "fi_type": "DEPOSIT",
        "transactions": [{
            "txn_id": "PAY008-ROW",
            "amount": "500.00",
            "txn_date": date.today().isoformat(),
            "raw": {"narration": "NEFT CR YESB009900112233"},
        }],
    }
    first = tenant_a.client.post("/api/v1/banking/aa/ingest/", feed, format="json")
    assert first.status_code == 201, first.data
    row = AaTransaction.objects.get(company=company, txn_id="PAY008-ROW")
    assert row.matched_payment_id == receipt.id
    assert row.amount == Decimal("500.00")
    again = {
        **feed,
        "transactions": [{
            "txn_id": "PAY008-ROW",
            "amount": "1.00",
            "txn_date": (date.today() - timedelta(days=3)).isoformat(),
            "raw": {"narration": "OVERWRITE"},
        }],
    }
    second = tenant_a.client.post("/api/v1/banking/aa/ingest/", again, format="json")
    assert second.status_code == 201, second.data
    row.refresh_from_db()
    assert row.amount == Decimal("500.00")
    assert row.matched_payment_id == receipt.id
    assert row.txn_date == date.today()
    assert AaConsent.objects.filter(company=company, consent_id="consent-pay-008").exists()


def test_bug_pay_005_debit_matches_supplier_payment(tenant_a):
    from banking.models import AaTransaction
    from banking.services import match_aa_to_receipts
    from payments.models import SupplierPayment
    from tests.conftest import make_supplier

    company = tenant_a.company
    supplier = make_supplier(company, name="Tata Steel")
    payment = SupplierPayment.objects.create(
        company=company, supplier=supplier, amount=Decimal("800.00"),
        payment_date=date.today(), utr="SBIN009988776655",
    )
    other = SupplierPayment.objects.create(
        company=company, supplier=supplier, amount=Decimal("432.10"),
        payment_date=date.today(),
    )
    consent = _aa_consent(company, "consent-pay-005")
    debit_utr = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY005-UTR",
        amount=Decimal("-800.00"), txn_date=date.today(),
        raw={"narration": "NEFT DR SBIN009988776655"},
    )
    debit_amt = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY005-AMT",
        amount=Decimal("-432.10"), txn_date=date.today(),
        raw={"narration": "ACH DR VENDOR"},
    )
    matched = match_aa_to_receipts(company=company)
    assert matched == 2
    debit_utr.refresh_from_db()
    debit_amt.refresh_from_db()
    assert debit_utr.matched_supplier_payment_id == payment.id
    assert debit_utr.matched_payment_id is None
    assert debit_amt.matched_supplier_payment_id == other.id
    assert debit_amt.raw.get("_match_method") == "amount_date"


def test_bug_pay_002_expired_consent_is_refused(tenant_a, settings):
    from banking.models import AaConsent, AaTransaction
    from banking.fiu_adapter import fetch_live_transactions_for_consent
    from banking.services import match_aa_to_receipts

    settings.FIU_BASE_URL = "https://fiu.example"
    consent = AaConsent.objects.create(
        company=tenant_a.company, consent_id="consent-pay-002", status=AaConsent.Status.ACTIVE,
    )
    err = urllib.error.HTTPError(
        url="https://fiu.example/consents/consent-pay-002/transactions",
        code=410,
        msg="Gone",
        hdrs=None,
        fp=io.BytesIO(b'{"error":"consent_expired"}'),
    )
    before = Notification.objects.filter(company=tenant_a.company).count()
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(BusinessRuleError, match="expired"):
            fetch_live_transactions_for_consent(
                consent_id=consent.consent_id,
                fi_type="DEPOSIT",
                api_key="tok",
                company=tenant_a.company,
            )
    consent.refresh_from_db()
    assert consent.status == AaConsent.Status.EXPIRED
    assert Notification.objects.filter(company=tenant_a.company).count() == before + 1
    AaTransaction.objects.create(
        company=tenant_a.company, consent=consent, txn_id="PAY002-ROW",
        amount=Decimal("10.00"), txn_date=date.today(), raw={"narration": "NEFT"},
    )
    with pytest.raises(BusinessRuleError, match="expired"):
        match_aa_to_receipts(company=tenant_a.company)
    assert AaTransaction.objects.get(txn_id="PAY002-ROW").matched_payment_id is None


def test_bug_pay_003_fuzzy_narration_matches_only_when_unique(tenant_a):
    from banking.models import AaTransaction
    from banking.services import match_aa_to_receipts
    from tests.conftest import make_customer

    company = tenant_a.company
    infosys = make_customer(company, name="Infosys Ltd")
    acme = make_customer(company, name="Acme Traders")
    infosys_two = make_customer(company, name="Infosys Solutions")
    unique_receipt = _receipt(company, infosys, amount=Decimal("2500.00"))
    _receipt(company, acme, amount=Decimal("2500.00"))
    _receipt(company, infosys, amount=Decimal("2600.00"))
    _receipt(company, infosys_two, amount=Decimal("2600.00"))
    consent = _aa_consent(company, "consent-pay-003")
    unique_row = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY003-UNIQUE",
        amount=Decimal("2500.00"), txn_date=date.today(),
        raw={"narration": "NEFT-CMS-INFOSYS-1234"},
    )
    ambiguous_row = AaTransaction.objects.create(
        company=company, consent=consent, txn_id="PAY003-AMBIG",
        amount=Decimal("2600.00"), txn_date=date.today(),
        raw={"narration": "NEFT-CMS-INFOSYS-9999"},
    )
    match_aa_to_receipts(company=company)
    unique_row.refresh_from_db()
    ambiguous_row.refresh_from_db()
    assert unique_row.matched_payment_id == unique_receipt.id
    assert unique_row.raw.get("_match_method") == "narration"
    assert ambiguous_row.matched_payment_id is None


def _fiu_response(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    return resp


def test_bug_pay_009_fiu_rejects_malformed_money(settings):
    from banking.fiu_adapter import fetch_live_transactions_for_consent

    settings.FIU_BASE_URL = "https://fiu.example"
    bad = {"transactions": [{"txn_id": "bad", "amount": {"evil": "1"}, "narration": "X"}]}
    with patch("urllib.request.urlopen", return_value=_fiu_response(bad)):
        with pytest.raises(BusinessRuleError, match="schema"):
            fetch_live_transactions_for_consent(consent_id="c-bad", fi_type="DEPOSIT", api_key="tok")

    good = {"transactions": [{
        "txn_id": "ok",
        "amount": "12.50",
        "txn_date": "2026-10-01",
        "narration": "NEFT",
        "surprise": {"amount": "999"},
    }]}
    with patch("urllib.request.urlopen", return_value=_fiu_response(good)):
        out = fetch_live_transactions_for_consent(consent_id="c-ok", fi_type="DEPOSIT", api_key="tok")
    assert len(out) == 1
    assert out[0].amount == Decimal("12.50")
    assert "surprise" not in out[0].raw
    assert out[0].raw["amount"] == "12.50"


def test_bug_inv_003_blind_count_hides_expected_qty_until_review(tenant_a):
    from inventory.models import MovementType, StockMovement
    from inventory.services import InventoryService
    from tests.conftest import add_stock, make_product

    product = make_product(tenant_a.company, sku="INV003")
    add_stock(tenant_a, product, "10")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/inventory/stock-counts/",
        {"warehouse": warehouse.id, "blind": True},
        format="json",
    )
    assert created.status_code == 201, created.data
    sid = created.data["id"]
    counter = tenant_a.client.get(f"/api/v1/inventory/stock-counts/{sid}/counter/")
    assert counter.status_code == 200, counter.data
    line = counter.data["lines"][0]
    assert "system_qty" not in line
    assert "variance" not in line
    assert "expected_qty" not in line
    counted = tenant_a.client.patch(
        f"/api/v1/inventory/stock-counts/{sid}/",
        {"lines": [{"id": line["id"], "counted_qty": "7"}]},
        format="json",
    )
    assert counted.status_code == 200, counted.data
    assert "system_qty" not in counted.data["lines"][0]
    review = tenant_a.client.get(f"/api/v1/inventory/stock-counts/{sid}/review/")
    assert review.status_code == 200, review.data
    reviewed = review.data["lines"][0]
    assert Decimal(str(reviewed["variance"])) == Decimal("-3.000")
    assert Decimal(str(reviewed["system_qty"])) == Decimal("10.000")
    posted = tenant_a.client.post(f"/api/v1/inventory/stock-counts/{sid}/post/")
    assert posted.status_code == 200, posted.data
    move = StockMovement.objects.get(
        company=tenant_a.company, reference_type="stock_count", reference_id=str(sid),
    )
    assert move.movement_type == MovementType.ADJUSTMENT
    assert move.quantity == Decimal("-3.000")


def _seed_vertical(company, *, label: str):
    from complaints.models import Complaint
    from contracts.models import Contract
    from insurance.models import Policy, PolicyProduct
    from manufacturing.models import Bom, BomLine, WorkOrder
    from payroll.models import Employee, PayRun, PaySlip
    from projects.models import Project
    from tests.conftest import make_customer, make_product
    from workshop.models import JobCard, JobCardLine

    today = date.today()
    later = today + timedelta(days=400)
    customer = make_customer(company, name=f"{label} Customer", phone="9999911111")
    product = make_product(company, name=f"{label} Widget", sku=f"SKU-{label}")
    Project.objects.create(company=company, customer=customer, name=f"{label} Project")
    policy_product = PolicyProduct.objects.create(
        company=company, name=f"{label} Cover", insurer_name="Insurer",
        line=PolicyProduct.Line.MOTOR, tenure_months=12,
        sum_insured=Decimal("1000.00"), premium=Decimal("100.00"),
    )
    Policy.objects.create(
        company=company, customer=customer, product=policy_product,
        start_date=today, end_date=later, premium=Decimal("100.00"),
        nominee=f"{label} Nominee",
    )
    job = JobCard.objects.create(company=company, customer=customer, complaint=f"{label} job")
    JobCardLine.objects.create(
        company=company, job=job, kind=JobCardLine.Kind.PART, product=product,
        quantity=Decimal("1"), unit_price=Decimal("10"),
    )
    bom = Bom.objects.create(company=company, product=product, name=f"{label} BOM")
    BomLine.objects.create(company=company, bom=bom, component=product, qty=Decimal("1"))
    WorkOrder.objects.create(company=company, bom=bom, qty=Decimal("1"))
    Contract.objects.create(
        company=company, customer=customer, product=product,
        contract_type=Contract.Type.AMC, start_date=today, end_date=later,
    )
    employee = Employee.objects.create(
        company=company, name=f"{label} Employee", code=f"E-{label}", salary=Decimal("20000"),
    )
    run = PayRun.objects.create(company=company, period="2026-09")
    PaySlip.objects.create(
        company=company, pay_run=run, employee=employee,
        gross=Decimal("20000"), net=Decimal("18000"),
    )
    Complaint.objects.create(
        company=company, customer=customer, category=Complaint.Category.DAMAGED,
        description=f"{label} complaint text",
    )
    return customer


def test_bug_sec_006_erase_company_clears_vertical_rows():
    from complaints.models import Complaint
    from payroll.models import Employee
    from projects.models import Project
    from tests.conftest import make_tenant

    tomb = make_tenant("sec006tomb")
    customer = _seed_vertical(tomb.company, label="Tomb")
    erase_company(tomb.company, mode="tombstone", reason="dpdp", skip_export=True)
    customer.refresh_from_db()
    assert customer.name == "[erased]"
    assert customer.phone == ""
    assert Employee.objects.filter(company=tomb.company).count() == 0
    assert Complaint.objects.filter(company=tomb.company).count() == 0
    assert Project.objects.filter(company=tomb.company).count() == 0
    tomb.company.refresh_from_db()
    assert tomb.company.name.startswith("[erased")

    hard = make_tenant("sec006hard")
    _seed_vertical(hard.company, label="Hard")
    hard_id = hard.company.id
    erase_company(hard.company, mode="hard", reason="dpdp", skip_export=True)
    assert not Company.objects.filter(pk=hard_id).exists()
    assert not Employee.objects.filter(name="Hard Employee").exists()


def test_bug_sec_019_production_postgres_requires_rls():
    pg = "django.db.backends.postgresql"
    sqlite = "django.db.backends.sqlite3"
    with pytest.raises(ImproperlyConfigured, match="POSTGRES_RLS_ENABLED"):
        _assert_postgres_rls_required(django_env="production", engine=pg, rls_enabled=False)
    with pytest.raises(ImproperlyConfigured, match="POSTGRES_RLS_ENABLED"):
        _assert_postgres_rls_required(django_env="staging", engine=pg, rls_enabled=False)
    _assert_postgres_rls_required(django_env="production", engine=pg, rls_enabled=True)
    _assert_postgres_rls_required(django_env="test", engine=pg, rls_enabled=False)
    _assert_postgres_rls_required(django_env="development", engine=pg, rls_enabled=False)
    _assert_postgres_rls_required(django_env="", engine=pg, rls_enabled=False)
    _assert_postgres_rls_required(django_env="production", engine=sqlite, rls_enabled=False)
    _assert_postgres_rls_required(django_env="staging", engine=sqlite, rls_enabled=False)
