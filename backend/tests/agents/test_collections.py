"""Collections Agent (R2): facts tie to the ledger, drafts cite invoices, numbers are never invented."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from agents import runner, services, spec
from agents.catalog import collections as collections_pkg
from agents.catalog.collections import context as ctx
from agents.enums import ProposalStatus, RunStatus, Trigger
from agents.models import AgentProposal
from core.services.llm_providers import fake
from payments.models import PaymentPromise
from sales.models import SalesInvoice
from tests.conftest import make_customer, make_tenant
from tests.test_pdf_and_share import _complete

from .conftest import enable_agents, owner_cu, staff_cu

pytestmark = pytest.mark.django_db


@pytest.fixture
def col(db):
    """A tenant with the Collections agent registered and enabled."""
    # Autodiscover registers it at start-up; only register (and later remove) it when a test removed it.
    added = "COLLECTIONS" not in spec.AGENTS
    if added:
        spec.register(collections_pkg.AGENT)
    t = make_tenant("col1")
    enable_agents(t.company, "AGENT_COLLECTIONS")
    yield t
    if added:
        spec.unregister("COLLECTIONS")


def overdue_invoice(t, *, days=10, name="Ravi Kumar"):
    data, _ = _complete(
        t, product_kwargs={"sku": f"SKU-{name}", "name": f"Item {name}"}, customer_kwargs={"name": name},
    )
    inv = SalesInvoice.objects.get(pk=data["id"])
    inv.due_date = timezone.localdate() - timedelta(days=days)
    inv.save(update_fields=["due_date"])
    return inv


def run_for(t, ref):
    run = services.create_run(company=t.company, agent_kind="COLLECTIONS", trigger=Trigger.ATTENTION_ROW, trigger_ref=ref, user=t.owner)
    return runner.execute_run(run.pk)


def test_inr_uses_indian_grouping():
    assert ctx.inr("125000") == "1,25,000.00"
    assert ctx.inr(Decimal("999.5")) == "999.50"
    assert ctx.inr("10000000") == "1,00,00,000.00"
    assert ctx.inr("0") == "0.00"


def test_ref_parsing_covers_every_row_shape(col):
    cid = 42
    for ref in (f"AR_CUSTOMER:{cid}", f"AR_COLLECTION_RISK:customer:{cid}", f"AR_OVERDUE_CRITICAL:customer:{cid}"):
        assert ctx.customer_ids_from_ref(col.company, ref) == [cid]
    assert ctx.customer_ids_from_ref(col.company, "sweep:2026-10-21") == []
    assert ctx.customer_ids_from_ref(col.company, "DEAD_STOCK:product:3") == []


def test_facts_tie_to_the_ledger_and_the_draft_cites_the_invoice(col):
    inv = overdue_invoice(col, days=12)
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True  # nothing is scripted, so the model call fails and the template draft is used
    [p] = AgentProposal.objects.filter(run=run)
    assert p.kind == "REMINDER" and p.dedupe_key == f"AR_CUSTOMER:{inv.customer_id}"
    from ledgers.services import LedgerService

    owed = LedgerService.customer_outstanding(col.company, inv.customer)
    assert Decimal(p.payload["total_overdue"]) == owed
    assert ctx.inr(owed) in p.payload["text"]
    assert any(e["type"] == "invoice" and e["id"] == inv.id and e["href"] == f"/sales/history/{inv.id}" for e in p.evidence)
    assert set(p.payload["variants"]) == {"en:polite", "en:firm", "hi:polite", "hi:firm"}


def test_tone_is_firm_after_a_broken_promise(col):
    inv = overdue_invoice(col, days=20)
    PaymentPromise.objects.create(
        company=col.company, customer=inv.customer, promised_date=timezone.localdate() - timedelta(days=3),
        promised_amount=Decimal("50.00"),
    )
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    [p] = AgentProposal.objects.filter(run=run)
    assert p.payload["tone"] == "firm" and "promised" in p.payload["text"]
    assert any(e["type"] == "promise" for e in p.evidence)


def test_no_overdue_means_no_draft(col):
    cust = make_customer(col.company, name="Clear Co")
    run = run_for(col, f"AR_CUSTOMER:{cust.pk}")
    assert run.status == RunStatus.SUCCEEDED and not AgentProposal.objects.filter(run=run).exists()


def test_model_wording_is_used_only_when_every_number_is_in_the_books(col):
    inv = overdue_invoice(col, days=12)
    from ledgers.services import LedgerService

    owed = ctx.inr(LedgerService.customer_outstanding(col.company, inv.customer))
    good = f"Dear Ravi Kumar, ₹{owed} is pending with col1 Traders. Kindly pay soon. Thanks."
    fake.script("COLLECTIONS", step=1, response={"text": json.dumps({"text": good}), "tokens_in": 50, "tokens_out": 20})
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    [p] = AgentProposal.objects.filter(run=run)
    assert run.rules_only is False and p.payload["text"] == good
    # The other variants stay template-written.
    assert p.payload["variants"]["hi:polite"].startswith("आदरणीय")


@pytest.mark.parametrize("bad", [
    "Dear Ravi, please pay ₹9,999.00 now.",                      # invented amount
    "Dear Ravi, pay within 7 days or 5% interest applies.",      # invented terms
    "Dear Ravi, you should claim the ITC on this bill.",         # tax advice
    "ok",                                                         # too short
])
def test_bad_model_wording_falls_back_to_the_template(col, bad):
    inv = overdue_invoice(col, days=12)
    fake.script("COLLECTIONS", step=1, response={"text": json.dumps({"text": bad})})
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    [p] = AgentProposal.objects.filter(run=run)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True
    assert p.payload["text"] != bad and "gentle reminder" in p.payload["text"] or "overdue" in p.payload["text"]


def test_staff_without_reminder_access_cannot_prepare(col):
    from agents import policy
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        policy.check_start(col.company, staff_cu(col), "COLLECTIONS")
    assert policy.check_start(col.company, owner_cu(col), "COLLECTIONS").kind == "COLLECTIONS"


def test_approve_records_a_share_and_rechecks_the_ledger(col):
    inv = overdue_invoice(col, days=12)
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    [p] = AgentProposal.objects.filter(run=run)
    done = services.approve_proposal(company=col.company, company_user=owner_cu(col), proposal_id=p.pk, revision=0)
    assert done.status == ProposalStatus.EXECUTED
    assert done.result_ref["type"] == "reminder_shared" and done.result_ref["customer_id"] == inv.customer_id


def test_a_draft_goes_stale_when_the_customer_pays_first(col):
    inv = overdue_invoice(col, days=12)
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    [p] = AgentProposal.objects.filter(run=run)
    receipt = col.client.post(
        "/api/v1/payments/receipts/", {"customer": inv.customer_id, "amount": str(inv.grand_total), "mode": "CASH"}, format="json",
    )
    assert receipt.status_code in (200, 201), receipt.data
    alloc = col.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": inv.id, "amount": str(inv.grand_total)}, format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError) as exc:
        services.approve_proposal(company=col.company, company_user=owner_cu(col), proposal_id=p.pk, revision=0)
    assert exc.value.get_codes() == "AGT_E_STALE"
    p.refresh_from_db()
    assert p.status == ProposalStatus.FAILED and p.failure_code == "STALE"


def test_still_open_cancels_only_cleared_conditions(col):
    inv = overdue_invoice(col, days=12)
    other = make_customer(col.company, name="Paid Up")
    keys = [f"AR_CUSTOMER:{inv.customer_id}", f"AR_CUSTOMER:{other.pk}", "SOMETHING_ELSE:1"]
    assert ctx.still_open(col.company, keys) == {keys[0], keys[2]}


def test_sweep_ranks_by_amount_age_and_skips_opt_outs_and_holdouts(col):
    big = overdue_invoice(col, days=40, name="Big Debtor")
    small = overdue_invoice(col, days=5, name="Small Debtor")
    optout = overdue_invoice(col, days=30, name="Opted Out")
    optout.customer.dunning_opt_out = True
    optout.customer.save()
    run = services.create_run(company=col.company, agent_kind="COLLECTIONS", trigger=Trigger.SCHEDULE, trigger_ref="sweep:2026-10-21")
    done = runner.execute_run(run.pk)
    assert done.status == RunStatus.SUCCEEDED and done.rules_only is True and fake.CALLS == []
    names = [p.payload["customer_name"] for p in AgentProposal.objects.filter(run=done).order_by("id")]
    assert "Opted Out" not in names and set(names) == {"Big Debtor", "Small Debtor"}
    assert names.index("Big Debtor") < names.index("Small Debtor")
    assert {big.customer_id, small.customer_id} == {int(p.dedupe_key.split(":")[1]) for p in AgentProposal.objects.filter(run=done)}


def test_holdout_is_stable_and_off_unless_the_company_opts_in(col):
    ids = range(1, 200)
    assert not any(ctx.holdout(col.company, i) for i in ids)
    col.company.feature_flags = {**col.company.feature_flags, "AGENT_COLLECTIONS_HOLDOUT": True}
    held = [i for i in ids if ctx.holdout(col.company, i)]
    assert held == [i for i in ids if ctx.holdout(col.company, i)]
    assert 25 <= len(held) <= 55  # about 20%


def test_ranking_is_deterministic_and_respects_weights():
    a = {"customer_id": 1, "overdue_amount": "1000", "oldest_days_overdue": 5, "broken_promise_total": "0", "avg_payment_delay_days": 0}
    b = {"customer_id": 2, "overdue_amount": "900", "oldest_days_overdue": 90, "broken_promise_total": "500", "avg_payment_delay_days": 30}
    assert [x["customer_id"] for x in ctx.rank_customers([a, b])] == [2, 1]
    assert [x["customer_id"] for x in ctx.rank_customers([b, a])] == [2, 1]
    tie = [dict(a, customer_id=7), dict(a, customer_id=3)]
    assert [x["customer_id"] for x in ctx.rank_customers(tie)] == [3, 7]


def test_dates_in_drafts_are_dd_mm_yyyy_and_come_from_the_facts():
    assert ctx.nice_date(date(2026, 10, 1)) == "01/10/2026"
    assert ctx.nice_date("2026-10-01") == "01/10/2026"
