"""Wave 5 vertical-module regressions that are in place so far."""

from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from projects.models import Project, ProjectMilestone
from projects.services import close_project
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def test_bug_prj_004_planned_milestone_blocks_close(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="PRJ004")
    project = Project.objects.create(
        company=tenant_a.company,
        customer=customer,
        name="Site",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    ProjectMilestone.objects.create(
        company=tenant_a.company,
        project=project,
        name="Foundation",
        amount=Decimal("1000.00"),
        service_product=product,
        status=ProjectMilestone.Status.PLANNED,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="milestone"):
        close_project(project, tenant_a.owner)
    project.refresh_from_db()
    assert project.status == Project.Status.OPEN
