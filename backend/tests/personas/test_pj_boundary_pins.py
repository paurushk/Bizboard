"""Boundaries the product keeps. These journeys stay refused."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.django_db


def test_j_amc_p9_visit_stays_on_contracts():
    """J-AMC-P9-VISIT. A contract does not create a job card.

    A job card may name the contract that covers it (CCJ plan JOB-09) and read its coverage, but the
    link is one way: contracts never build or touch job cards, and the workshop never creates or
    changes a contract.
    """
    backend = Path(__file__).resolve().parents[2]
    contracts = "\n".join(path.read_text(encoding="utf-8") for path in (backend / "contracts").rglob("*.py"))
    workshop = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (backend / "workshop").rglob("*.py")
        if "migrations" not in path.parts
    )
    assert "JobCard" not in contracts
    for write in ("Contract.objects.create", "Contract(", "renew_contract", "create_contract_schedule"):
        assert write not in workshop


def test_j_care_p10_ticket_has_no_serial():
    """J-CARE-P10-TICKET. A ticket names a customer and does not name a serial."""
    from support.models import Ticket

    names = {field.name for field in Ticket._meta.fields}
    assert "serial" not in names
    assert "customer" in names
