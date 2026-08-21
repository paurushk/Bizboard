"""Wave 22 Sprint F0 — GST / accounting / payroll residuals."""

from decimal import Decimal

import pytest
from django.db.models import Sum

from accounting.models import JournalEntry, JournalLine
from accounting.services import PostingService, seed_chart_of_accounts
from accounts.models import CompanyGstin
from core.exceptions import BusinessRuleError
from payroll.models import Employee, PayRun
from payroll.services import complete_pay_run, compute_statutory
from purchases.models import PurchaseInvoice
from reporting.gstr2b import match_gstr2b_to_purchases
from reporting.gst_returns import build_gstr1, build_gstr3b
from reporting.models import Gstr2bIngest
from sales.models import SalesInvoice, SalesItem
from sales.services import SalesService
from tests.conftest import make_customer, make_product, make_supplier


@pytest.mark.django_db
def test_bb_000695_sales_rcm_posts_no_output_gst(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    customer = make_customer(company)
    product = make_product(company, sku="RCM-P", gst_rate="18")
    inv = SalesInvoice.objects.create(
        company=company,
        customer=customer,
        invoice_date="2026-04-15",
        status=SalesInvoice.Status.DRAFT,
        taxable_total=Decimal("1000.00"),
        cgst_total=Decimal("90.00"),
        sgst_total=Decimal("90.00"),
        igst_total=Decimal("0"),
        grand_total=Decimal("1180.00"),
        is_reverse_charge=True,
    )
    SalesItem.objects.create(
        company=company,
        invoice=inv,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal("1000"),
        taxable_amount=Decimal("1000"),
        cgst=Decimal("90"),
        sgst=Decimal("90"),
        igst=Decimal("0"),
        line_total=Decimal("1180"),
    )
    PostingService.post_sales_invoice(inv, user=tenant_a.owner)
    entry = JournalEntry.objects.get(
        company=company, source_type="SALES_INVOICE", source_id=inv.id, purpose="COMPLETE"
    )
    codes = {line.account.code for line in entry.lines.all()}
    assert "2210" not in codes and "2220" not in codes and "2230" not in codes
    ar_amt = JournalLine.objects.filter(entry=entry, account__code="1200").aggregate(d=Sum("debit"))["d"]
    assert ar_amt == Decimal("1000.00")


@pytest.mark.django_db
def test_bb_000697_gstr3b_reuses_gstr1_stamp(tenant_a):
    company = tenant_a.company
    CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True
    )
    secondary = CompanyGstin.objects.create(
        company=company, gstin="27AAAAA0000A1Z2", state="Maharashtra", is_primary=False, is_active=True
    )
    g1 = build_gstr1(company, "2026-04", company_gstin=secondary.id)
    assert g1.get("company_gstin_id") == secondary.id
    build_gstr3b(company, "2026-04", gstr1=g1, company_gstin=secondary.id)
    assert g1["company_gstin_id"] == secondary.id


@pytest.mark.django_db
def test_bb_000703_704_payroll_employer_and_esi_ceiling(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    emp_hi = Employee.objects.create(
        company=company,
        name="Hi",
        code="E1",
        salary=Decimal("30000"),
        pf_applicable=True,
        esi_applicable=True,
        status=Employee.Status.ACTIVE,
    )
    computed = compute_statutory(emp_hi, company)
    assert computed["esi_employee"] == Decimal("0.00")
    assert computed["esi_employer"] == Decimal("0.00")
    assert computed["pf_employer"] > 0

    Employee.objects.create(
        company=company,
        name="Lo",
        code="E2",
        salary=Decimal("15000"),
        pf_applicable=True,
        esi_applicable=True,
        status=Employee.Status.ACTIVE,
    )
    run = PayRun.objects.create(company=company, period="2026-04")
    complete_pay_run(run, tenant_a.owner)
    entry = JournalEntry.objects.get(company=company, source_type="PayRun", purpose="PAYROLL")
    expense = JournalLine.objects.filter(entry=entry, account__code="5800").aggregate(d=Sum("debit"))["d"]
    slips_gross = sum((s.gross for s in run.slips.all()), Decimal("0"))
    employer = sum((s.pf_employer + s.esi_employer for s in run.slips.all()), Decimal("0"))
    assert expense == slips_gross + employer


@pytest.mark.django_db
def test_bb_000708_multi_gstin_requires_explicit_stamp(tenant_a):
    company = tenant_a.company
    CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True
    )
    CompanyGstin.objects.create(
        company=company, gstin="27AAAAA0000A1Z2", state="Maharashtra", is_primary=False, is_active=True
    )
    customer = make_customer(company)
    product = make_product(company, sku="GSTIN-P", gst_rate="18")
    inv = SalesInvoice.objects.create(
        company=company,
        customer=customer,
        invoice_date="2026-04-15",
        status=SalesInvoice.Status.DRAFT,
        taxable_total=Decimal("100"),
        cgst_total=Decimal("9"),
        sgst_total=Decimal("9"),
        grand_total=Decimal("118"),
    )
    SalesItem.objects.create(
        company=company,
        invoice=inv,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        taxable_amount=Decimal("100"),
        cgst=Decimal("9"),
        sgst=Decimal("9"),
        line_total=Decimal("118"),
    )
    with pytest.raises(BusinessRuleError, match="company_gstin"):
        SalesService.complete(inv, tenant_a.owner)


@pytest.mark.django_db
def test_bb_000716_gstr2b_partial_no_sticky_fk(tenant_a):
    company = tenant_a.company
    supplier = make_supplier(company, gstin="29DDDDD0000D1Z7")
    inv = PurchaseInvoice.objects.create(
        company=company,
        supplier=supplier,
        number="PI-PARTIAL-1",
        invoice_date="2026-04-01",
        status=PurchaseInvoice.Status.COMPLETED,
        taxable_total=Decimal("1000"),
        cgst_total=Decimal("90"),
        sgst_total=Decimal("90"),
        grand_total=Decimal("1180"),
    )
    row = Gstr2bIngest.objects.create(
        company=company,
        period="2026-04",
        supplier_gstin="29DDDDD0000D1Z7",
        invoice_number="PI-PARTIAL-1",
        taxable_value=Decimal("1500"),
        cgst=Decimal("135"),
        sgst=Decimal("135"),
    )
    match_gstr2b_to_purchases(company, "2026-04", persist=True)
    row.refresh_from_db()
    assert row.match_status == Gstr2bIngest.MatchStatus.PARTIAL
    assert row.purchase_invoice_id is None
    assert inv.id  # exists but must not be sticky-linked on amount mismatch



@pytest.mark.django_db
def test_bb_000711_tcs_posts_without_enable_tds(tenant_a, settings):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    settings.ENABLE_TDS = False
    customer = make_customer(company)
    product = make_product(company, sku="TCS-P", gst_rate="18")
    inv = SalesInvoice.objects.create(
        company=company,
        customer=customer,
        invoice_date="2026-04-15",
        status=SalesInvoice.Status.DRAFT,
        taxable_total=Decimal("1000"),
        cgst_total=Decimal("90"),
        sgst_total=Decimal("90"),
        grand_total=Decimal("1180"),
        tcs_amount=Decimal("1.18"),
    )
    SalesItem.objects.create(
        company=company,
        invoice=inv,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal("1000"),
        taxable_amount=Decimal("1000"),
        cgst=Decimal("90"),
        sgst=Decimal("90"),
        line_total=Decimal("1180"),
    )
    PostingService.post_sales_invoice(inv, user=tenant_a.owner)
    assert JournalLine.objects.filter(entry__source_id=inv.id, account__code="2266").exists()
