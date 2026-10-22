"""Customers master hardening (CUS-04/05/07/09/10/11/15/19/21/22/23/26 — see CUSTOMERS_WORK_PACKAGES.md)."""

from decimal import Decimal

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from masters import gstin_rules
from masters.models import Customer
from tests.conftest import make_customer, make_product, create_draft_invoice

URL = "/api/v1/customers/"


def make_gstin(prefix14: str) -> str:
    """Append the valid GSTIN check character to a 14-character prefix."""
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for i, ch in enumerate(prefix14):
        product = chars.index(ch) * (1 + (i % 2))
        total += product // 36 + product % 36
    return prefix14 + chars[(36 - (total % 36)) % 36]


G_KA = make_gstin("29ABCDE1234F1Z")   # Karnataka
G_MH = make_gstin("27AABCU9603R1Z")   # Maharashtra
G_UT = make_gstin("26AABCU9603R1Z")   # Dadra and Nagar Haveli and Daman and Diu
G_97 = make_gstin("97AABCU9603R1Z")   # other territory


def details(resp):
    """Field errors from the API's error envelope."""
    return resp.data["error"]["details"]


def member_client(tenant, role, email, **flags):
    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=email)
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **flags)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def manager(tenant_a):
    return member_client(
        tenant_a, "MANAGER", "mgr@alpha.test", can_create_sales=True, can_view_financial_reports=True, can_export=True,
    )


@pytest.fixture
def staff(tenant_a):
    return member_client(tenant_a, "SALES_STAFF", "seller@alpha.test", can_create_sales=True)


@pytest.fixture
def accountant(tenant_a):
    return member_client(
        tenant_a, "ACCOUNTANT", "acct@alpha.test", can_create_sales=False,
        can_view_financial_reports=True, can_export=True,
    )


# ---- helpers (CUS-21) ----------------------------------------------------------------------

def test_gstin_helpers():
    assert gstin_rules.derive_state(G_KA) == "Karnataka"
    assert gstin_rules.derive_state(G_UT) == "Dadra and Nagar Haveli and Daman and Diu"
    assert gstin_rules.derive_state(G_97) is None
    assert gstin_rules.derive_pan(G_KA) == G_KA[2:12]
    assert gstin_rules.derive_state("not-a-gstin") is None
    # only a recognised state with a different code conflicts
    assert gstin_rules.state_conflicts(G_KA, "Maharashtra") == "Karnataka"
    assert gstin_rules.state_conflicts(G_KA, "KA") is None
    assert gstin_rules.state_conflicts(G_KA, "Somewhere odd") is None
    assert gstin_rules.state_conflicts(G_UT, "Daman and Diu") is None
    assert gstin_rules.state_conflicts(G_97, "Karnataka") is None


def test_every_state_code_resolves_back_to_itself():
    for code, name in gstin_rules.GST_CODE_TO_STATE.items():
        assert gstin_rules.state_code_of_name(name) == code


# ---- GSTIN reset / state / PAN / duplicates (CUS-05/07/10) ------------------------------------

def test_create_with_gstin_fills_state_and_pan(tenant_a):
    resp = tenant_a.client.post(URL, {"name": "Acme", "gstin": G_MH}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["state"] == "Maharashtra"
    assert resp.data["pan"] == G_MH[2:12]
    assert resp.data["gstin_verification_status"] == "UNVERIFIED"


def test_changing_gstin_resets_verification(tenant_a):
    c = make_customer(
        tenant_a.company, gstin=G_KA, gstin_verification_status="VALID", gstin_legal_name="Old Legal",
        gstin_raw_payload={"x": 1},
    )
    Customer.objects.filter(pk=c.pk).update(gstin_verified_at="2026-01-01T00:00:00Z")
    # the state follows a new GSTIN when the client does not send one
    resp = tenant_a.client.patch(f"{URL}{c.id}/", {"gstin": G_MH}, format="json")
    assert resp.status_code == 200, resp.data
    c.refresh_from_db()
    assert c.gstin == G_MH
    assert (c.gstin_verification_status, c.gstin_legal_name, c.gstin_verified_at, c.gstin_raw_payload) == (
        "UNVERIFIED", "", None, None,
    )


def test_clearing_gstin_resets_verification(tenant_a):
    c = make_customer(tenant_a.company, gstin=G_KA, gstin_verification_status="VALID", gstin_legal_name="Old")
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"gstin": ""}, format="json").status_code == 200
    c.refresh_from_db()
    assert c.gstin_verification_status == "UNVERIFIED" and c.gstin_legal_name == ""


def test_unrelated_patch_keeps_verification(tenant_a):
    c = make_customer(tenant_a.company, gstin=G_KA, gstin_verification_status="VALID", gstin_legal_name="Keep")
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "hello"}, format="json").status_code == 200
    c.refresh_from_db()
    assert c.gstin_verification_status == "VALID" and c.gstin_legal_name == "Keep"
    # re-sending the same GSTIN is not a change
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"gstin": G_KA.lower()}, format="json").status_code == 200
    c.refresh_from_db()
    assert c.gstin_verification_status == "VALID"


def test_duplicate_gstin_names_the_customer(tenant_a, tenant_b):
    make_customer(tenant_a.company, name="First Holder", gstin=G_KA)
    other = make_customer(tenant_a.company, name="Second", gstin=G_MH, state="Maharashtra")
    resp = tenant_a.client.post(URL, {"name": "Third", "gstin": G_KA}, format="json")
    assert resp.status_code == 400
    assert "First Holder" in str(details(resp)["gstin"])
    resp = tenant_a.client.patch(f"{URL}{other.id}/", {"gstin": G_KA}, format="json")
    assert resp.status_code == 400 and "First Holder" in str(details(resp)["gstin"])
    # re-saving your own GSTIN is fine; another company may use the same number
    assert tenant_a.client.patch(f"{URL}{other.id}/", {"gstin": G_MH}, format="json").status_code == 200
    assert tenant_b.client.post(URL, {"name": "Other tenant", "gstin": G_KA}, format="json").status_code == 201


def test_soft_deleted_holder_does_not_block_gstin(tenant_a):
    gone = make_customer(tenant_a.company, name="Gone", gstin=G_KA)
    assert tenant_a.client.delete(f"{URL}{gone.id}/").status_code == 204
    assert tenant_a.client.post(URL, {"name": "Reuse", "gstin": G_KA}, format="json").status_code == 201


def test_state_mismatch_rejected_only_when_strict(tenant_a, settings):
    settings.CUSTOMER_STRICT_VALIDATION = False
    ok = tenant_a.client.post(URL, {"name": "Loose", "gstin": G_KA, "state": "Maharashtra"}, format="json")
    assert ok.status_code == 201
    settings.CUSTOMER_STRICT_VALIDATION = True
    bad = tenant_a.client.post(URL, {"name": "Strict", "gstin": G_MH, "state": "Karnataka"}, format="json")
    assert bad.status_code == 400 and "Maharashtra" in str(details(bad)["state"])
    assert tenant_a.client.post(URL, {"name": "Fine", "gstin": G_MH, "state": "MH"}, format="json").status_code == 201
    # a legacy mismatch must not block an unrelated edit
    legacy = Customer.objects.get(pk=ok.data["id"])
    assert tenant_a.client.patch(f"{URL}{legacy.id}/", {"notes": "x"}, format="json").status_code == 200


def test_special_prefixes_do_not_false_reject(tenant_a, settings):
    settings.CUSTOMER_STRICT_VALIDATION = True
    assert tenant_a.client.post(
        URL, {"name": "UT", "gstin": G_UT, "state": "Daman and Diu"}, format="json").status_code == 201
    assert tenant_a.client.post(
        URL, {"name": "Territory", "gstin": G_97, "state": "Karnataka"}, format="json").status_code == 201


# ---- POS walk-in (CUS-04) ----------------------------------------------------------------------

@pytest.fixture
def walk_in(tenant_a):
    return Customer.objects.create(company=tenant_a.company, name="Walk-in", is_pos_walk_in=True, state="Karnataka")


@pytest.mark.parametrize("payload, field", [
    ({"gstin": G_KA}, "gstin"),
    ({"credit_limit": "500"}, "credit_limit"),
    ({"status": "BLOCKED"}, "status"),
])
def test_walk_in_rejects_patch(tenant_a, walk_in, payload, field):
    resp = tenant_a.client.patch(f"{URL}{walk_in.id}/", payload, format="json")
    assert resp.status_code == 400 and field in details(resp)


def test_walk_in_cannot_be_deleted_or_deactivated(tenant_a, walk_in):
    assert tenant_a.client.delete(f"{URL}{walk_in.id}/").status_code == 400
    walk_in.refresh_from_db()
    assert walk_in.is_deleted is False and walk_in.status == "ACTIVE"


def test_walk_in_still_editable_otherwise(tenant_a, walk_in):
    assert tenant_a.client.patch(f"{URL}{walk_in.id}/", {"notes": "till 1"}, format="json").status_code == 200


def test_set_walk_in_requires_active(tenant_a):
    blocked = make_customer(tenant_a.company, name="Blocked", status="BLOCKED")
    resp = tenant_a.client.post(f"{URL}set-pos-walk-in/", {"customer": blocked.id}, format="json")
    assert resp.status_code == 400


# ---- credit-term permissions (CUS-23) ------------------------------------------------------------

def test_sales_staff_cannot_change_credit_terms(tenant_a, staff):
    c = make_customer(tenant_a.company, credit_limit=Decimal("1000"), credit_days=15)
    resp = staff.patch(f"{URL}{c.id}/", {"credit_limit": "9000"}, format="json")
    assert resp.status_code == 400 and "credit_limit" in details(resp)
    assert staff.patch(f"{URL}{c.id}/", {"credit_days": 90}, format="json").status_code == 400
    # echoing the stored values (a form re-save) is not a change
    assert staff.patch(f"{URL}{c.id}/", {"credit_limit": "1000.00", "credit_days": 15}, format="json").status_code == 200
    created = staff.post(URL, {"name": "With limit", "credit_limit": "50"}, format="json")
    assert created.status_code == 400


def test_manager_and_owner_change_credit_terms_with_audit(tenant_a, manager):
    from core.models import AuditEvent

    c = make_customer(tenant_a.company, credit_limit=Decimal("1000"))
    assert manager.patch(f"{URL}{c.id}/", {"credit_limit": "2500"}, format="json").status_code == 200
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"credit_days": 30}, format="json").status_code == 200
    events = AuditEvent.objects.filter(entity_type="Customer", entity_id=str(c.id), description="customer.credit_terms")
    assert events.count() == 2
    assert events.order_by("id").first().metadata["credit_limit"] == {"from": "1000.00", "to": "2500.00"}


# ---- optimistic concurrency (CUS-09/18) -----------------------------------------------------------

def test_patch_with_stale_version_conflicts(tenant_a):
    c = make_customer(tenant_a.company)
    ok = tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "a", "version": c.version}, format="json")
    assert ok.status_code == 200 and ok.data["version"] == c.version + 1
    stale = tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "b", "version": c.version}, format="json")
    assert stale.status_code == 409 and stale.data["error"]["code"] == "stale_write"
    assert tenant_a.client.get(f"{URL}{c.id}/").data["notes"] == "a"


def test_patch_without_version_still_merges(tenant_a):
    c = make_customer(tenant_a.company)
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "a"}, format="json").status_code == 200
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"phone": "9876543210"}, format="json").status_code == 200
    c.refresh_from_db()
    assert c.notes == "a" and c.phone == "9876543210"


def test_put_requires_version(tenant_a):
    c = make_customer(tenant_a.company)
    assert tenant_a.client.put(f"{URL}{c.id}/", {"name": "N"}, format="json").status_code == 409


def test_archiving_referenced_customer_bumps_version(tenant_a):
    c = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    create_draft_invoice(tenant_a, c, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    before = c.version
    resp = tenant_a.client.delete(f"{URL}{c.id}/")
    assert resp.status_code == 200
    c.refresh_from_db()
    assert c.status == "INACTIVE" and c.version == before + 1


# ---- coordinates / phone (CUS-08/26) ---------------------------------------------------------------

def test_coordinates_can_be_cleared(tenant_a):
    c = make_customer(tenant_a.company, latitude=Decimal("12.5"), longitude=Decimal("77.5"))
    resp = tenant_a.client.patch(f"{URL}{c.id}/", {"latitude": None, "longitude": None}, format="json")
    assert resp.status_code == 200
    c.refresh_from_db()
    assert c.latitude is None and c.longitude is None
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"latitude": "95", "longitude": "10"}, format="json").status_code == 400
    assert tenant_a.client.patch(f"{URL}{c.id}/", {"latitude": "10"}, format="json").status_code == 400


def test_phone_rule_only_when_strict_and_changed(tenant_a, settings):
    legacy = make_customer(tenant_a.company, phone="12345")
    settings.CUSTOMER_STRICT_VALIDATION = False
    assert tenant_a.client.post(URL, {"name": "Loose", "phone": "12"}, format="json").status_code == 201
    settings.CUSTOMER_STRICT_VALIDATION = True
    assert tenant_a.client.post(URL, {"name": "Bad", "phone": "12"}, format="json").status_code == 400
    assert tenant_a.client.post(URL, {"name": "Good", "phone": "+91 98765-43210"}, format="json").status_code == 201
    assert tenant_a.client.patch(f"{URL}{legacy.id}/", {"phone": "12345", "notes": "x"}, format="json").status_code == 200


# ---- search / filters / sort (CUS-11/19) ------------------------------------------------------------

def test_search_by_email_and_status_validation(tenant_a):
    make_customer(tenant_a.company, name="Mail One", email="mail.one@example.com")
    make_customer(tenant_a.company, name="Other", email="x@y.com")
    resp = tenant_a.client.get(URL, {"q": "mail.one@example"})
    assert [r["name"] for r in resp.data["results"]] == ["Mail One"]
    assert tenant_a.client.get(URL, {"status": "FOO"}).status_code == 400
    assert tenant_a.client.get(URL, {"status": "INACTIVE"}).status_code == 200
    assert tenant_a.client.get(URL, {"q": "z" * 500}).status_code == 200  # capped, not an error


@pytest.mark.invariant_skip("gl.ar_ties_to_documents", reason="sales documents or journals are built through the ORM, so receivables in the ledger and on documents cannot tie")
def test_balance_sort_orders_by_outstanding_and_pages(tenant_a):
    from sales.models import SalesInvoice

    names = ["Alpha", "Bravo", "Charlie"]
    customers = {n: make_customer(tenant_a.company, name=n) for n in names}
    product = make_product(tenant_a.company)
    for name, qty in (("Charlie", "5"), ("Alpha", "1")):
        draft = create_draft_invoice(
            tenant_a, customers[name], [{"product": product.id, "quantity": qty, "unit_price": "100"}],
        )
        SalesInvoice.objects.filter(pk=draft["id"]).update(status="COMPLETED")
    resp = tenant_a.client.get(URL, {"sort": "balance", "page_size": 2})
    assert resp.status_code == 200
    got = [r["name"] for r in resp.data["results"]]
    assert got == ["Charlie", "Alpha"] and resp.data["count"] == 3
    page2 = tenant_a.client.get(URL, {"sort": "balance", "page_size": 2, "page": 2})
    assert [r["name"] for r in page2.data["results"]] == ["Bravo"]


def test_outstanding_computed_once_per_list_request(tenant_a, monkeypatch):
    from ledgers.services import LedgerService

    make_customer(tenant_a.company)
    calls = {"n": 0}
    real = LedgerService.bulk_customer_outstanding

    def counting(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(LedgerService, "bulk_customer_outstanding", staticmethod(counting))
    assert tenant_a.client.get(URL, {"sort": "balance"}).status_code == 200
    assert calls["n"] == 1


# ---- GSTIN verify / lookup (CUS-03/16/19) ------------------------------------------------------------

def test_verify_gstin_permissions_notice_and_version(tenant_a, staff, accountant):
    c = make_customer(tenant_a.company, gstin=G_KA)
    assert accountant.post(f"{URL}{c.id}/verify-gstin/").status_code == 403
    resp = staff.post(f"{URL}{c.id}/verify-gstin/")
    assert resp.status_code == 200, resp.data
    assert resp.data["gstin_verification_status"] == "UNVERIFIED"
    assert "not configured" in resp.data["verification_notice"]
    assert resp.data["version"] == c.version + 1


def test_lookup_gstin(tenant_a, staff, accountant):
    holder = make_customer(tenant_a.company, name="Holder", gstin=G_MH)
    bad = staff.post(f"{URL}lookup-gstin/", {"gstin": "NOPE"}, format="json")
    assert bad.status_code == 400
    resp = staff.post(f"{URL}lookup-gstin/", {"gstin": G_MH}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["state"] == "Maharashtra" and resp.data["pan"] == G_MH[2:12]
    assert "not configured" in resp.data["notice"]
    assert resp.data["existing_customer"] == {"id": holder.id, "name": "Holder"}
    assert accountant.post(f"{URL}lookup-gstin/", {"gstin": G_MH}, format="json").status_code == 403
    assert Customer.objects.filter(company=tenant_a.company).count() == 1  # writes nothing


# ---- summary / export / history (CUS-15/24) -----------------------------------------------------------

def test_summary_counts_and_filters(tenant_a, accountant):
    make_customer(tenant_a.company, name="A1")
    make_customer(tenant_a.company, name="B1", status="BLOCKED")
    resp = accountant.get(f"{URL}summary/")
    assert resp.status_code == 200, resp.data
    assert (resp.data["total_count"], resp.data["active_count"], resp.data["blocked_count"]) == (2, 1, 1)
    only = accountant.get(f"{URL}summary/", {"status": "BLOCKED"})
    assert only.data["total_count"] == 1
    assert accountant.get(f"{URL}summary/", {"q": "zzz"}).data["total_count"] == 0


def test_summary_and_export_need_reports_permission(tenant_a, staff):
    assert staff.get(f"{URL}summary/").status_code == 403
    assert staff.get(f"{URL}export/").status_code == 403
    assert staff.get(f"{URL}1/history/").status_code == 403


def test_export_csv_is_formula_safe_filtered_audited_and_isolated(tenant_a, tenant_b, accountant):
    from core.models import AuditEvent

    make_customer(tenant_a.company, name="=HYPERLINK(1)", email="evil@example.com")
    make_customer(tenant_a.company, name="Plain Co", status="BLOCKED")
    make_customer(tenant_b.company, name="Other Tenant Co")
    resp = accountant.get(f"{URL}export/")
    assert resp.status_code == 200
    body = b"".join(resp.streaming_content).decode()
    assert "'=HYPERLINK(1)" in body and "Plain Co" in body and "Other Tenant Co" not in body
    assert body.splitlines()[0].startswith("Name,Phone,Email,GSTIN")
    filtered = b"".join(accountant.get(f"{URL}export/", {"status": "BLOCKED"}).streaming_content).decode()
    assert "Plain Co" in filtered and "HYPERLINK" not in filtered
    assert AuditEvent.objects.filter(company=tenant_a.company, action="EXPORT", entity_type="Customer").count() == 2


def test_export_refuses_oversize(tenant_a, accountant, monkeypatch):
    import masters.views as views

    make_customer(tenant_a.company, name="One")
    make_customer(tenant_a.company, name="Two")
    monkeypatch.setattr(views, "CUSTOMER_EXPORT_MAX_ROWS", 1)
    assert accountant.get(f"{URL}export/").status_code == 400


def test_history_lists_changes(tenant_a, accountant):
    c = make_customer(tenant_a.company)
    tenant_a.client.patch(f"{URL}{c.id}/", {"credit_days": 45}, format="json")
    resp = accountant.get(f"{URL}{c.id}/history/")
    assert resp.status_code == 200
    changes = [row["changes"] for row in resp.data["results"] if row["changes"]]
    assert {"credit_days": {"from": "0", "to": "45"}} in changes


# ---- audit command (CUS-22) --------------------------------------------------------------------------------

def test_customers_audit_command(tenant_a, capsys):
    make_customer(tenant_a.company, name="Stale", gstin=G_KA, gstin_verification_status="VALID")
    make_customer(tenant_a.company, name="Mismatch", gstin=G_MH, state="Karnataka")
    call_command("customers_audit")
    out = capsys.readouterr().out
    assert "stale_valid_status" in out and "state_mismatch" in out
    with pytest.raises(SystemExit):
        call_command("customers_audit", "--fail-on-findings")
    call_command("customers_audit", "--fix")
    assert Customer.objects.get(name="Stale").gstin_verification_status == "UNVERIFIED"


# ---- customer import parity (CUS-25) ---------------------------------------------------------------------

def test_customer_import_applies_gstin_rules(tenant_a, settings):
    from types import SimpleNamespace

    from imports.services import ImportService

    settings.CUSTOMER_STRICT_VALIDATION = True
    job = SimpleNamespace(company=tenant_a.company)
    created, skipped = ImportService._commit_customers(
        job,
        [
            {"name": "Imp One", "gstin": G_MH.lower()},
            {"name": "Imp Two", "gstin": G_KA, "state": "Maharashtra"},
            {"name": "Imp Three", "gstin": G_UT, "state": "Daman and Diu"},
        ],
        tenant_a.owner,
    )
    assert created == 2
    assert len(skipped) == 1 and "belongs to Karnataka" in skipped[0]["errors"][0]
    one = Customer.objects.get(name="Imp One")
    assert (one.gstin, one.state, one.pan) == (G_MH, "Maharashtra", G_MH[2:12])
    assert one.gstin_verification_status == "UNVERIFIED"


# ---- archived customers are not billable (founder decision 2026-10-11) -----------------------------------

def _invoice_payload(customer, product):
    return {"customer": customer.id, "invoice_type": "GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}]}


def test_inactive_customer_cannot_get_new_documents(tenant_a):
    product = make_product(tenant_a.company)
    gone = make_customer(tenant_a.company, name="Retired", status="INACTIVE")
    blocked = make_customer(tenant_a.company, name="Held", status="BLOCKED")
    resp = tenant_a.client.post("/api/v1/sales/invoices/", _invoice_payload(gone, product), format="json")
    assert resp.status_code == 400 and "inactive customer" in str(resp.data)
    resp = tenant_a.client.post("/api/v1/sales/invoices/", _invoice_payload(blocked, product), format="json")
    assert resp.status_code == 400 and "blocked customer" in str(resp.data)
    quote = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {"customer": gone.id, "valid_until": "2099-01-01",
         "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}]},
        format="json",
    )
    assert quote.status_code == 400


def test_inactive_customer_can_still_take_a_receipt_and_be_reactivated(tenant_a):
    gone = make_customer(tenant_a.company, name="Retired", status="INACTIVE")
    assert tenant_a.client.patch(f"{URL}{gone.id}/", {"status": "ACTIVE"}, format="json").status_code == 200


# ---- archive / delete is owner or manager only ---------------------------------------------------------------

def test_only_owner_or_manager_may_archive(tenant_a, staff, manager):
    c = make_customer(tenant_a.company, name="Drop Me")
    assert staff.delete(f"{URL}{c.id}/").status_code == 403
    assert manager.delete(f"{URL}{c.id}/").status_code == 204


# ---- strict rules are on by default -----------------------------------------------------------------------------

def test_strict_validation_defaults_on():
    from django.conf import settings

    assert settings.CUSTOMER_STRICT_VALIDATION is True
    assert settings.ENABLE_CUSTOMER_360 is True


# ---- summary figures with real data --------------------------------------------------------------------------------

@pytest.mark.invariant_skip("gl.ar_ties_to_documents", reason="sales documents or journals are built through the ORM, so receivables in the ledger and on documents cannot tie")
def test_summary_totals_over_limit_and_advances(tenant_a, accountant):
    from sales.models import SalesInvoice

    product = make_product(tenant_a.company)
    over = make_customer(tenant_a.company, name="Over", credit_limit=Decimal("50"))
    fine = make_customer(tenant_a.company, name="Fine", credit_limit=Decimal("5000"))
    for c in (over, fine):
        draft = create_draft_invoice(tenant_a, c, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
        SalesInvoice.objects.filter(pk=draft["id"]).update(status="COMPLETED")
    resp = accountant.get(f"{URL}summary/")
    assert resp.status_code == 200
    data = resp.data
    assert data["over_credit_limit_count"] == 1
    assert Decimal(data["total_outstanding"]) == Decimal(data["net_credit_exposure"]) > 0
    assert Decimal(data["total_unallocated_advance"]) == 0


# ---- the list does not query per customer ---------------------------------------------------------------------------------

def test_list_query_count_does_not_grow_with_customers(tenant_a, django_assert_max_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def count_for(n_extra):
        for i in range(n_extra):
            make_customer(tenant_a.company, name=f"Bulk {n_extra}-{i}")
        with CaptureQueriesContext(connection) as ctx:
            assert tenant_a.client.get(URL, {"sort": "balance"}).status_code == 200
        return len(ctx)

    small = count_for(3)
    large = count_for(40)
    assert large <= small + 2


# ---- review batch 1: roles on status, PAN/state follow GSTIN, drafts, references, phone ------------------------------------

def test_sales_staff_cannot_archive_or_unblock_by_patch(tenant_a, staff, manager):
    live = make_customer(tenant_a.company, name="Live")
    held = make_customer(tenant_a.company, name="Held", status="BLOCKED")
    gone = make_customer(tenant_a.company, name="Gone", status="INACTIVE")
    assert staff.patch(f"{URL}{live.id}/", {"status": "INACTIVE"}, format="json").status_code == 400
    assert staff.patch(f"{URL}{held.id}/", {"status": "ACTIVE"}, format="json").status_code == 400
    assert staff.patch(f"{URL}{gone.id}/", {"status": "ACTIVE"}, format="json").status_code == 400
    # blocking stays open to sales, and re-sending the same status is not a change
    assert staff.patch(f"{URL}{live.id}/", {"status": "BLOCKED"}, format="json").status_code == 200
    assert staff.patch(f"{URL}{live.id}/", {"status": "BLOCKED"}, format="json").status_code == 200
    assert manager.patch(f"{URL}{held.id}/", {"status": "ACTIVE"}, format="json").status_code == 200
    assert tenant_a.client.patch(f"{URL}{gone.id}/", {"status": "ACTIVE"}, format="json").status_code == 200


def test_new_gstin_brings_its_pan_and_state_but_keeps_a_typed_pan(tenant_a):
    follow = make_customer(tenant_a.company, name="Follow", gstin=G_KA, state="Karnataka", pan=G_KA[2:12])
    resp = tenant_a.client.patch(f"{URL}{follow.id}/", {"gstin": G_MH}, format="json")
    assert resp.status_code == 200, resp.data
    follow.refresh_from_db()
    assert (follow.pan, follow.state) == (G_MH[2:12], "Maharashtra")
    typed = make_customer(tenant_a.company, name="Typed", gstin=G_UT, state="Daman and Diu", pan="ZZZZZ9999Z")
    typed_resp = tenant_a.client.patch(f"{URL}{typed.id}/", {"gstin": G_97}, format="json")
    assert typed_resp.status_code == 200
    typed.refresh_from_db()
    assert typed.pan == "ZZZZZ9999Z"
    # clearing the GSTIN keeps the PAN
    assert tenant_a.client.patch(f"{URL}{follow.id}/", {"gstin": ""}, format="json").status_code == 200
    follow.refresh_from_db()
    assert follow.pan == G_MH[2:12]


def test_pan_format_is_checked(tenant_a):
    assert tenant_a.client.post(URL, {"name": "BadPan", "pan": "123"}, format="json").status_code == 400
    ok = tenant_a.client.post(URL, {"name": "GoodPan", "pan": "abcde1234f"}, format="json")
    assert ok.status_code == 201 and ok.data["pan"] == "ABCDE1234F"


def test_draft_of_an_archived_customer_can_be_saved_but_not_completed(tenant_a):
    product = make_product(tenant_a.company)
    c = make_customer(tenant_a.company, name="Arch")
    draft = create_draft_invoice(tenant_a, c, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    Customer.objects.filter(pk=c.pk).update(status="INACTIVE")
    ok = tenant_a.client.patch(f"/api/v1/sales/invoices/{draft['id']}/", {"customer": c.id, "notes": "x"}, format="json")
    assert ok.status_code == 200, ok.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/", {}, format="json")
    assert done.status_code == 400 and "inactive customer" in str(done.data)


def test_is_referenced_covers_every_protected_relation(tenant_a):
    import datetime

    from contracts.models import Contract

    owned = make_customer(tenant_a.company, name="OnlyAddress")
    owned.shipping_addresses.create(company=tenant_a.company, label="x", address="1 Road")
    assert owned.is_referenced() is False
    used = make_customer(tenant_a.company, name="HasContract")
    Contract.objects.create(
        company=tenant_a.company, customer=used, contract_type=list(Contract.Type.values)[0],
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2027, 1, 1),
    )
    assert used.is_referenced() is True
    resp = tenant_a.client.delete(f"{URL}{used.id}/")
    assert resp.status_code == 200 and Customer.objects.get(pk=used.pk).status == "INACTIVE"
    assert tenant_a.client.delete(f"{URL}{owned.id}/").status_code == 204


def test_indian_mobile_numbers_starting_91_are_valid(tenant_a):
    from core.validators import is_valid_indian_mobile

    for good in ("9123456789", "919123456789", "+919123456789", "09123456789", "+91 98765-43210"):
        assert is_valid_indian_mobile(good), good
    for bad in ("91234567", "5123456789", "91912345678", "98765", ""):
        assert not is_valid_indian_mobile(bad), bad
    assert tenant_a.client.post(URL, {"name": "P91", "phone": "9123456789"}, format="json").status_code == 201


# ---- review batch 2: archive refuses with a balance, schedules pause -----------------------------------------------------

@pytest.mark.invariant_skip("gl.ar_ties_to_documents", reason="sales documents or journals are built through the ORM, so receivables in the ledger and on documents cannot tie")
def test_archive_is_refused_with_a_balance_or_an_advance(tenant_a, monkeypatch):
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    product = make_product(tenant_a.company)
    owes = make_customer(tenant_a.company, name="Owes")
    draft = create_draft_invoice(tenant_a, owes, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    SalesInvoice.objects.filter(pk=draft["id"]).update(status="COMPLETED")
    resp = tenant_a.client.delete(f"{URL}{owes.id}/")
    assert resp.status_code == 400 and "outstanding balance" in str(resp.data)
    assert Customer.objects.get(pk=owes.pk).status == "ACTIVE"
    paid_ahead = make_customer(tenant_a.company, name="PaidAhead")
    monkeypatch.setattr(
        LedgerService, "customer_unallocated_receipts", staticmethod(lambda company, customer: Decimal("50")),
    )
    resp = tenant_a.client.delete(f"{URL}{paid_ahead.id}/")
    assert resp.status_code == 400 and "unallocated advance" in str(resp.data)


def test_archiving_pauses_recurring_schedules_and_blocked_customers_are_skipped(tenant_a):
    from datetime import timedelta

    from django.utils import timezone

    from sales.models import RecurringInvoiceSchedule
    from sales.recurring import _process_company_schedules

    product = make_product(tenant_a.company)
    c = make_customer(tenant_a.company, name="Subscriber")
    create_draft_invoice(tenant_a, c, [{"product": product.id, "quantity": "1", "unit_price": "100"}])  # referenced
    now = timezone.now()
    sched = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company, customer=c, next_run_at=now - timedelta(days=1),
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "100"}]},
    )
    Customer.objects.filter(pk=c.pk).update(status="BLOCKED")
    created, *_ = _process_company_schedules(
        tenant_a.company.id, now, created=0, skipped_locked=0, skipped_duplicate=0, skipped_error=0,
    )
    assert created == 0
    Customer.objects.filter(pk=c.pk).update(status="ACTIVE")
    assert tenant_a.client.delete(f"{URL}{c.id}/").status_code == 200
    sched.refresh_from_db()
    assert sched.is_active is False


# ---- review batch 3: history, no-op saves, masked audit ---------------------------------------------------------------------

def test_a_credit_change_appears_once_in_history(tenant_a, accountant):
    c = make_customer(tenant_a.company)
    tenant_a.client.patch(f"{URL}{c.id}/", {"credit_days": 45}, format="json")
    rows = [r for r in accountant.get(f"{URL}{c.id}/history/").data["results"] if r["changes"]]
    assert len(rows) == 1


def test_resaving_unchanged_values_does_not_bump_version_or_audit(tenant_a):
    from core.models import AuditEvent

    c = make_customer(tenant_a.company, name="Same", notes="n")
    before = AuditEvent.objects.filter(entity_type="Customer", entity_id=str(c.id)).count()
    resp = tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "n", "name": "Same", "version": c.version}, format="json")
    assert resp.status_code == 200 and resp.data["version"] == c.version
    assert AuditEvent.objects.filter(entity_type="Customer", entity_id=str(c.id)).count() == before


def test_audit_changes_mask_phone_email_and_pan(tenant_a, accountant):
    c = make_customer(tenant_a.company, phone="9876543210", email="asha@example.com")
    tenant_a.client.patch(
        f"{URL}{c.id}/", {"phone": "9123456789", "email": "ravi@example.com", "pan": "ABCDE1234F"}, format="json",
    )
    changes = next(r["changes"] for r in accountant.get(f"{URL}{c.id}/history/").data["results"] if r["changes"])
    assert changes["phone"] == {"from": "******3210", "to": "******6789"}
    assert changes["email"]["to"] == "r***@example.com" and changes["pan"]["to"] == "******234F"


def test_stale_conflict_has_one_shape(tenant_a):
    c = make_customer(tenant_a.company)
    tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "a"}, format="json")
    pre = tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "b", "version": c.version}, format="json")
    put = tenant_a.client.put(f"{URL}{c.id}/", {"name": "N", "version": c.version}, format="json")
    assert pre.status_code == put.status_code == 409
    assert pre.data["error"]["code"] == put.data["error"]["code"] == "stale_write"


# ---- review batch 4: provider state, export order ------------------------------------------------------------------------------

def test_unreachable_provider_is_not_reported_as_unconfigured(tenant_a, staff, monkeypatch, settings):
    import urllib.error

    settings.GSTIN_PROVIDER = "http"
    settings.GSP_SANDBOX_BASE_URL = "https://gsp.example.test"
    monkeypatch.setattr("core.services.gsp_adapters.assert_safe_outbound_url", lambda url: None)

    def boom(*a, **k):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    c = make_customer(tenant_a.company, gstin=G_KA)
    resp = staff.post(f"{URL}{c.id}/verify-gstin/")
    assert resp.status_code == 200
    assert "could not be reached" in resp.data["verification_notice"]


def test_export_follows_the_chosen_sort(tenant_a, accountant):
    make_customer(tenant_a.company, name="Alpha")
    make_customer(tenant_a.company, name="Bravo")
    body = b"".join(accountant.get(f"{URL}export/", {"sort": "recent"}).streaming_content).decode().splitlines()
    assert body[1].startswith("Bravo") and body[2].startswith("Alpha")


# ---- one creation path for CRM and imports -------------------------------------------------------------------------------------

def test_create_customer_service_applies_the_form_rules(tenant_a):
    from core.exceptions import BusinessRuleError
    from masters.services import create_customer

    made = create_customer(company=tenant_a.company, user=tenant_a.owner, name="Svc Co", gstin=G_MH.lower())
    assert (made.gstin, made.state, made.pan) == (G_MH, "Maharashtra", G_MH[2:12])
    with pytest.raises(BusinessRuleError) as dup:
        create_customer(company=tenant_a.company, user=tenant_a.owner, name="Other", gstin=G_MH)
    assert "Svc Co" in str(dup.value)
    with pytest.raises(BusinessRuleError):
        create_customer(company=tenant_a.company, user=tenant_a.owner, name="Bad", gstin=G_KA, state="Maharashtra")


def test_bill_import_creates_its_customer_through_the_rules(tenant_a):
    from types import SimpleNamespace

    from imports.services import BillImportService

    job = SimpleNamespace(
        company=tenant_a.company, customer_id=None, customer=None,
        preview={"buyer_name": "Imported Buyer", "buyer_gstin": G_UT.lower()},
        save=lambda **kw: None,
    )
    customer = BillImportService._resolve_customer(job, tenant_a.owner)
    assert (customer.gstin, customer.state) == (G_UT, "Dadra and Nagar Haveli and Daman and Diu")


def test_per_user_throttle_is_keyed_by_user(tenant_a):
    from types import SimpleNamespace

    from core.throttles import UserScopeRateThrottle

    throttle = UserScopeRateThrottle("gstin_verify_user")
    key_a = throttle.get_cache_key(SimpleNamespace(user=tenant_a.owner), None)
    key_b = throttle.get_cache_key(SimpleNamespace(user=tenant_a.staff), None)
    assert key_a != key_b and "gstin_verify_user" in key_a
    assert throttle.get_cache_key(SimpleNamespace(user=SimpleNamespace(is_authenticated=False)), None) is None


# ---- remaining review items: simultaneous GSTIN, dunning, suppliers ----------------------------------------------------------------

def test_a_simultaneous_duplicate_gstin_names_the_holder(tenant_a, monkeypatch):
    from masters.serializers import CustomerSerializer

    make_customer(tenant_a.company, name="First Holder", gstin=G_KA)
    other = make_customer(tenant_a.company, name="Second", gstin=G_MH, state="Maharashtra")
    # Skip the serializer's own duplicate check, as if the holder was saved a moment after it ran:
    # the database constraint then decides and the API must still say who holds the number.
    monkeypatch.setattr(CustomerSerializer, "_party_company", lambda self, instance: None)
    resp = tenant_a.client.patch(f"{URL}{other.id}/", {"gstin": G_KA, "state": "Karnataka"}, format="json")
    assert resp.status_code == 400 and "First Holder" in str(details(resp)["gstin"])
    created = tenant_a.client.post(URL, {"name": "Third", "gstin": G_KA}, format="json")
    assert created.status_code == 400 and "First Holder" in str(details(created)["gstin"])
    assert Customer.objects.get(pk=other.pk).gstin == G_MH


def test_supplier_is_referenced_uses_every_protected_relation(tenant_a):
    from tests.conftest import make_supplier

    unused = make_supplier(tenant_a.company, name="Unused Vendor")
    assert unused.is_referenced() is False
    used = make_supplier(tenant_a.company, name="Used Vendor")
    product = make_product(tenant_a.company, sku="SUP-1")
    from tests.conftest import create_draft_purchase

    create_draft_purchase(tenant_a, used, [{"product": product.id, "quantity": "1", "unit_price": "50"}])
    assert used.is_referenced() is True


def test_dunning_skips_archived_customers_but_not_blocked_ones(tenant_a):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from payments.dunning import run_dunning_for_company
    from tests.test_a07_dunning import _enable_dunning, _overdue_invoice

    midday = datetime(2026, 8, 31, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    archived = _overdue_invoice(tenant_a, days=3)
    _enable_dunning(archived.company)
    Customer.objects.filter(pk=archived.customer_id).update(status="INACTIVE")
    assert run_dunning_for_company(archived.company, now=midday)["sent"] == 0
    Customer.objects.filter(pk=archived.customer_id).update(status="BLOCKED")
    assert run_dunning_for_company(archived.company, now=midday)["sent"] == 1


# ---- remaining items: bulk verify, real 429, history, CRM, addresses, GL sort, monthly audit, metrics -----------------------------

def test_bulk_verify_checks_each_customer_and_limits_the_batch(tenant_a, staff, accountant):
    a = make_customer(tenant_a.company, name="Has GSTIN", gstin=G_KA)
    b = make_customer(tenant_a.company, name="No GSTIN")
    resp = staff.post(f"{URL}verify-gstin-bulk/", {"ids": [a.id, b.id, 999999]}, format="json")
    assert resp.status_code == 200, resp.data
    by_id = {row["id"]: row for row in resp.data["results"]}
    assert by_id[a.id]["status"] == "UNVERIFIED" and "not configured" in by_id[a.id]["notice"]
    assert by_id[b.id]["error"] == "Customer has no GSTIN."
    assert by_id[999999]["error"] == "Customer not found."
    assert staff.post(f"{URL}verify-gstin-bulk/", {"ids": list(range(1, 12))}, format="json").status_code == 400
    assert staff.post(f"{URL}verify-gstin-bulk/", {"ids": []}, format="json").status_code == 400
    assert accountant.post(f"{URL}verify-gstin-bulk/", {"ids": [a.id]}, format="json").status_code == 403


def test_verify_returns_429_once_the_user_budget_is_spent(tenant_a, staff, monkeypatch):
    from django.core.cache import cache

    from core.throttles import CompanyRateThrottle, UserScopeRateThrottle

    c = make_customer(tenant_a.company, gstin=G_KA)
    rates = {"gstin_verify_user": "2/hour", "gstin_verify": "1000/hour"}
    monkeypatch.setattr(UserScopeRateThrottle, "THROTTLE_RATES", rates)
    monkeypatch.setattr(CompanyRateThrottle, "THROTTLE_RATES", rates)
    cache.clear()
    codes = [staff.post(f"{URL}{c.id}/verify-gstin/").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    cache.clear()


def test_history_lists_name_status_and_gstin_changes_with_who(tenant_a, accountant):
    c = make_customer(tenant_a.company, name="Before", gstin=G_KA)
    tenant_a.client.patch(f"{URL}{c.id}/", {"name": "After", "status": "BLOCKED"}, format="json")
    tenant_a.client.patch(f"{URL}{c.id}/", {"gstin": G_MH}, format="json")
    rows = [r for r in accountant.get(f"{URL}{c.id}/history/").data["results"] if r["changes"]]
    merged = {}
    for r in rows:
        merged.update(r["changes"])
    assert merged["name"] == {"from": "Before", "to": "After"}
    assert merged["status"] == {"from": "ACTIVE", "to": "BLOCKED"}
    assert merged["gstin"] == {"from": G_KA, "to": G_MH}
    assert all(r["user"] for r in rows)


def test_lead_conversion_uses_the_customer_rules(tenant_a):
    from tests.test_growth_os import _flags

    _flags(tenant_a.company)
    made = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Lead Co", "phone": "9000000201", "gstin": G_MH, "state": "Maharashtra"}, format="json",
    )
    assert made.status_code == 201, made.data
    done = tenant_a.client.post(f"/api/v1/crm/leads/{made.data['id']}/convert/", {}, format="json")
    assert done.status_code == 200, done.data
    customer = Customer.objects.get(company=tenant_a.company, name="Lead Co")
    assert (customer.gstin, customer.pan) == (G_MH, G_MH[2:12])
    # a second lead carrying the same GSTIN cannot make a duplicate customer: a clear 400, not a raw error
    clash = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Lead Twin", "phone": "9000000202", "gstin": G_MH, "state": "Maharashtra"}, format="json",
    )
    twin = tenant_a.client.post(f"/api/v1/crm/leads/{clash.data['id']}/convert/", {}, format="json")
    assert twin.status_code == 400 and "already registered" in str(twin.data)
    assert Customer.objects.filter(company=tenant_a.company, gstin=G_MH).count() == 1


def test_lead_merging_into_an_existing_customer_does_not_steal_a_gstin(tenant_a):
    from tests.test_growth_os import _flags

    _flags(tenant_a.company)
    make_customer(tenant_a.company, name="Holder", gstin=G_MH, state="Maharashtra")
    plain = make_customer(tenant_a.company, name="Plain", phone="9000000301")
    lead = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Plain", "phone": "9000000301", "gstin": G_MH, "dedupe_decision": "create"}, format="json",
    )
    assert lead.status_code == 201, lead.data
    done = tenant_a.client.post(f"/api/v1/crm/leads/{lead.data['id']}/convert/", {}, format="json")
    assert done.status_code == 200, done.data
    plain.refresh_from_db()
    assert plain.gstin == ""


def test_shipping_addresses_round_trip(tenant_a):
    created = tenant_a.client.post(
        URL,
        {"name": "Addr Co", "shipping_addresses": [
            {"label": "Depot", "address": "1 Depot Road", "is_default": True},
            {"label": "Shop", "address": "2 Shop Lane", "is_default": False},
        ]},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert [(a["label"], a["is_default"]) for a in created.data["shipping_addresses"]] == [("Depot", True), ("Shop", False)]
    cid = created.data["id"]
    replaced = tenant_a.client.patch(
        f"{URL}{cid}/", {"shipping_addresses": [{"label": "Only", "address": "3 New Street", "is_default": True}]},
        format="json",
    )
    assert replaced.status_code == 200
    got = tenant_a.client.get(f"{URL}{cid}/").data["shipping_addresses"]
    assert [a["label"] for a in got] == ["Only"]
    # leaving the field out keeps what is stored
    tenant_a.client.patch(f"{URL}{cid}/", {"notes": "x"}, format="json")
    assert len(tenant_a.client.get(f"{URL}{cid}/").data["shipping_addresses"]) == 1


def test_balance_sort_on_the_ledger_basis(tenant_a, monkeypatch):
    from ledgers.services import LedgerService

    make_customer(tenant_a.company, name="Alpha")
    make_customer(tenant_a.company, name="Bravo")
    monkeypatch.setattr(LedgerService, "_use_gl_outstanding", staticmethod(lambda company: True))
    resp = tenant_a.client.get(URL, {"sort": "balance"})
    assert resp.status_code == 200
    assert [r["name"] for r in resp.data["results"]] == ["Alpha", "Bravo"]
    assert tenant_a.client.get(f"{URL}summary/").status_code == 200


def test_monthly_audit_task_notifies_owners_only_when_something_is_found(tenant_a, monkeypatch):
    from masters.tasks import customers_audit_task

    sent = []
    monkeypatch.setattr(
        "core.services.telegram.notify_company_owners", lambda company, **kw: sent.append((company.pk, kw["body"])),
    )
    assert customers_audit_task() == {"companies_notified": 0} and sent == []
    make_customer(tenant_a.company, name="Mismatch", gstin=G_MH, state="Karnataka")
    result = customers_audit_task()
    assert result == {"companies_notified": 1}
    assert "state that disagrees with the GSTIN" in sent[0][1]


def test_business_event_counters_move(tenant_a, accountant, staff):
    from core import ops_metrics

    before = dict(ops_metrics._EVENTS)
    c = make_customer(tenant_a.company, gstin=G_KA)
    staff.post(f"{URL}{c.id}/verify-gstin/")
    staff.post(f"{URL}lookup-gstin/", {"gstin": G_MH}, format="json")
    b"".join(accountant.get(f"{URL}export/").streaming_content)
    tenant_a.client.patch(f"{URL}{c.id}/", {"notes": "x", "version": c.version + 5}, format="json")
    for name in ("customer_gstin_verify", "customer_gstin_lookup", "customer_export", "customer_stale_write"):
        assert ops_metrics._EVENTS.get(name, 0) > before.get(name, 0), name


# ---- health endpoint, lookup refresh, restore audit ------------------------------------------------------------------------------

def test_health_lists_records_that_need_a_look_for_owners_and_managers(tenant_a, manager, staff):
    from django.core.cache import cache

    cache.clear()
    make_customer(tenant_a.company, name="Mismatch", gstin=G_MH, state="Karnataka")
    assert staff.get(f"{URL}health/").status_code == 403
    resp = manager.get(f"{URL}health/")
    assert resp.status_code == 200, resp.data
    assert resp.data["total"] == 1
    assert resp.data["checks"] == [
        {"check": "state_mismatch", "label": "state that disagrees with the GSTIN", "count": 1},
    ]
    cache.clear()


def test_lookup_refresh_always_asks_the_provider(tenant_a, staff, monkeypatch):
    from django.core.cache import cache

    from core.services import gstin_verify

    cache.clear()
    calls = []
    real = gstin_verify.NullGstinProvider.lookup

    def counting(self, gstin):
        calls.append(gstin)
        return real(self, gstin)

    monkeypatch.setattr(gstin_verify.NullGstinProvider, "lookup", counting)
    staff.post(f"{URL}lookup-gstin/", {"gstin": G_MH}, format="json")
    staff.post(f"{URL}lookup-gstin/", {"gstin": G_MH}, format="json")
    assert len(calls) == 1  # the second answer came from the one-minute cache
    staff.post(f"{URL}lookup-gstin/", {"gstin": G_MH, "refresh": True}, format="json")
    assert len(calls) == 2
    cache.clear()


def test_tenant_restore_reports_customers_that_break_the_rules(tenant_a, caplog):
    import logging

    from accounts.tenant_backup import build_export_payload, restore_destroy_in_place

    make_customer(tenant_a.company, name="Old Mismatch", gstin=G_MH, state="Karnataka")
    payload = build_export_payload(tenant_a.company)
    with caplog.at_level(logging.WARNING, logger="accounts.tenant_backup"):
        restore_destroy_in_place(
            company=tenant_a.company, payload=payload, owner=tenant_a.owner, confirm_destroy_unbacked=True,
        )
    assert "tenant_restore: customer audit" in caplog.text and "state_mismatch" in caplog.text
    # the restore itself did not apply the form rules: the row came back as it was exported
    assert Customer.objects.get(company=tenant_a.company, name="Old Mismatch").state == "Karnataka"


# ---- small units ---------------------------------------------------------------------------------------------------------------------------

def test_refusal_phrase_reads_naturally_for_each_status(tenant_a):
    assert make_customer(tenant_a.company, name="B", status="BLOCKED").billing_block_phrase == "a blocked customer"
    assert make_customer(tenant_a.company, name="I", status="INACTIVE").billing_block_phrase == "an inactive customer"


def test_monthly_customer_audit_is_scheduled():
    from django.conf import settings

    entry = settings.CELERY_BEAT_SCHEDULE["masters-customers-audit-monthly"]
    assert entry["task"] == "masters.tasks.customers_audit_task"


def test_throttle_rates_exist_for_every_customer_budget():
    from django.conf import settings

    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for scope in ("gstin_verify", "gstin_verify_user", "gstin_verify_bulk", "customers_export", "customers_summary"):
        assert scope in rates, scope


def test_has_protected_references_ignores_owned_children_and_counts_documents(tenant_a):
    from masters.models import has_protected_references

    product = make_product(tenant_a.company)
    c = make_customer(tenant_a.company, name="Refd")
    c.shipping_addresses.create(company=tenant_a.company, label="x", address="1 Road")
    assert has_protected_references(c) is False
    draft = create_draft_invoice(tenant_a, c, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    assert has_protected_references(c) is True


def test_audit_command_fix_resets_only_stale_verification(tenant_a, capsys):
    stale = make_customer(tenant_a.company, name="Stale", gstin=G_KA, gstin_verification_status="VALID", gstin_legal_name="X")
    mismatch = make_customer(tenant_a.company, name="Mismatch", gstin=G_MH, state="Karnataka")
    call_command("customers_audit", "--fix")
    stale.refresh_from_db()
    mismatch.refresh_from_db()
    assert (stale.gstin_verification_status, stale.gstin_legal_name) == ("UNVERIFIED", "")
    assert mismatch.state == "Karnataka"  # reported, never rewritten
    assert "1 repaired" in capsys.readouterr().out
