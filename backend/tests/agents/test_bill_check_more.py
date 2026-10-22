"""Block D of the test plan: Bill Check against real goods receipts, protection-rule boundaries, edits and roles."""
# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)

import json
import uuid
from decimal import Decimal

import pytest

from agents import runner, services
from agents.catalog.bill_check import compare, context as ctx
from agents.enums import ProposalStatus, RunStatus, Trigger
from agents.models import AgentProposal
from core.services.llm_providers import fake
from masters.models import Supplier
from purchases.models import GoodsReceipt, GoodsReceiptItem, PurchaseInvoice, PurchaseOrder, PurchaseOrderItem
from tests.conftest import create_draft_purchase, make_product, make_supplier

from .test_bill_check import BASE, bc, bill_off_order, codes, d, key, run_for  # noqa: F401

pytestmark = pytest.mark.django_db


def grn_for(t, bill, qty, *, price="100", status=GoodsReceipt.Status.COMPLETED, product=None, order=None):
    grn = GoodsReceipt.objects.create(
        company=t.company, supplier=t.supplier, status=status, purchase_order=order, converted_purchase=bill,
        created_by=t.owner, updated_by=t.owner,
    )
    GoodsReceiptItem.objects.create(
        company=t.company, goods_receipt=grn, product=product or t.widget, quantity_received=Decimal(qty),
        quantity_accepted=Decimal(qty), unit_price=Decimal(price),
    )
    return grn


def plain_bill(t, qty="10", rate="100", number="PB1"):
    pur = create_draft_purchase(t, t.supplier, [{"product": t.widget.id, "quantity": qty, "unit_price": rate, "gst_rate": "0"}])
    PurchaseInvoice.objects.filter(pk=pur["id"]).update(supplier_bill_number=number)
    return PurchaseInvoice.objects.get(pk=pur["id"])


def findings(bill):
    return {f["code"]: f for f in compare.compare_bill(bill)["findings"]}


# --- goods receipts -----------------------------------------------------------------------------------
@pytest.mark.parametrize("billed,received,flag", [("10", "8", True), ("10", "12", True), ("10", "10", False)])
def test_quantity_against_the_accepted_receipt(bc, billed, received, flag):
    bill = plain_bill(bc, qty=billed)
    grn_for(bc, bill, received)
    assert ("QTY_VS_GRN" in codes(bill)) is flag


def test_received_goods_missing_from_the_bill(bc):
    bill = plain_bill(bc, qty="5")
    other = make_product(bc.company, name="Gadget", sku="BC-G", gst_rate="0")
    grn_for(bc, bill, "5")
    grn_for(bc, bill, "3", product=other)
    assert "GRN_NOT_BILLED" in codes(bill)


def test_rate_is_checked_against_the_receipt_when_there_is_no_order(bc):
    bill = plain_bill(bc, rate="130")
    grn_for(bc, bill, "10", price="100")
    assert "RATE_DIFF" in codes(bill)


def test_a_receipt_that_is_not_completed_is_ignored(bc):
    bill = plain_bill(bc, qty="10")
    grn_for(bc, bill, "2", status=GoodsReceipt.Status.DRAFT)
    assert "QTY_VS_GRN" not in codes(bill)


def test_several_receipts_are_added_together(bc):
    bill = plain_bill(bc, qty="10")
    grn_for(bc, bill, "6")
    grn_for(bc, bill, "4")
    assert "QTY_VS_GRN" not in codes(bill)


def test_no_order_and_no_receipt_means_nothing_to_compare(bc):
    assert codes(plain_bill(bc, rate="999")) == set()


def test_a_bill_with_a_receipt_has_no_missing_receipt_note(bc):
    bill = bill_off_order(bc, bill_rate="100")
    grn_for(bc, bill, "10", order=bill.source_orders.first())
    assert "NO_GRN" not in findings(bill)


# --- order lines --------------------------------------------------------------------------------------
def test_an_item_billed_but_not_on_the_order(bc):
    from purchases.models import PurchaseItem

    bill = bill_off_order(bc, bill_rate="100")
    extra = make_product(bc.company, name="Gadget", sku="BC-G2", gst_rate="0")
    PurchaseItem.objects.create(
        company=bc.company, invoice=bill, product=extra, quantity=Decimal("1"), unit_price=Decimal("5"), gst_rate=Decimal("0"),
    )
    assert "NOT_ON_PO" in codes(bill)


def test_either_of_two_agreed_rates_passes(bc):
    bill = bill_off_order(bc, bill_rate="110", po_rate="100")
    order = bill.source_orders.first()
    PurchaseOrderItem.objects.create(company=bc.company, purchase_order=order, product=bc.widget, quantity=Decimal("5"), unit_price=Decimal("110"), gst_rate=Decimal("0"))
    assert "RATE_DIFF" not in codes(bill)


# --- protection-rule boundaries -------------------------------------------------------------------------
@pytest.mark.invariant_skip("gl.ap_ties_to_documents", reason="purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
def test_duplicate_number_ignores_cancelled_bills_other_suppliers_and_case(bc):
    base = plain_bill(bc, number="Inv-77")
    PurchaseInvoice.objects.filter(pk=base.pk).update(status=PurchaseInvoice.Status.CANCELLED)
    twin = plain_bill(bc, number="INV-77")
    assert "DUPLICATE_BILL_NO" not in findings(twin)  # the earlier one was cancelled
    PurchaseInvoice.objects.filter(pk=base.pk).update(status=PurchaseInvoice.Status.COMPLETED)
    assert "DUPLICATE_BILL_NO" in findings(twin)  # case-insensitive
    other = make_supplier(bc.company, name="Other Supplier")
    PurchaseInvoice.objects.filter(pk=base.pk).update(supplier=other)
    assert "DUPLICATE_BILL_NO" not in findings(twin)


def _history(t, n, amount="1000"):
    for _ in range(n):
        PurchaseInvoice.objects.create(
            company=t.company, supplier=t.supplier, status=PurchaseInvoice.Status.COMPLETED,
            grand_total=Decimal(amount), number=f"HX{uuid.uuid4().hex[:6]}", created_by=t.owner, updated_by=t.owner,
        )


@pytest.mark.invariant_skip("gl.ap_ties_to_documents", "money.header_totals_identity", reason="documents are built through the ORM with header totals that do not match their lines; purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
@pytest.mark.parametrize("earlier,amount,flag", [(5, "99999", False), (6, "1000", False), (6, "1000.01", True), (10, "5000", True)])
def test_amount_high_boundary_and_history_floor(bc, earlier, amount, flag):
    bill = plain_bill(bc)
    _history(bc, earlier, "1000")
    PurchaseInvoice.objects.filter(pk=bill.pk).update(grand_total=Decimal(amount))
    assert ("AMOUNT_HIGH" in findings(PurchaseInvoice.objects.get(pk=bill.pk))) is flag


@pytest.mark.parametrize("value,flag", [(None, False), ("2026-04-01", True)])
def test_cancelled_gstin_needs_a_date(bc, value, flag):
    Supplier.objects.filter(pk=bc.supplier.pk).update(gstin_cancelled_on=value)
    assert ("GSTIN_CANCELLED" in findings(PurchaseInvoice.objects.get(pk=plain_bill(bc).pk))) is flag


# --- the draft ------------------------------------------------------------------------------------------
def two_difference_bill(t):
    bill = bill_off_order(t, bill_rate="120", bill_qty="12")
    return bill


def test_every_difference_appears_in_the_message_and_the_table(bc):
    bill = two_difference_bill(bc)
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill))
    assert {"RATE_DIFF", "QTY_OVER_PO"} <= codes(bill)
    text = p.payload["text"]
    assert "rate is 120.00" in text and "has 12" in text
    assert sum(1 for r in p.payload["rows"] if r["mismatch"]) == 2


def test_an_edited_message_is_kept_on_approve(bc):
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill_off_order(bc, bill_rate="120")))
    payload = json.loads(json.dumps(p.payload))
    payload["text"] = "Hi team, please recheck the Widget rate on this bill. Thanks."
    assert bc.client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": payload, "revision": 0}, format="json").status_code == 200
    p.refresh_from_db()
    r = bc.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": p.revision}, format="json", **key())
    assert r.status_code == 200 and d(r)["payload"]["text"].startswith("Hi team")


def test_an_edit_with_an_oversized_message_is_refused(bc):
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill_off_order(bc, bill_rate="120")))
    payload = json.loads(json.dumps(p.payload))
    payload["text"] = "x" * 2001
    assert bc.client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": payload, "revision": 0}, format="json").status_code == 400


def test_a_sweep_with_two_bills_never_uses_the_model(bc):
    bill_off_order(bc, bill_rate="120", number="M1")
    bill_off_order(bc, bill_rate="130", number="M2")
    fake.reset()
    run = services.create_run(company=bc.company, agent_kind="BILL_CHECK", trigger=Trigger.SCHEDULE, trigger_ref="sweep:m", user=bc.owner)
    run = runner.execute_run(run.pk)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True and fake.CALLS == []
    assert AgentProposal.objects.filter(run=run).count() == 2


def test_the_draft_is_cancelled_when_the_bill_is_completed_or_cancelled(bc):
    bill = bill_off_order(bc, bill_rate="120")
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill))
    assert ctx.still_open(bc.company, [p.dedupe_key, "OTHER:1"]) == {p.dedupe_key, "OTHER:1"}
    PurchaseInvoice.objects.filter(pk=bill.pk).update(status=PurchaseInvoice.Status.CANCELLED)
    assert ctx.still_open(bc.company, [p.dedupe_key]) == set()


def test_a_second_run_for_the_same_bill_returns_the_same_draft(bc):
    bill = bill_off_order(bc, bill_rate="120")
    first = AgentProposal.objects.get(run=run_for(bc, bill))
    run2 = run_for(bc, bill)
    assert run2.status == RunStatus.SUCCEEDED and AgentProposal.objects.filter(kind="SUPPLIER_QUERY").count() == 1
    assert AgentProposal.objects.get(kind="SUPPLIER_QUERY").pk == first.pk


# --- executor -------------------------------------------------------------------------------------------
def test_an_unrelated_edit_to_the_bill_keeps_the_draft_valid(bc):
    bill = bill_off_order(bc, bill_rate="120")
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill))
    PurchaseInvoice.objects.filter(pk=bill.pk).update(notes="checked by Ravi")
    r = bc.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key())
    assert r.status_code == 200


@pytest.mark.invariant_skip("gl.ap_ties_to_documents", reason="purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
def test_a_bill_completed_meanwhile_makes_the_draft_stale(bc):
    bill = bill_off_order(bc, bill_rate="120")
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill))
    PurchaseInvoice.objects.filter(pk=bill.pk).update(status=PurchaseInvoice.Status.COMPLETED)
    r = bc.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key())
    assert r.status_code == 409
    p.refresh_from_db()
    assert p.status == ProposalStatus.FAILED and p.failure_code == "STALE"


# --- roles ----------------------------------------------------------------------------------------------
def test_a_user_without_purchase_rights_cannot_prepare_or_approve(bc):
    bill = bill_off_order(bc, bill_rate="120")
    r = bc.staff_client.post(f"{BASE}/runs/", {"agent": "BILL_CHECK", "triggerRef": f"BILL_CHECK:{bill.pk}"}, format="json", **key())
    assert r.status_code in (400, 403)
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill))
    assert bc.staff_client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key()).status_code == 404
    assert PurchaseOrder.objects.count() == 1  # only the fixture's order; nothing was created
