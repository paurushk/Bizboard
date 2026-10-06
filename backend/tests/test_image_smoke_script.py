"""scripts/image_smoke.sh (F-PORT-01 / PRE-2), driven by a stub `docker` that records every call.

The real script needs a built image and Postgres; here the contract is what matters: which checks run,
in which order, that the first failure stops the run, that production-style settings are used (and a
wildcard host never is), and that the container is cleaned up.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SH = shutil.which("sh")
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "image_smoke.sh"
pytestmark = pytest.mark.skipif(SH is None, reason="needs a POSIX sh")

DOCKER_STUB = r"""#!/bin/sh
# Records the call, then answers like the real image would unless FAKE_FAIL_STEP / FAKE_PY say otherwise.
echo "$*" >> "$DOCKER_LOG"
case "$*" in
  *"rm -f"*) exit 0 ;;
  *"logs "*) echo "gunicorn: stub log line"; exit 0 ;;
  *"exec "*) [ "${FAKE_HEALTH:-200}" = "200" ] && echo 200; exit 0 ;;
  *"run -d "*) echo "stubcontainerid"; exit 0 ;;
  *"sys.version_info"*) echo "collectstatic: 154 static files copied"; echo "${FAKE_PY:-3.13}"; exit 0 ;;
  *"check --deploy"*) [ "${FAKE_FAIL_STEP:-}" = "check" ] && { echo "SystemCheckError" >&2; exit 1; }; echo "System check identified no issues"; exit 0 ;;
  *"makemigrations --check"*) [ "${FAKE_FAIL_STEP:-}" = "drift" ] && { echo "Migrations for 'x'" >&2; exit 1; }; exit 0 ;;
  *"migrate --noinput"*) [ "${FAKE_FAIL_STEP:-}" = "migrate" ] && { echo "OperationalError" >&2; exit 1; }; exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def harness(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "docker"
    stub.write_text(DOCKER_STUB, encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    log = tmp_path / "docker.log"
    log.write_text("")
    env = dict(os.environ)
    env.update({
        "PATH": f"{bindir.as_posix()}{os.pathsep}{env['PATH']}",
        "DOCKER_LOG": log.as_posix(),
        "SMOKE_HEALTH_RETRIES": "2",
        "SMOKE_HEALTH_SLEEP": "0",
    })
    for k in ("FAKE_PY", "FAKE_FAIL_STEP", "FAKE_HEALTH", "SMOKE_DOCKER_ARGS", "SMOKE_REDIS_URL"):
        env.pop(k, None)
    return env, log


def smoke(env, *args, **extra):
    return subprocess.run([SH, str(SCRIPT), *args], env={**env, **extra}, capture_output=True, text=True, timeout=60)  # noqa: S603


def calls(log: Path) -> list[str]:
    return [ln for ln in log.read_text().splitlines() if ln.strip()]


DB = "postgresql://u:p@127.0.0.1:5432/smoke"


def test_happy_path_runs_every_check_in_order_and_reports_ok(harness):
    env, log = harness
    r = smoke(env, "img:ci", DB, "3.13")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "IMAGE SMOKE OK (python 3.13)" in r.stdout
    text = "\n".join(calls(log))
    order = [text.index(k) for k in ("sys.version_info", "check --deploy", "makemigrations --check", "migrate --noinput", "run -d")]
    assert order == sorted(order), "checks must run: interpreter, deploy check, drift, migrate, boot"


def test_interpreter_mismatch_fails_first_and_runs_nothing_else(harness):
    env, log = harness
    r = smoke(env, "img:ci", DB, "3.13", FAKE_PY="3.14")
    assert r.returncode == 1
    assert "image runs Python 3.14 but CI tests 3.13" in r.stderr
    assert not any("check --deploy" in c or "migrate" in c for c in calls(log))


def test_entrypoint_noise_before_the_version_does_not_break_the_comparison(harness):
    env, _ = harness
    # the stub prints a collectstatic line before the version, like the real entrypoint
    assert smoke(env, "img:ci", DB, "3.13").returncode == 0


def test_without_an_expected_version_any_interpreter_is_accepted_but_reported(harness):
    env, _ = harness
    r = smoke(env, "img:ci", DB, FAKE_PY="3.12")
    assert r.returncode == 0 and "image python: 3.12" in r.stdout


@pytest.mark.parametrize("step,needle,must_not_run", [
    ("check", "SystemCheckError", "migrate --noinput"),
    ("drift", "Migrations for", "migrate --noinput"),
    ("migrate", "OperationalError", "run -d"),
])
def test_the_first_failing_check_stops_the_run(harness, step, needle, must_not_run):
    env, log = harness
    r = smoke(env, "img:ci", DB, "3.13", FAKE_FAIL_STEP=step)
    assert r.returncode != 0
    assert needle in r.stderr
    assert not any(must_not_run in c for c in calls(log)), f"{must_not_run!r} ran after {step} failed"


def test_a_server_that_never_answers_health_fails_and_prints_its_logs(harness):
    env, log = harness
    r = smoke(env, "img:ci", DB, "3.13", FAKE_HEALTH="500")
    assert r.returncode == 1
    assert "did not return 200" in r.stderr
    assert "gunicorn: stub log line" in r.stderr, "the container log is the only clue when boot fails"


def test_the_container_is_removed_on_success_and_on_failure(harness):
    env, log = harness
    smoke(env, "img:ci", DB, "3.13")
    assert any("rm -f" in c and "bb-image-smoke-" in c for c in calls(log))
    log.write_text("")
    smoke(env, "img:ci", DB, "3.13", FAKE_HEALTH="500")
    assert any("rm -f" in c and "bb-image-smoke-" in c for c in calls(log))


def test_production_style_settings_are_used_and_a_wildcard_host_never_is(harness):
    env, log = harness
    smoke(env, "img:ci", DB, "3.13")
    run_line = next(c for c in calls(log) if "check --deploy" in c)
    for must in ("DJANGO_ENV=production", "DJANGO_DEBUG=0", "USE_TLS=1", f"DATABASE_URL={DB}"):
        assert must in run_line, must
    assert "DJANGO_ALLOWED_HOSTS=*" not in run_line and "ALLOWED_HOSTS=*" not in run_line
    assert "CELERY_TASK_ALWAYS_EAGER" not in run_line, "production forbids eager Celery"


def test_the_secret_key_is_a_throwaway_and_long_enough_for_the_production_check(harness):
    env, log = harness
    smoke(env, "img:ci", DB, "3.13")
    run_line = next(c for c in calls(log) if "check --deploy" in c)
    key = next(tok for tok in run_line.split() if tok.startswith("DJANGO_SECRET_KEY="))
    assert key.startswith("DJANGO_SECRET_KEY=smoke-only-") and len(key.split("=", 1)[1]) >= 40


def test_redis_url_is_overridable(harness):
    env, log = harness
    smoke(env, "img:ci", DB, "3.13", SMOKE_REDIS_URL="redis://cache.internal:6380/2")
    assert any("REDIS_URL=redis://cache.internal:6380/2" in c for c in calls(log))


def test_extra_docker_args_are_passed_through(harness):
    env, log = harness
    smoke(env, "img:ci", DB, "3.13", SMOKE_DOCKER_ARGS="--add-host=host.docker.internal:host-gateway")
    assert all("--add-host=host.docker.internal:host-gateway" in c for c in calls(log) if c.startswith("run "))


def test_missing_arguments_print_usage_and_fail(harness):
    env, _ = harness
    assert smoke(env).returncode != 0
    r = smoke(env, "img:ci")
    assert r.returncode != 0 and "database url required" in r.stderr
