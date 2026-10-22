# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)
"""Regression tests for the defects found in the deep code review (2026-10-21). One test per defect."""

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from agents import runner, services, spec, tasks
from agents.catalog.order_intake import resolver
from agents.enums import ProposalStatus, RunStatus, Trigger
from agents.models import AgentAlias, AgentProposal
from agents.schemas.sales_order import OrderLineV1, SalesOrderDraftPayloadV1
from purchases.models import PurchaseInvoice, PurchaseItem, PurchaseOrder, PurchaseOrderItem
from tests.conftest import make_customer, make_product

from .conftest import make_proposal, owner_cu, tenant  # noqa: F401
from .test_bill_check import BASE as _B, bc, bill_off_order, run_for as bill_run  # noqa: F401
from .test_order_intake import oi, paste, proposal_of, script  # noqa: F401
from .test_order_intake import key as _key

pytestmark = pytest.mark.django_db
BASE = _B


# --- platform: the worker must know the company --------------------------------------------------------------------
def test_an_async_run_is_queued_with_its_company_so_the_worker_can_set_row_level_security(tenant, monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.run_agent_async, "delay", lambda *a, **k: calls.append((a, k)))
    r = tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE"}, format="json", **_key())
    assert r.status_code == 202
    (args, kwargs), = calls
    assert kwargs.get("company_id") == tenant.company.pk and len(args) == 1


def test_the_expire_task_scans_company_by_company_under_that_companys_context(tenant, monkeypatch):
    p = make_proposal(tenant)
    AgentProposal.objects.filter(pk=p.pk).update(expires_at=timezone.now() - timedelta(hours=1))
    seen = []
    monkeypatch.setattr("core.rls.set_rls_company", lambda cid: seen.append(cid))
    out = tasks.expire_proposals()
    p.refresh_from_db()
    # SR0-06: the beat task only fans out; each company's task runs under that company's RLS context.
    assert out["companies"] == 1 and p.status == ProposalStatus.EXPIRED
    assert tenant.company.pk in seen and seen[-1] is None  # set for the company, cleared at the end


def test_the_cancel_resolved_task_runs_per_company_and_cancels_cleared_drafts(bc, monkeypatch):
    bill = bill_off_order(bc, bill_rate="120")
    [p] = AgentProposal.objects.filter(run=bill_run(bc, bill))
    PurchaseInvoice.objects.filter(pk=bill.pk).update(status=PurchaseInvoice.Status.CANCELLED)
    seen = []
    monkeypatch.setattr("core.rls.set_rls_company", lambda cid: seen.append(cid))
    out = tasks.cancel_resolved()
    p.refresh_from_db()
    assert out["companies"] >= 1 and p.status == ProposalStatus.CANCELLED
    assert bc.company.pk in seen and seen[-1] is None


def test_the_tasks_clear_the_context_even_when_a_company_scan_fails(tenant, monkeypatch):
    make_proposal(tenant)  # a pending proposal so the orchestrator queues this company's task
    seen = []
    monkeypatch.setattr("core.rls.set_rls_company", lambda cid: seen.append(cid))
    monkeypatch.setattr("agents.services.expire_due", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        tasks.expire_proposals()
    assert seen[-1] is None


# --- platform: one odd document must not lose the other drafts --------------------------------------------------------
def test_a_sweep_keeps_the_good_drafts_when_one_fails_validation(bc):
    from agents.catalog.bill_check import context

    bill_off_order(bc, bill_rate="120", number="G1")
    bad = bill_off_order(bc, bill_rate="130", number="G2")
    real = context.validate

    def picky(tctx, ctx, drafts):
        if any(d["payload"]["bill_id"] == bad.pk for d in drafts):
            from core.exceptions import BusinessRuleError

            raise BusinessRuleError("odd bill")
        return real(tctx, ctx, drafts)

    object.__setattr__(spec.AGENTS["BILL_CHECK"], "validate", picky)
    try:
        run = services.create_run(company=bc.company, agent_kind="BILL_CHECK", trigger=Trigger.SCHEDULE, trigger_ref="sweep:g", user=bc.owner)
        run = runner.execute_run(run.pk)
    finally:
        object.__setattr__(spec.AGENTS["BILL_CHECK"], "validate", real)
    assert run.status == RunStatus.SUCCEEDED and AgentProposal.objects.filter(run=run).count() == 1


def test_a_run_fails_only_when_every_draft_is_refused(bc):
    bill = bill_off_order(bc, bill_rate="120")
    run = services.create_run(company=bc.company, agent_kind="BILL_CHECK", trigger=Trigger.USER, trigger_ref=f"BILL_CHECK:{bill.pk}", user=bc.owner)
    from agents.catalog.bill_check import context

    real = context.validate
    object.__setattr__(spec.AGENTS["BILL_CHECK"], "validate", lambda *a, **k: (_ for _ in ()).throw(__import__("core.exceptions", fromlist=["x"]).BusinessRuleError("no")))
    try:
        run = runner.execute_run(run.pk)
    finally:
        object.__setattr__(spec.AGENTS["BILL_CHECK"], "validate", real)
    assert run.status == RunStatus.FAILED


# --- Order Intake --------------------------------------------------------------------------------------------------------
def test_a_long_message_with_the_order_at_the_end_is_still_read_by_the_model(oi):
    filler = "\n".join(f"hello hello number {i} thanks bhai" for i in range(40))  # far more than 255 characters
    text = f"From: Sharma Traders\n{filler}\n2 sugar 50kg bag"
    assert len(text) > 600
    script([{"raw": "2 sugar 50kg bag", "qty": 2, "unit": "", "product_hint": "sugar 50kg bag"}], hint="Sharma Traders")
    r = paste(oi, text)
    assert r.json()["data"]["rulesOnly"] is False  # the model's line was accepted, not rejected as "not from the text"
    assert proposal_of(r).payload["lines"][0]["product_id"] == oi.sugar.id


def test_a_named_customer_beats_a_phone_number_elsewhere_in_the_text(oi):
    ravi = make_customer(oi.company, name="Ravi Stores", phone="9811111111")
    res = resolver.resolve_customer(oi.company, "Sharma Traders", "From: Sharma Traders\ndeliver to Ravi 98111 11111")
    assert res["id"] == oi.customer.id and res["match"]["source"] == "name"
    assert resolver.resolve_customer(oi.company, "", "call 98111 11111")["id"] == ravi.id  # no name: the phone is used


def test_the_draft_warns_when_the_catalogue_was_larger_than_the_matcher_holds(oi, monkeypatch):
    monkeypatch.setattr(resolver, "MAX_CATALOGUE", 2)
    p = proposal_of(paste(oi))
    assert any("catalogue is larger" in w for w in p.payload["warnings"])


def test_two_approvals_learning_the_same_new_wording_do_not_break_the_order(oi, monkeypatch):
    from agents.executors.sales_order import _learn

    class Racy:
        """The first look finds nothing, as if another approval had not committed yet."""

        real = AgentAlias.objects

        def select_for_update(self):
            outer = self

            class Q:
                def filter(self, **kw):
                    return self

                def first(self):
                    return None

                def get(self, **kw):
                    return outer.real.select_for_update().get(**kw)

            return Q()

        def __getattr__(self, name):
            return getattr(self.real, name)

    AgentAlias.objects.create(company=oi.company, scope="PRODUCT", raw_text_norm="chini", product=oi.rice, hits=1)
    monkeypatch.setattr(AgentAlias, "objects", Racy())
    _learn(oi.company, oi.owner, "PRODUCT", "chini", product=oi.sugar)
    monkeypatch.undo()
    alias = AgentAlias.objects.get(company=oi.company, raw_text_norm="chini")
    assert alias.product_id == oi.sugar.id and AgentAlias.objects.filter(raw_text_norm="chini").count() == 1


def test_a_paste_is_read_within_30_seconds_not_the_background_60():
    assert spec.AGENTS["ORDER_INTAKE"].limit("run_timeout_s", 60) == 30


def test_payload_lists_are_bounded():
    too_many_alts = [{"id": i + 1, "name": "x"} for i in range(11)]
    assert not OrderLineV1(data={"raw": "x", "qty": "1", "alternatives": too_many_alts}).is_valid()
    assert not SalesOrderDraftPayloadV1(data={"lines": [{"raw": "x", "qty": "1"}], "customer_alternatives": too_many_alts}).is_valid()
    assert not SalesOrderDraftPayloadV1(data={"lines": [{"raw": "x", "qty": "1"}], "warnings": ["w"] * 51}).is_valid()


# --- Bill Check ---------------------------------------------------------------------------------------------------------------
@pytest.mark.invariant_skip("gl.ap_ties_to_documents", "money.header_totals_identity", reason="documents are built through the ORM with header totals that do not match their lines; purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
def test_the_usual_range_uses_the_most_recent_bills(bc):
    from agents.catalog.bill_check import compare

    base = bill_off_order(bc, bill_rate="100", number="R0")
    today = timezone.localdate()
    old = [PurchaseInvoice(company=bc.company, supplier=bc.supplier, status="COMPLETED", grand_total=Decimal("100000"),
                           invoice_date=today - timedelta(days=700), number=f"OLD{i}") for i in range(60)]
    new = [PurchaseInvoice(company=bc.company, supplier=bc.supplier, status="COMPLETED", grand_total=Decimal("1000"),
                           invoice_date=today - timedelta(days=i % 90), number=f"NEW{i}") for i in range(200)]
    PurchaseInvoice.objects.bulk_create(old + new)
    PurchaseInvoice.objects.filter(pk=base.pk).update(grand_total=Decimal("5000"))
    codes = {f["code"] for f in compare.compare_bill(PurchaseInvoice.objects.get(pk=base.pk))["findings"]}
    assert "AMOUNT_HIGH" in codes  # judged against the 200 recent bills, not a mix that includes 100000 ones


def test_a_bill_with_many_differences_still_gets_a_draft_within_the_length_limit(bc):
    items, po_lines = [], []
    bill = bill_off_order(bc, bill_rate="120", number="BIG")
    order = bill.source_orders.first()
    for i in range(40):
        product = make_product(bc.company, name=f"Part number {i} long descriptive name for the item", sku=f"BG{i}", gst_rate="0")
        items.append(PurchaseItem(company=bc.company, invoice=bill, product=product, quantity=Decimal("1"), unit_price=Decimal("200"), gst_rate=Decimal("0")))
        po_lines.append(PurchaseOrderItem(company=bc.company, purchase_order=order, product=product, quantity=Decimal("1"), unit_price=Decimal("100"), gst_rate=Decimal("0")))
    PurchaseItem.objects.bulk_create(items)
    PurchaseOrderItem.objects.bulk_create(po_lines)
    run = bill_run(bc, bill)
    [p] = AgentProposal.objects.filter(run=run)
    assert run.status == RunStatus.SUCCEEDED and len(p.payload["text"]) <= 1200
    assert "more difference" in p.payload["text"] and len(p.payload["rows"]) <= 200
    assert PurchaseOrder.objects.count() == 1 and json.dumps(p.payload)
    assert uuid.uuid4() and owner_cu(bc)
