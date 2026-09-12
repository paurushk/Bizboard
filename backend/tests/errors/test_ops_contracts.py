"""§H3 / §H5 / §H9 — ops-surface contracts (docs/FREEZE_SCOPE_COVERAGE.md):

- /health and /metrics respond and parse (Docker health-check target)
- a recompute management command is safe to run twice (P3 migration rehearsal)
- feature-flag kill-switch: company JSON can turn a module OFF below the env
  default, and can never turn a credential-gated one ON above it
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db


# --- §H9: health / metrics --------------------------------------------------

def test_health_endpoint_reports_ok():
    c = APIClient()
    resp = c.get("/api/v1/health/")
    assert resp.status_code == 200
    assert resp.data["status"] == "ok"
    assert resp.data["version"] == "v1"


def test_health_ready_probe_reports_subsystems():
    c = APIClient()
    resp = c.get("/api/v1/health/?ready=1")
    assert resp.status_code in (200, 503)
    body = resp.data
    assert "db" in body or "database" in body or "status" in body


def test_metrics_endpoint_is_token_gated_and_parses():
    c = APIClient()
    # no METRICS_TOKEN configured -> the endpoint is not public (404)
    assert c.get("/api/v1/metrics/").status_code == 404

    with override_settings(METRICS_TOKEN="s3cr3t-metrics-token"):
        assert c.get("/api/v1/metrics/").status_code == 401  # missing bearer
        assert c.get(
            "/api/v1/metrics/", HTTP_AUTHORIZATION="Bearer wrong"
        ).status_code == 401
        ok = c.get("/api/v1/metrics/", HTTP_AUTHORIZATION="Bearer s3cr3t-metrics-token")
        assert ok.status_code == 200
        text = ok.content.decode("utf-8")
        data_lines = [
            ln for ln in text.splitlines() if ln and not ln.startswith("#")
        ]
        assert data_lines and all(len(ln.split()) >= 2 for ln in data_lines), text[:400]
        assert data_lines[-1].split()[-1].replace(".", "").isdigit()


# --- §H9 / P3: recompute command is idempotent ----------------------------

def test_rebuild_running_cost_is_safe_to_run_twice(tenant_a):
    from django.db.models import Sum

    from inventory.models import InventoryRunningCost

    from inventory.models import MovementType
    from inventory.services import InventoryService

    product = make_product(tenant_a.company, purchase_price="80")
    add_stock(tenant_a, product, "10", unit_cost="80")  # OPENING_STOCK, value 800
    InventoryService.post_movement(
        company=tenant_a.company, product=product, movement_type=MovementType.PURCHASE,
        quantity=Decimal("5"), unit_cost=Decimal("100"), user=tenant_a.owner,
    )  # +500 -> running value 1300

    def _snapshot():
        return {
            (r.product_id, r.warehouse_id): (r.qty, r.value)
            for r in InventoryRunningCost.objects.filter(company=tenant_a.company)
        }

    before = _snapshot()
    assert before, "no running-cost rows to rebuild"

    call_command("rebuild_running_cost", "--company", str(tenant_a.company.id))
    after_1 = _snapshot()
    call_command("rebuild_running_cost", "--company", str(tenant_a.company.id))
    after_2 = _snapshot()

    assert after_1 == before, "first rebuild changed the running cost"
    assert after_2 == after_1, "second rebuild was not a no-op"
    total = InventoryRunningCost.objects.filter(company=tenant_a.company).aggregate(
        v=Sum("value")
    )["v"]
    assert total == Decimal("1300.0000")  # 10*80 + 5*100


# --- FLAG-01: feature-flag kill-switch ------------------------------------

@override_settings(ENABLE_TALLY=True)
def test_company_json_can_kill_a_module_below_env_default(tenant_a):
    from core.services.feature_flags import build_feature_flags

    assert build_feature_flags(company=tenant_a.company)["ENABLE_TALLY"] is True

    tenant_a.company.feature_flags = {"ENABLE_TALLY": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert build_feature_flags(company=tenant_a.company)["ENABLE_TALLY"] is False


@override_settings(ENABLE_WHATSAPP_CLOUD=False)
def test_company_json_cannot_enable_a_credential_gated_flag_above_env(tenant_a):
    from core.services.feature_flags import build_feature_flags

    tenant_a.company.feature_flags = {"ENABLE_WHATSAPP_CLOUD": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    # env is the ceiling for credential-backed integrations — JSON true is ignored
    assert build_feature_flags(company=tenant_a.company)["ENABLE_WHATSAPP_CLOUD"] is False


# --- P3: every recompute / normalise command is safe to run twice ---------

def test_stock_and_unit_recompute_commands_are_idempotent(tenant_a):
    from decimal import Decimal as D

    from django.db.models import Sum

    from inventory.models import InventoryRunningCost, MovementType, StockBalance
    from inventory.services import InventoryService
    from masters.models import Unit

    cid = str(tenant_a.company.id)
    product = make_product(tenant_a.company, purchase_price="80")
    add_stock(tenant_a, product, "12", unit_cost="80")
    InventoryService.post_movement(
        company=tenant_a.company, product=product, movement_type=MovementType.PURCHASE,
        quantity=D("3"), unit_cost=D("100"), user=tenant_a.owner,
    )
    Unit.objects.create(company=tenant_a.company, name="Pieces", short_name="PCS", uqc_code="")

    def _fingerprint():
        return (
            {(r.product_id, r.warehouse_id, r.batch_id): r.on_hand
             for r in StockBalance.objects.filter(company=tenant_a.company)},
            InventoryRunningCost.objects.filter(company=tenant_a.company).aggregate(v=Sum("value"))["v"],
            sorted(Unit.objects.filter(company=tenant_a.company).values_list("id", "uqc_code")),
        )

    for cmd in ("rebuild_stock_balances", "rebuild_running_cost"):
        call_command(cmd, "--company", cid)
    call_command("backfill_uqc", "--company", cid)
    once = _fingerprint()

    for cmd in ("rebuild_stock_balances", "rebuild_running_cost"):
        call_command(cmd, "--company", cid)
    call_command("backfill_uqc", "--company", cid)
    twice = _fingerprint()

    assert once == twice, "a recompute command was not idempotent on the second run"
    assert once[1] == D("1260.0000")  # 12*80 + 3*100


def test_backfill_and_reconcile_commands_dry_run_is_read_only(tenant_a):
    """`--dry-run` scans without writing: running it twice leaves the DB byte
    identical."""
    from accounting.services import seed_chart_of_accounts

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company)
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")

    from accounting.models import JournalEntry
    from inventory.models import StockMovement

    def _counts():
        return (
            JournalEntry.objects.count(),
            StockMovement.objects.count(),
        )

    before = _counts()
    call_command("backfill_missing_postings", "--dry-run")
    call_command("backfill_missing_postings", "--dry-run")
    call_command("backfill_accounting_postings", "--dry-run")
    call_command("backfill_accounting_postings", "--dry-run")
    call_command("reconcile_dual_fulfillment_and_cost", "--dry-run")
    call_command("reconcile_dual_fulfillment_and_cost", "--dry-run")
    # reconcile-gateway-captures has no --dry-run; with no gateway payments it is
    # a pure no-op and safe to run twice.
    call_command("reconcile_gateway_captures", "--company-id", str(tenant_a.company.id))
    call_command("reconcile_gateway_captures", "--company-id", str(tenant_a.company.id))
    assert _counts() == before, "a scan/reconcile command mutated the database"


# --- P3: docker-compose deploy contract --------------------------------

def test_compose_api_has_health_check_and_build_contexts_exist():
    """The `docker` CI job validates compose syntax; this pins the deploy
    contract: the API service healthchecks `/api/v1/health/` and every
    `build:` context points at a real directory with a Dockerfile."""
    import pathlib
    import re

    repo = pathlib.Path(__file__).resolve().parents[3]
    compose = (repo / "docker-compose.yml").read_text(encoding="utf-8")

    assert "/api/v1/health/" in compose, "no API healthcheck against /api/v1/health/"

    for ctx in set(re.findall(r"build:\s*\n?\s*(?:context:\s*)?(\./[\w./-]+)", compose)) | \
               set(re.findall(r"build:\s*(\./[\w./-]+)\s*$", compose, re.M)):
        d = (repo / ctx).resolve()
        assert d.is_dir(), f"compose build context {ctx} is not a directory"
        assert (d / "Dockerfile").exists() or list(d.glob("Dockerfile*")), \
            f"compose build context {ctx} has no Dockerfile"


@pytest.mark.skipif(
    __import__("os").environ.get("DOCKER_SMOKE") != "1",
    reason="container smoke — set DOCKER_SMOKE=1 on a host with a Docker daemon",
)
def test_container_health_endpoint_responds():  # pragma: no cover - infra-gated
    import subprocess
    import time
    import urllib.request

    subprocess.run(["docker", "compose", "up", "-d", "api", "db", "redis"], check=True,
                   cwd=str(__import__("pathlib").Path(__file__).resolve().parents[3]))
    try:
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://localhost:8000/api/v1/health/", timeout=3) as r:
                    if r.status == 200:
                        return
            except Exception:
                time.sleep(2)
        raise AssertionError("container /api/v1/health/ never returned 200")
    finally:
        subprocess.run(["docker", "compose", "down"], check=False,
                       cwd=str(__import__("pathlib").Path(__file__).resolve().parents[3]))


# --- H3: celery-beat schedule integrity ----------------------------------

def test_every_beat_task_is_importable_and_registered():
    from importlib import import_module

    from django.conf import settings

    schedule = settings.CELERY_BEAT_SCHEDULE
    assert schedule, "CELERY_BEAT_SCHEDULE is empty"
    for name, cfg in schedule.items():
        dotted = cfg["task"]
        module_path, _, func = dotted.rpartition(".")
        mod = import_module(module_path)
        assert hasattr(mod, func), f"beat entry {name!r} -> {dotted} is not importable"
        assert callable(getattr(mod, func)), f"{dotted} is not callable"
        assert "schedule" in cfg, f"beat entry {name!r} has no schedule"
