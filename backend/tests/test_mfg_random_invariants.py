"""Phase 4 of the test plan: random sequences of real operations, with the books checked after every step.

Each run picks operations from issue, return, receive, reverse the latest document, close, reopen and re-price stock,
at random quantities, on two work orders at once. A step the rules refuse is fine (that is the rules working); a step
that is accepted must leave stock, work in progress, variance and the ledger agreeing. The seed is in the test name,
so a failure replays exactly.
"""

import os
import random
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from manufacturing.models import StandardCost, WorkOrder
from manufacturing.services import flow, issue as issue_svc, receipt as receipt_svc, release_work_order, revaluation
from tests.conftest import make_product
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = pytest.mark.django_db

STEPS = 28


def D(v):
    return Decimal(str(v))


class Run:
    def __init__(self, tenant, method, seed, with_standard):
        self.rng = random.Random(seed)  # noqa: S311  (a repeatable test sequence, not a secret)
        self.tenant = tenant
        self.user = tenant.owner
        self.company = prepare(tenant, method=method, costing_gl=True)
        self.raw = stocked(tenant, "RND-RAW", 5000, 10)
        self.fg = make_product(self.company, sku="RND-FG")
        bom = make_bom(self.company, self.fg, [(self.raw, 2)], user=self.user)
        self.orders = [
            release_work_order(make_wo(self.company, bom, 40, user=self.user), self.user),
            release_work_order(make_wo(self.company, bom, 25, user=self.user), self.user),
        ]
        if with_standard:
            StandardCost.objects.create(
                company=self.company, product=self.fg, effective_from=timezone.localdate() - timedelta(days=1),
                material=D("21"), labour=D("2"),
            )
        self.posted = []          # (kind, document), oldest first
        self.log = []

    def wo(self):
        order = self.rng.choice(self.orders)
        return WorkOrder.objects.get(pk=order.pk)

    # each operation returns True when it did something
    def issue(self):
        wo = self.wo()
        line = wo.component_lines.first()
        left = line.qty - (line.qty_issued - line.qty_returned)
        qty = D(self.rng.randint(1, max(1, int(left) + 4)))        # sometimes more than is left: the rules should refuse
        doc = issue_svc.create_issue(wo, self.user, [{"wo_line": line, "qty": qty, "extra_reason": "random"}])
        self.posted.append(("issue", issue_svc.post_issue(doc, self.user)))
        return f"issue {qty} on {wo.pk}"

    def back(self):
        wo = self.wo()
        line = wo.component_lines.first()
        out = line.qty_issued - line.qty_returned
        if out <= 0:
            return None
        qty = D(self.rng.randint(1, int(out)))
        doc = issue_svc.create_return(wo, self.user, [{"wo_line": line, "qty": qty}])
        self.posted.append(("return", issue_svc.post_return(doc, self.user)))
        return f"return {qty} on {wo.pk}"

    def receive(self):
        wo = self.wo()
        good = D(self.rng.randint(1, 15))
        bad = D(self.rng.choice([0, 0, 1, 2]))
        final = self.rng.random() < 0.3
        doc = receipt_svc.create_receipt(wo, self.user, {"is_final": final, "lines": [
            {"kind": "MAIN", "qty_good": good, "qty_rejected": bad},
        ]})
        self.posted.append(("receipt", receipt_svc.post_receipt(doc, self.user, override_wip=True)))
        return f"receive {good}+{bad}{' final' if final else ''} on {wo.pk}"

    def undo(self):
        if not self.posted:
            return None
        kind, doc = self.posted[-1]
        fn = {"issue": issue_svc.reverse_issue, "return": issue_svc.reverse_return, "receipt": receipt_svc.reverse_receipt}[kind]
        fn(doc, self.user, "random undo")
        self.posted.pop()
        return f"undo {kind} {doc.pk}"

    def close(self):
        wo = self.wo()
        flow.close_work_order(wo, self.user)
        return f"close {wo.pk}"

    def reopen(self):
        wo = self.wo()
        flow.reopen_work_order(wo, self.user, "random reopen")
        return f"reopen {wo.pk}"

    def finish(self):
        wo = self.wo()
        flow.complete_separate(wo, self.user)
        return f"finish {wo.pk}"

    def reprice(self):
        revaluation.post(revaluation.preview(self.company, self.user), self.user)
        return "reprice"

    def step(self):
        op = self.rng.choices(
            [self.issue, self.back, self.receive, self.undo, self.close, self.reopen, self.finish, self.reprice],
            weights=[5, 2, 4, 2, 1, 1, 1, 1],
        )[0]
        try:
            what = op()
        except BusinessRuleError:
            return                                  # refused by a rule: nothing may have changed
        if what:
            self.log.append(what)


@pytest.mark.parametrize("with_standard", [False, True], ids=["actual", "standard"])
@pytest.mark.parametrize("method", ["WAVG", "FIFO"])
# MFG_RANDOM_SEEDS=60 for a longer hunt; the default keeps the suite quick
@pytest.mark.parametrize("seed", range(int(os.environ.get("MFG_RANDOM_SEEDS", "6"))))
def test_the_books_agree_after_every_step_of_a_random_run(tenant_a, method, seed, with_standard):
    run = Run(tenant_a, method, seed, with_standard)
    for n in range(STEPS):
        run.step()
        try:
            assert_all_invariants(run.company)
        except AssertionError as exc:               # name the step and the history that led to it
            raise AssertionError(f"seed {seed} {method} step {n}: {exc}\nhistory: {run.log}") from exc
    assert run.log, "a run that did nothing proves nothing"
