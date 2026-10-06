"""guard_runtime_alignment (RT-1) and the guard runner (QOS-0105).

The runner's own --selftest proves each guard can fail on a synthetic bad tree. These tests add the
other half: good trees pass, each kind of drift is reported precisely, real Dockerfile syntax
(digest pins, multi-stage builds) parses, and the real repository is clean.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = ROOT / "scripts" / "ci_gates" / "guards" / "guard_runtime_alignment.py"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("_guard_runtime_alignment_test", GUARD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tree(tmp_path, *, backend, web, ci):
    (tmp_path / "backend").mkdir()
    (tmp_path / "web").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    if backend is not None:
        (tmp_path / "backend" / "Dockerfile").write_text(backend, encoding="utf-8")
    if web is not None:
        (tmp_path / "web" / "Dockerfile").write_text(web, encoding="utf-8")
    if ci is not None:
        (tmp_path / ".github" / "workflows" / "ci.yml").write_text(ci, encoding="utf-8")
    return tmp_path


PIN = "@sha256:" + "a" * 64
GOOD_CI = 'jobs:\n  a:\n    - with:\n        python-version: "3.13"\n  b:\n    - with:\n        node-version: "22"\n'


def test_aligned_tree_passes_including_digest_pins_and_multistage_builds(guard, tmp_path):
    t = _tree(
        tmp_path,
        backend=f"FROM python:3.13-slim-bookworm{PIN}\nRUN true\n",
        web=f"FROM node:22-alpine{PIN} AS build\nRUN true\nFROM nginx:1.31-alpine{PIN}\nCOPY --from=build /a /b\n",
        ci=GOOD_CI,
    )
    assert guard.check(t) == []


def test_python_drift_is_reported_with_both_versions(guard, tmp_path):
    t = _tree(tmp_path, backend="FROM python:3.14-slim\n", web="FROM node:22-alpine\n", ci=GOOD_CI)
    (msg,) = guard.check(t)
    assert "Python" in msg and "3.14" in msg and "3.13" in msg


def test_node_drift_is_reported_and_nginx_stage_is_not_mistaken_for_node(guard, tmp_path):
    t = _tree(tmp_path, backend="FROM python:3.13-slim\n", web="FROM node:26-alpine AS b\nFROM nginx:1.31\n", ci=GOOD_CI)
    (msg,) = guard.check(t)
    assert "Node" in msg and "26" in msg and "22" in msg


def test_both_drifting_reports_both(guard, tmp_path):
    t = _tree(tmp_path, backend="FROM python:3.12\n", web="FROM node:20\n", ci=GOOD_CI)
    assert len(guard.check(t)) == 2


def test_ci_testing_several_versions_is_flagged_because_the_comparison_is_meaningless(guard, tmp_path):
    ci = 'python-version: "3.12"\npython-version: "3.13"\nnode-version: "22"\n'
    t = _tree(tmp_path, backend="FROM python:3.13\n", web="FROM node:22\n", ci=ci)
    (msg,) = guard.check(t)
    assert "several" in msg and "Python" in msg


def test_a_missing_ci_value_is_a_violation_not_a_silent_pass(guard, tmp_path):
    out = guard.check(_tree(tmp_path, backend="FROM python:3.13\n", web="FROM node:22\n", ci="jobs: {}\n"))
    assert len(out) == 2 and all("version found" in m for m in out)


def test_a_missing_dockerfile_is_reported(guard, tmp_path):
    out = guard.check(_tree(tmp_path, backend=None, web="FROM node:22\n", ci=GOOD_CI))
    assert len(out) == 1 and "FROM line found" in out[0] and "Dockerfile" in out[0]


def test_unquoted_and_patch_level_ci_versions_are_understood(guard, tmp_path):
    ci = "python-version: 3.13\nnode-version: 22\n"
    t = _tree(tmp_path, backend="FROM python:3.13.7-slim\n", web="FROM node:22.11-alpine\n", ci=ci)
    assert guard.check(t) == []


def test_the_selftest_fixture_really_is_a_violation(guard, tmp_path):
    guard.make_bad_tree(tmp_path)
    assert guard.check(tmp_path), "make_bad_tree must trigger the guard or the runner's --selftest is meaningless"


def test_the_real_repository_is_aligned(guard):
    assert guard.check(ROOT) == []


# --- the runner -------------------------------------------------------------------------

def _runner(*args):
    return subprocess.run(  # noqa: S603 - repo guard script run with this interpreter
        [sys.executable, str(ROOT / "scripts" / "ci_gates" / "run_guards.py"), *args],
        capture_output=True, text=True, timeout=300, cwd=ROOT,
    )


def test_all_guards_pass_on_the_repository():
    r = _runner()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok    runtime_alignment" in r.stdout and "ok    config_consistency" in r.stdout


def test_every_guard_can_fail_selftest():
    r = _runner("--selftest")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "runtime_alignment (fires on bad input)" in r.stdout


def test_gate_inventory_documents_the_runtime_guard():
    text = (ROOT / "scripts" / "ci_gates" / "GATE_INVENTORY.md").read_text(encoding="utf-8")
    assert "guard_runtime_alignment" in text
