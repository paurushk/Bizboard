from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from agents import outcomes, services
from agents.catalog import collections as collections_pkg
from agents.enums import ProposalStatus
from agents.models import AgentProposal
from agents import spec
from payments.models import CustomerReceipt, ReceiptStatus
from tests.conftest import make_customer, make_tenant

from .conftest import enable_agents, owner_cu

pytestmark = pytest.mark.django_db


@pytest.fixture
def col():
    added = "COLLECTIONS" not in spec.AGENTS
    if added:
        spec.register(collections_pkg.AGENT)
    t = make_tenant("out1")
    enable_agents(t.company, "AGENT_COLLECTIONS")
    yield t
    if added:
        spec.unregister("COLLECTIONS")


def reminder(t, customer, *, status=ProposalStatus.PENDING, revision=0):
    run = services.create_run(company=t.company, agent_kind="COLLECTIONS", trigger="USER", trigger_ref=f"r-{customer.pk}", user=t.owner)
    [p] = services.create_proposals(run, [{
        "kind": "REMINDER", "title": "Reminder", "dedupe_key": f"AR_CUSTOMER:{customer.pk}",
        "payload": {"customer_id": customer.pk, "customer_name": customer.name, "text": "Dear x, pay 100.00 soon please now",
                    "total_overdue": "100.00"},
        "evidence": [{"type": "customer", "id": customer.pk, "label": "x"}],
    }])
    AgentProposal.objects.filter(pk=p.pk).update(status=status, revision=revision, decided_at=timezone.now())
    return p


def receipt(t, customer, amount, *, days_after=1):
    return CustomerReceipt.objects.create(
        company=t.company, customer=customer, amount=Decimal(amount), mode="CASH", status=ReceiptStatus.POSTED,
        receipt_date=timezone.localdate() + timedelta(days=days_after),
    )


def test_funnel_rates_and_treated_recovery(col):
    a, b, c = (make_customer(col.company, name=n) for n in ("A Co", "B Co", "C Co"))
    reminder(col, a, status=ProposalStatus.EXECUTED)
    reminder(col, b, status=ProposalStatus.EXECUTED, revision=2)
    reminder(col, c, status=ProposalStatus.REJECTED)
    receipt(col, a, "500", days_after=2)
    receipt(col, b, "300", days_after=20)  # outside the 7-day window
    out = outcomes.collections_outcomes(col.company)
    assert out["funnel"]["EXECUTED"] == 2 and out["funnel"]["REJECTED"] == 1
    assert out["approval_rate"] == round(2 / 3, 3) and out["edited_rate"] == 0.5
    assert out["treated"]["customers"] == 2 and out["treated"]["received_within_7_days"] == "500.00"
    assert out["held_out"]["enabled"] is False


def test_empty_company_reports_none_not_errors(col):
    out = outcomes.collections_outcomes(col.company)
    assert out["approval_rate"] is None and out["edited_rate"] is None and out["treated"]["customers"] == 0


def test_command_prints_json(col, capsys):
    call_command("agents_outcomes", col.company.pk, "--days", "7")
    assert '"funnel"' in capsys.readouterr().out


def test_other_companies_are_not_counted(col):
    other = make_tenant("out2")
    cust = make_customer(other.company, name="Other Co")
    enable_agents(other.company, "AGENT_COLLECTIONS")
    reminder(other, cust, status=ProposalStatus.EXECUTED)
    assert outcomes.collections_outcomes(col.company)["funnel"]["EXECUTED"] == 0
    assert owner_cu(col)  # fixture sanity
