"""Builders shared by the manufacturing tests."""

from decimal import Decimal

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from accounts.models import CompanyUser
from manufacturing.models import Bom, BomLine, BomOutput, MfgSettings, WorkOrder
from manufacturing.services import _snapshot_bom
from manufacturing.services import bom as bom_svc
from manufacturing.services.common import get_settings, next_number
from tests.conftest import add_stock, make_product


def prepare(tenant, *, method="WAVG", accounting=True, separate=True, costing_gl=False, **settings_kw):
    """Switch a test company onto the document flow (or leave it on the one-step flow)."""
    company = tenant.company
    company.inventory_valuation_method = method
    company.accounting_enabled = accounting
    flags = dict(company.feature_flags or {})
    if costing_gl:
        flags["MFG_COSTING_GL"] = True
    company.feature_flags = flags
    company.save()
    if accounting:
        seed_chart_of_accounts(company, tenant.owner)
    cfg = get_settings(company)
    cfg.default_issue_mode = (
        MfgSettings.IssueMode.SEPARATE if separate else MfgSettings.IssueMode.AUTO_AT_RELEASE
    )
    for k, v in settings_kw.items():
        setattr(cfg, k, v)
    cfg.save()
    return company


def member(tenant, role, email=None, **caps):
    """A second user on the tenant with the given role, plus an authenticated client."""
    from accounts.models import User
    from rest_framework.test import APIClient

    email = email or f"{role.lower()}@{tenant.company.name.split()[0].lower()}.test"
    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=role.title())
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **caps)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def make_bom(company, fg, components, *, user=None, status="ACTIVE", outputs=(), output_qty="1",
             yield_pct="100", name="BOM", additional=()):
    """components: [(product, qty), ...] or dicts with BomLine kwargs."""
    bom = Bom.objects.create(
        company=company, product=fg, name=name, status="DRAFT",
        revision_no=bom_svc.next_revision_no(company, fg), output_qty=Decimal(output_qty),
        yield_pct=Decimal(yield_pct), created_by=user, updated_by=user,
    )
    for comp in components:
        if isinstance(comp, dict):
            BomLine.objects.create(bom=bom, company=company, **comp)
        else:
            BomLine.objects.create(bom=bom, company=company, component=comp[0], qty=Decimal(str(comp[1])))
    for out in outputs:
        BomOutput.objects.create(bom=bom, company=company, **out)
    for add in additional:
        from manufacturing.models import BomAdditionalCost

        BomAdditionalCost.objects.create(bom=bom, company=company, **add)
    if status == "ACTIVE":
        bom = bom_svc.activate_revision(bom, user)
    return bom


def make_wo(company, bom, qty, *, user=None, mode=None, warehouse=None, **kw):
    """A draft work order with its lines snapshotted (what the serializer does)."""
    mode = mode or get_settings(company).default_issue_mode
    wo = WorkOrder.objects.create(
        company=company, bom=bom, qty=Decimal(str(qty)), issue_mode=mode, warehouse=warehouse,
        number=next_number(company, "mfg_wo", "WO"), created_by=user, updated_by=user, **kw,
    )
    _snapshot_bom(wo)
    bom_svc.lock_bom(bom)
    return wo


def stocked(tenant, sku, qty, cost, **kw):
    p = make_product(tenant.company, name=sku, sku=sku, purchase_price=str(cost), **kw)
    if Decimal(str(qty)) > 0:
        add_stock(tenant, p, str(qty), unit_cost=str(cost))
    return p


def account_net(company, code):
    """Debit minus credit on one account across posted and reversed journals."""
    total = Decimal("0")
    for entry in JournalEntry.objects.filter(
        company=company, status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
    ).prefetch_related("lines__account"):
        for jl in entry.lines.all():
            if jl.account.code == code:
                total += jl.debit - jl.credit
    return total


def body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def rows(resp):
    """The list of records in a list response, paginated or not."""
    data = body(resp)
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data
