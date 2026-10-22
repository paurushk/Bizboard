"""Phase 2 of the test plan: every role against the routes that change or reveal something.

The expectations are written here as policy, not read back from the views, so a view that quietly widens its roles fails.
A route that is allowed answers anything but 403 (404 for an id that does not exist, 400 for an empty body); a route that
is not allowed answers 403 before it looks at the id or the body.
"""

import pytest

from tests.mfg_helpers import member, prepare

pytestmark = pytest.mark.django_db

ALL = {"OWNER", "MANAGER", "INVENTORY_STAFF", "ACCOUNTANT", "AUDITOR", "VIEWER"}
WORK = {"OWNER", "MANAGER", "INVENTORY_STAFF"}          # the floor and above
PLAN = {"OWNER", "MANAGER"}                              # set-up, reversals, approvals
CLOSE = {"OWNER", "MANAGER", "ACCOUNTANT"}               # closing orders, standard costs
COST = {"OWNER", "MANAGER", "ACCOUNTANT", "AUDITOR"}     # may see what things cost
TAX = {"OWNER", "ACCOUNTANT"}                            # ITC-04 filing

M, Q, J = "/api/v1/manufacturing", "/api/v1/quality", "/api/v1/jobwork"
X = 999999

ROUTES = [
    # recipes
    ("get", f"{M}/boms/", ALL), ("post", f"{M}/boms/", PLAN), ("post", f"{M}/boms/{X}/activate/", PLAN),
    ("post", f"{M}/boms/{X}/revise/", PLAN), ("delete", f"{M}/boms/{X}/", PLAN),
    ("get", f"{M}/boms/export/", ALL), ("post", f"{M}/boms/import/", PLAN),
    # work orders
    ("get", f"{M}/work-orders/", ALL), ("get", f"{M}/work-orders/export/", ALL), ("post", f"{M}/work-orders/", WORK),
    ("get", f"{M}/work-orders/{X}/print/", ALL),
    ("post", f"{M}/work-orders/{X}/release/", WORK), ("post", f"{M}/work-orders/{X}/complete/", WORK),
    ("post", f"{M}/work-orders/{X}/close/", CLOSE), ("post", f"{M}/work-orders/{X}/reopen/", PLAN),
    ("post", f"{M}/work-orders/{X}/cancel/", PLAN),
    ("post", f"{M}/quick-production/", WORK),
    # the documents
    ("get", f"{M}/material-issues/", ALL), ("post", f"{M}/material-issues/", WORK),
    ("post", f"{M}/material-issues/{X}/post/", WORK), ("delete", f"{M}/material-issues/{X}/discard/", WORK),
    ("post", f"{M}/material-issues/{X}/request-approval/", WORK), ("post", f"{M}/material-issues/{X}/approve/", PLAN),
    ("post", f"{M}/material-issues/{X}/reject/", PLAN), ("post", f"{M}/material-issues/{X}/reverse/", PLAN),
    ("post", f"{M}/material-returns/", WORK), ("post", f"{M}/material-returns/{X}/reverse/", PLAN),
    ("post", f"{M}/production-receipts/", WORK), ("post", f"{M}/production-receipts/{X}/post/", WORK),
    ("post", f"{M}/production-receipts/{X}/reverse/", PLAN), ("get", f"{M}/production-receipts/{X}/print-label/", ALL),
    # costs
    ("get", f"{M}/standard-costs/", COST), ("post", f"{M}/standard-costs/", CLOSE),
    ("get", f"{M}/standard-revaluations/", COST), ("post", f"{M}/standard-revaluations/", CLOSE),
    ("post", f"{M}/standard-revaluations/{X}/post/", CLOSE), ("post", f"{M}/standard-revaluations/{X}/reverse/", PLAN),
    ("get", f"{M}/reports/consumption/", ALL),
    # planning
    ("get", f"{M}/mrp-runs/", ALL), ("post", f"{M}/mrp-runs/run/", WORK), ("post", f"{M}/mrp-runs/{X}/convert/", PLAN),
    # shop floor
    ("post", f"{M}/work-centres/", PLAN), ("post", f"{M}/machines/", PLAN), ("post", f"{M}/operators/", PLAN),
    ("post", f"{M}/operators/{X}/set-pin/", PLAN), ("post", f"{M}/downtime-reasons/", PLAN),
    ("post", f"{M}/machines/{X}/breakdown/", WORK), ("post", f"{M}/maintenance-plans/{X}/complete/", WORK),
    ("post", f"{M}/maintenance-log/{X}/resolve/", WORK),
    ("post", f"{M}/job-cards/{X}/start/", WORK), ("post", f"{M}/job-cards/{X}/subcontract/", WORK),
    ("post", f"{M}/job-cards/{X}/reopen/", PLAN),
    ("get", f"{M}/settings/", ALL), ("patch", f"{M}/settings/", PLAN),
    # quality
    ("get", f"{Q}/templates/", ALL), ("post", f"{Q}/templates/", PLAN), ("post", f"{Q}/defect-codes/", PLAN),
    ("post", f"{Q}/inspections/", WORK), ("post", f"{Q}/inspections/{X}/complete/", WORK),
    ("post", f"{Q}/non-conformances/", WORK), ("delete", f"{Q}/non-conformances/{X}/", PLAN),
    ("post", f"{Q}/batches/{X}/status/", PLAN),
    # job work
    ("get", f"{J}/orders/", ALL), ("post", f"{J}/orders/", WORK), ("post", f"{J}/orders/{X}/close/", PLAN),
    ("post", f"{J}/orders/{X}/receive-material/", WORK),
    ("post", f"{J}/challans/", WORK), ("post", f"{J}/challans/{X}/issue/", WORK), ("post", f"{J}/challans/{X}/reverse/", PLAN),
    ("post", f"{J}/receipts/", WORK), ("post", f"{J}/receipts/{X}/reverse/", PLAN),
    ("get", f"{J}/itc04/", ALL), ("post", f"{J}/itc04-filings/prepare/", TAX), ("post", f"{J}/itc04-filings/{X}/mark-filed/", TAX),
]


@pytest.fixture
def firm(tenant_a):
    prepare(tenant_a)
    flags = dict(tenant_a.company.feature_flags or {})
    flags.update({
        "manufacturing_pack_grant": True, "MFG_PLANNING": True, "MFG_QUALITY": True, "MFG_JOB_WORK": True,
        "MFG_COSTING_GL": True, "MFG_SHOP_FLOOR": True,
    })
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    return tenant_a


def client_for(tenant, role):
    if role == "OWNER":
        return tenant.client
    return member(tenant, role, can_manage_inventory=(role == "INVENTORY_STAFF"))[1]


@pytest.mark.parametrize("role", sorted(ALL))
def test_each_role_may_do_exactly_what_the_policy_says(firm, role):
    client = client_for(firm, role)
    wrong = []
    for method, url, allowed in ROUTES:
        resp = getattr(client, method)(url, {}, format="json") if method not in ("get", "delete") else getattr(client, method)(url)
        denied = resp.status_code == 403
        if role in allowed and denied:
            wrong.append(f"{role} should be allowed {method.upper()} {url} but got 403")
        if role not in allowed and not denied:
            wrong.append(f"{role} should be refused {method.upper()} {url} but got {resp.status_code}")
        assert resp.status_code != 500, f"{method.upper()} {url} crashed for {role}"
    assert not wrong, "\n".join(wrong)


def test_a_company_without_the_module_sees_nothing_at_all(tenant_a, settings):
    settings.ENABLE_MANUFACTURING = False                       # the platform default: dark unless a plan or grant turns it on
    prepare(tenant_a)
    wrong = []
    for method, url, _allowed in ROUTES:
        resp = getattr(tenant_a.client, method)(url, {}, format="json") if method not in ("get", "delete") else getattr(tenant_a.client, method)(url)
        if resp.status_code != 404:
            wrong.append(f"{method.upper()} {url} answered {resp.status_code} with the module off")
    assert not wrong, "\n".join(wrong)


def test_a_switched_off_sub_module_answers_not_found_even_for_the_owner(tenant_a):
    prepare(tenant_a)
    flags = dict(tenant_a.company.feature_flags or {})
    flags["manufacturing_pack_grant"] = True                    # the module is on, every sub-module is off
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    off = {
        "MFG_QUALITY": (Q, ("templates/", "inspections/", "non-conformances/", "defect-codes/")),
        "MFG_JOB_WORK": (J, ("orders/", "challans/", "receipts/", "itc04/")),
        "MFG_COSTING_GL": (M, ("standard-costs/", "standard-revaluations/")),
        "MFG_PLANNING": (M, ("mrp-runs/", "shortages/", "board/")),
        "MFG_SHOP_FLOOR": (M, ("work-centres/", "machines/", "job-cards/", "operators/", "load/")),
    }
    wrong = []
    for flag, (base, paths) in off.items():
        for path in paths:
            code = tenant_a.client.get(f"{base}/{path}").status_code
            if code != 404:
                wrong.append(f"{flag}: GET {base}/{path} answered {code}")
    assert not wrong, "\n".join(wrong)
    assert tenant_a.client.get(f"{M}/boms/").status_code == 200       # the core of the module still works
