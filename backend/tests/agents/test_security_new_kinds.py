"""Block A of the test plan: tenancy, roles, switches, idempotency and text handling for the R3 to R5 proposal kinds."""
# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)

import json
import uuid

import pytest

from agents import runner, services
from agents.enums import Trigger
from agents.models import AgentProposal, AgentRun, AgentStep
from core.services.llm_providers import fake
from inventory.models import StockTransfer, Warehouse
from purchases.models import PurchaseInvoice, PurchaseOrder
from sales.models import SalesOrder
from tests.conftest import make_customer, make_product, make_supplier, make_tenant

from .conftest import enable_agents
from .test_bill_check import bc, bill_off_order, run_for as bill_run  # noqa: F401
from .test_inventory_risk import iv, short_item, sweep  # noqa: F401
from .test_order_intake import TEXT, oi, paste, proposal_of  # noqa: F401

pytestmark = pytest.mark.django_db
BASE = "/api/v1/agents"


def key():
    return {"HTTP_IDEMPOTENCY_KEY": f"k-{uuid.uuid4()}"}


def d(resp):
    return resp.json()["data"]


def patch(client, p, payload, revision=None):
    return client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": payload, "revision": p.revision if revision is None else revision}, format="json")


def approve(client, p):
    return client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": p.revision}, format="json", **key())


def foreign(slug):
    """Masters that belong to a different company."""
    t = make_tenant(slug)
    t.customer = make_customer(t.company, name="Foreign Co")
    t.product = make_product(t.company, name="Foreign item", sku="FRN1")
    t.supplier = make_supplier(t.company, name="Foreign Supplier")
    t.warehouse = Warehouse.objects.create(company=t.company, name="Foreign godown", code="FG")
    return t


def edited(p):
    return json.loads(json.dumps(p.payload))


# --- 1. ids from another company in an edited payload --------------------------------------------
def test_order_with_another_companys_product_or_customer_creates_nothing(oi):
    other = foreign("sec-o1")
    p = proposal_of(paste(oi))
    payload = edited(p)
    payload["lines"][0]["product_id"] = other.product.pk
    assert patch(oi.client, p, payload).status_code == 200  # the edit stores ids; the executor is the guard
    p.refresh_from_db()
    assert approve(oi.client, p).status_code in (400, 409)
    assert SalesOrder.objects.count() == 0

    p2 = proposal_of(paste(oi, TEXT + "\n1 extra"))
    payload = edited(p2)
    payload["customer_id"] = other.customer.pk
    assert patch(oi.client, p2, payload).status_code == 200
    p2.refresh_from_db()
    assert approve(oi.client, p2).status_code == 400
    assert SalesOrder.objects.count() == 0


def test_transfer_with_another_companys_ids_creates_nothing(iv):
    other = foreign("sec-i1")
    short_item(iv)
    p = AgentProposal.objects.get(run=sweep(iv), kind="STOCK_TRANSFER")
    for field, value in (("to_warehouse_id", other.warehouse.pk), ("from_warehouse_id", other.warehouse.pk)):
        payload = edited(p)
        payload[field] = value
        assert patch(iv.client, p, payload).status_code == 200
        p.refresh_from_db()
        assert approve(iv.client, p).status_code == 409
        p.refresh_from_db()
        assert StockTransfer.objects.count() == 0
        p = AgentProposal.objects.get(pk=p.pk)
        AgentProposal.objects.filter(pk=p.pk).update(status="PENDING", failure_code="", attempts=0)
        p.refresh_from_db()
    payload = edited(p)
    payload["lines"][0]["product_id"] = other.product.pk
    patch(iv.client, p, payload)
    p.refresh_from_db()
    assert approve(iv.client, p).status_code == 409 and StockTransfer.objects.count() == 0


def test_purchase_with_another_companys_supplier_or_product_creates_nothing(iv):
    other = foreign("sec-i2")
    short_item(iv)
    p = AgentProposal.objects.get(run=sweep(iv), kind="PURCHASE_REQUEST")
    payload = edited(p)
    payload["supplier_id"] = other.supplier.pk
    assert patch(iv.client, p, payload).status_code == 200
    p.refresh_from_db()
    assert approve(iv.client, p).status_code == 400 and PurchaseOrder.objects.count() == 0
    AgentProposal.objects.filter(pk=p.pk).update(status="PENDING", failure_code="", attempts=0)
    p.refresh_from_db()
    payload = edited(p)
    payload["lines"][0]["product_id"] = other.product.pk
    patch(iv.client, p, payload)
    p.refresh_from_db()
    assert approve(iv.client, p).status_code == 400 and PurchaseOrder.objects.count() == 0


def test_supplier_query_for_another_companys_bill_is_refused(bc):
    other = foreign("sec-b1")
    bill = bill_off_order(bc, bill_rate="120")
    [p] = AgentProposal.objects.filter(run=bill_run(bc, bill))
    payload = edited(p)
    other_bill = PurchaseInvoice.objects.create(company=other.company, supplier=other.supplier, created_by=other.owner, updated_by=other.owner)
    payload["bill_id"] = other_bill.pk
    assert patch(bc.client, p, payload).status_code == 200
    p.refresh_from_db()
    assert approve(bc.client, p).status_code == 409


# --- 2. a user without the right gets no access to any verb ---------------------------------------
def _staff_denied(client, p):
    assert client.get(f"{BASE}/proposals/{p.pk}/").status_code == 404
    assert client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": {}, "revision": 0}, format="json").status_code == 404
    for verb in ("approve", "retry", "reject", "cancel"):
        assert client.post(f"{BASE}/proposals/{p.pk}/{verb}/", {"revision": 0}, format="json", **key()).status_code == 404, verb
    p.refresh_from_db()
    assert p.status == "PENDING"


def test_staff_cannot_touch_order_drafts(oi):
    _staff_denied(oi.staff_client, proposal_of(paste(oi)))


def test_staff_cannot_touch_stock_or_purchase_drafts(iv):
    short_item(iv)
    for p in AgentProposal.objects.filter(run=sweep(iv)):
        _staff_denied(iv.staff_client, p)


def test_staff_cannot_touch_supplier_queries(bc):
    [p] = AgentProposal.objects.filter(run=bill_run(bc, bill_off_order(bc, bill_rate="120")))
    _staff_denied(bc.staff_client, p)


def test_staff_cannot_start_any_of_the_new_agents(oi, iv, bc):
    for agent, extra in (("ORDER_INTAKE", {"text": "2 sugar"}), ("INVENTORY_RISK", {}), ("BILL_CHECK", {"triggerRef": "BILL_CHECK:1"})):
        r = oi.staff_client.post(f"{BASE}/runs/", {"agent": agent, **extra}, format="json", **key())
        assert r.status_code in (400, 403), agent
    assert AgentRun.objects.count() == 0


def test_a_purchases_only_user_cannot_approve_a_stock_transfer(iv):
    from accounts.models import CompanyUser

    short_item(iv)
    cu = CompanyUser.objects.get(company=iv.company, user=iv.staff)
    cu.can_create_purchases = True
    cu.save()
    run_kinds = {p.kind: p for p in AgentProposal.objects.filter(run=sweep(iv))}
    assert approve(iv.staff_client, run_kinds["STOCK_TRANSFER"]).status_code == 404  # not visible: needs inventory rights
    assert approve(iv.staff_client, run_kinds["PURCHASE_REQUEST"]).status_code == 200


# --- 3. switches ------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["agent_flag_off", "master_off", "kill_switch"])
def test_pasting_when_agents_are_switched_off_is_refused(oi, settings, mode):
    if mode == "agent_flag_off":
        flags = dict(oi.company.feature_flags)
        flags["AGENT_ORDER_INTAKE"] = False
        oi.company.feature_flags = flags
    elif mode == "master_off":
        oi.company.feature_flags = {k: v for k, v in oi.company.feature_flags.items() if k != "ENABLE_AGENTS"}
    else:
        settings.AGENTS_GLOBAL_KILL = True
    oi.company.save()
    r = paste(oi)
    assert r.status_code == 403 and AgentRun.objects.count() == 0


# --- 4. other companies' runs and drafts ------------------------------------------------------------
def test_another_company_cannot_see_or_act_on_new_kind_drafts(oi, iv, bc):
    other = make_tenant("sec-x1")
    enable_agents(other.company, "AGENT_ORDER_INTAKE", "AGENT_INVENTORY_RISK", "AGENT_BILL_CHECK")
    short_item(iv)
    drafts = [proposal_of(paste(oi)), *AgentProposal.objects.filter(run=sweep(iv))]
    drafts += list(AgentProposal.objects.filter(run=bill_run(bc, bill_off_order(bc, bill_rate="120"))))
    assert len(drafts) >= 4
    for p in drafts:
        assert other.client.get(f"{BASE}/proposals/{p.pk}/").status_code == 404
        assert approve(other.client, p).status_code == 404
        assert patch(other.client, p, {}, 0).status_code == 404
    assert d(other.client.get(f"{BASE}/proposals/"))["results"] == []
    run = AgentRun.objects.first()
    assert other.client.get(f"{BASE}/runs/{run.pk}/").status_code == 404


# --- 5. replaying the same paste ---------------------------------------------------------------------
def test_the_same_idempotency_key_gives_the_same_run_and_one_draft(oi):
    k = key()
    body = {"agent": "ORDER_INTAKE", "text": TEXT}
    r1 = oi.client.post(f"{BASE}/runs/", body, format="json", **k)
    r2 = oi.client.post(f"{BASE}/runs/", body, format="json", **k)
    assert r1.status_code == r2.status_code == 200 and d(r1)["id"] == d(r2)["id"]
    assert AgentRun.objects.count() == 1 and AgentProposal.objects.count() == 1


def test_the_same_key_with_different_text_is_not_replayed(oi):
    k = key()
    r1 = oi.client.post(f"{BASE}/runs/", {"agent": "ORDER_INTAKE", "text": TEXT}, format="json", **k)
    r2 = oi.client.post(f"{BASE}/runs/", {"agent": "ORDER_INTAKE", "text": "From: Sharma Traders\n3 toor dal"}, format="json", **k)
    assert r1.status_code == 200 and r2.status_code in (400, 409, 422)


# --- 6. raw text is not stored and is scrubbed on the way to a model ------------------------------------
def test_pasted_text_is_never_stored_on_the_run_or_its_steps(oi):
    secret = "ZQX-SECRET-NOTE-7731"
    text = f"From: Sharma Traders\n2 sugar 50kg bag {secret}\ncall 98765 43210"
    r = paste(oi, text)
    assert r.status_code == 200
    blob = json.dumps(list(AgentRun.objects.values()), default=str) + json.dumps(list(AgentStep.objects.values()), default=str)
    assert secret not in blob and "98765" not in blob


def test_phone_numbers_are_masked_before_the_model_sees_the_text(oi):
    fake.reset()
    fake.script("ORDER_INTAKE", step=1, response={"text": json.dumps({"customer_hint": "", "lines": []}), "tokens_in": 5, "tokens_out": 5})
    paste(oi, "From: Sharma Traders\n2 sugar 50kg bag\ncall 98765 43210 or a@b.com")
    sent = json.dumps(fake.CALLS[0]["messages"])
    assert "98765 43210" not in sent and "a@b.com" not in sent and "9876543210" not in sent


def test_a_run_started_through_the_service_has_no_input_column_to_leak_text(oi):
    run = services.create_run(company=oi.company, agent_kind="ORDER_INTAKE", trigger=Trigger.USER, trigger_ref="TEXT:x", user=oi.owner)
    runner.execute_run(run.pk, {"text": "2 sugar"})
    run.refresh_from_db()
    assert "2 sugar" not in json.dumps({k: str(v) for k, v in vars(run).items() if not k.startswith("_")})
