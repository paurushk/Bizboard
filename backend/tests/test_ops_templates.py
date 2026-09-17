"""Ops templates + CI skip-jobs that close the remaining Split-lane LLM items."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.secret_rotation import ROTATION_ORDER, check_required_secrets

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_DOCS = (
    "docs/ops/STRIDE.md",
    "docs/ops/SECRET_ROTATION.md",
    "docs/ops/EXPAND_CONTRACT.md",
    "docs/ops/POSTGRES.md",
    "docs/ops/SLO.md",
    "docs/ops/ALERTS.md",
    "docs/ops/INCIDENT_RESPONSE.md",
    "docs/ops/POSTMORTEM.md",
    "docs/ops/CUTOVER.md",
    "docs/ops/ERASURE_PLAYBOOK.md",
    "docs/ops/CHARGEBACKS.md",
    "docs/pilot/FAQS.md",
    "docs/pilot/TRAINING_A1_A26.md",
    "deploy/pgbouncer.ini",
    "docs/ops/FREEZE_EXCEPTION.md",
    "docs/ops/RISK_REGISTER.md",
    "docs/ops/RELEASE_CHECKLIST.md",
    "docs/ops/ADR_TOPOLOGY.md",
    "docs/ops/RECREATE_FROM_SHA.md",
    "docs/ops/SECURITY_GROUPS.md",
    "docs/ops/UNIT_ECONOMICS.md",
    "docs/ops/TENANT_MODEL.md",
    "docs/ops/MFA_SSO.md",
    "docs/ops/INDEXES.md",
    "docs/ops/DB_FAILOVER.md",
    "docs/ops/BACKUP_ALERT.md",
    "docs/ops/STATUS_COMMS.md",
    "docs/ops/LOG_RETENTION.md",
    "docs/ops/WORKER_SCALE.md",
    "docs/ops/BCP.md",
    "docs/ops/OIDC.md",
    "docs/ops/FORWARD_FIX.md",
    "docs/ops/SLO_DRIFT.md",
    "docs/ops/RELEASE_HYGIENE.md",
    "docs/ops/CUTOVER_DRY_RUN.md",
    "docs/ops/QOS_FREEZE_CLASS.md",
    "docs/ops/PCI_SCOPE.md",
    "docs/ops/SUBPROCESSORS.md",
    "docs/ops/PRODUCT_BEHAVIORS_FOR_COUNSEL.md",
    "docs/ops/ACCESS_REVIEW.md",
    "docs/ops/ONCALL_ROSTER.md",
    "docs/ops/DR_CADENCE.md",
    "docs/ops/VENDOR_SLA.md",
    "docs/ops/SPF_DKIM.md",
    "docs/ops/TICKET_TAXONOMY.md",
    "docs/ops/HYPERCARE.md",
    "docs/ops/FLAG_LIFECYCLE.md",
    "docs/ops/INTEGRATIONS.md",
    "docs/ops/EVIDENCE_PACK.md",
    "docs/ops/SUPPORT_MACROS.md",
    "docs/pilot/BETA_ARCHETYPE_CHECKLIST.md",
    "docs/ops/REFUND_CANCELLATION.md",
    "docs/ops/FEEDBACK_TRIAGE.md",
    "docs/pilot/CSAT.md",
    "docs/ops/DATA_CATEGORIES.md",
    "docs/ops/CDN.md",
    "docs/ops/ADOPTION_ROLLUP.md",
    "docker-compose.rollback.yml",
)


def test_ops_templates_exist_and_are_non_empty():
    missing = []
    for rel in REQUIRED_DOCS:
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size < 200:
            missing.append(rel)
    assert missing == [], missing


def test_zap_job_skips_without_staging_url():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "\n  zap:\n" in text
    assert "continue-on-error: true" in text
    block = text.split("\n  zap:\n", 1)[1].split("\n  qos-dashboard:", 1)[0]
    assert "STAGING_BASE_URL" in block
    assert "skip: STAGING_BASE_URL secret is empty" in block
    required = (ROOT / "scripts" / "ci_gates" / "REQUIRED_CHECKS.txt").read_text(encoding="utf-8")
    assert "zap" in required


def test_postgres_statement_timeouts_are_configured():
    src = (ROOT / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
    assert "statement_timeout=30000" in src
    assert "idle_in_transaction_session_timeout=60000" in src
    assert "CONN_HEALTH_CHECKS" in src
    pgb = (ROOT / "deploy" / "pgbouncer.ini").read_text(encoding="utf-8")
    assert "pool_mode = transaction" in pgb
    assert "CONN_MAX_AGE" in pgb or "CONN_MAX_AGE" in (ROOT / "docs" / "ops" / "POSTGRES.md").read_text(
        encoding="utf-8"
    )


def test_secret_rotation_check_fails_on_placeholder():
    missing = check_required_secrets({"SECRET_KEY": "changeme"})
    assert "SECRET_KEY" in missing
    assert "OTP_PEPPER" in ROTATION_ORDER


def test_secret_rotation_reuses_settings_placeholder_vocabulary():
    """secret_rotation.py must not maintain its own narrower placeholder
    list -- a value settings.py's boot-time guard would refuse to start
    with (e.g. the repo's own .env.example default) must fail this
    rotation-readiness check too, not silently read as "clear"."""
    from config.settings import _DEFAULT_SECRET

    missing = check_required_secrets({"SECRET_KEY": _DEFAULT_SECRET})
    assert "SECRET_KEY" in missing


def test_secret_rotation_enforces_secret_key_min_length():
    missing = check_required_secrets({"SECRET_KEY": "a-real-looking-but-short-secret"})
    assert "SECRET_KEY" in missing


def test_secret_rotation_drill_command_dry_run(capsys):
    call_command("secret_rotation_drill")
    captured = capsys.readouterr().out
    assert "SECRET_KEY" in captured
    assert "Dry-run only" in captured


def test_secret_rotation_drill_check_env_fails():
    from unittest.mock import patch

    with patch(
        "core.management.commands.secret_rotation_drill.check_required_secrets",
        return_value=["SECRET_KEY"],
    ):
        with pytest.raises(CommandError):
            call_command("secret_rotation_drill", "--check-env")


def test_expand_contract_sop_names_the_guard():
    text = (ROOT / "docs" / "ops" / "EXPAND_CONTRACT.md").read_text(encoding="utf-8")
    assert "EXPAND_CONTRACT_OK" in text
    assert "guard_zdt_migrations" in text
    assert "RemoveField" in text


def test_freeze_table_b_defaults_stay_off_in_deploy_artifacts():
    cd = (ROOT / ".github" / "workflows" / "cd.yml").read_text(encoding="utf-8")
    assert "VITE_ENABLE_GSTR=false" in cd
    assert "VITE_ENABLE_EINVOICE_SUBMIT=false" in cd
    assert "VITE_ENABLE_MANUFACTURING=false" in cd
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "VITE_ENABLE_GSTR:-false" in compose
    assert "VITE_ENABLE_EINVOICE_SUBMIT:-false" in compose
    rollback = (ROOT / "docker-compose.rollback.yml").read_text(encoding="utf-8")
    assert "BIZBOARD_API_PREVIOUS_IMAGE" in rollback
    assert "pin_image_digests.sh" in cd
    prod = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    staging = (ROOT / ".env.staging.example").read_text(encoding="utf-8")
    for text in (prod, staging):
        assert "ENABLE_FIXED_ASSETS=0" in text
        assert "ENABLE_BOE=0" in text
        assert "ENABLE_GSTR=0" in text
        assert "ENABLE_MANUFACTURING=0" in text
        assert "ENABLE_POS=1" in text
        assert "ENABLE_TDS=1" in text
        assert "ENABLE_SETUP_WIZARD=1" in text


def test_freeze_baseline_script_hashes_scope():
    import hashlib
    import subprocess
    import sys

    script = ROOT / "scripts" / "ops" / "freeze_baseline.py"
    proc = subprocess.run(  # noqa: S603 — repo-local script, argv is a list
        [sys.executable, str(script)], capture_output=True, text=True, check=True
    )
    expected = hashlib.sha256((ROOT / "docs" / "FREEZE_SCOPE.md").read_bytes()).hexdigest()
    assert expected in proc.stdout


def test_help_event_retention_is_scheduled():
    from django.conf import settings

    assert settings.CELERY_BEAT_SCHEDULE["help-prune-events"]["task"] == "core.tasks.prune_help_events_task"
    assert "180 days" in (ROOT / "docs" / "ops" / "LOG_RETENTION.md").read_text(encoding="utf-8")


def test_pci_scope_and_gateway_payload_never_keep_pan():
    from payments.services import _GATEWAY_PAYLOAD_PII_KEYS, redact_gateway_payload

    pci = (ROOT / "docs" / "ops" / "PCI_SCOPE.md").read_text(encoding="utf-8")
    assert "not PAN" in pci
    assert "card_number" in _GATEWAY_PAYLOAD_PII_KEYS
    assert "cvv" in _GATEWAY_PAYLOAD_PII_KEYS
    cleaned = redact_gateway_payload(
        {"id": "pay_1", "amount": 100, "card_number": "4111111111111111", "cvv": "123"}
    )
    assert cleaned["id"] == "pay_1"
    assert "card_number" not in cleaned
    assert "cvv" not in cleaned


def test_subprocessors_doc_lists_code_inventory():
    from core.integration_inventory import INTEGRATIONS

    text = (ROOT / "docs" / "ops" / "SUBPROCESSORS.md").read_text(encoding="utf-8")
    missing = [row["name"] for row in INTEGRATIONS if row["name"] not in text]
    assert missing == [], missing
    counsel = (ROOT / "docs" / "ops" / "PRODUCT_BEHAVIORS_FOR_COUNSEL.md").read_text(encoding="utf-8")
    assert "Do not treat this as Terms of Service" in counsel
    page = (ROOT / "docs" / "ops" / "INTEGRATIONS.md").read_text(encoding="utf-8")
    missing_page = [row["name"] for row in INTEGRATIONS if row["name"] not in page]
    assert missing_page == [], missing_page
    for row in INTEGRATIONS:
        assert row["fallback"] in page, row["name"]


def test_release_notes_script_buckets_money_tax_stock():
    import importlib.util
    import subprocess
    import sys

    script = ROOT / "scripts" / "ops" / "release_notes.py"
    spec = importlib.util.spec_from_file_location("release_notes", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.bucket("fix payment allocation drift") == "money"
    assert mod.bucket("gstr worksheet header") == "tax"
    assert mod.bucket("stock transfer godown") == "stock"
    assert mod.bucket("docs: support macros") == "other"
    rendered = mod.render(["fix gst rate", "docs only"])
    assert rendered.index("## tax") < rendered.index("## other")
    proc = subprocess.run(  # noqa: S603 — repo-local script, argv is a list
        [sys.executable, str(script), "HEAD", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    assert "# Release notes (C.4)" in proc.stdout
    assert "## money" in proc.stdout


def test_support_macros_do_not_claim_gst_filing():
    macros = (ROOT / "docs" / "ops" / "SUPPORT_MACROS.md").read_text(encoding="utf-8")
    assert "offline worksheets" in macros.lower()
    assert "login-as-you" in macros
    assert "one-click GSP" not in macros
    checklist = (ROOT / "docs" / "pilot" / "BETA_ARCHETYPE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )
    assert "ARCH-03" in checklist
    assert "ARCH-07" in checklist
    flags = (ROOT / "docs" / "ops" / "FLAG_LIFECYCLE.md").read_text(encoding="utf-8")
    assert "FREEZE_DARK_PLAN_MODULES" in flags
    assert "ENABLE_FIXED_ASSETS" in flags
    pack = (ROOT / "docs" / "ops" / "EVIDENCE_PACK.md").read_text(encoding="utf-8")
    assert "G16 Legal" in pack
    assert "ToS" in pack
    refund = (ROOT / "docs" / "ops" / "REFUND_CANCELLATION.md").read_text(encoding="utf-8")
    assert "current_period_end" in refund
    assert "Not** a finance policy" in refund or "Not a finance policy" in refund
    csat = (ROOT / "docs" / "pilot" / "CSAT.md").read_text(encoding="utf-8")
    assert "worksheets" in csat.lower()
    assert "GSTN" in csat
    triage = (ROOT / "docs" / "ops" / "FEEDBACK_TRIAGE.md").read_text(encoding="utf-8")
    assert "FREEZE_EXCEPTION" in triage
    cutover = (ROOT / "docs" / "ops" / "CUTOVER.md").read_text(encoding="utf-8")
    assert "6.1b" in cutover
    cats = (ROOT / "docs" / "ops" / "DATA_CATEGORIES.md").read_text(encoding="utf-8")
    dpdp = (ROOT / "docs" / "pilot" / "DPDP_POSTURE.md").read_text(encoding="utf-8")
    for label in ("Identity", "Party PII", "Money documents", "Files", "Telemetry"):
        assert label in cats
        assert label in dpdp
    indexes = (ROOT / "docs" / "ops" / "INDEXES.md").read_text(encoding="utf-8")
    assert "company, status, invoice_date" in indexes
    cdn = (ROOT / "docs" / "ops" / "CDN.md").read_text(encoding="utf-8")
    assert "static-only" in cdn.lower()
    assert "no-store" in cdn
    assert "/api" in cdn
    nginx = (ROOT / "web" / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_pass" not in nginx
    assert "location /api" not in nginx
    assert 'Cache-Control "no-cache, no-store, must-revalidate"' in nginx
    assert 'Cache-Control "public, immutable"' in nginx
    rollup = (ROOT / "docs" / "ops" / "ADOPTION_ROLLUP.md").read_text(encoding="utf-8")
    assert "wizard_completed" in rollup
    assert "Do not treat this as" in rollup

