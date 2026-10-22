"""Behavioural cross-tenant matrix over the whole API surface (F-SEC-01 / PRE-5).

``test_endpoint_isolation.py`` proves scoping by *reading class source* for the word
"company" and exempts any route whose name contains "plan", "help", "public",
"auth" ... That is a heuristic. This test is behavioural:

1. Enumerate every ``/api/v1/`` route from the generated OpenAPI schema (same source
   CI already diffs), keep those with exactly one path parameter (detail routes and
   detail actions).
2. Resolve the view -> its model; make a row of that model owned by TENANT B
   (generic builder, no per-model factory), using a pk tenant A does not own.
3. As TENANT A, call the route with every documented method and B's pk.
   * 2xx  -> LEAK (A read/changed/deleted B's row)            -> test fails
   * 5xx  -> unscoped lookup crashing instead of 404           -> test fails
   * 403 / 404 / 405                                           -> isolated
   * other 4xx (400/409/415/422) -> INCONCLUSIVE (validation may run before lookup)
4. For GET routes a control request as TENANT B must return 200, proving the route
   is live. Otherwise a feature-flag/permission 404 would look like "isolated".
5. List routes: B's row must not appear in A's list.

Coverage is reported and ratcheted (``MIN_*``), so the matrix cannot silently
shrink to nothing. Routes that cannot be probed (several path params, no model, a
model without a ``company`` column, a row that cannot be built) are *counted*, not
hidden: ``tests/tenancy/_route_matrix_unprobed.txt`` lists them and may only shrink.
"""

from __future__ import annotations

import datetime as dt
import decimal
import pathlib
import re
import uuid
from unittest import mock

import pytest
from django.apps import apps
from django.db import models, transaction
from django.urls import Resolver404, resolve
from django.utils import timezone

pytestmark = pytest.mark.django_db

HERE = pathlib.Path(__file__).parent
UNPROBED_FILE = HERE / "_route_matrix_unprobed.txt"

# Ratchets. Raise these as coverage grows; never lower them to make a failure pass.
MIN_PROBED_ROUTES = 240
MIN_CONTROLLED_GET_ROUTES = 80

_PARAM = re.compile(r"\{([^}]+)\}")
_METHODS = ("get", "post", "put", "patch", "delete")
_LEAK = "LEAK"


# --- generic row builder ------------------------------------------------------

_BUILD_ERRORS: dict[str, str] = {}

# For APIViews that carry no queryset: the model a ``<name>_id`` path param refers to.
PARAM_MODELS = {
    "customer_id": "masters.Customer",
    "supplier_id": "masters.Supplier",
    "thread_id": "insights.AssistantThread",
    "invoice_id": "sales.SalesInvoice",
}

# Per-route model overrides for views whose queryset is built in ``get_queryset``.
PATH_MODELS = {
    "/api/v1/crm/leads/ingest-jobs/{job_id}/": "crm.LeadIngestJob",
    "/api/v1/insights/assistant/threads/{id}/": "insights.AssistantThread",
    "/api/v1/integrations/tally/runs/{id}/errors/": "integrations.IntegrationSyncRun",
}


def _build_file_asset(company):
    from django.core.files.base import ContentFile

    from core.models import FileAsset

    return FileAsset.objects.create(
        company=company, kind="ATTACHMENT", original_name="iso.txt", content_type="text/plain",
        size=1, file=ContentFile(b"x", name="iso.txt"),
    )


def _build_import_job(company):
    from imports.models import ImportJob

    kind = ImportJob._meta.get_field("kind").choices[0][0]
    return ImportJob.objects.create(company=company, kind=kind, file=_build_file_asset(company))


def _build_referral_code(company):
    from crm.models import ReferralCode
    from tests.conftest import make_customer

    return ReferralCode.objects.create(
        company=company, referrer_customer=make_customer(company, name="Referrer"), code="ISO-REF",
    )


def _build_referral_reward(company):
    from crm.models import Lead, Opportunity, ReferralReward

    code = _ensure_row(__import__("crm.models", fromlist=["ReferralCode"]).ReferralCode, company) or _build_referral_code(company)
    lead = _ensure_row(Lead, company)
    opp = _ensure_row(Opportunity, company)
    if not (lead and opp):
        return None
    return ReferralReward.objects.create(
        company=company, referral_code=code, lead=lead, opportunity=opp, reward_amount=decimal.Decimal("1"),
    )


def _build_stock_transfer(company):
    from inventory.models import StockTransfer, Warehouse

    a = Warehouse.objects.filter(company=company).first() or Warehouse.objects.create(
        company=company, name="WH-A", code="ISO-A", is_default=True)
    b = Warehouse.objects.exclude(pk=a.pk).filter(company=company).first() or Warehouse.objects.create(
        company=company, name="WH-B", code="ISO-B")
    return StockTransfer.objects.create(company=company, from_warehouse=a, to_warehouse=b, number="TR-ISO")


def _build_payment_allocation(company):
    from payments.models import CustomerReceipt, PaymentAllocation
    from sales.models import SalesInvoice

    receipt = _ensure_row(CustomerReceipt, company)
    invoice = _ensure_row(SalesInvoice, company)
    if not (receipt and invoice):
        return None
    return PaymentAllocation.objects.create(
        company=company, receipt=receipt, sales_invoice=invoice, amount=decimal.Decimal("1"),
    )


# Models whose constraints defeat the generic builder.
BUILDERS = {
    "FileAsset": _build_file_asset,
    "ImportJob": _build_import_job,
    "ReferralCode": _build_referral_code,
    "ReferralReward": _build_referral_reward,
    "StockTransfer": _build_stock_transfer,
    "PaymentAllocation": _build_payment_allocation,
}

def _value_for(field, company, depth):
    if field.choices:
        return field.choices[0][0]
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field, (models.CharField, models.TextField)):
        return ("x" * 3)[: field.max_length or 3] if field.max_length else "xxx"
    if isinstance(field, models.EmailField):
        return "iso@example.test"
    if isinstance(field, models.DecimalField):
        return decimal.Decimal("1")
    if isinstance(field, (models.IntegerField, models.AutoField)):
        return 1
    if isinstance(field, models.FloatField):
        return 1.0
    if isinstance(field, models.DateTimeField):
        return timezone.now()
    if isinstance(field, models.DateField):
        return timezone.localdate()
    if isinstance(field, models.TimeField):
        return dt.time(10, 0)
    if isinstance(field, models.UUIDField):
        return uuid.uuid4()
    if isinstance(field, models.JSONField):
        return {}
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        return _ensure_row(field.related_model, company, depth + 1)
    return None


def _ensure_row(model, company, depth=0):
    """Return a row of ``model`` owned by ``company`` (or None if it cannot be built)."""
    if depth > 4:
        return None
    names = {f.name for f in model._meta.concrete_fields}
    scoped = "company" in names
    if model._meta.model_name == "company":
        return company
    qs = model._default_manager.all()
    if scoped:
        qs = qs.filter(company=company)
    elif depth == 0:
        return None  # not tenant-owned: nothing to isolate
    existing = qs.first()
    if existing is not None:
        return existing
    custom = BUILDERS.get(model.__name__)
    if custom is not None:
        try:
            with transaction.atomic():
                return custom(company)
        except Exception as exc:  # noqa: BLE001
            _BUILD_ERRORS[model.__name__] = f"{type(exc).__name__}: {str(exc)[:160]}"
            return None
    kwargs = {}
    for f in model._meta.concrete_fields:
        if f.primary_key and (f.auto_created or isinstance(f, models.AutoField)):
            continue
        if f.name == "company":
            kwargs["company"] = company
            continue
        if f.has_default() or f.null or f.blank and not isinstance(f, (models.ForeignKey,)):
            if not isinstance(f, (models.ForeignKey, models.OneToOneField)) or f.null:
                continue
        v = _value_for(f, company, depth)
        if v is None:
            return None
        kwargs[f.name] = v
    try:
        with transaction.atomic():
            return model._default_manager.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 — a model we cannot build generically is reported, not fatal
        _BUILD_ERRORS[model.__name__] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return None


# --- route discovery ----------------------------------------------------------

def _schema_paths():
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)["paths"]


def _model_of(view_cls):
    qs = getattr(view_cls, "queryset", None)
    if qs is not None and hasattr(qs, "model"):
        return qs.model
    ser = getattr(view_cls, "serializer_class", None)
    meta = getattr(ser, "Meta", None)
    return getattr(meta, "model", None)


def _pk_of(row):
    return row.pk


def _contains_id(payload, pk):
    if isinstance(payload, dict):
        if payload.get("id") == pk:
            return True
        return any(_contains_id(v, pk) for v in payload.values() if isinstance(v, (dict, list)))
    if isinstance(payload, list):
        return any(_contains_id(v, pk) for v in payload)
    return False


def _call(client, method, url):
    """Issue one request inside a savepoint so a DB error in one probe (which marks the
    test transaction for rollback) cannot poison every probe after it."""
    # A probe against an unscoped route can fail deep inside the request and leave the test
    # transaction flagged broken without unwinding to this level; the SQL transaction is still
    # sound, so clear the flag or no later probe could open its savepoint.
    transaction.get_connection().needs_rollback = False
    sid = transaction.savepoint()
    try:
        resp = getattr(client, method)(url, {}, format="json") if method != "get" else client.get(url)
    except Exception:
        transaction.savepoint_rollback(sid)
        # the failed probe marked the test transaction broken; the savepoint rollback undid it,
        # so clear the flag or the next probe cannot even open its own savepoint
        transaction.get_connection().needs_rollback = False
        raise
    conn = transaction.get_connection()
    if conn.needs_rollback:
        conn.needs_rollback = False
        transaction.savepoint_rollback(sid)
    else:
        transaction.savepoint_commit(sid)
    return resp


def _body(resp):
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


@pytest.mark.invariant_skip("inventory.balance_equals_movements", "inventory.serial_traceability", "roadmap.vendor_share_company_is_vendor", reason="cross-tenant fixture rows are built through the ORM; serial rows are created directly through the ORM, without a godown or movement; stock balances or movements are written directly through the ORM")
def test_every_detail_route_is_isolated_across_tenants(tenant_a, tenant_b):

    # Turn every rollout-grantable flag on for both tenants so a flag gate does not
    # make a route look isolated for the wrong reason.
    from core.services.feature_flags import ROLLOUT_GRANTABLE_KEYS

    for t in (tenant_a, tenant_b):
        t.company.feature_flags = {k: True for k in ROLLOUT_GRANTABLE_KEYS}
        t.company.accounting_enabled = True
        t.company.save(update_fields=["feature_flags", "accounting_enabled"])

    paths = _schema_paths()
    probed, controlled, inconclusive, leaks, crashes = [], [], [], [], []
    unprobed: dict[str, str] = {}
    list_checked = 0

    with mock.patch("requests.sessions.Session.request", side_effect=ConnectionError("blocked in test")):
        for path, ops in sorted(paths.items()):
            if not path.startswith("/api/v1/"):
                continue
            params = _PARAM.findall(path)
            methods = [m for m in _METHODS if m in ops]
            if not methods:
                continue
            probe_url = _PARAM.sub("999999999", path)
            try:
                match = resolve(probe_url)
            except Resolver404:
                unprobed[path] = "unresolvable"
                continue
            view_cls = getattr(match.func, "cls", None) or getattr(match.func, "view_class", None)
            model = _model_of(view_cls) if view_cls else None
            if path in PATH_MODELS:
                model = apps.get_model(PATH_MODELS[path])
            elif model is None and len(params) == 1 and params[0] in PARAM_MODELS:
                model = apps.get_model(PARAM_MODELS[params[0]])

            if len(params) == 0:
                # LIST route: B's row must not appear in A's list.
                if "get" in methods and model is not None and "company" in {f.name for f in model._meta.concrete_fields}:
                    row_b = _ensure_row(model, tenant_b.company)
                    if row_b is not None and not model._default_manager.filter(
                        pk=row_b.pk, company=tenant_a.company
                    ).exists():
                        resp = _call(tenant_a.client, "get", path)
                        if resp.status_code == 200 and _contains_id(_body(resp), _pk_of(row_b)):
                            leaks.append(f"LIST {path}: tenant B row {row_b.pk} visible to tenant A")
                        list_checked += 1
                continue

            if len(params) != 1:
                unprobed[path] = f"{len(params)} path params"
                continue
            if model is None:
                unprobed[path] = "view has no queryset/serializer model"
                continue
            if "company" not in {f.name for f in model._meta.concrete_fields} and model._meta.model_name != "company":
                unprobed[path] = f"{model.__name__} has no company column"
                continue

            row_b = None
            for _ in range(3):
                cand = _ensure_row(model, tenant_b.company)
                if cand is None:
                    break
                if not model._default_manager.filter(pk=cand.pk, company=tenant_a.company).exists():
                    row_b = cand
                    break
                # pk collides with one of A's own rows; make another B row.
                cand_new = None
                try:
                    with transaction.atomic():
                        cand.pk = None
                        cand._state.adding = True
                        cand.save()
                        cand_new = cand
                except Exception:  # noqa: BLE001
                    break
                if cand_new and not model._default_manager.filter(pk=cand_new.pk, company=tenant_a.company).exists():
                    row_b = cand_new
                    break
            if row_b is None:
                unprobed[path] = (
                    f"could not build a {model.__name__} row for tenant B"
                    f" ({_BUILD_ERRORS.get(model.__name__, 'no error captured')})"
                )
                continue

            url = _PARAM.sub(str(row_b.pk), path)
            path_ok = True
            for m in methods:
                try:
                    resp = _call(tenant_a.client, m, url)
                except Exception as exc:  # noqa: BLE001
                    crashes.append(f"{m.upper()} {path}: raised {type(exc).__name__}: {exc}")
                    path_ok = False
                    continue
                sc = resp.status_code
                if 200 <= sc < 300:
                    leaks.append(f"{m.upper()} {path}: tenant A got {sc} for tenant B's {model.__name__} {row_b.pk}")
                    path_ok = False
                elif sc >= 500:
                    crashes.append(f"{m.upper()} {path}: tenant A got {sc} (unscoped lookup should be 404)")
                    path_ok = False
                elif sc not in (403, 404, 405):
                    inconclusive.append(f"{m.upper()} {path}: {sc}")
            if path_ok:
                probed.append(path)
            if "get" in methods:
                ctrl = _call(tenant_b.client, "get", url)
                if ctrl.status_code == 200:
                    controlled.append(path)

    summary = (
        f"probed={len(probed)} controlled_get={len(controlled)} list_checked={list_checked} "
        f"inconclusive={len(inconclusive)} unprobed={len(unprobed)}"
    )
    print("\n[route-isolation-matrix]", summary)
    for line in inconclusive:
        print("[route-isolation-matrix] INCONCLUSIVE", line)
    for p_, why in sorted(unprobed.items()):
        print("[route-isolation-matrix] UNPROBED", p_, "#", why)

    assert not leaks, "CROSS-TENANT LEAKS:\n  " + "\n  ".join(leaks)
    assert not crashes, "cross-tenant requests crashed (should be 404):\n  " + "\n  ".join(crashes)

    # The unprobed list is a ratchet: it may only shrink.
    if UNPROBED_FILE.exists():
        allowed = {
            ln.split("#", 1)[0].strip() for ln in UNPROBED_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        }
        new = sorted(set(unprobed) - allowed)
        assert not new, (
            "New route(s) the isolation matrix cannot probe. Make them probeable (single path "
            "param + company-owned model) or add them to tests/tenancy/_route_matrix_unprobed.txt "
            "WITH a reason and a hand-written cross-tenant test:\n  "
            + "\n  ".join(f"{p}   # {unprobed[p]}" for p in new)
        )

    assert len(probed) >= MIN_PROBED_ROUTES, f"matrix coverage shrank: {summary}"
    assert len(controlled) >= MIN_CONTROLLED_GET_ROUTES, f"too few live-controlled routes: {summary}"


# --- routes the generic matrix cannot drive (two path params / required query) ---

def _grant_all(*tenants):
    from core.services.feature_flags import ROLLOUT_GRANTABLE_KEYS

    for t in tenants:
        t.company.feature_flags = {k: True for k in ROLLOUT_GRANTABLE_KEYS}
        t.company.accounting_enabled = True
        t.company.save(update_fields=["feature_flags", "accounting_enabled"])


def _assert_isolated(resp, label):
    assert resp.status_code in (400, 403, 404, 405), f"{label}: tenant A got {resp.status_code}"
    body = resp.content[:400]
    assert b'"success":true' not in body, f"{label}: tenant A got a success envelope"


def test_collection_risk_is_isolated(tenant_a, tenant_b):
    from tests.conftest import make_customer

    _grant_all(tenant_a, tenant_b)
    cust = make_customer(tenant_b.company, name="Secret Debtor")
    assert tenant_b.client.get(f"/api/v1/payments/collection-risk/{cust.pk}/").status_code == 200  # control
    resp = tenant_a.client.get(f"/api/v1/payments/collection-risk/{cust.pk}/")
    _assert_isolated(resp, "collection-risk")
    assert b"Secret Debtor" not in resp.content


def test_supplier_price_history_is_isolated(tenant_a, tenant_b):
    from tests.conftest import make_product, make_supplier

    _grant_all(tenant_a, tenant_b)
    sup = make_supplier(tenant_b.company, name="Secret Supplier")
    prod = make_product(tenant_b.company, name="Secret Product", sku="SEC-1")
    url = f"/api/v1/purchases/suppliers/{sup.pk}/price-history/?product={prod.pk}"
    assert tenant_b.client.get(url).status_code == 200  # control
    resp = tenant_a.client.get(url)
    _assert_isolated(resp, "price-history")
    assert b"Secret" not in resp.content


def test_opportunity_line_detail_is_isolated(tenant_a, tenant_b):
    from crm.models import Opportunity, OpportunityLine

    _grant_all(tenant_a, tenant_b)
    opp = _ensure_row(Opportunity, tenant_b.company)
    line = _ensure_row(OpportunityLine, tenant_b.company)
    assert opp is not None and line is not None, _BUILD_ERRORS
    url = f"/api/v1/crm/opportunities/{line.opportunity_id}/lines/{line.pk}/"
    for method in ("get", "patch", "delete"):
        resp = getattr(tenant_a.client, method)(url, **({"data": {}, "format": "json"} if method != "get" else {}))
        _assert_isolated(resp, f"opportunity line {method}")
    assert OpportunityLine.objects.filter(pk=line.pk).exists()


def test_project_milestone_actions_are_isolated(tenant_a, tenant_b):
    from projects.models import ProjectMilestone

    _grant_all(tenant_a, tenant_b)
    ms = _ensure_row(ProjectMilestone, tenant_b.company)
    assert ms is not None, _BUILD_ERRORS
    for action in ("invoice", "ready"):
        url = f"/api/v1/projects/{ms.project_id}/milestones/{ms.pk}/{action}/"
        resp = tenant_a.client.post(url, {}, format="json")
        _assert_isolated(resp, f"milestone {action}")
    ms.refresh_from_db()
    assert ms.status == ProjectMilestone._meta.get_field("status").get_default()


def test_pod_slip_pdf_is_isolated(tenant_a, tenant_b):
    from sales.models import DeliveryRouteStop

    _grant_all(tenant_a, tenant_b)
    stop = _ensure_row(DeliveryRouteStop, tenant_b.company)
    assert stop is not None, _BUILD_ERRORS
    url = f"/api/v1/sales/delivery-routes/{stop.route_id}/stops/{stop.pk}/pod.pdf"
    resp = tenant_a.client.get(url)
    assert resp.status_code in (403, 404), f"pod slip: tenant A got {resp.status_code}"
    assert resp.get("Content-Type", "").split(";")[0] != "application/pdf"


def test_route_planning_and_cashier_actions_are_isolated(tenant_a, tenant_b):
    """Preflight, cancel, cashier count and receipt link on another tenant's route: never 2xx, never a change."""
    from sales.models import DeliveryRoute

    _grant_all(tenant_a, tenant_b)
    route = _ensure_row(DeliveryRoute, tenant_b.company)
    assert route is not None, _BUILD_ERRORS
    before = (route.status, route.updated_at)
    base = f"/api/v1/sales/delivery-routes/{route.pk}"
    resp = tenant_a.client.get(f"{base}/preflight/")
    assert resp.status_code in (403, 404), f"preflight: tenant A got {resp.status_code}"
    for action in ("cancel", "verify-handover", "link-receipt", "add-orders", "start"):
        resp = tenant_a.client.post(f"{base}/{action}/", {"orderIds": [], "cash": "0", "upi": "0"}, format="json")
        assert resp.status_code in (400, 403, 404), f"{action}: tenant A got {resp.status_code}"
        assert resp.status_code != 400 or action == "add-orders", f"{action}: validation ran before the lookup"
    route.refresh_from_db()
    assert (route.status, route.updated_at) == before


def test_route_candidates_never_list_another_tenants_orders(tenant_a, tenant_b):
    from sales.models import SalesOrder

    _grant_all(tenant_a, tenant_b)
    order = _ensure_row(SalesOrder, tenant_b.company)
    assert order is not None, _BUILD_ERRORS
    order.status = SalesOrder.Status.CONFIRMED
    order.save(update_fields=["status"])
    resp = tenant_a.client.get("/api/v1/sales/delivery-routes/candidates/", {"show_unavailable": "true", "ids": str(order.pk)})
    assert resp.status_code == 200
    body = resp.json()
    body = body.get("data", body)
    assert body["count"] == 0


def test_dead_letter_replay_and_list_are_isolated(tenant_a, tenant_b):
    from billing.models import DeadLetterEvent

    _grant_all(tenant_a, tenant_b)
    ev = DeadLetterEvent.objects.create(
        company=tenant_b.company, provider="razorpay", event_id="iso-evt-b", payload={"secret": "b-only"},
    )
    resp = tenant_a.client.post(f"/api/v1/billing/dlq/{ev.pk}/replay/", {}, format="json")
    assert resp.status_code in (403, 404), f"tenant A got {resp.status_code} replaying tenant B's DLQ event"
    ev.refresh_from_db()
    assert ev.status == DeadLetterEvent.Status.PENDING and ev.replayed_at is None
    listing = tenant_a.client.get("/api/v1/billing/dlq/")
    assert b"iso-evt-b" not in listing.content and b"b-only" not in listing.content


@pytest.mark.invariant_skip("inventory.balance_equals_movements", "inventory.serial_traceability", "roadmap.vendor_share_company_is_vendor", "tenancy.stock_rows_same_company", reason="cross-tenant fixture rows are built through the ORM; serial rows are created directly through the ORM, without a godown or movement; stock balances or movements are written directly through the ORM")
def test_matrix_detects_removed_scoping(tenant_a, tenant_b, monkeypatch):
    """Test the test: with the tenant filter removed from the base viewset the matrix
    must report leaks. A matrix that cannot fail proves nothing."""
    from rest_framework import viewsets

    from core.viewsets import CompanyScopedViewSet

    paths = _schema_paths()  # generate the schema BEFORE mutating
    monkeypatch.setitem(globals(), "_schema_paths", lambda: paths)
    monkeypatch.setattr(
        CompanyScopedViewSet, "get_queryset", lambda self: viewsets.ModelViewSet.get_queryset(self)
    )
    with pytest.raises(AssertionError) as ei:
        test_every_detail_route_is_isolated_across_tenants(tenant_a, tenant_b)
    msg = str(ei.value)
    assert "CROSS-TENANT LEAKS" in msg
    assert msg.count("tenant A got 200") >= 20, "expected many leaks once scoping is removed"


def test_unprobed_file_has_no_stale_entries_and_every_entry_has_a_reason():
    """The ratchet file may only shrink. A route that was renamed or removed must leave the file,
    and 'covered by' entries must name a test that really exists in this module."""
    lines = [ln for ln in UNPROBED_FILE.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    assert lines, "the file exists to record the few routes the matrix cannot drive"
    paths = _schema_paths()
    module_source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for ln in lines:
        path, _, reason = ln.partition("#")
        path, reason = path.strip(), reason.strip()
        assert path in paths, f"stale entry (route no longer exists): {path}"
        assert len(reason) >= 15, f"{path}: every entry needs a real reason"
        if reason.startswith("covered by "):
            test_name = reason.split()[2]
            assert f"def {test_name}(" in module_source, f"{path}: '{test_name}' does not exist"


def test_the_matrix_floors_have_not_been_lowered():
    """MIN_* are ratchets. If you are here because a floor blocked you, fix coverage instead."""
    assert MIN_PROBED_ROUTES >= 240
    assert MIN_CONTROLLED_GET_ROUTES >= 80


def test_public_token_routes_are_explicitly_listed_not_silently_skipped():
    text = UNPROBED_FILE.read_text(encoding="utf-8")
    for needle in ("/api/v1/public/pay/{token}/", "/api/v1/public/customer-portal/{token}/", "/api/v1/webhooks/payments/{provider}/"):
        assert needle in text, f"{needle} must stay documented as public-by-design"


def test_milestone_edit_and_delete_are_isolated(tenant_a, tenant_b):
    from projects.models import ProjectMilestone

    _grant_all(tenant_a, tenant_b)
    ms = _ensure_row(ProjectMilestone, tenant_b.company)
    assert ms is not None, _BUILD_ERRORS
    before = (ms.name, ms.status)
    for action in ("edit", "delete"):
        url = f"/api/v1/projects/{ms.project_id}/milestones/{ms.pk}/{action}/"
        resp = tenant_a.client.post(url, {"name": "hijacked"}, format="json")
        _assert_isolated(resp, f"milestone {action}")
    ms.refresh_from_db()
    assert (ms.name, ms.status) == before


def test_approval_decide_is_isolated(tenant_a, tenant_b):
    from planwave.models import ApprovalRequest
    from planwave.services import submit_approval

    row = submit_approval(
        company=tenant_b.company, action="invoice_cancel", requester=tenant_b.staff, payload={"invoice": 1},
    )
    resp = tenant_a.client.post(f"/api/v1/plan/approvals/{row.pk}/decide/", {"accept": True}, format="json")
    _assert_isolated(resp, "approval decide")
    row = ApprovalRequest.objects.get(pk=row.pk)
    assert row.status == ApprovalRequest.Status.PENDING and row.approver_id is None
    # control: the owning tenant's owner can decide it
    assert tenant_b.client.post(
        f"/api/v1/plan/approvals/{row.pk}/decide/", {"accept": True}, format="json",
    ).status_code == 200


def test_shopify_pending_apply_is_isolated(tenant_a, tenant_b):
    from integrations.models import IntegrationConnection
    from masters.models import Product
    from tests.conftest import make_product

    _grant_all(tenant_a, tenant_b)
    product = make_product(tenant_b.company, sku="SHOP-ISO")
    conn_b = IntegrationConnection.objects.create(
        company=tenant_b.company, provider=IntegrationConnection.Provider.SHOPIFY,
        status=IntegrationConnection.Status.ACTIVE, shop_domain="b.myshopify.com",
        metadata={"shopify_pending": {"gid-1": {"sku": product.sku, "delta": "5", "updated_at": "x"}}},
    )
    # tenant A has no Shopify connection at all, and must not reach B's held change
    resp = tenant_a.client.post("/api/v1/integrations/shopify/pending/gid-1/apply/", {}, format="json")
    _assert_isolated(resp, "shopify pending apply")
    conn_b.refresh_from_db()
    assert "gid-1" in conn_b.metadata["shopify_pending"]
    assert Product.objects.get(pk=product.pk).pk == product.pk


def test_public_invoice_link_never_crosses_tenants(tenant_a, tenant_b):
    """A public invoice token opens only its own invoice, and tenant B cannot mint or revoke A's link."""
    from rest_framework.test import APIClient

    from sales.models import InvoicePublicLink
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    product = make_product(tenant_a.company, sku="ISO-PUB", hsn_code="3004", gst_rate="18")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Iso Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"},
    ])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    minted = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/")
    assert minted.status_code == 200, minted.data
    token = minted.data["url"].rsplit("/", 1)[-1]

    # Tenant B has no route to A's invoice, either to mint or to revoke.
    assert tenant_b.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/").status_code == 404
    assert tenant_b.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/revoke/").status_code == 404
    assert InvoicePublicLink.objects.get(token=token).revoked_at is None

    anon = APIClient()
    page = anon.get(f"/api/v1/public/invoices/{token}/")
    assert page.status_code == 200
    assert page.data["bill_to"]["name"] == "Iso Buyer"
    # A guessed or foreign-looking token reveals nothing, and does not say whether it existed.
    for bad in ("x" * 43, token[:-1] + ("A" if token[-1] != "A" else "B")):
        for suffix in ("", "pdf/", "pay/"):
            call = anon.post if suffix == "pay/" else anon.get
            res = call(f"/api/v1/public/invoices/{bad}/{suffix}")
            assert res.status_code == 404, (bad, suffix, res.status_code)


def test_public_quotation_link_never_crosses_tenants(tenant_a, tenant_b):
    """Each shared quotation token opens only its own quotation; tenant B cannot reach A's quote or link."""
    from rest_framework.test import APIClient

    from sales.models import QuotationPublicLink
    from tests.conftest import make_customer, make_product

    def make_quote(tenant, name):
        product = make_product(tenant.company, sku=f"ISO-Q-{name}")
        customer = make_customer(tenant.company, name=name)
        resp = tenant.client.post(
            "/api/v1/sales/quotations/",
            {"customer": customer.id, "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}]},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        return resp.data["id"]

    quote_a = make_quote(tenant_a, "Alpha Buyer")
    quote_b = make_quote(tenant_b, "Beta Buyer")
    token_a = tenant_a.client.post(f"/api/v1/sales/quotations/{quote_a}/share/", {}, format="json").data["url"].rsplit("/", 1)[-1]
    token_b = tenant_b.client.post(f"/api/v1/sales/quotations/{quote_b}/share/", {}, format="json").data["url"].rsplit("/", 1)[-1]

    # Tenant B has no route to A's quotation, to share, link, revoke or copy it.
    for suffix in ("share/", "public-link/", "public-link/revoke/", "duplicate/"):
        assert tenant_b.client.post(f"/api/v1/sales/quotations/{quote_a}/{suffix}", {}, format="json").status_code == 404, suffix
    assert QuotationPublicLink.objects.get(token=token_a).revoked_at is None

    anon = APIClient()
    assert anon.get(f"/api/v1/public/quotations/{token_a}/").data["bill_to"]["name"] == "Alpha Buyer"
    assert anon.get(f"/api/v1/public/quotations/{token_b}/").data["bill_to"]["name"] == "Beta Buyer"
    # A guessed or altered token reveals nothing.
    for bad in ("x" * 43, token_a[:-1] + ("A" if token_a[-1] != "A" else "B")):
        for suffix in ("", "pdf/"):
            assert anon.get(f"/api/v1/public/quotations/{bad}/{suffix}").status_code == 404, (bad, suffix)


def _money_in_receipt(tenant, customer, amount):
    from decimal import Decimal

    from payments.services import PaymentService

    return PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal(amount), mode="CASH", user=tenant.owner
    )


def test_public_receipt_voucher_never_crosses_tenants(tenant_a, tenant_b, client):
    from django.core import signing

    from payments.receipt_share import SALT, mint_voucher_token
    from tests.conftest import make_customer

    theirs = _money_in_receipt(tenant_b, make_customer(tenant_b.company), "10")
    # A token minted for tenant B's receipt names tenant B; asking for it as tenant A's company, or
    # with the company swapped, never resolves.
    swapped = signing.dumps({"r": theirs.pk, "c": tenant_a.company.pk}, salt=SALT)
    assert client.get(f"/api/v1/public/receipt-voucher/{swapped}/").status_code == 404
    assert client.get(f"/api/v1/public/receipt-voucher/{mint_voucher_token(theirs)}/").status_code == 200


def test_portal_receipt_voucher_never_crosses_customers_or_tenants(tenant_a, tenant_b):
    from datetime import timedelta

    from django.utils import timezone
    from payments.models import CustomerPortalToken
    from rest_framework.test import APIClient

    from tests.conftest import make_customer

    for tenant in (tenant_a, tenant_b):
        tenant.company.feature_flags = {**(tenant.company.feature_flags or {}), "ENABLE_CUSTOMER_PORTAL": True}
        tenant.company.save(update_fields=["feature_flags"])
    mine = make_customer(tenant_a.company, name="Mine")
    other_customer = make_customer(tenant_a.company, name="Someone else")
    theirs = make_customer(tenant_b.company, name="Theirs")
    own = _money_in_receipt(tenant_a, mine, "10")
    others = _money_in_receipt(tenant_a, other_customer, "10")
    foreign = _money_in_receipt(tenant_b, theirs, "10")
    row = CustomerPortalToken.objects.create(
        company=tenant_a.company, customer=mine, token="portal-iso-1",
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    anon = APIClient()
    base = f"/api/v1/public/customer-portal/{row.token}/receipts"
    if anon.get(f"/api/v1/public/customer-portal/{row.token}/").status_code == 404:
        pytest.skip("customer portal flag not enabled in this configuration")
    assert anon.get(f"{base}/{own.pk}/voucher/").status_code == 200
    assert anon.get(f"{base}/{others.pk}/voucher/").status_code == 404  # another customer, same company
    assert anon.get(f"{base}/{foreign.pk}/voucher/").status_code == 404  # another tenant


def test_manufacturing_routes_are_isolated(tenant_a, tenant_b):
    """Tenant A cannot read or act on tenant B's manufacturing records through any route the matrix cannot drive.

    The generic matrix needs one path parameter and a row it can build on its own; the manufacturing documents need a
    recipe, stock and a released order first, so they are built here and every route is tried with tenant B's ids.
    """
    from rest_framework.test import APIClient

    from inventory.models import BatchLot
    from manufacturing.models import DowntimeReason, WorkCentre
    from manufacturing.services import issue as issue_svc
    from manufacturing.services import planning, release_work_order, shopfloor
    from tests.conftest import make_product
    from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

    for t in (tenant_a, tenant_b):
        prepare(t, separate=True)
        t.company.feature_flags = {
            **(t.company.feature_flags or {}), "manufacturing_pack_grant": True, "MFG_PLANNING": True,
            "MFG_QUALITY": True, "MFG_JOB_WORK": True, "MFG_COSTING_GL": True, "MFG_SHOP_FLOOR": True,
        }
        t.company.save(update_fields=["feature_flags"])

    company, user = tenant_b.company, tenant_b.owner
    centre = WorkCentre.objects.create(company=company, code="ISO", name="Bench")
    fg = make_product(company, sku="ISO-FG", name="Secret finished good")
    raw = stocked(tenant_b, "ISO-RAW", 100, 10)
    bom = make_bom(company, fg, [(raw, 1)], user=user)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Secret step", "work_centre": centre, "run_minutes_per_unit": 1}], user)
    wo = release_work_order(make_wo(company, bom, 10, user=user), user)
    card = shopfloor.create_job_cards(wo, user)[0]
    from manufacturing.services import receipt as receipt_svc

    issue = issue_svc.create_issue(wo, user)

    receipt = receipt_svc.create_receipt(wo, user, {"lines": [{"kind": "MAIN", "qty_good": 1}]})
    taken = issue_svc.post_issue(issue_svc.create_issue(wo, user, [{"wo_line": wo.component_lines.first(), "qty": 2}]), user)
    ret = issue_svc.create_return(wo, user, [{"wo_line": wo.component_lines.first().pk, "qty": 1}])
    assert taken.status == "POSTED"
    run = planning.run_mrp(company, user, horizon_days=7)
    lot = BatchLot.objects.create(company=company, product=fg, batch_no="ISO-SECRET")
    reason = DowntimeReason.objects.create(company=company, code="ISO", name="Secret reason")
    event = shopfloor.start_downtime(company, None, work_centre=centre, reason=reason)

    # control: the owner of B reaches all of it, so a 404 for A means something
    assert tenant_b.client.get(f"/api/v1/manufacturing/work-orders/{wo.pk}/").status_code == 200
    assert tenant_b.client.get(f"/api/v1/manufacturing/job-cards/{card.pk}/").status_code == 200
    assert tenant_b.client.get(f"/api/v1/manufacturing/material-issues/{issue.pk}/").status_code == 200
    assert tenant_b.client.get(f"/api/v1/manufacturing/production-receipts/{receipt.pk}/").status_code == 200

    base = "/api/v1/manufacturing"
    tries = [
        ("get", f"{base}/boms/{bom.pk}/routing/"),
        ("put", f"{base}/boms/{bom.pk}/routing/"),
        ("get", f"{base}/job-cards/{card.pk}/"),
        ("get", f"{base}/job-cards/{card.pk}/subcontract-defaults/"),
        *[("post", f"{base}/job-cards/{card.pk}/{v}/") for v in ("start", "pause", "report", "finish", "reopen", "subcontract")],
        ("get", f"{base}/material-issues/{issue.pk}/"),
        ("get", f"{base}/material-issues/{issue.pk}/print/"),
        *[("post", f"{base}/material-issues/{issue.pk}/{v}/") for v in ("post", "reverse", "approve", "reject", "request-approval")],
        ("delete", f"{base}/material-issues/{issue.pk}/discard/"),
        ("get", f"{base}/production-receipts/{receipt.pk}/"),
        ("get", f"{base}/production-receipts/{receipt.pk}/print-label/"),
        *[("post", f"{base}/production-receipts/{receipt.pk}/{v}/") for v in ("post", "reverse")],
        ("delete", f"{base}/production-receipts/{receipt.pk}/discard/"),
        ("get", f"{base}/material-returns/{ret.pk}/"),
        *[("post", f"{base}/material-returns/{ret.pk}/{v}/") for v in ("post", "reverse")],
        ("delete", f"{base}/material-returns/{ret.pk}/discard/"),
        ("get", f"{base}/mrp-runs/{run.pk}/"),
        ("post", f"{base}/mrp-runs/{run.pk}/convert/"),
        ("get", f"{base}/work-orders/{wo.pk}/"),
        ("get", f"{base}/work-orders/{wo.pk}/print/"),
        ("get", f"{base}/work-orders/{wo.pk}/availability/"),
        *[("post", f"{base}/work-orders/{wo.pk}/{v}/") for v in ("release", "complete", "close", "cancel", "reopen", "set-priority")],
        ("post", f"/api/v1/quality/batches/{lot.pk}/status/"),
    ]
    for method, url in tries:
        resp = getattr(tenant_a.client, method)(url, {}, format="json") if method != "get" and method != "delete" else getattr(tenant_a.client, method)(url)
        _assert_isolated(resp, f"{method.upper()} {url}")
        for secret in (b"Secret finished good", b"Secret step", b"ISO-SECRET"):
            assert secret not in resp.content, f"{url} leaked {secret!r}"

    # a report is scoped by the company, not by an id in the path
    rep = tenant_a.client.get(f"{base}/reports/consumption/")
    assert rep.status_code == 200 and b"Secret finished good" not in rep.content and b"ISO-RAW" not in rep.content

    # the tablet: tenant A's operator cannot touch tenant B's job card or stoppage
    shopfloor.create_operator(tenant_a.company, tenant_a.owner, code="OPA", name="Asha", pin="4821")
    tablet = APIClient()
    login = tablet.post(f"{base}/tablet/login/", {"company": tenant_a.company.pk, "code": "OPA", "pin": "4821"}, format="json")
    assert login.status_code == 200, login.content[:200]
    hdr = {"HTTP_X_OPERATOR_TOKEN": login.json()["data"]["token"]}
    for verb in ("start", "pause", "report", "finish"):
        _assert_isolated(tablet.post(f"{base}/tablet/cards/{card.pk}/{verb}/", {}, format="json", **hdr), f"tablet {verb}")
    _assert_isolated(tablet.post(f"{base}/tablet/downtime/end/", {"event": event.pk}, format="json", **hdr), "tablet downtime end")
    cards = tablet.get(f"{base}/tablet/cards/", **hdr)
    assert cards.status_code == 200 and b"Secret step" not in cards.content
