"""FG-2d — tenant isolation over the whole API surface.

Two parts:

1. STRUCTURAL sweep — introspect every view mounted under /api/v1/ and assert it
   is tenant-scoped: a ``CompanyScopedViewSet`` subclass, or a view whose
   ``get_queryset`` visibly filters by company, or an explicitly allow-listed
   non-tenant endpoint (health, auth, schema, plan catalogue, ...). A new
   ViewSet that forgets scoping fails here immediately — no per-endpoint test
   needed.

2. LIVE cross-tenant probes — for the core document/master endpoints, create a
   row as tenant B and assert tenant A cannot read it (list omits it, detail is
   403/404) or mutate it.
"""

from __future__ import annotations

import inspect
import textwrap

import pytest
from django.urls import get_resolver

pytestmark = pytest.mark.django_db

# Views that legitimately serve no tenant-scoped data.
_ALLOWLIST_SUFFIXES = (
    "HealthView",
    "MetricsView",
    "SpectacularAPIView",
    "SpectacularSwaggerView",
    "GatedSchemaView",
    "GatedSwaggerView",
    # core.views.IntegrationsInventoryView: reports which outbound-integration
    # settings keys are PRESENT (booleans only, never secret values) for this
    # deployment -- that is per-deployment, not per-company, so it is
    # identical for every tenant by design. Gated to IsOwner + HasCompany
    # (company membership required to call it at all) even though the
    # response itself carries no tenant-scoped data to leak.
    "IntegrationsInventoryView",
)
_ALLOWLIST_MODULES = (
    "accounts.urls_auth",  # login / register / token — pre-company
    "rest_framework",
)
_ALLOWLIST_NAME_HINTS = (
    "auth", "login", "register", "token", "otp", "password", "health", "metrics",
    "schema", "docs", "webhook", "public", "plan", "help",  # help catalogue is global
)


def _iter_api_views():
    """Yield (pattern_name, view_callback) for every route under api/v1/."""
    resolver = get_resolver()
    stack = [(list(resolver.url_patterns), "")]
    seen = set()
    while stack:
        patterns, prefix = stack.pop()
        for p in patterns:
            if hasattr(p, "url_patterns"):
                stack.append((list(p.url_patterns), prefix + str(p.pattern)))
                continue
            full = prefix + str(p.pattern)
            if "api/v1/" not in full and not full.startswith("api/v1"):
                # root resolver includes api/v1/ as a nested resolver; the prefix
                # carries it once we descend. Keep everything we reach from here.
                pass
            cb = p.callback
            key = id(cb)
            if key in seen:
                continue
            seen.add(key)
            yield full, cb


def _view_class(cb):
    return getattr(cb, "cls", None) or getattr(cb, "view_class", None)


_SCOPE_SIGNALS = (
    "company", "get_company_user", "company_user", "self.company",
    "company_id", "for_company", "request.user",
)


def _is_tenant_scoped(view_cls) -> bool:
    from core.viewsets import CompanyScopedViewSet

    if issubclass(view_cls, CompanyScopedViewSet):
        return True
    # Scan the view class's own source (methods included) for a scoping signal —
    # report/search/integration APIViews scope inside get()/post(), not via a
    # get_queryset() method.
    for klass in view_cls.__mro__:
        if klass.__module__.startswith(("rest_framework", "django")):
            continue
        try:
            src = textwrap.dedent(inspect.getsource(klass))
        except (OSError, TypeError):
            continue
        if any(sig in src for sig in _SCOPE_SIGNALS):
            return True
    return False


# Views the structural heuristic still can't prove. Each is scoped by inspection
# but needs a real cross-tenant test before it leaves the baseline. The set may
# only shrink — a new unscoped view fails the test.
def _load_baseline() -> set[str]:
    import pathlib

    f = pathlib.Path(__file__).parent / "_isolation_baseline.txt"
    if not f.exists():
        return set()
    return {
        line.split("#", 1)[0].strip()
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_every_api_view_is_tenant_scoped_or_allowlisted():
    from rest_framework.views import APIView

    offenders = []
    for name, cb in _iter_api_views():
        view_cls = _view_class(cb)
        if view_cls is None or not issubclass(view_cls, APIView):
            continue
        cls_name = view_cls.__name__
        if cls_name.endswith(_ALLOWLIST_SUFFIXES):
            continue
        mod = view_cls.__module__
        if any(m in mod for m in _ALLOWLIST_MODULES):
            continue
        if any(h in name.lower() for h in _ALLOWLIST_NAME_HINTS):
            continue
        if any(h in cls_name.lower() for h in _ALLOWLIST_NAME_HINTS):
            continue
        if _is_tenant_scoped(view_cls):
            continue
        offenders.append(cls_name)

    offenders = set(offenders)
    baseline = _load_baseline()
    new_unscoped = offenders - baseline
    assert not new_unscoped, (
        "New API view(s) not provably tenant-scoped — subclass CompanyScopedViewSet, "
        "scope get_queryset/get()/post() by company, or (last resort) add to "
        "tests/tenancy/_isolation_baseline.txt WITH a real cross-tenant test:\n  "
        + "\n  ".join(sorted(new_unscoped))
    )
    fixed = baseline - offenders
    if fixed:
        # Not a failure — just keep the baseline honest.
        print(
            "tenancy baseline can be trimmed (now provably scoped): "
            + ", ".join(sorted(fixed))
        )


# --- Live cross-tenant probes -------------------------------------------------

def _make_customer(t):
    from tests.conftest import make_customer

    return make_customer(t.company)


def _make_supplier(t):
    from tests.conftest import make_supplier

    return make_supplier(t.company)


def _make_product(t):
    from tests.conftest import make_product

    return make_product(t.company)


_PROBES = [
    ("customers", "/api/v1/customers/", _make_customer),
    ("suppliers", "/api/v1/suppliers/", _make_supplier),
    ("products", "/api/v1/products/", _make_product),
]


@pytest.mark.parametrize("label,list_url,factory", _PROBES, ids=[p[0] for p in _PROBES])
def test_tenant_a_cannot_read_tenant_b_row(tenant_a, tenant_b, label, list_url, factory):
    obj_b = factory(tenant_b)

    detail = tenant_a.client.get(f"{list_url}{obj_b.pk}/")
    assert detail.status_code in (403, 404), (
        f"{label}: tenant A got {detail.status_code} for tenant B's row"
    )

    listing = tenant_a.client.get(list_url)
    assert listing.status_code == 200, listing.data
    body = listing.data
    rows = body.get("results", body) if isinstance(body, dict) else body
    ids = {r.get("id") for r in rows} if isinstance(rows, list) else set()
    assert obj_b.pk not in ids, f"{label}: tenant B's row leaked into tenant A's list"


@pytest.mark.parametrize("label,list_url,factory", _PROBES, ids=[p[0] for p in _PROBES])
def test_tenant_a_cannot_mutate_tenant_b_row(tenant_a, tenant_b, label, list_url, factory):
    obj_b = factory(tenant_b)
    resp = tenant_a.client.patch(f"{list_url}{obj_b.pk}/", {"name": "hijacked"}, format="json")
    assert resp.status_code in (403, 404), f"{label}: tenant A PATCHed tenant B's row ({resp.status_code})"
    obj_b.refresh_from_db()
    assert obj_b.name != "hijacked"


def _enable(tenant, flag):
    flags = dict(tenant.company.feature_flags or {})
    flags[flag] = True
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def _ids(payload):
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    return {row.get("id") for row in rows} if isinstance(rows, list) else set()


def test_job_card_is_not_readable_across_tenants(tenant_a, tenant_b):
    from tests.conftest import make_customer
    from workshop.models import JobCard

    _enable(tenant_a, "ENABLE_WORKSHOP")
    _enable(tenant_b, "ENABLE_WORKSHOP")
    job = JobCard.objects.create(
        company=tenant_b.company, customer=make_customer(tenant_b.company), complaint="secret", number="JOB-ISO",
    )
    assert tenant_a.client.get(f"/api/v1/workshop/job-cards/{job.pk}/").status_code == 404
    listing = tenant_a.client.get("/api/v1/workshop/job-cards/")
    assert listing.status_code == 200, listing.data
    assert job.pk not in _ids(listing.data)
    patched = tenant_a.client.patch(f"/api/v1/workshop/job-cards/{job.pk}/", {"complaint": "hijack"}, format="json")
    assert patched.status_code in (403, 404, 405)
    job.refresh_from_db()
    assert job.complaint == "secret"


def test_project_is_not_readable_across_tenants(tenant_a, tenant_b):
    from tests.conftest import make_customer
    from projects.models import Project

    _enable(tenant_a, "ENABLE_PROJECTS")
    _enable(tenant_b, "ENABLE_PROJECTS")
    project = Project.objects.create(
        company=tenant_b.company, customer=make_customer(tenant_b.company), name="Secret site", number="PRJ-ISO",
    )
    assert tenant_a.client.get(f"/api/v1/projects/{project.pk}/").status_code == 404
    listing = tenant_a.client.get("/api/v1/projects/")
    assert listing.status_code == 200, listing.data
    assert project.pk not in _ids(listing.data)
    patched = tenant_a.client.patch(f"/api/v1/projects/{project.pk}/", {"name": "hijack"}, format="json")
    assert patched.status_code in (403, 404, 405)
    project.refresh_from_db()
    assert project.name == "Secret site"


def test_policy_is_not_readable_across_tenants(tenant_a, tenant_b):
    from django.utils import timezone

    from insurance.models import Policy, PolicyProduct
    from tests.conftest import make_customer

    _enable(tenant_a, "ENABLE_INSURANCE")
    _enable(tenant_b, "ENABLE_INSURANCE")
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.owner).update(can_manage_policies=True)
    CompanyUser.objects.filter(company=tenant_b.company, user=tenant_b.owner).update(can_manage_policies=True)
    product = PolicyProduct.objects.create(
        company=tenant_b.company, name="Cover", insurer_name="Insurer", line="OTHER",
        tenure_months=1, sum_insured=1, premium=1,
    )
    today = timezone.localdate()
    policy = Policy.objects.create(
        company=tenant_b.company, customer=make_customer(tenant_b.company), product=product,
        nominee="Secret", start_date=today, end_date=today, premium=1, number="POL-ISO",
    )
    assert tenant_a.client.get(f"/api/v1/insurance/policies/{policy.pk}/").status_code == 404
    listing = tenant_a.client.get("/api/v1/insurance/policies/")
    assert listing.status_code == 200, listing.data
    assert policy.pk not in _ids(listing.data)
    patched = tenant_a.client.patch(
        f"/api/v1/insurance/policies/{policy.pk}/", {"nominee": "hijack"}, format="json",
    )
    assert patched.status_code in (403, 404, 405)
    policy.refresh_from_db()
    assert policy.nominee == "Secret"


def test_shared_ticket_is_not_readable_across_tenants(tenant_a, tenant_b):
    from django.utils import timezone

    from support.models import VendorTicketShare

    _enable(tenant_a, "ENABLE_SUPPORT_TICKETS")
    _enable(tenant_b, "ENABLE_SUPPORT_TICKETS")
    share = VendorTicketShare.objects.create(
        company=tenant_b.company,
        vendor_company=tenant_b.company,
        source_company=tenant_a.company,
        source_ticket_id=1,
        subject="Secret",
        status="OPEN",
        shared_at=timezone.now(),
    )
    assert tenant_a.client.get(f"/api/v1/support/shared/{share.pk}/").status_code == 404
    listing = tenant_a.client.get("/api/v1/support/shared/")
    assert listing.status_code == 200, listing.data
    assert share.pk not in _ids(listing.data)
    posted = tenant_a.client.post("/api/v1/support/shared/", {"subject": "hijack"}, format="json")
    assert posted.status_code in (403, 405)
    share.refresh_from_db()
    assert share.subject == "Secret"
