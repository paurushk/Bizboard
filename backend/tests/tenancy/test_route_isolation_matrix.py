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
    sid = transaction.savepoint()
    try:
        resp = getattr(client, method)(url, {}, format="json") if method != "get" else client.get(url)
    except Exception:
        transaction.savepoint_rollback(sid)
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
