import random
import zlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Company, CompanyUser, User
from django.core.cache import cache
from masters.models import Customer, Product, Supplier


@pytest.fixture(autouse=True)
def clear_cache_before_each_test():
    cache.clear()
    yield
    cache.clear()


# --- Phase 2: crown-jewel invariant sweep after each test -----------------
# For every Company created during a test, run core.invariants while the DB is
# still available (in the call phase, before pytest-django rolls back and revokes
# access). OFF by default — enable with INVARIANTS_STRICT=1 (the advisory
# `invariant-sweep` CI job does). Opt a test out with
# @pytest.mark.no_invariant_check when it deliberately builds a broken mid-state.
# Workflow tests call assert_all_invariants() explicitly regardless of the flag.

@pytest.fixture(autouse=True)
def _invariant_sweep_tracker(request):
    """Record Company pks created during the test; the check runs in the
    pytest_runtest_call hookwrapper below (still inside the DB window)."""
    import os

    request.node._inv_company_pks = None
    if os.environ.get("INVARIANTS_STRICT") != "1":
        yield
        return
    if request.node.get_closest_marker("no_invariant_check"):
        yield
        return

    from django.db.models.signals import post_save

    pks: set = set()
    request.node._inv_company_pks = pks

    def _track(sender, instance, created, **kwargs):
        if created and instance.pk is not None:
            pks.add(instance.pk)

    post_save.connect(_track, sender=Company, dispatch_uid="inv_sweep_track")
    try:
        yield
    finally:
        post_save.disconnect(sender=Company, dispatch_uid="inv_sweep_track")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    outcome = yield
    pks = getattr(item, "_inv_company_pks", None)
    if not pks or outcome.excinfo is not None:
        return
    from django.db import DatabaseError, connection, transaction

    # A test that deliberately provokes an IntegrityError leaves the transaction
    # unusable — nothing to sweep, and querying would raise TransactionManagementError.
    if getattr(connection, "needs_rollback", False) or not connection.in_atomic_block:
        return
    from core.invariants import InvariantViolation, assert_all_invariants

    try:
        with transaction.atomic():  # isolate the read; roll back cleanly on any error
            companies = list(Company.objects.filter(pk__in=pks))
            for company in companies:
                assert_all_invariants(company)
    except InvariantViolation as exc:
        outcome.force_exception(exc)
    except DatabaseError:
        return  # transaction was already broken by the test body


# --- Phase 1 determinism ---------------------------------------------------
# FG-1b: keep a single test run reproducible. `random` is seeded per test;
# clock-freeze and socket-ban are opt-in via env until the suite is triaged
# (TESTS_FREEZE_CLOCK=1 / TESTS_NO_SOCKET=1) — see scripts/ci_gates/GATE_INVENTORY.md.

@pytest.fixture(autouse=True)
def _deterministic_random():
    random.seed(0)
    yield


@pytest.fixture(autouse=True)
def _freeze_clock_opt_in():
    import os

    if os.environ.get("TESTS_FREEZE_CLOCK") != "1":
        yield
        return
    import time as _time

    from freezegun import freeze_time
    from rest_framework.throttling import SimpleRateThrottle

    # DRF's `SimpleRateThrottle.timer` is the bare `time.time` builtin captured
    # as a class attribute at import. Builtins aren't descriptors, so `self.timer()`
    # normally just calls `time.time()`. But freezegun's module sweep rewrites
    # every reference that `is time.time` to `fake_time` — a plain Python function,
    # which *does* bind as a method on instance access — so `self.timer()` becomes
    # `fake_time(self)` and every throttled endpoint 500s with "fake_time() takes
    # 0 positional arguments but 1 was given". Wrapping the real function in a
    # `staticmethod` breaks the `is time.time` identity check, so freezegun leaves
    # it alone and the throttle timer keeps ticking on the real clock (no test
    # asserts throttle timing under a frozen clock). Model/serializer timestamps
    # still freeze — they route through `django.utils.timezone.now`.
    _real_timer = SimpleRateThrottle.__dict__.get("timer", _time.time)
    SimpleRateThrottle.timer = staticmethod(_time.time)
    try:
        with freeze_time("2026-06-15 09:30:00"):
            yield
    finally:
        SimpleRateThrottle.timer = _real_timer


@pytest.fixture(autouse=True)
def _no_socket_opt_in():
    import os

    if os.environ.get("TESTS_NO_SOCKET") != "1":
        yield
        return
    try:
        import pytest_socket
    except ImportError:
        yield
        return
    pytest_socket.disable_socket(allow_unix_socket=True)
    try:
        yield
    finally:
        pytest_socket.enable_socket()


def _stable_phone(slug: str) -> str:
    """Deterministic 10-digit phone for a tenant slug.

    FREEZE-001: previously ``9{abs(hash(slug)) % 10**9:09d}`` — str hashing is
    salted per process (PYTHONHASHSEED), so the same slug produced a different
    phone every run, making any test that touched it non-reproducible.
    """
    return f"9{zlib.crc32(slug.encode('utf-8')) % 10**9:09d}"


def register_via_api(client, payload):
    """POST /auth/register/ requires a verified email OTP code. Fetches one
    via the debug-echo path (settings_test.py sets OTP_DEBUG_ECHO=True) and
    submits it alongside the caller's register payload — same shape any real
    call site would use for the two-step sign-up flow."""
    otp_resp = client.post(
        "/api/v1/auth/register/otp/request/", {"email": payload["email"]}, format="json",
    )
    code = otp_resp.data.get("debug_code")
    assert code, f"expected debug_code in OTP response, got {otp_resp.data!r}"
    return client.post(
        "/api/v1/auth/register/", {**payload, "otp_code": code}, format="json",
    )


def make_tenant(slug, state="Karnataka"):
    owner = User.objects.create_user(
        email=f"owner@{slug}.test", password="StrongPass123!", full_name=f"{slug} owner",
        phone=_stable_phone(slug),
    )
    staff = User.objects.create_user(
        email=f"staff@{slug}.test", password="StrongPass123!", full_name=f"{slug} staff",
    )
    company = Company.objects.create(
        name=f"{slug} Traders",
        state=state,
        ai_features_enabled=True,
        # Fixture companies are GST-capable shops. Skip-wizard empty-GSTIN is
        # tested explicitly (B14 / GSTIN_MISSING_COMPANY), not as the default.
        gstin="29AAAAA0000A1ZY",
        gstin_verification_status="VALID",
        gstin_verified_at=timezone.now(),
    )
    CompanyUser.objects.create(
        company=company, user=owner, role=CompanyUser.Role.OWNER,
        can_manage_inventory=True, can_import=True,
    )
    CompanyUser.objects.create(
        company=company, user=staff, role=CompanyUser.Role.SALES_STAFF,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    staff_client = APIClient()
    staff_client.force_authenticate(user=staff)
    return SimpleNamespace(
        company=company, owner=owner, staff=staff, client=client, staff_client=staff_client
    )


def make_product(company, name="Widget", sku="WID-1", gst_rate="18",
                 purchase_price="80", selling_price="100", reorder_level="0", **kwargs):
    return Product.objects.create(
        company=company, name=name, sku=sku, gst_rate=Decimal(gst_rate),
        purchase_price=Decimal(purchase_price), selling_price=Decimal(selling_price),
        reorder_level=Decimal(reorder_level), **kwargs,
    )


def make_customer(company, name="Ravi Kumar", state="Karnataka", **kwargs):
    return Customer.objects.create(company=company, name=name, state=state, **kwargs)


def make_supplier(company, name="Mega Suppliers", state="Karnataka", **kwargs):
    return Supplier.objects.create(company=company, name=name, state=state, **kwargs)


@pytest.fixture
def tenant_a(db):
    return make_tenant("alpha", state="Karnataka")


@pytest.fixture
def tenant_b(db):
    return make_tenant("beta", state="Maharashtra")


def add_stock(tenant, product, qty, unit_cost="80"):
    from inventory.models import MovementType
    from inventory.services import InventoryService

    return InventoryService.post_movement(
        company=tenant.company, product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal(qty), unit_cost=Decimal(unit_cost), user=tenant.owner,
    )


def clear_company_gstin(company):
    """Force the legacy unscoped document series (W0-04 empty-GSTIN path)."""
    company.gstin = ""
    company.gstin_verification_status = "UNVERIFIED"
    company.gstin_verified_at = None
    company.save(update_fields=["gstin", "gstin_verification_status", "gstin_verified_at"])
    return company


def create_draft_invoice(tenant, customer, items, invoice_type="GST", **extra):
    payload = {
        "customer": customer.id,
        "invoice_type": invoice_type,
        "items": items,
        **extra,
    }
    invoice_date = payload.get("invoice_date")
    if invoice_date is not None and hasattr(invoice_date, "isoformat") and not isinstance(invoice_date, str):
        payload["invoice_date"] = invoice_date.isoformat()
    resp = tenant.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def create_draft_purchase(tenant, supplier, items, purchase_type="GST"):
    payload = {
        "supplier": supplier.id,
        "purchase_type": purchase_type,
        "items": items,
    }
    resp = tenant.client.post("/api/v1/purchases/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data
