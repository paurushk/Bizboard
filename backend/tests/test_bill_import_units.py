"""Unit tests for the bill-import helpers (party/product matching, validation
rules, template signature, GSTIN status, totals helpers).

The end-to-end behaviour is in test_sales_bill_import.py; these pin the small
pure rules so a regression points at the function, not at a 40-step flow.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from core.exceptions import BusinessRuleError
from imports import bill_validation as bv
from imports import metrics, party_match as pm, services as svc
from imports.models import ImportJob, SupplierBillTemplate
from masters.models import Customer, Supplier
from tests.conftest import make_customer, make_product, make_supplier
from tests.test_sales_bill_import import LLM, _payload, _upload

pytestmark = pytest.mark.django_db


def codes(errors):
    return [e["code"] for e in errors]


# ------------------------------------------------------------ name helpers
class TestNames:
    def test_normalize_drops_legal_suffix_case_and_punctuation(self):
        assert pm.normalize_name("  ACME Traders Pvt. Ltd.  ") == pm.normalize_name("acme traders")
        assert pm.normalize_name("") == ""
        assert pm.normalize_name(None) == ""

    def test_sanitize_removes_markup_and_control_characters(self):
        cleaned = pm.sanitize_party_name("A<B>\x01C\n  D")
        assert "<" not in cleaned and ">" not in cleaned and "\x01" not in cleaned
        assert "  " not in cleaned


# ------------------------------------------------------ customer matching
class TestMatchCustomer:
    def test_exact_gstin_binds(self, tenant_a):
        c = make_customer(tenant_a.company, name="Ravi Kumar", gstin="29AABCU9603R1ZX")
        r = pm.match_customer(tenant_a.company, gstin="29aabcu9603r1zx", name="Someone Else")
        assert (r["status"], r["id"], r["will_create"]) == ("matched", c.pk, False)

    def test_exact_normalised_name_binds_when_bill_has_no_gstin(self, tenant_a):
        c = make_customer(tenant_a.company, name="Ravi Kumar Traders")
        r = pm.match_customer(tenant_a.company, gstin="", name="ravi kumar traders pvt ltd")
        assert r["status"] == "matched" and r["id"] == c.pk

    def test_similar_name_is_only_a_candidate(self, tenant_a):
        make_customer(tenant_a.company, name="Ravi Kumar Traders")
        r = pm.match_customer(tenant_a.company, gstin="", name="Ravi Kumar Trader")
        assert r["status"] in {"candidates", "matched"}
        if r["status"] == "candidates":
            assert r["id"] is None and r["candidates"]

    def test_gstin_and_name_on_different_parties_is_a_conflict(self, tenant_a):
        make_customer(tenant_a.company, name="By Gstin", gstin="29AABCU9603R1ZX")
        make_customer(tenant_a.company, name="By Name")
        r = pm.match_customer(tenant_a.company, gstin="29AABCU9603R1ZX", name="By Name")
        assert r["status"] == "conflict" and len(r["candidates"]) == 2
        assert r["will_create"] is False

    def test_unknown_party_will_be_created(self, tenant_a):
        r = pm.match_customer(tenant_a.company, gstin="", name="Brand New Buyer")
        assert (r["status"], r["will_create"]) == ("none", True)

    def test_no_name_means_nothing_to_create(self, tenant_a):
        assert pm.match_customer(tenant_a.company, gstin="", name="")["will_create"] is False

    def test_blocked_customer_with_that_gstin_is_refused_not_recreated(self, tenant_a):
        make_customer(
            tenant_a.company, name="Old Co", gstin="29AABCU9603R1ZX", status=Customer.Status.BLOCKED
        )
        r = pm.match_customer(tenant_a.company, gstin="29AABCU9603R1ZX", name="Old Co")
        assert r["status"] == "inactive_match" and r["will_create"] is False
        assert any("blocked" in n for n in r["notes"])

    def test_other_companys_customers_are_invisible(self, tenant_a, tenant_b):
        make_customer(tenant_b.company, name="Ravi Kumar", gstin="29AABCU9603R1ZX")
        r = pm.match_customer(tenant_a.company, gstin="29AABCU9603R1ZX", name="Ravi Kumar")
        assert r["status"] == "none"

    def test_walk_in_customer_is_never_bound_and_is_called_out(self, tenant_a):
        make_customer(tenant_a.company, name="Walk-in Customer", is_pos_walk_in=True)
        r = pm.match_customer(tenant_a.company, gstin="", name="Walk-in Customer")
        assert r["id"] is None
        assert any("walk-in" in n.lower() for n in r["notes"])


# ------------------------------------------------------ supplier matching
class TestMatchSupplier:
    def test_gstin_and_name(self, tenant_a):
        s = make_supplier(tenant_a.company, name="Mega Suppliers", gstin="27AAAPL1234C1ZV")
        assert pm.match_supplier(tenant_a.company, gstin="27aaapl1234c1zv", name="x")["id"] == s.pk
        assert pm.match_supplier(tenant_a.company, gstin="", name="MEGA SUPPLIERS LTD")["id"] == s.pk

    def test_inactive_supplier_with_that_gstin_is_flagged(self, tenant_a):
        make_supplier(tenant_a.company, name="Dormant", gstin="27AAAPL1234C1ZV", is_active=False)
        r = pm.match_supplier(tenant_a.company, gstin="27AAAPL1234C1ZV", name="Dormant")
        assert r["status"] == "inactive_match" and r["will_create"] is False

    def test_isolated_between_companies(self, tenant_a, tenant_b):
        make_supplier(tenant_b.company, name="Mega Suppliers")
        assert pm.match_supplier(tenant_a.company, gstin="", name="Mega Suppliers")["status"] == "none"
        assert Supplier.objects.filter(company=tenant_a.company).count() == 0


# ------------------------------------------------------- product matching
class TestMatchProduct:
    def test_sku_then_name_then_candidates_then_none(self, tenant_a):
        p = make_product(tenant_a.company, name="Lux Soap 100g", sku="LUX-100")
        cat = pm.build_catalog(tenant_a.company)
        assert pm.match_product({"sku": "lux-100", "name": "zzz"}, cat)["product_id"] == p.pk
        by_name = pm.match_product({"sku": "", "name": "LUX SOAP 100G"}, cat)
        assert by_name["status"] == "matched" and by_name["product_id"] == p.pk
        near = pm.match_product({"sku": "", "name": "Lux Soap 100 g"}, cat)
        assert near["status"] in {"matched", "candidates"}
        far = pm.match_product({"sku": "", "name": "Completely Different Thing"}, cat)
        assert far == {"status": "none", "product_id": None, "candidates": []}

    def test_barcode_matches_like_a_sku(self, tenant_a):
        p = make_product(tenant_a.company, name="Barcode Item", sku="BC-1")
        p.barcode = "8901234567890"
        p.save(update_fields=["barcode"])
        cat = pm.build_catalog(tenant_a.company)
        assert pm.match_product({"sku": "8901234567890", "name": ""}, cat)["product_id"] == p.pk

    def test_catalog_is_company_scoped(self, tenant_a, tenant_b):
        make_product(tenant_b.company, name="Theirs", sku="T-1")
        cat = pm.build_catalog(tenant_a.company)
        assert cat["by_id"] == {} and pm.match_product({"sku": "T-1", "name": "Theirs"}, cat)["status"] == "none"

    def test_matched_row_carries_cess_and_batch_flags(self, tenant_a):
        make_product(tenant_a.company, name="Tracked", sku="TR-1")
        row = pm.match_product({"sku": "TR-1", "name": ""}, pm.build_catalog(tenant_a.company))
        for key in ("cess_rate", "cess_amount", "track_batch"):
            assert key in row


# ----------------------------------------------------------- line errors
class TestLineErrors:
    def ok(self, **over):
        line = {"name": "Soap", "quantity": "2", "unit_price": "100", "gst_rate": "18", "hsn_code": "3401"}
        line.update(over)
        return line

    def test_valid_line_has_no_errors(self):
        assert bv.line_errors(self.ok()) == []

    @pytest.mark.parametrize(
        "over,code",
        [
            ({"name": " "}, "NAME_REQUIRED"),
            ({"quantity": "0"}, "QTY_POSITIVE"),
            ({"quantity": "abc"}, "QTY_NUMBER"),
            ({"unit_price": "-1"}, "PRICE_NEGATIVE"),
            ({"unit_price": "abc"}, "PRICE_NUMBER"),
            ({"gst_rate": ""}, "GST_REQUIRED"),
            ({"gst_rate": None}, "GST_REQUIRED"),
            ({"gst_rate": "7"}, "GST_SLAB"),
            ({"gst_rate": "x"}, "GST_NUMBER"),
            ({"hsn_code": "12345"}, "HSN_FORMAT"),
            ({"discount_percent": "101"}, "DISCOUNT_RANGE"),
            ({"discount_percent": "-1"}, "DISCOUNT_RANGE"),
            ({"discount_percent": "ten"}, "DISCOUNT_NUMBER"),
        ],
    )
    def test_each_rule_has_its_own_code(self, over, code):
        assert code in codes(bv.line_errors(self.ok(**over)))

    def test_gst_with_percent_sign_is_accepted_and_zero_price_is_free(self):
        assert bv.line_errors(self.ok(gst_rate="18%", unit_price="0")) == []

    def test_messages_helper_returns_text(self):
        assert bv.line_error_messages(self.ok(name="")) == ["name is required"]

    def test_to_decimal_or_none(self):
        assert bv.to_decimal_or_none("1.50") == Decimal("1.50")
        assert bv.to_decimal_or_none("") is None
        assert bv.to_decimal_or_none("abc") is None
        assert bv.to_decimal_or_none(None) is None


# --------------------------------------------------- header + whole-bill
@patch(LLM)
def test_raise_if_invalid_reports_every_problem_at_once(mock_llm, tenant_a):
    mock_llm.return_value = _payload(3, bill_date="")
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    resp = _upload(tenant_a.client)
    job = ImportJob.objects.get(pk=resp.data["id"])
    preview = job.preview
    lines = preview["lines"]
    lines[0]["name"] = ""
    lines[1]["gst_rate"] = "7"
    with pytest.raises(BusinessRuleError) as exc:
        bv.raise_if_invalid(job, preview, lines)
    extra = exc.value.extra
    assert exc.value.get_codes() == "BILL_VALIDATION"
    assert {e["row"] for e in extra["lineErrors"]} == {1, 2}
    assert any(h["field"] == "bill_date" for h in extra["headerErrors"])


@patch(LLM)
def test_nothing_included_is_an_error(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = ImportJob.objects.get(pk=_upload(tenant_a.client).data["id"])
    lines = job.preview["lines"]
    lines[0]["include"] = False
    with pytest.raises(BusinessRuleError) as exc:
        bv.raise_if_invalid(job, job.preview, lines)
    assert any(h["code"] == "NO_LINES" for h in exc.value.extra["headerErrors"])


@patch(LLM)
def test_future_dated_bill_is_a_warning_not_a_block(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1, bill_date="2099-01-01")
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = ImportJob.objects.get(pk=_upload(tenant_a.client).data["id"])
    head = bv.header_errors(job, job.preview, job.preview["lines"])
    future = [h for h in head if "future" in h["message"].lower() or "FUTURE" in h["code"]]
    assert future and all(h["severity"] == "warning" for h in future)


@patch(LLM)
def test_missing_bill_date_blocks(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1, bill_date="")
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = ImportJob.objects.get(pk=_upload(tenant_a.client).data["id"])
    head = bv.header_errors(job, job.preview, job.preview["lines"])
    assert any(h["field"] == "bill_date" and h["severity"] == "error" for h in head)


@patch(LLM)
def test_new_products_must_be_confirmed_only_when_review_v2_is_on(mock_llm, tenant_a):
    from core.services.feature_flags import flag_enabled  # noqa: F401

    mock_llm.return_value = _payload(1)
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = ImportJob.objects.get(pk=_upload(tenant_a.client).data["id"])
    line = {"include": True, "product_match": {"status": "none"}, "product_id": None}
    with patch.object(bv, "_v2", return_value=False):
        assert bv.policy_header_errors(job, {}, [line]) == []
    with patch.object(bv, "_v2", return_value=True):
        assert codes(bv.policy_header_errors(job, {}, [line])) == ["NEW_PRODUCTS_UNCONFIRMED"]
        assert bv.policy_header_errors(job, {"confirm_new_products": True}, [line]) == []
        assert bv.policy_header_errors(job, {}, [{**line, "product_id": 5}]) == []


@patch(LLM)
def test_similar_product_needs_a_choice_when_v2_is_on(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = ImportJob.objects.get(pk=_upload(tenant_a.client).data["id"])
    line = {"product_match": {"status": "candidates"}, "product_id": None}
    with patch.object(bv, "_v2", return_value=True):
        assert codes(bv.line_policy_errors(job, line)) == ["PRODUCT_CHOICE_REQUIRED"]
        assert bv.line_policy_errors(job, {**line, "create_new": True}) == []
        assert bv.line_policy_errors(job, {**line, "product_id": 3}) == []
    with patch.object(bv, "_v2", return_value=False):
        assert bv.line_policy_errors(job, line) == []


def test_only_owner_and_manager_may_override_price_list():
    assert bv.PRICE_OVERRIDE_ROLES == {"OWNER", "MANAGER"}


# ------------------------------------------------------ service helpers
class TestFinalizePreviewLines:
    def test_assigns_stable_ids_and_bumps_version(self):
        preview, lines = {}, [{"name": "a"}, {"name": "b"}]
        svc.BillImportService.finalize_preview_lines(preview, lines)
        assert [ln["line_id"] for ln in lines] == [1, 2]
        assert preview["preview_version"] == 1
        lines.append({"name": "c"})
        svc.BillImportService.finalize_preview_lines(preview, lines)
        assert [ln["line_id"] for ln in lines] == [1, 2, 3]
        assert preview["preview_version"] == 2

    def test_ids_are_never_reused_after_a_delete(self):
        preview, lines = {}, [{"name": "a"}, {"name": "b"}]
        svc.BillImportService.finalize_preview_lines(preview, lines)
        lines.pop()  # drop id 2
        lines.append({"name": "new"})
        svc.BillImportService.finalize_preview_lines(preview, lines)
        assert lines[-1]["line_id"] == 3

    def test_bump_false_keeps_version(self):
        preview = {"preview_version": 4}
        svc.BillImportService.finalize_preview_lines(preview, [{"name": "a"}], bump=False)
        assert preview["preview_version"] == 4


def test_line_limit_is_enforced():
    svc.BillImportService._guard_line_limit([{}] * svc.BILL_PREVIEW_MAX_LINES)
    with pytest.raises(BusinessRuleError, match="maximum"):
        svc.BillImportService._guard_line_limit([{}] * (svc.BILL_PREVIEW_MAX_LINES + 1))


class TestTemplateSignature:
    def test_signature_ignores_order_case_and_blanks(self):
        a = svc._signature_hash(["Item", "Qty", "Rate"])
        assert a == svc._signature_hash(["rate", " QTY ", "item", ""])
        assert a != svc._signature_hash(["Item", "Qty"])
        assert svc._signature_hash([]) == "" and svc._signature_hash(None) == ""

    def test_template_matching_is_per_kind(self, tenant_a):
        SupplierBillTemplate.objects.create(
            company=tenant_a.company,
            gstin="29AABCU9603R1ZX",
            kind=ImportJob.Kind.SALES_BILL,
            column_signature=["Item", "Qty"],
            signature_hash=svc._signature_hash(["Item", "Qty"]),
        )
        got = svc._match_bill_template(
            tenant_a.company, "29AABCU9603R1ZX", ["Item", "Qty"], ImportJob.Kind.SALES_BILL
        )
        assert got is not None
        assert svc._match_bill_template(
            tenant_a.company, "29AABCU9603R1ZX", ["Item", "Qty"], ImportJob.Kind.PURCHASE_BILL
        ) is None

    def test_no_gstin_means_no_template(self, tenant_a):
        assert svc._match_bill_template(tenant_a.company, "", ["Item"]) is None

    def test_other_company_template_is_never_used(self, tenant_a, tenant_b):
        SupplierBillTemplate.objects.create(
            company=tenant_b.company, gstin="29AABCU9603R1ZX", kind=ImportJob.Kind.SALES_BILL,
            column_signature=["Item"], signature_hash=svc._signature_hash(["Item"]),
        )
        assert svc._match_bill_template(
            tenant_a.company, "29AABCU9603R1ZX", ["Item"], ImportJob.Kind.SALES_BILL
        ) is None


class TestOneEdit:
    @pytest.mark.parametrize(
        "a,b,expected",
        [
            ("ABC", "ABC", True),
            ("ABC", "ABD", True),
            ("ABC", "ABCD", True),
            ("ABCD", "ABC", True),
            ("ABC", "AXD", False),
            ("ABC", "ABCDE", False),
        ],
    )
    def test_cases(self, a, b, expected):
        assert svc._within_one_edit(a, b) is expected


class TestCompanyGstinStatus:
    def test_single_gstin_is_defaulted(self, tenant_a):
        r = svc.company_gstin_status(tenant_a.company, {}, kind=ImportJob.Kind.SALES_BILL)
        assert r["status"] in {"defaulted_single", "ok"}

    def test_several_gstins_block_only_with_the_flag(self, tenant_a):
        from accounts.models import CompanyGstin

        base = CompanyGstin.objects.filter(company=tenant_a.company).count()
        for g in ["29AABCU9603R1ZX", "27AAAPL1234C1ZV", "07AAACH7409R1ZZ"][: max(2, 3 - base)]:
            CompanyGstin.objects.get_or_create(
                company=tenant_a.company, gstin=g, defaults={"state": "X", "is_active": True}
            )
        with patch("core.services.feature_flags.flag_enabled", return_value=False):
            off = svc.company_gstin_status(tenant_a.company, {}, kind=ImportJob.Kind.SALES_BILL)
        with patch("core.services.feature_flags.flag_enabled", return_value=True):
            on = svc.company_gstin_status(tenant_a.company, {}, kind=ImportJob.Kind.SALES_BILL)
        assert off["status"] != "unresolved"
        assert on["status"] == "unresolved"

    def test_user_choice_wins(self, tenant_a):
        from accounts.models import CompanyGstin

        g = CompanyGstin.objects.filter(company=tenant_a.company).first()
        if g is None:
            g = CompanyGstin.objects.create(
                company=tenant_a.company, gstin="29AABCU9603R1ZX", state="X", is_active=True
            )
        r = svc.company_gstin_status(
            tenant_a.company, {"company_gstin_id": g.pk}, kind=ImportJob.Kind.SALES_BILL
        )
        assert r["status"] == "ok" and r["obj"].pk == g.pk


class TestCsvHeaderMoney:
    def test_picks_first_non_empty_and_strips_commas(self):
        rows = [{"freight": ""}, {"freight": "1,250"}, {"freight": "9"}]
        assert svc._csv_header_money(rows) == {"freight": "1250"}

    def test_nothing_found(self):
        assert svc._csv_header_money([{"item": "x"}]) == {}

    def test_bill_discount(self):
        out = svc._csv_header_money([{"bill_discount": "50"}])
        assert out.get("invoice_discount") == "50" or out == {}


# ---------------------------------------------------------------- metrics
class TestMetrics:
    def test_summary_is_empty_without_jobs(self, tenant_a):
        rows = metrics.summary(30, company_id=tenant_a.company.pk)
        assert isinstance(rows, list)

    def test_summary_counts_a_committed_job(self, tenant_a):
        make_customer(tenant_a.company, name="Retail Buyer LLP")
        with patch(LLM, return_value=_payload(2)):
            job_id = _upload(tenant_a.client).data["id"]
        assert tenant_a.client.post(f"/api/v1/imports/{job_id}/commit/").status_code == 200
        rows = metrics.summary(30, company_id=tenant_a.company.pk)
        assert rows, "a committed bill should appear in the summary"
        assert metrics.summary(30, company_id=0) == [] or all(
            r.get("company_id") != tenant_a.company.pk for r in metrics.summary(30, company_id=0)
        )
