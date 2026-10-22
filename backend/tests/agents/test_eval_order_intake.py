"""Replay evaluation for Order Intake (AGT-309) on a SYNTHETIC set (tests/agents/eval/orders.json).

Every case runs through the real run path. Cases with a `recorded` answer replay that model response through the fake
provider; the rest run on the rules parser (the fake provider has no script, so the model step fails and rules are used).
The set is generated, not pilot data: replace or extend it with anonymised real messages before relying on the numbers.
"""

import json
import pathlib
from decimal import Decimal

import pytest

from agents import runner, services, spec
from agents.catalog import order_intake as oi_pkg
from agents.enums import RunStatus, Trigger
from agents.models import AgentProposal
from core.services.llm_providers import fake
from tests.conftest import make_customer, make_product, make_tenant

from .conftest import enable_agents

pytestmark = pytest.mark.django_db

CASES = json.loads((pathlib.Path(__file__).parent / "eval" / "orders.json").read_text(encoding="utf-8"))
CATALOGUE = [
    ("SUG50", "Sugar 50kg bag"), ("RIC25", "Basmati Rice 25kg"), ("DAL1", "Toor Dal 1kg"), ("OIL1", "Mustard Oil 1L"),
    ("SLT1", "Tata Salt 1kg"), ("ATA10", "Aashirvaad Atta 10kg"), ("PAR1", "Parle G Biscuit"), ("TEA250", "Red Label Tea 250g"),
]
LINE_MATCH_MIN = 0.95


@pytest.fixture
def world(db):
    added = "ORDER_INTAKE" not in spec.AGENTS
    if added:
        spec.register(oi_pkg.AGENT)
    t = make_tenant("evo1")
    enable_agents(t.company, "AGENT_ORDER_INTAKE")
    for name in ("Sharma Traders", "Gupta General Store", "Verma & Sons"):
        make_customer(t.company, name=name)
    t.skus = {}
    for sku, name in CATALOGUE:
        p = make_product(t.company, sku=sku, name=name, selling_price="100")
        t.skus[p.pk] = sku
    yield t
    if added:
        spec.unregister("ORDER_INTAKE")


def run_case(t, case):
    fake.reset()
    if case.get("recorded"):
        fake.script("ORDER_INTAKE", step=1, response={"text": json.dumps(case["recorded"]), "tokens_in": 30, "tokens_out": 20})
    run = services.create_run(company=t.company, agent_kind="ORDER_INTAKE", trigger=Trigger.USER, trigger_ref=f"TEXT:{case['id']}", user=t.owner)
    run = runner.execute_run(run.pk, {"text": case["text"]})
    p = AgentProposal.objects.filter(run=run).first()
    resolved = []
    if p:
        resolved = [(t.skus[l["product_id"]], str(Decimal(l["qty"]).normalize())) for l in p.payload["lines"] if l["product_id"] and l["qty"]]
    return run, p, resolved


def test_line_match_on_the_synthetic_set(world):
    expected = found = wrong = 0
    misses = []
    for case in CASES:
        run, p, resolved = run_case(world, case)
        want = [(e["sku"], str(Decimal(e["qty"]).normalize())) for e in case["expect"]]
        if not want:
            assert p is None or all(l["product_id"] is None for l in p.payload["lines"]), case["id"]
            continue
        assert run.status == RunStatus.SUCCEEDED, case["id"]
        expected += len(want)
        hit = [w for w in want if w in resolved]
        found += len(hit)
        wrong += len([r for r in resolved if r not in want])
        misses += [(case["id"], w) for w in want if w not in resolved]
        if case.get("customer"):
            assert p.payload["customer_name"] == case["customer"], case["id"]
    rate = found / expected
    assert wrong == 0, f"{wrong} line(s) resolved to the wrong product or quantity"
    assert rate >= LINE_MATCH_MIN, f"line match {rate:.3f} < {LINE_MATCH_MIN}; misses: {misses}"


def test_the_set_has_the_size_and_mix_the_plan_asks_for():
    assert len(CASES) >= 50
    assert sum(1 for c in CASES if c.get("recorded")) >= 10  # Hinglish through the model path
    assert any(c["id"].startswith("inj") for c in CASES) and any(c["id"].startswith("chat") for c in CASES)
