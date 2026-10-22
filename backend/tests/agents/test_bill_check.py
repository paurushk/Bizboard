"""Bill Check Agent (R5): differences are facts, the draft is copy/share only, and nothing is blocked or changed."""

import json
import uuid
from decimal import Decimal

import pytest

from agents import runner, services, spec
from agents.catalog import bill_check as bc_pkg
from agents.catalog.bill_check import compare
from agents.enums import ProposalStatus, RunStatus, Trigger
from agents.models import AgentProposal
from core.exceptions import BusinessRuleError
from core.services.llm_providers import fake
from purchases.models import PurchaseInvoice, PurchaseOrder, PurchaseOrderItem
from purchases.services import PurchaseService
from tests.conftest import create_draft_purchase, make_product, make_supplier, make_tenant

from .conftest import enable_agents

pytestmark = pytest.mark.django_db
BASE = "/api/v1/agents"


def key():
    return {"HTTP_IDEMPOTENCY_KEY": f"k-{uuid.uuid4()}"}


def d(resp):
    return resp.json()["data"]


@pytest.fixture
def bc(db):
    added = "BILL_CHECK" not in spec.AGENTS
    if added:
        spec.register(bc_pkg.AGENT)
    t = make_tenant("bc1")
    enable_agents(t.company, "AGENT_BILL_CHECK")
    t.supplier = make_supplier(t.company, name="Mega Foods")
    t.widget = make_product(t.company, name="Widget", sku="BC-A", gst_rate="0", purchase_price="100")
    yield t
    if added:
        spec.unregister("BILL_CHECK")


def bill_off_order(t, *, bill_qty="10", bill_rate="120", po_qty="10", po_rate="100", bill_gst="0", po_gst="0", number="MF/2026/114"):
    pur = create_draft_purchase(t, t.supplier, [{"product": t.widget.id, "quantity": bill_qty, "unit_price": bill_rate, "gst_rate": bill_gst}])
    order = PurchaseOrder.objects.create(company=t.company, supplier=t.supplier, created_by=t.owner, updated_by=t.owner)
    PurchaseOrderItem.objects.create(
        company=t.company, purchase_order=order, product=t.widget, quantity=Decimal(po_qty), unit_price=Decimal(po_rate), gst_rate=Decimal(po_gst),
    )
    order.converted_purchase_id = pur["id"]
    order.save(update_fields=["converted_purchase"])
    PurchaseInvoice.objects.filter(pk=pur["id"]).update(supplier_bill_number=number)
    return PurchaseInvoice.objects.get(pk=pur["id"])


def run_for(t, bill):
    run = services.create_run(company=t.company, agent_kind="BILL_CHECK", trigger=Trigger.USER, trigger_ref=f"PURCHASE_BILL:{bill.pk}", user=t.owner)
    return runner.execute_run(run.pk)


def codes(bill):
    return {f["code"] for f in compare.compare_bill(bill)["findings"]} - {"NO_GRN"}  # no receipt is recorded in these fixtures


def test_rate_quantity_and_tax_differences_are_found(bc):
    assert codes(bill_off_order(bc, bill_rate="120")) == {"RATE_DIFF"}
    assert "QTY_OVER_PO" in codes(bill_off_order(bc, bill_qty="12", bill_rate="100", number="B2"))
    assert "GST_RATE_DIFF" in codes(bill_off_order(bc, bill_rate="100", bill_gst="18", number="B3"))
    assert codes(bill_off_order(bc, bill_rate="100", number="B4")) == set()


def test_a_bill_on_an_order_with_no_goods_receipt_is_noted_for_the_owner_only(bc):
    bill = bill_off_order(bc, bill_rate="100")
    [f] = [f for f in compare.compare_bill(bill)["findings"] if f["code"] == "NO_GRN"]
    assert f["to_supplier"] is False
    assert not AgentProposal.objects.filter(run=run_for(bc, bill)).exists()


def test_a_rate_inside_the_tolerance_is_clean(bc):
    assert codes(bill_off_order(bc, bill_rate="100.40")) == set()


def test_the_comparator_agrees_with_the_existing_three_way_match(bc):
    for rate, qty in (("120", "10"), ("100", "10"), ("100", "12"), ("100.4", "10"), ("99", "9")):
        bill = bill_off_order(bc, bill_rate=rate, bill_qty=qty, number=f"X{rate}{qty}")
        try:
            PurchaseService.match_bill_to_po(bill)
            blocked = False
        except BusinessRuleError:
            blocked = True
        flagged = bool({"RATE_DIFF", "QTY_OVER_PO", "QTY_VS_GRN", "NOT_ON_PO"} & codes(bill))
        assert flagged == blocked, (rate, qty)


@pytest.mark.invariant_skip("gl.ap_ties_to_documents", reason="purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
def test_protection_rules(bc):
    first = bill_off_order(bc, bill_rate="100", number="DUP-1")
    PurchaseInvoice.objects.filter(pk=first.pk).update(status=PurchaseInvoice.Status.COMPLETED)
    second = bill_off_order(bc, bill_rate="100", number="DUP-1")
    assert "DUPLICATE_BILL_NO" in codes(second)
    bc.supplier.gstin_cancelled_on = "2026-04-01"
    bc.supplier.save(update_fields=["gstin_cancelled_on"])
    assert "GSTIN_CANCELLED" in codes(PurchaseInvoice.objects.get(pk=second.pk))


@pytest.mark.invariant_skip("gl.ap_ties_to_documents", "money.header_totals_identity", reason="documents are built through the ORM with header totals that do not match their lines; purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
def test_amount_far_above_usual_needs_history_first(bc):
    base = bill_off_order(bc, bill_rate="100", number="H0")
    assert "AMOUNT_HIGH" not in codes(base)
    for i in range(7):
        PurchaseInvoice.objects.create(
            company=bc.company, supplier=bc.supplier, status=PurchaseInvoice.Status.COMPLETED,
            grand_total=Decimal("1000") + i, number=f"H{i + 1}", created_by=bc.owner, updated_by=bc.owner,
        )
    PurchaseInvoice.objects.filter(pk=base.pk).update(grand_total=Decimal("9000"))
    assert "AMOUNT_HIGH" in codes(PurchaseInvoice.objects.get(pk=base.pk))
    assert compare.p95([Decimal(i) for i in range(1, 101)]) == Decimal(95)


def test_the_draft_states_facts_cites_the_bill_and_changes_nothing(bc):
    bill = bill_off_order(bc, bill_rate="120")
    before = (bill.status, bill.grand_total, bill.items.count())
    run = run_for(bc, bill)
    assert run.status == RunStatus.SUCCEEDED
    [p] = AgentProposal.objects.filter(run=run)
    text = p.payload["text"]
    assert "Mega Foods" in text and "MF/2026/114" in text and "120.00" in text and "100.00" in text
    assert any(r["mismatch"] for r in p.payload["rows"]) and p.evidence[0]["id"] == bill.pk
    bill.refresh_from_db()
    assert (bill.status, bill.grand_total, bill.items.count()) == before


def test_a_clean_bill_gets_no_draft(bc):
    run = run_for(bc, bill_off_order(bc, bill_rate="100"))
    assert run.status == RunStatus.SUCCEEDED and not AgentProposal.objects.filter(run=run).exists()


def test_model_wording_is_accepted_only_if_numbers_and_tax_are_clean(bc):
    bill = bill_off_order(bc, bill_rate="120")
    good = "Hello Mega Foods, on bill MF/2026/114 the rate for Widget is 120.00 but our purchase order says 100.00. Widget: please check."
    fake.script("BILL_CHECK", step=1, response={"text": json.dumps({"text": good})})
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill))
    assert p.payload["text"] == good
    for bad in (good.replace("100.00", "95.00"), good + " You should claim the ITC on it.", "Short."):
        AgentProposal.objects.all().delete()
        fake.script("BILL_CHECK", step=1, response={"text": json.dumps({"text": bad})})
        run = run_for(bc, bill)
        [p] = AgentProposal.objects.filter(run=run)
        assert run.rules_only is True and p.payload["text"] != bad


def test_approve_is_copy_only_and_goes_stale_when_the_bill_changes(bc):
    bill = bill_off_order(bc, bill_rate="120")
    [p] = AgentProposal.objects.filter(run=run_for(bc, bill))
    ok = bc.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key())
    assert ok.status_code == 200 and d(ok)["resultRef"]["type"] == "supplier_query_shared"

    other = bill_off_order(bc, bill_rate="120", number="Z9")
    [q] = AgentProposal.objects.filter(run=run_for(bc, other))
    other.items.update(unit_price=Decimal("100.00"))
    stale = bc.client.post(f"{BASE}/proposals/{q.pk}/approve/", {"revision": 0}, format="json", **key())
    assert stale.status_code == 409
    q.refresh_from_db()
    assert q.status == ProposalStatus.FAILED and q.failure_code == "STALE"


@pytest.mark.invariant_skip("gl.ap_ties_to_documents", reason="purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
def test_a_completed_bill_is_not_a_target(bc):
    bill = bill_off_order(bc, bill_rate="120")
    PurchaseInvoice.objects.filter(pk=bill.pk).update(status=PurchaseInvoice.Status.COMPLETED)
    assert run_for(bc, bill).status == RunStatus.FAILED


def test_the_sweep_checks_every_draft_bill(bc):
    bill_off_order(bc, bill_rate="120", number="S1")
    bill_off_order(bc, bill_rate="100", number="S2")
    run = services.create_run(company=bc.company, agent_kind="BILL_CHECK", trigger=Trigger.SCHEDULE, trigger_ref="sweep:x", user=bc.owner)
    run = runner.execute_run(run.pk)
    assert run.rules_only is True and AgentProposal.objects.filter(run=run).count() == 1
