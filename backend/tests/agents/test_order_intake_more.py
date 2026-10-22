"""Block B of the test plan: Order Intake parsing, matching, warnings, the model path, the executor and learning."""
# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)

import json
from decimal import Decimal

import pytest
from django.db import transaction

from agents import runner, services
from agents.catalog.order_intake import parsing, resolver
from agents.enums import RunStatus, Trigger
from agents.models import AgentAlias, AgentProposal
from agents.schemas.sales_order import SalesOrderDraftPayloadV1
from core.services.llm_providers import fake
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product
from sales.models import SalesOrder
from tests.conftest import make_customer, make_product

from .test_order_intake import BASE, TEXT, approve, d, key, oi, paste, proposal_of, script  # noqa: F401

pytestmark = pytest.mark.django_db


# --- parsing --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["", "   ", "\n\n", ";;;"])
def test_blank_text_has_no_lines(text):
    assert parsing.parse_order(text)["lines"] == []


def test_the_line_cap_is_100():
    text = "\n".join(f"{i + 1} item{i}" for i in range(150))
    assert len(parsing.parse_order(text)["lines"]) == parsing.MAX_LINES


@pytest.mark.parametrize("raw,qty", [("0 sugar", None), ("-3 sugar", "3"), ("99999999 sugar", None), ("1000000 sugar", "1000000"), ("2,5 kg atta", "2.5")])
def test_quantity_bounds(raw, qty):
    line = parsing.parse_line(raw)
    assert line is None or line["qty"] == qty


@pytest.mark.parametrize("raw,name", [("5 × tata salt", "tata salt"), ("5 X tata salt", "tata salt"), ("tata salt × 5", "tata salt")])
def test_multiplication_sign_forms(raw, name):
    line = parsing.parse_line(raw)
    assert line["qty"] == "5" and line["product_hint"] == name


def test_a_line_that_is_only_a_number_is_dropped():
    assert parsing.parse_line("12") is None


def test_devanagari_text_is_kept_by_normalisation():
    assert parsing.normalize("चीनी  बोरी!") == "चीनी बोरी"


# --- resolver ---------------------------------------------------------------------------------------------
def test_two_close_customers_are_left_for_the_person_to_pick(oi):
    make_customer(oi.company, name="Sharma Traders Delhi")
    res = resolver.resolve_customer(oi.company, "Sharma")
    assert res["id"] is None and len(res["alternatives"]) >= 2


def test_soft_deleted_and_inactive_masters_are_never_matched(oi):
    gone = make_product(oi.company, name="Jaggery Block", sku="JG1")
    Product.objects.filter(pk=gone.pk).update(is_deleted=True)
    dormant = make_product(oi.company, name="Jaggery Powder", sku="JG2", status="INACTIVE")
    index = resolver.ProductIndex(oi.company)
    assert index.resolve("jaggery")["id"] is None and dormant.pk not in {r[0] for r in index.rows}
    Customer.objects.filter(pk=oi.customer.pk).update(is_deleted=True)
    assert resolver.resolve_customer(oi.company, "Sharma Traders")["id"] is None


def test_a_phone_with_country_code_matches(oi):
    assert resolver.resolve_customer(oi.company, "", "order from +91 98765 43210")["id"] == oi.customer.id


def test_an_alias_to_a_deleted_product_is_ignored(oi):
    AgentAlias.objects.create(company=oi.company, scope="PRODUCT", raw_text_norm="chini", product=oi.sugar)
    Product.objects.filter(pk=oi.sugar.pk).update(is_deleted=True)
    assert resolver.ProductIndex(oi.company).resolve("chini")["id"] is None


def test_equal_scores_are_never_auto_picked(oi):
    make_product(oi.company, name="Toor Dal 2kg", sku="DAL2")
    res = resolver.ProductIndex(oi.company).resolve("toor dal")
    assert res["id"] is None and {a["name"] for a in res["alternatives"]} >= {"Toor Dal 1kg", "Toor Dal 2kg"}


# --- draft warnings -----------------------------------------------------------------------------------------
def _stock(oi, product, qty):
    InventoryService.post_movement(
        company=oi.company, product=product, movement_type=MovementType.OPENING_STOCK, quantity=Decimal(qty),
        unit_cost=Decimal("10"), user=oi.owner,
    )


def _warnings(p, index=0):
    return p.payload["lines"][index]["warnings"]


def test_stock_warning_at_the_boundary(oi):
    _stock(oi, oi.sugar, "5")
    assert not any("available" in w for w in _warnings(proposal_of(paste(oi, "From: Sharma Traders\n5 sugar 50kg bag"))))
    p = proposal_of(paste(oi, "From: Sharma Traders\n6 sugar 50kg bag"))
    assert any("Only 5 available" in w for w in _warnings(p))


def test_a_service_item_gets_no_stock_warning(oi):
    svc = make_product(oi.company, name="Delivery Charge", sku="SVC1", product_type="SERVICE")
    p = proposal_of(paste(oi, "From: Sharma Traders\n2 delivery charge"))
    assert p.payload["lines"][0]["product_id"] == svc.pk and not _warnings(p)


def test_unit_mismatch_warning(oi):
    from masters.models import Unit

    pcs = Unit.objects.create(company=oi.company, name="Piece", short_name="pcs")
    Product.objects.filter(pk=oi.dal.pk).update(unit=pcs)
    p = proposal_of(paste(oi, "From: Sharma Traders\n2 dozen toor dal 1kg"))
    assert any("dozen" in w for w in _warnings(p))


@pytest.mark.parametrize("status", ["BLOCKED", "INACTIVE"])
def test_a_blocked_or_inactive_customer_is_warned_about(oi, status):
    Customer.objects.filter(pk=oi.customer.pk).update(status=status)
    p = proposal_of(paste(oi))
    assert any(status.lower() in w for w in p.payload["warnings"])


def test_over_the_credit_limit_warning(oi, monkeypatch):
    Customer.objects.filter(pk=oi.customer.pk).update(credit_limit=Decimal("1000"))
    monkeypatch.setattr("payments.dunning.customer_risk_snapshot", lambda company, cust, **kw: {"outstanding": "5000"})
    p = proposal_of(paste(oi))
    assert any("credit limit" in w for w in p.payload["warnings"])


# --- the model path --------------------------------------------------------------------------------------------
def test_a_buyer_name_that_is_not_in_the_text_is_dropped(oi):
    script([{"raw": "2 sugar 50kg bag", "qty": 2, "unit": "", "product_hint": "sugar 50kg bag"}], hint="Totally Different Co")
    p = proposal_of(paste(oi, "2 sugar 50kg bag"))
    assert p.payload["customer_hint"] == "" and p.payload["customer_id"] is None


@pytest.mark.parametrize("bad_qty", [True, "lots", -1, 0, 10 ** 9])
def test_a_bad_model_quantity_falls_back_to_the_rules(oi, bad_qty):
    script([{"raw": "2 sugar 50kg bag", "qty": bad_qty, "unit": "", "product_hint": "sugar 50kg bag"}])
    run = runner.execute_run(services.create_run(company=oi.company, agent_kind="ORDER_INTAKE", trigger=Trigger.USER, trigger_ref="TEXT:bq", user=oi.owner).pk, {"text": "2 sugar 50kg bag"})
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True


def test_more_than_100_model_lines_fall_back_to_the_rules(oi):
    lines = [{"raw": "2 sugar 50kg bag", "qty": 2, "unit": "", "product_hint": "sugar"}] * 101
    script(lines)
    run = runner.execute_run(services.create_run(company=oi.company, agent_kind="ORDER_INTAKE", trigger=Trigger.USER, trigger_ref="TEXT:big", user=oi.owner).pk, {"text": "2 sugar 50kg bag"})
    assert run.rules_only is True


def test_model_json_wrapped_in_a_code_fence_falls_back_to_the_rules(oi):
    fake.reset()
    fake.script("ORDER_INTAKE", step=1, response={"text": "```json\n{\"customer_hint\": \"\", \"lines\": []}\n```", "tokens_in": 5, "tokens_out": 5})
    run = runner.execute_run(services.create_run(company=oi.company, agent_kind="ORDER_INTAKE", trigger=Trigger.USER, trigger_ref="TEXT:fence", user=oi.owner).pk, {"text": "2 sugar 50kg bag"})
    assert run.rules_only is True and AgentProposal.objects.filter(run=run).count() == 1


def test_consent_off_never_calls_the_model(oi):
    oi.company.ai_features_enabled = False
    oi.company.save(update_fields=["ai_features_enabled"])
    fake.reset()
    assert paste(oi).status_code == 200 and fake.CALLS == []


# --- the executor ---------------------------------------------------------------------------------------------------
def _edit(oi, p, mutate):
    payload = json.loads(json.dumps(p.payload))
    mutate(payload)
    assert oi.client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": payload, "revision": p.revision}, format="json").status_code == 200
    p.refresh_from_db()
    return p


def test_an_inactive_product_makes_the_draft_stale(oi):
    p = proposal_of(paste(oi))
    Product.objects.filter(pk=oi.sugar.pk).update(status="INACTIVE")
    r = approve(oi, p)
    assert r.status_code == 409 and SalesOrder.objects.count() == 0
    p.refresh_from_db()
    assert p.failure_code == "STALE"


def test_a_deleted_customer_fails_cleanly(oi):
    p = proposal_of(paste(oi))
    Customer.objects.filter(pk=oi.customer.pk).update(is_deleted=True)
    assert approve(oi, p).status_code == 400 and SalesOrder.objects.count() == 0


def test_decimal_quantities_and_repeated_products(oi):
    p = proposal_of(paste(oi, "From: Sharma Traders\n2.5 toor dal 1kg\n1.5 toor dal 1kg"))
    r = approve(oi, p)
    order = SalesOrder.objects.get(pk=d(r)["resultRef"]["id"])
    assert sorted(i.quantity for i in order.items.all()) == [Decimal("1.500"), Decimal("2.500")]


@pytest.mark.parametrize("qty", ["0", "-1", "abc"])
def test_an_edited_bad_quantity_is_refused_at_edit(oi, qty):
    p = proposal_of(paste(oi))
    payload = json.loads(json.dumps(p.payload))
    payload["lines"][0]["qty"] = qty
    r = oi.client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": payload, "revision": p.revision}, format="json")
    assert r.status_code == 400


def test_the_order_is_dated_on_the_day_of_approval(oi):
    from django.utils import timezone

    p = proposal_of(paste(oi))
    order = SalesOrder.objects.get(pk=d(approve(oi, p))["resultRef"]["id"])
    assert order.order_date == timezone.localdate() and order.status == "DRAFT"


# --- learning ---------------------------------------------------------------------------------------------------------
def test_a_correction_repoints_an_earlier_alias(oi):
    AgentAlias.objects.create(company=oi.company, scope="PRODUCT", raw_text_norm="chini", product=oi.rice, hits=4)
    p = proposal_of(paste(oi, "From: Sharma Traders\n3 chini"))
    assert p.payload["lines"][0]["product_id"] == oi.rice.id
    p = _edit(oi, p, lambda pl: pl["lines"][0].update(product_id=oi.sugar.id, product_name=oi.sugar.name))
    assert approve(oi, p).status_code == 200
    alias = AgentAlias.objects.get(company=oi.company, raw_text_norm="chini")
    assert alias.product_id == oi.sugar.id and alias.hits == 1


def test_exact_name_and_code_matches_are_not_learned(oi):
    p = proposal_of(paste(oi, "From: Sharma Traders\n2 SUG50\n1 toor dal 1kg"))
    assert approve(oi, p).status_code == 200
    assert not AgentAlias.objects.filter(scope="PRODUCT").exists()


def test_hits_increase_once_per_approval(oi):
    def fix(pl):  # the edit starts from the original draft, so fix everything that is missing in one go
        if pl["customer_id"] is None:
            pl.update(customer_id=oi.customer.id, customer_name=oi.customer.name)
        if pl["lines"][0]["product_id"] is None:
            pl["lines"][0].update(product_id=oi.sugar.id, product_name=oi.sugar.name)

    for n in (1, 2, 3):
        p = proposal_of(paste(oi, f"From: Sharma ji\n{n} chini"))
        p = _edit(oi, p, fix)
        r = approve(oi, p)
        assert r.status_code == 200, r.content
    assert AgentAlias.objects.get(company=oi.company, raw_text_norm="chini").hits == 3


def test_aliases_roll_back_with_the_order(oi, monkeypatch):
    p = proposal_of(paste(oi, "From: Sharma ji\n3 chini"))
    p = _edit(oi, p, lambda pl: (pl.update(customer_id=oi.customer.id, customer_name=oi.customer.name), pl["lines"][0].update(product_id=oi.sugar.id, product_name=oi.sugar.name)))

    def boom(*a, **k):
        raise RuntimeError("alias write failed")

    monkeypatch.setattr("agents.executors.sales_order._learn", boom)
    from agents.services import approve_proposal
    from tests.agents.conftest import owner_cu

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            approve_proposal(company=oi.company, company_user=owner_cu(oi), proposal_id=p.pk, revision=p.revision)
    assert SalesOrder.objects.count() == 0 and not AgentAlias.objects.exists()


# --- payload serializer ------------------------------------------------------------------------------------------------
def _valid():
    return {"lines": [{"raw": "x", "qty": "2", "product_id": 1}]}


@pytest.mark.parametrize("mutate,ok", [
    (lambda p: None, True),
    (lambda p: p.update(lines=[]), False),
    (lambda p: p.update(lines=_valid()["lines"] * 101), False),
    (lambda p: p["lines"][0].update(qty="0.0001"), True),
    (lambda p: p["lines"][0].update(qty="1000001"), False),
    (lambda p: p["lines"][0].update(match={"source": "telepathy"}), False),
])
def test_payload_validation(mutate, ok):
    data = _valid()
    mutate(data)
    assert SalesOrderDraftPayloadV1(data=data).is_valid() is ok
