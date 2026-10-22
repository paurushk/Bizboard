"""The demo seeding and the thirty-day simulation commands run clean and leave the books in step."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.invariants import assert_all_invariants
from manufacturing.models import Bom, WorkOrder

pytestmark = pytest.mark.django_db(transaction=True)


def test_seeding_twice_adds_nothing_new(tenant_a):
    call_command("seed_manufacturing_demo", email=tenant_a.owner.email)
    first = (Bom.objects.filter(company=tenant_a.company).count(), WorkOrder.objects.count())
    call_command("seed_manufacturing_demo", email=tenant_a.owner.email)
    assert (Bom.objects.filter(company=tenant_a.company).count(), WorkOrder.objects.count()) == first
    assert first[0] == 2


def test_the_month_simulation_keeps_every_invariant(tenant_a):
    out = StringIO()
    call_command("simulate_manufacturing_month", email=tenant_a.owner.email, days=6, seed=7, stdout=out)
    assert "days ok" in out.getvalue() and " 0 refusals" in out.getvalue(), out.getvalue()
    assert WorkOrder.objects.filter(company=tenant_a.company).exists()
    assert_all_invariants(tenant_a.company)


def test_both_commands_refuse_on_production(tenant_a, settings):
    settings.DJANGO_ENV = "production"
    with pytest.raises(CommandError):
        call_command("seed_manufacturing_demo", email=tenant_a.owner.email)
    with pytest.raises(CommandError):
        call_command("simulate_manufacturing_month", email=tenant_a.owner.email)
