"""SET-04: bank accounts keep the full number sealed, validate, deactivate and print on invoices."""

from io import BytesIO

import pytest
from pypdf import PdfReader

from accounts.models import CompanyUser
from core.models import AuditEvent
from payments.models import BankAccount, CustomerReceipt
from payments.services import invoice_bank_details, sync_company_bank_account
from sales.models import SalesInvoice
from sales.pdf.gst_tax_invoice import render_gst_tax_invoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

URL = "/api/v1/payments/bank-accounts/"
NUMBER = "123456789012"
OTHER_NUMBER = "998877665544"


def _create(client, **body):
    body.setdefault("name", "HDFC Current")
    return client.post(URL, body, format="json")


def _pdf_text(invoice) -> str:
    reader = PdfReader(BytesIO(render_gst_tax_invoice(invoice)))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _completed_invoice(tenant):
    product = make_product(tenant.company, sku="BANK-1", hsn_code="1001")
    add_stock(tenant, product, "10")
    draft = create_draft_invoice(
        tenant,
        make_customer(tenant.company),
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    SalesInvoice.objects.filter(pk=draft["id"]).update(include_bank_details=True, include_payment_qr=True)
    return SalesInvoice.objects.get(pk=draft["id"])


# ---- validation -----------------------------------------------------------------------------


def test_ifsc_is_validated_and_upper_cased(tenant_a):
    assert _create(tenant_a.client, ifsc="HDFC123").status_code == 400
    ok = _create(tenant_a.client, ifsc="hdfc0001234")
    assert ok.status_code == 201, ok.data
    assert ok.data["ifsc"] == "HDFC0001234"


@pytest.mark.parametrize("number", ["12345", "abcdefghijk", "1234567890123456789"])
def test_bad_account_number_is_refused(tenant_a, number):
    assert _create(tenant_a.client, account_number=number).status_code == 400


def test_blank_name_is_refused(tenant_a):
    assert _create(tenant_a.client, name="   ").status_code == 400


def test_bad_upi_is_refused(tenant_a):
    assert _create(tenant_a.client, upi_id="not a upi").status_code == 400


# ---- the full number -------------------------------------------------------------------------


def test_full_number_is_sealed_never_returned_and_masked_is_derived(tenant_a):
    r = _create(tenant_a.client, account_number=" 1234 5678 9012 ", upi_id="shop@okhdfc")
    assert r.status_code == 201, r.data
    assert "account_number" not in r.data
    assert r.data["account_number_masked"] == "XXXXXXXX9012"
    assert r.data["has_full_number"] is True
    row = BankAccount.objects.get(pk=r.data["id"])
    assert NUMBER not in row.account_number_sealed
    assert row.plain_account_number == NUMBER
    listed = tenant_a.client.get(URL).data
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert all("account_number" not in x for x in rows)


def test_typed_masked_value_is_ignored(tenant_a):
    r = _create(tenant_a.client, account_number_masked="XXXX0000")
    assert r.status_code == 201
    assert r.data["account_number_masked"] == ""


def test_same_full_number_cannot_be_saved_twice_but_same_last_four_can(tenant_a):
    assert _create(tenant_a.client, name="A", account_number=NUMBER).status_code == 201
    dup = _create(tenant_a.client, name="B", account_number=NUMBER)
    assert dup.status_code == 400
    assert "already saved" in str(dup.data)
    same_last4 = _create(tenant_a.client, name="C", account_number="555566669012")
    assert same_last4.status_code == 201, same_last4.data


def test_other_company_can_use_the_same_number(tenant_a, tenant_b):
    assert _create(tenant_a.client, account_number=NUMBER).status_code == 201
    assert _create(tenant_b.client, account_number=NUMBER).status_code == 201


def test_only_the_owner_sees_the_full_number_and_each_look_is_audited(tenant_a):
    acct = _create(tenant_a.client, account_number=NUMBER).data["id"]
    r = tenant_a.client.get(f"{URL}{acct}/reveal-number/")
    assert r.status_code == 200 and r.data["account_number"] == NUMBER
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="bank_account.reveal_number", entity_id=str(acct)
    ).count() == 1
    assert tenant_a.staff_client.get(f"{URL}{acct}/reveal-number/").status_code in (403, 404)


def test_staff_with_payments_access_cannot_change_the_printed_details(tenant_a):
    CompanyUser.objects.filter(user=tenant_a.staff).update(can_create_payments=True)
    plain = _create(tenant_a.staff_client, name="Petty box", account_type="CASH_BOX")
    assert plain.status_code == 201, plain.data
    for body in ({"account_number": NUMBER}, {"upi_id": "a@okhdfc"}, {"print_on_invoices": True}):
        r = _create(tenant_a.staff_client, name="X", **body)
        assert r.status_code == 403, (body, r.data)
    r = tenant_a.staff_client.patch(f"{URL}{plain.data['id']}/", {"upi_id": "a@okhdfc"}, format="json")
    assert r.status_code == 403


# ---- deactivate, default, invoice account ------------------------------------------------------


def test_delete_switches_the_account_off_and_keeps_it(tenant_a):
    _create(tenant_a.client, name="Main", is_default=True)
    other = _create(tenant_a.client, name="Old").data["id"]
    assert tenant_a.client.delete(f"{URL}{other}/").status_code == 204
    row = BankAccount.objects.get(pk=other)
    assert row.is_active is False
    # Pickers no longer offer it; the Bank Accounts screen can still list it.
    def _ids(resp):
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        return {x["id"] for x in data}

    assert other not in _ids(tenant_a.client.get(URL))
    assert other in _ids(tenant_a.client.get(URL + "?include_inactive=1"))
    assert tenant_a.client.delete(f"{URL}{other}/").status_code == 204  # repeat is harmless


def test_default_account_cannot_be_switched_off(tenant_a):
    main = _create(tenant_a.client, name="Main", is_default=True).data["id"]
    assert tenant_a.client.delete(f"{URL}{main}/").status_code == 400
    assert tenant_a.client.patch(f"{URL}{main}/", {"is_active": False}, format="json").status_code == 400
    assert BankAccount.objects.get(pk=main).is_active is True


def test_making_another_account_default_moves_the_flag(tenant_a):
    first = _create(tenant_a.client, name="One", is_default=True).data["id"]
    second = _create(tenant_a.client, name="Two").data["id"]
    assert tenant_a.client.patch(f"{URL}{second}/", {"is_default": True}, format="json").status_code == 200
    assert BankAccount.objects.get(pk=first).is_default is False
    assert BankAccount.objects.get(pk=second).is_default is True
    assert BankAccount.objects.filter(company=tenant_a.company, is_default=True).count() == 1


def test_invoice_account_needs_a_full_number_and_is_exclusive(tenant_a):
    no_number = _create(tenant_a.client, name="A", print_on_invoices=True)
    assert no_number.status_code == 400
    cash = _create(tenant_a.client, name="Box", account_type="CASH_BOX", account_number=NUMBER, print_on_invoices=True)
    assert cash.status_code == 400
    a = _create(tenant_a.client, name="A", account_number=NUMBER, print_on_invoices=True)
    assert a.status_code == 201, a.data
    b = _create(tenant_a.client, name="B", account_number=OTHER_NUMBER, print_on_invoices=True)
    assert b.status_code == 201, b.data
    assert BankAccount.objects.get(pk=a.data["id"]).print_on_invoices is False
    assert BankAccount.objects.get(pk=b.data["id"]).print_on_invoices is True


def test_invoice_account_cannot_be_switched_off(tenant_a):
    a = _create(tenant_a.client, name="A", account_number=NUMBER, print_on_invoices=True).data["id"]
    assert tenant_a.client.delete(f"{URL}{a}/").status_code == 400


def test_opening_balance_is_locked_once_money_has_moved(tenant_a):
    acct = _create(tenant_a.client, name="A", opening_balance="100.00").data["id"]
    ok = tenant_a.client.patch(f"{URL}{acct}/", {"opening_balance": "250.00"}, format="json")
    assert ok.status_code == 200 and ok.data["opening_locked"] is False
    CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=make_customer(tenant_a.company),
        amount="10.00",
        bank_account_id=acct,
    )
    locked = tenant_a.client.patch(f"{URL}{acct}/", {"opening_balance": "999.00"}, format="json")
    assert locked.status_code == 400
    assert "adjustment" in str(locked.data)
    assert tenant_a.client.get(f"{URL}{acct}/").data["opening_locked"] is True


# ---- what bills print -------------------------------------------------------------------------


def test_company_fields_apply_until_an_invoice_account_is_chosen(tenant_a):
    company = tenant_a.company
    company.bank_name, company.bank_account, company.bank_ifsc = "Company Bank", NUMBER, "HDFC0001234"
    company.upi_id = "shop@okhdfc"
    company.save()
    details = invoice_bank_details(company)
    assert details == {
        "bank_name": "Company Bank",
        "account_number": NUMBER,
        "ifsc": "HDFC0001234",
        "upi_id": "shop@okhdfc",
    }
    _create(tenant_a.client, name="Unrelated", account_number=OTHER_NUMBER)
    assert invoice_bank_details(company)["account_number"] == NUMBER


def test_chosen_invoice_account_rules_the_details(tenant_a):
    company = tenant_a.company
    company.bank_name, company.bank_account, company.upi_id = "Company Bank", NUMBER, "old@okhdfc"
    company.save()
    _create(
        tenant_a.client, name="New Bank", account_number=OTHER_NUMBER, ifsc="ICIC0002222",
        upi_id="new@okicici", print_on_invoices=True,
    )
    assert invoice_bank_details(company) == {
        "bank_name": "New Bank",
        "account_number": OTHER_NUMBER,
        "ifsc": "ICIC0002222",
        "upi_id": "new@okicici",
    }


def test_invoice_pdf_is_the_same_before_and_after_the_details_move_to_a_bank_account(tenant_a):
    company = tenant_a.company
    company.bank_name, company.bank_account, company.bank_ifsc = "Company Bank", NUMBER, "HDFC0001234"
    company.upi_id = "shop@okhdfc"
    company.save()
    invoice = _completed_invoice(tenant_a)
    before = _pdf_text(invoice)
    for needle in ("Company Bank", NUMBER, "HDFC0001234", "shop@okhdfc"):
        assert needle in before

    sync_company_bank_account(company)  # what the backfill does
    assert BankAccount.objects.get(company=company, print_on_invoices=True).plain_account_number == NUMBER
    after = _pdf_text(SalesInvoice.objects.get(pk=invoice.pk))
    assert after == before


def test_invoice_pdf_follows_a_later_change_of_invoice_account(tenant_a):
    invoice = _completed_invoice(tenant_a)
    _create(
        tenant_a.client, name="Fresh Bank", account_number=OTHER_NUMBER, ifsc="ICIC0002222",
        upi_id="fresh@okicici", print_on_invoices=True,
    )
    text = _pdf_text(invoice)
    for needle in ("Fresh Bank", OTHER_NUMBER, "ICIC0002222", "fresh@okicici"):
        assert needle in text


# ---- the Company page and the sync ---------------------------------------------------------------


def test_saving_the_company_form_does_not_overwrite_bank_account_edits(tenant_a):
    company = tenant_a.company
    company.bank_name, company.bank_account, company.bank_ifsc = "Company Bank", NUMBER, "HDFC0001234"
    company.save()
    tenant_a.client.get(URL)  # bootstraps the first account
    acct = BankAccount.objects.get(company=company)
    tenant_a.client.patch(f"{URL}{acct.id}/", {"name": "Renamed here", "ifsc": "ICIC0002222"}, format="json")
    r = tenant_a.client.patch("/api/v1/company/", {"city": "Pune"}, format="json")
    assert r.status_code == 200, r.data
    acct.refresh_from_db()
    assert acct.name == "Renamed here" and acct.ifsc == "ICIC0002222"


def test_changing_the_company_bank_fields_updates_the_invoice_account(tenant_a):
    company = tenant_a.company
    r = tenant_a.client.patch(
        "/api/v1/company/",
        {"bank_name": "Via Company", "bank_account": NUMBER, "bank_ifsc": "HDFC0001234", "upi_id": "shop@okhdfc"},
        format="json",
    )
    assert r.status_code == 200, r.data
    acct = BankAccount.objects.get(company=company, print_on_invoices=True)
    assert acct.name == "Via Company"
    assert acct.plain_account_number == NUMBER
    assert acct.upi_id == "shop@okhdfc"
    assert acct.is_default is True


def test_backfill_copies_company_details_once_and_skips_companies_that_chose_an_account(tenant_a, tenant_b):
    from django.core.management import call_command

    a = tenant_a.company
    a.bank_name, a.bank_account, a.upi_id = "A Bank", NUMBER, "a@okhdfc"
    a.save()
    b = tenant_b.company
    b.bank_name, b.bank_account = "B Bank", OTHER_NUMBER
    b.save()
    BankAccount.objects.create(company=b, name="Chosen", print_on_invoices=True, account_number_sealed="x")

    call_command("backfill_bank_account_details", "--dry-run")
    assert not BankAccount.objects.filter(company=a).exists()
    call_command("backfill_bank_account_details")
    chosen = BankAccount.objects.get(company=a, print_on_invoices=True)
    assert chosen.plain_account_number == NUMBER and chosen.upi_id == "a@okhdfc"
    assert BankAccount.objects.filter(company=b).count() == 1
    call_command("backfill_bank_account_details")
    assert BankAccount.objects.filter(company=a).count() == 1
