"""GST Guard v2 — the real pre-submission validator wired into completion.

Covers ``reporting.gst_guard`` (validate_document, its individual check
functions, and the OWNER/MANAGER override) plus its wiring into
``SalesService.complete()`` (regular + POS invoices) and
``SalesNotesService.complete_credit_note()``.

Distinct from ``test_gst_guard.py``, which covers the older read-time
COMP-006 buyer-GSTIN checks inside ``build_gst_health()`` — a different
surface with fixtures that don't fit this write-time completion-path guard.
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from core.models import AuditEvent
from core.services.gstin_verify import GstinLookupResult
from masters.models import HsnRate
from reporting.gst_guard import (
    GstGuardBlocked,
    _check_buyer_gstin,
    _check_hsn_master,
    _check_rate_consistency,
    document_has_gst_guard_override,
    validate_document,
)
from reporting.gst_health import gstin_format_and_status
from sales.models import SalesCreditNote, SalesCreditNoteItem, SalesInvoice, SalesItem
from sales.notes_services import SalesNotesService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

VALID_GSTIN = "29AAAAA0000A1ZY"
BAD_CHECKSUM = "29AAAAA0000A1Z6"


def _enable_guard(company):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_GST_GUARD"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _prep_intra_state(tenant):
    tenant.company.state = "Karnataka"
    tenant.company.save(update_fields=["state"])


def _make_membership_client(tenant, *, role, can_create_sales=False, suffix="x"):
    user = User.objects.create_user(
        email=f"{role.lower()}-{suffix}@{tenant.company.id}.test",
        password="StrongPass123!",
        full_name=f"{role.title()} {suffix}",
    )
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=role, can_create_sales=can_create_sales,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


# ---------------------------------------------------------------------------
# Unit tests: individual check functions
# ---------------------------------------------------------------------------


def test_check_buyer_gstin_blank_is_clean():
    assert _check_buyer_gstin("", {}) == []


@pytest.mark.django_db
def test_check_buyer_gstin_bad_checksum_is_blocking():
    issues = _check_buyer_gstin(BAD_CHECKSUM, {})
    assert len(issues) == 1
    assert issues[0].code == "GSTIN_CHECKSUM_INVALID"
    assert "checksum" in issues[0].message.lower()


@pytest.mark.django_db
def test_check_buyer_gstin_inactive_status_is_blocking(monkeypatch):
    class Live:
        def lookup(self, gstin):
            return GstinLookupResult(
                gstin=gstin, legal_name="", status="CANCELLED",
                state_code="29", taxpayer_type="", raw={},
            )

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", lambda: Live())
    issues = _check_buyer_gstin(VALID_GSTIN, {})
    assert len(issues) == 1
    assert issues[0].code == "GSTIN_STATUS_INACTIVE"
    assert "CANCELLED" in issues[0].message


@pytest.mark.django_db
def test_check_buyer_gstin_valid_gstin_is_clean(monkeypatch):
    class Live:
        def lookup(self, gstin):
            return GstinLookupResult(
                gstin=gstin, legal_name="", status="VALID",
                state_code="29", taxpayer_type="", raw={},
            )

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", lambda: Live())
    assert _check_buyer_gstin(VALID_GSTIN, {}) == []


def test_check_buyer_gstin_reuses_gst_health_shared_function(monkeypatch):
    """Must not reimplement the checksum/status decision — it delegates to the
    exact function gst_health._buyer_gstin_guard uses (shared, one place)."""
    calls = []
    real = gstin_format_and_status

    def spy(gstin, cache):
        calls.append(gstin)
        return real(gstin, cache)

    monkeypatch.setattr("reporting.gst_guard.gstin_format_and_status", spy)
    _check_buyer_gstin(BAD_CHECKSUM, {})
    assert calls == [BAD_CHECKSUM]


@pytest.mark.django_db
def test_check_hsn_master_no_rows_is_warning():
    result = _check_hsn_master("999999", date(2026, 1, 1))
    assert result is not None
    severity, issue = result
    assert severity == "warning"
    assert issue.code == "HSN_NOT_IN_MASTER"


@pytest.mark.django_db
def test_check_hsn_master_date_out_of_range_is_blocking():
    # 554433 is not in the seeded starter HSN table (unlike common codes such
    # as 1905) -- this row is the only one that can match.
    HsnRate.objects.create(
        hsn_sac="554433", rate=Decimal("18"), valid_from=date(2020, 1, 1),
        valid_to=date(2020, 12, 31), version="v1",
    )
    result = _check_hsn_master("554433", date(2026, 1, 1))
    assert result is not None
    severity, issue = result
    assert severity == "blocking"
    assert issue.code == "HSN_RATE_DATE_INVALID"


@pytest.mark.django_db
def test_check_hsn_master_date_in_range_is_clean():
    HsnRate.objects.create(
        hsn_sac="554433", rate=Decimal("18"), valid_from=date(2020, 1, 1),
        valid_to=None, version="v1",
    )
    assert _check_hsn_master("554433", date(2026, 1, 1)) is None


@pytest.mark.django_db
def test_check_hsn_master_blank_hsn_is_none():
    assert _check_hsn_master("", date(2026, 1, 1)) is None


@pytest.mark.django_db
def test_check_rate_consistency_no_history_is_clean(tenant_a):
    assert _check_rate_consistency(
        tenant_a.company, "1905", Decimal("18"), date(2026, 1, 1)
    ) is None


@pytest.mark.django_db
def test_check_rate_consistency_matching_history_is_clean(tenant_a):
    product = make_product(tenant_a.company, sku="RC-0", hsn_code="1905", gst_rate="18")
    customer = make_customer(tenant_a.company)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        invoice_type="GST", invoice_date=date(2026, 1, 1), number="RC-INV-0",
        taxable_total=Decimal("100"), grand_total=Decimal("118"),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="1905",
        taxable_amount=Decimal("100"),
    )
    assert _check_rate_consistency(
        tenant_a.company, "1905", Decimal("18"), date(2026, 2, 1)
    ) is None


@pytest.mark.django_db
def test_check_rate_consistency_mismatch_is_warning(tenant_a):
    product = make_product(tenant_a.company, sku="RC-1", hsn_code="1905", gst_rate="18")
    customer = make_customer(tenant_a.company)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        invoice_type="GST", invoice_date=date(2026, 1, 1), number="RC-INV-1",
        taxable_total=Decimal("100"), grand_total=Decimal("118"),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="1905",
        taxable_amount=Decimal("100"),
    )
    issue = _check_rate_consistency(tenant_a.company, "1905", Decimal("12"), date(2026, 2, 1))
    assert issue is not None
    assert issue.code == "GST_RATE_INCONSISTENT"
    assert "1905" in issue.message


@pytest.mark.django_db
def test_check_rate_consistency_never_flags_price_only_differences(tenant_a):
    """Rate consistency is about the GST%, never the unit price / discount /
    price list / UOM — those are normal business variation."""
    product = make_product(tenant_a.company, sku="RC-price", hsn_code="1905", gst_rate="18")
    customer = make_customer(tenant_a.company)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        invoice_type="GST", invoice_date=date(2026, 1, 1), number="RC-INV-price",
        taxable_total=Decimal("100"), grand_total=Decimal("118"),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("250"), gst_rate=Decimal("18"), hsn_code="1905",
        taxable_amount=Decimal("250"), discount_percent=Decimal("10"),
    )
    # Same GST% as history (18%), wildly different unit price/discount -- clean.
    assert _check_rate_consistency(
        tenant_a.company, "1905", Decimal("18"), date(2026, 2, 1)
    ) is None


@pytest.mark.django_db
def test_check_rate_consistency_ignores_overridden_lines(tenant_a):
    product = make_product(tenant_a.company, sku="RC-2", hsn_code="1905", gst_rate="18")
    customer = make_customer(tenant_a.company)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        invoice_type="GST", invoice_date=date(2026, 1, 1), number="RC-INV-2",
        taxable_total=Decimal("100"), grand_total=Decimal("118"),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="1905",
        taxable_amount=Decimal("100"), rate_override=True,
    )
    # The only history row is an acknowledged rate_override -- excluded from
    # "recent rates", so it must not seed a false mismatch either way.
    assert _check_rate_consistency(
        tenant_a.company, "1905", Decimal("12"), date(2026, 2, 1)
    ) is None


@pytest.mark.django_db
def test_check_rate_consistency_is_tenant_scoped(tenant_a, tenant_b):
    product = make_product(tenant_a.company, sku="RC-3", hsn_code="1905", gst_rate="18")
    customer = make_customer(tenant_a.company)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        invoice_type="GST", invoice_date=date(2026, 1, 1), number="RC-INV-3",
        taxable_total=Decimal("100"), grand_total=Decimal("118"),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="1905",
        taxable_amount=Decimal("100"),
    )
    # tenant_b has no history at all for this HSN -- must never see tenant_a's rows.
    assert _check_rate_consistency(
        tenant_b.company, "1905", Decimal("12"), date(2026, 2, 1)
    ) is None


# ---------------------------------------------------------------------------
# validate_document(): combined behaviour, direct model construction
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_validate_document_missing_hsn_on_b2b_line_is_blocking(tenant_a):
    product = make_product(tenant_a.company, sku="VD-1", hsn_code="", gst_rate="18")
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.DRAFT,
        invoice_type="GST", invoice_date=date(2026, 1, 1),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="",
        taxable_amount=Decimal("100"),
    )
    result = validate_document(inv)
    assert any(i.code == "HSN_MISSING" for i in result.blocking)


@pytest.mark.django_db
def test_validate_document_missing_hsn_on_b2c_line_is_not_flagged(tenant_a):
    """B2C and composition invoices still get rate/HSN checks, but a missing
    HSN is only ever blocking for a B2B line (spec item 2)."""
    product = make_product(tenant_a.company, sku="VD-2", hsn_code="", gst_rate="18")
    customer = make_customer(tenant_a.company, gstin="")
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.DRAFT,
        invoice_type="GST", invoice_date=date(2026, 1, 1),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="",
        taxable_amount=Decimal("100"),
    )
    result = validate_document(inv)
    assert not any(i.code == "HSN_MISSING" for i in result.blocking)
    assert not result.blocking


@pytest.mark.django_db
def test_validate_document_hsn_digit_length_insufficient_is_blocking(tenant_a):
    product = make_product(tenant_a.company, sku="VD-3", hsn_code="19", gst_rate="18")
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.DRAFT,
        invoice_type="GST", invoice_date=date(2026, 1, 1),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="19",
        taxable_amount=Decimal("100"),
    )
    result = validate_document(inv)
    assert any(i.code == "HSN_DIGITS_INSUFFICIENT" for i in result.blocking)


@pytest.mark.django_db
def test_validate_document_bad_gstin_is_blocking_regardless_of_hsn(tenant_a):
    product = make_product(tenant_a.company, sku="VD-4", hsn_code="190500", gst_rate="18")
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.DRAFT,
        invoice_type="GST", invoice_date=date(2026, 1, 1),
    )
    SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="190500",
        taxable_amount=Decimal("100"),
    )
    result = validate_document(inv)
    assert any(i.code == "GSTIN_CHECKSUM_INVALID" for i in result.blocking)


@pytest.mark.django_db
def test_document_has_gst_guard_override_false_by_default(tenant_a):
    customer = make_customer(tenant_a.company)
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.DRAFT,
        invoice_type="GST", invoice_date=date(2026, 1, 1),
    )
    assert document_has_gst_guard_override(inv) is False


# ---------------------------------------------------------------------------
# Integration: wired into SalesService.complete() via the real API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_good_invoice_completes_cleanly(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    HsnRate.objects.create(
        hsn_sac="1905", rate=Decimal("18"), valid_from=date(2020, 1, 1),
        valid_to=None, version="v1",
    )
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN, state="Karnataka")
    product = make_product(tenant_a.company, sku="GOOD-1", hsn_code="1905", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    assert resp.data.get("gst_guard_warnings") == []


@pytest.mark.django_db
def test_validate_document_does_not_requery_per_line_for_a_repeated_hsn(
    tenant_a, django_assert_max_num_queries,
):
    """Regression for a fixed N+1: an invoice with several lines on the same
    HSN must hit the HSN-master and rate-consistency tables once per unique
    HSN, not once per line. 10 lines, same HSN, same rate -> validate_document
    itself should not scale with line count.
    """
    _prep_intra_state(tenant_a)
    HsnRate.objects.create(
        hsn_sac="1905", rate=Decimal("18"), valid_from=date(2020, 1, 1),
        valid_to=None, version="v1",
    )
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN, state="Karnataka")
    product = make_product(tenant_a.company, sku="MANY-1", hsn_code="1905", gst_rate="18")
    add_stock(tenant_a, product, "50")
    draft = create_draft_invoice(
        tenant_a, customer,
        [
            {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}
            for _ in range(10)
        ],
    )
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    # 10 lines sharing one HSN: a small constant number of queries regardless
    # of line count (company/customer/items load, plus exactly one HSN-master
    # query and one rate-consistency query for the single distinct HSN) — if
    # this regresses to one query per line, this bound fails long before 10.
    with django_assert_max_num_queries(6):
        result = validate_document(invoice)
    assert result.blocking == []
    assert result.warning == []


@pytest.mark.django_db
def test_bad_gstin_blocks_completion(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="BADG-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 400, resp.data
    err = resp.data.get("error") or resp.data
    assert err.get("code") == "gst_guard_blocked"
    details = err.get("details") or {}
    assert any(i.get("code") == "GSTIN_CHECKSUM_INVALID" for i in details.get("blocking", []))
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.DRAFT


@pytest.mark.django_db
def test_missing_hsn_b2b_blocks_completion(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN, state="Karnataka")
    product = make_product(tenant_a.company, sku="NOHSN-1", hsn_code="", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 400, resp.data
    err = resp.data.get("error") or resp.data
    assert err.get("code") == "gst_guard_blocked"
    details = err.get("details") or {}
    assert any(i.get("code") == "HSN_MISSING" for i in details.get("blocking", []))


@pytest.mark.django_db
def test_hsn_not_in_master_completes_with_warning(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN, state="Karnataka")
    # No HsnRate row seeded for this HSN anywhere -- an incomplete master.
    product = make_product(tenant_a.company, sku="NOMASTER-1", hsn_code="654321", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    warnings = resp.data.get("gst_guard_warnings") or []
    assert any(w.get("code") == "HSN_NOT_IN_MASTER" for w in warnings)
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.COMPLETED


@pytest.mark.django_db
def test_hsn_rate_date_out_of_range_blocks(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    # 554433 (and its 4-digit prefix 5544) is not in the seeded starter HSN
    # table, so this expired row is the only match -- full control.
    HsnRate.objects.create(
        hsn_sac="554433", rate=Decimal("18"), valid_from=date(2015, 1, 1),
        valid_to=date(2015, 12, 31), version="expired",
    )
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN, state="Karnataka")
    product = make_product(tenant_a.company, sku="EXPIRED-1", hsn_code="554433", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        invoice_date="2026-01-01",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 400, resp.data
    err = resp.data.get("error") or resp.data
    details = err.get("details") or {}
    assert any(i.get("code") == "HSN_RATE_DATE_INVALID" for i in details.get("blocking", []))


@pytest.mark.django_db
def test_rate_inconsistent_completes_with_warning(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN, state="Karnataka")
    # 554433 is not in the seeded starter HSN table, so the master never
    # normalizes the line's rate -- the mismatch below is genuine.
    product = make_product(tenant_a.company, sku="RATEFLIP-1", hsn_code="554433", gst_rate="18")
    add_stock(tenant_a, product, "10")
    # First invoice at 18% -- becomes "recent history" for this HSN.
    first = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    ok1 = tenant_a.client.post(f"/api/v1/sales/invoices/{first['id']}/complete/")
    assert ok1.status_code == 200, ok1.data

    # Second invoice, same HSN, a different (still allowed) GST% -- warning only.
    second = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "12"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{second['id']}/complete/")
    assert resp.status_code == 200, resp.data
    warnings = resp.data.get("gst_guard_warnings") or []
    assert any(w.get("code") == "GST_RATE_INCONSISTENT" for w in warnings)
    assert SalesInvoice.objects.get(pk=second["id"]).status == SalesInvoice.Status.COMPLETED


@pytest.mark.django_db
def test_owner_can_override_blocking_and_audit_trail_recorded(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="OVERRIDE-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert blocked.status_code == 400, blocked.data

    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"gst_guard_override_reason": "Confirmed GSTIN with customer over phone"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    assert invoice.status == SalesInvoice.Status.COMPLETED
    assert invoice.gst_guard_override_reason == "Confirmed GSTIN with customer over phone"
    assert invoice.gst_guard_overridden_by_id is not None
    assert invoice.gst_guard_overridden_at is not None
    assert AuditEvent.objects.filter(
        company=tenant_a.company,
        entity_type="SalesInvoice",
        entity_id=str(invoice.pk),
        description__icontains="GST Guard override",
    ).exists()


@pytest.mark.django_db
def test_manager_can_override_blocking(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="MGROVERRIDE-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    _user, manager_client = _make_membership_client(
        tenant_a, role=CompanyUser.Role.MANAGER, can_create_sales=True, suffix="mgr1",
    )
    resp = manager_client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"gst_guard_override_reason": "Manager approved"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.COMPLETED


@pytest.mark.django_db
def test_non_owner_manager_cannot_override_blocking(tenant_a):
    """A SALES_STAFF member with can_create_sales (able to complete invoices at
    all) still cannot override GST Guard -- override is OWNER/MANAGER only."""
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="STAFFOVR-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    _user, staff_client = _make_membership_client(
        tenant_a, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True, suffix="staff1",
    )
    resp = staff_client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"gst_guard_override_reason": "I promise it's fine"},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    err = resp.data.get("error") or resp.data
    assert err.get("code") == "gst_guard_blocked"
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.DRAFT


@pytest.mark.django_db
def test_flag_off_bypasses_gst_guard_entirely(tenant_a):
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="FLAGOFF-1", hsn_code="", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    assert resp.data.get("gst_guard_warnings") in (None, [])


@pytest.mark.django_db
def test_pos_checkout_is_gated_the_same_way(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="POS-GUARD-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")
    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
    }
    blocked = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert blocked.status_code == 400, blocked.data
    err = blocked.data.get("error") or blocked.data
    assert err.get("code") == "gst_guard_blocked"
    # No draft invoice survives -- pos-checkout is one atomic transaction.
    assert not SalesInvoice.objects.filter(company=tenant_a.company, customer=customer).exists()


@pytest.mark.django_db
def test_credit_note_completion_is_gated_the_same_way(tenant_a):
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin="", state="Karnataka")
    product = make_product(tenant_a.company, sku="CN-GUARD-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data

    # Now the customer's GSTIN turns out to be bad -- the note picks it up
    # via the invoice's completion-time filing_party_gstin fallback.
    customer.gstin = BAD_CHECKSUM
    customer.save(update_fields=["gstin"])

    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": draft["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data

    resp = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 400, resp.data
    err = resp.data.get("error") or resp.data
    assert err.get("code") == "gst_guard_blocked"
    assert SalesCreditNote.objects.get(pk=cn.data["id"]).status == SalesCreditNote.Status.DRAFT

    # OWNER override completes it and leaves an audit trail, same as invoices.
    ok = tenant_a.client.post(
        f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/",
        {"gst_guard_override_reason": "Confirmed with customer"},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    note = SalesCreditNote.objects.get(pk=cn.data["id"])
    assert note.status == SalesCreditNote.Status.COMPLETED
    assert note.gst_guard_override_reason == "Confirmed with customer"
    assert AuditEvent.objects.filter(
        company=tenant_a.company,
        entity_type="SalesCreditNote",
        entity_id=str(note.pk),
        description__icontains="GST Guard override",
    ).exists()


@pytest.mark.django_db
def test_complete_credit_note_direct_service_raises_typed_exception(tenant_a):
    """Service-level: complete_credit_note raises GstGuardBlocked (catchable),
    not a generic error, for a caller that isn't going through the API."""
    _enable_guard(tenant_a.company)
    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="CN-DIRECT-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")

    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        invoice_type="GST", invoice_date=date(2026, 1, 1), number="CN-DIRECT-SRC-1",
        filing_party_gstin="", taxable_total=Decimal("100"), grand_total=Decimal("118"),
    )
    src_item = SalesItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("100"), gst_rate=Decimal("18"), hsn_code="190500",
        taxable_amount=Decimal("100"),
    )
    note = SalesCreditNote.objects.create(
        company=tenant_a.company, customer=customer, sales_invoice=inv,
        status=SalesCreditNote.Status.DRAFT, note_date=date(2026, 1, 5),
        taxable_total=Decimal("100"), grand_total=Decimal("118"),
    )
    SalesCreditNoteItem.objects.create(
        company=tenant_a.company, credit_note=note, product=product, source_item=src_item,
        quantity=Decimal("1"), unit_price=Decimal("100"), gst_rate=Decimal("18"),
        hsn_code="190500", taxable_amount=Decimal("100"),
    )
    with pytest.raises(GstGuardBlocked) as exc_info:
        SalesNotesService.complete_credit_note(note, tenant_a.owner)
    assert exc_info.value.result.has_blocking


@pytest.mark.django_db
def test_trial_plan_alone_blocks_bad_gstin_owner_override_and_staff(tenant_a):
    """The only GST Guard grant is the trial plan. Company JSON stays empty."""
    from billing.services import ensure_register_trial, trial_plan_modules
    from core.services.feature_flags import flag_enabled

    ensure_register_trial(tenant_a.company)
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    if hasattr(tenant_a.company, "_feature_flags_cache"):
        del tenant_a.company._feature_flags_cache
    assert trial_plan_modules()["ENABLE_GST_GUARD"] is True
    assert flag_enabled(tenant_a.company, "ENABLE_GST_GUARD") is True
    assert tenant_a.company.feature_flags == {}

    _prep_intra_state(tenant_a)
    customer = make_customer(tenant_a.company, gstin=BAD_CHECKSUM, state="Karnataka")
    product = make_product(tenant_a.company, sku="TRIAL-GUARD-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert blocked.status_code == 400, blocked.data
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.DRAFT

    completed = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"gst_guard_override_reason": "Confirmed GSTIN with the buyer"},
        format="json",
    )
    assert completed.status_code == 200, completed.data
    assert SalesInvoice.objects.get(pk=draft["id"]).status == SalesInvoice.Status.COMPLETED

    staff_draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    _user, staff_client = _make_membership_client(
        tenant_a, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True, suffix="trialstaff",
    )
    staff = staff_client.post(
        f"/api/v1/sales/invoices/{staff_draft['id']}/complete/",
        {"gst_guard_override_reason": "Staff cannot override"},
        format="json",
    )
    assert staff.status_code == 400, staff.data
    err = staff.data.get("error") or staff.data
    assert err.get("code") == "gst_guard_blocked"
    assert SalesInvoice.objects.get(pk=staff_draft["id"]).status == SalesInvoice.Status.DRAFT

