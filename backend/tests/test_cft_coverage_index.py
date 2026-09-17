"""Every CFT-NNN in CROSS_FLOW_TEST_CHECKLIST.md must be cited in FREEZE_SCOPE_COVERAGE.md
and in a test file (except named LIM / creds-blocked ids).

Stops a review-gap id from existing only as prose. Mapping is the close for
already-gated cases; dedicated gap tests live in test_cft_checklist.py and
test_cft_cross_flow.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = ROOT / "docs" / "CROSS_FLOW_TEST_CHECKLIST.md"
COVERAGE = ROOT / "docs" / "FREEZE_SCOPE_COVERAGE.md"
TESTS = ROOT / "backend" / "tests"
WEB = ROOT / "web"

CFT_RE = re.compile(r"CFT-(?:NID-)?\d+")

# Voice-entry is not in freeze; live gateway refund/MDR needs D3 credentials.
LIM_IDS = frozenset({"CFT-078", "CFT-093"})

# Already-gated ids: the named test function must still exist.
ALREADY_GATED = {
    "CFT-NID-01": "test_reporting_includes_returned_insights_exclude",
    "CFT-002": "test_wf01_sale_intrastate_full_chain",
    "CFT-003": "test_completed_invoice_audited_edit_allows_line_change",
    "CFT-004": "test_cancel_completed_sale_restores_stock",
    "CFT-005": "test_fully_returned_invoice_marked_returned",
    "CFT-009": "test_negative_stock_policy",
    "CFT-010": "test_cannot_complete_twice",
    "CFT-011": "test_wf19_pos_checkout",
    "CFT-013": "test_wf04_purchase_full_chain",
    "CFT-015": "test_wf05_purchase_return",
    "CFT-018": "test_wf_grn_cancel_reverses_received_stock",
    "CFT-019": "test_wf01_sale_intrastate_full_chain",
    "CFT-020": "test_partial_allocation_reduces_outstanding",
    "CFT-021": "test_bb_000651_unallocate_reopens_invoice_and_reverses_je",
    "CFT-022": "test_public_pay_shows_live_outstanding_after_return",
    "CFT-024": "test_partial_allocation_reduces_outstanding",
    "CFT-033": "test_wf01_sale_intrastate_full_chain",
    "CFT-034": "test_wf04_purchase_full_chain",
    "CFT-035": "test_wf03_sales_return",
    "CFT-036": "test_wf22_stock_adjustment_writeoff",
    "CFT-037": "test_wf21_stock_transfer_between_godowns",
    "CFT-039": "test_cr_016_duplicate_opening_stock_file_rejected",
    "CFT-041": "test_cr062_inventory_summary_uses_movements_and_flags_drift",
    "CFT-049": "test_wf01_sale_intrastate_full_chain",
    "CFT-051": "test_h9_price_amend_keeps_sale_peel_cogs",
    "CFT-055": "test_h9_price_amend_keeps_sale_peel_cogs",
    "CFT-074": "test_products_import",
    "CFT-075": "test_cr_016_duplicate_opening_stock_file_rejected",
    "CFT-076": "test_void_opening_stock_import_allows_reimport",
    "CFT-077": "test_duplicate_webhook_one_receipt",
    "CFT-079": "test_wf01_sale_intrastate_full_chain",
    "CFT-080": "test_wf02_sale_interstate_with_cess",
    "CFT-081": "test_wf56_composition_bill_of_supply",
    "CFT-083": "test_wf55_reverse_charge_purchase",
    "CFT-086": "test_discount_percent_over_100_rejected",
    "CFT-087": "test_wf34_tcs_on_sales_206c",
    "CFT-088": "test_wf35_tds_on_purchases_194q",
    "CFT-091": "test_wf39_advance_payment_on_account",
    "CFT-094": "test_wf40_bad_debt_writeoff",
    "CFT-095": "test_wf41_bank_statement_import_and_matching",
    "CFT-096": "test_g3_bank_statement_bare_recommit_does_not_duplicate_auto_matches",
    "CFT-097": "test_concurrent_invoice_numbering_no_duplicate",
    "CFT-101": "test_wf44_invoice_amendment_h9",
    "CFT-103": "test_completed_invoice_amend_requires_owner_confirm",
    "CFT-104": "test_wf58_plan_limits",
    "CFT-105": "test_cannot_retrieve_other_companys_invoice",
    "CFT-106": "test_gst_tax_invoice_pdf_text_snapshot",
    "CFT-108": "test_sales_register_export_csv_snapshot",
    "CFT-109": "test_concurrent_stock_oversell_blocked",
    "CFT-110": "test_concurrent_payment_over_allocation_blocked",
    "CFT-111": "test_wf51_idempotency_contract",
    "CFT-113": "test_wf06_quotation_to_invoice",
    "CFT-114": "test_cft_114_cancel_so_after_challan_does_not_orphan_reservation",
    "CFT-115": "test_cft_115_partial_quotation_convert_remainder_still_convertible",
    "CFT-116": "test_cft_116_live_irn_blocks_line_amend",
    "CFT-117": "test_auto_credit_hold_blocks_severe_overdue_customer_with_no_credit_limit",
    "CFT-118": "test_cft_118_hold_releases_after_return_or_pay_residual_dn_keeps_hold",
    "CFT-119": "test_cft_119_return_restores_same_batch_and_serial",
    "CFT-120": "test_cft_120_stale_amend_revision_conflicts",
}


def _checklist_ids() -> set[str]:
    return set(CFT_RE.findall(CHECKLIST.read_text(encoding="utf-8")))


def _test_blob() -> str:
    chunks = []
    for root in (TESTS, WEB):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            name = path.name.lower()
            if "test" not in name and not name.endswith(".spec.ts"):
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
    return "\n".join(chunks)


def test_every_cft_id_is_cited_in_freeze_scope_coverage():
    checklist = CHECKLIST.read_text(encoding="utf-8")
    coverage = COVERAGE.read_text(encoding="utf-8")
    ids = set(CFT_RE.findall(checklist))
    assert "CFT-001" in ids
    assert "CFT-125" in ids
    assert "CFT-NID-01" in ids
    missing = sorted(cid for cid in ids if cid not in coverage)
    assert missing == [], f"CFT ids not cited in FREEZE_SCOPE_COVERAGE.md: {missing}"


def test_already_gated_cft_functions_still_exist():
    blob = _test_blob()
    missing = sorted(fn for fn in ALREADY_GATED.values() if f"def {fn}(" not in blob and f"function {fn}" not in blob)
    # pytest names are Python `def`; frontend tests may use describe/it only.
    py_blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in TESTS.rglob("test_*.py")
    )
    missing = sorted({fn for fn in ALREADY_GATED.values() if f"def {fn}(" not in py_blob})
    assert missing == [], f"CFT gate functions missing: {missing}"


def test_every_cft_id_is_cited_in_a_test_file_or_named_gate():
    ids = _checklist_ids()
    blob = _test_blob()
    covered = set(ALREADY_GATED) | LIM_IDS
    missing = sorted(
        cid for cid in ids
        if cid not in covered and cid not in blob
    )
    assert missing == [], f"CFT ids with no test citation: {missing}"
