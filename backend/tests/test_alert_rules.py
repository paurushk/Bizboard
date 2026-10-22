"""WP-D3: every Prometheus alert names a runbook that exists, and uses metrics the app exports."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "deploy" / "prometheus" / "alerts.yml"


def _rules():
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return [rule for group in data["groups"] for rule in group["rules"]]


def test_every_alert_has_a_severity_and_a_runbook_that_exists():
    alerts_md = (ROOT / "docs" / "ops" / "ALERTS.md").read_text(encoding="utf-8")
    anchors = {m.group(1) for m in re.finditer(r"^### ([a-z0-9-]+)\s*$", alerts_md, re.M)}
    for rule in _rules():
        assert rule["labels"]["severity"] in ("page", "ticket"), rule["alert"]
        runbook = rule["annotations"]["runbook"]
        path, _, anchor = runbook.partition("#")
        assert (ROOT / path).exists(), f"{rule['alert']}: {path} missing"
        if anchor:
            assert anchor in anchors, f"{rule['alert']}: no '### {anchor}' section in ALERTS.md"


def test_alerts_only_use_metrics_the_app_exports():
    from core import ops_metrics

    src = (ROOT / "backend" / "core" / "ops_metrics.py").read_text(encoding="utf-8")
    exported = set(re.findall(r"\b(bizboard_[a-z0-9_]+)", src))
    exported |= {f"bizboard_{name}" for name, _help in ops_metrics._GAUGE_HELP}
    exported = {re.sub(r"_(total|bucket|count|sum)$", "", n) for n in exported}
    for rule in _rules():
        for name in set(re.findall(r"\b(bizboard_[a-z0-9_]+)", rule["expr"])):
            base = re.sub(r"_(total|bucket|count|sum)$", "", name)
            assert base in exported, f"{rule['alert']} uses {name}, which core/ops_metrics.py does not export"
