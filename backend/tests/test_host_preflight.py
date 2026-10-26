"""WP-4: the pure parts of scripts/host/preflight.py and the host scripts' safety properties."""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("preflight", ROOT / "scripts" / "host" / "preflight.py")
preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preflight)


def _good_env():
    env = {k: "a-real-looking-value-123" for k in preflight.REQUIRED_ENV}
    env.update(DJANGO_ENV="staging", POSTGRES_RLS_ENABLED="1", NUM_TRUSTED_PROXIES="2", BACKUP_REQUIRE_OFFSITE="1")
    return env


def test_env_check_passes_a_complete_env_and_names_each_problem():
    assert preflight.env_problems(_good_env()) == []
    env = _good_env()
    env.pop("OTP_PEPPER")
    env["DJANGO_SECRET_KEY"] = "CHANGE_ME"
    env["POSTGRES_RLS_ENABLED"] = "0"
    env["APP_BIND"] = "0.0.0.0"  # noqa: S104 - the bad value under test
    problems = " | ".join(preflight.env_problems(env))
    for expected in ("OTP_PEPPER missing", "DJANGO_SECRET_KEY is a placeholder", "POSTGRES_RLS_ENABLED is not 1", "APP_BIND=0.0.0.0"):
        assert expected in problems


def test_parse_env_ignores_comments_and_quotes():
    env = preflight.parse_env("# c\nA=1\nB='two'\n  C=\"3\"\nnot a line\n")
    assert env == {"A": "1", "B": "two", "C": "3"}


def test_only_ssh_and_the_edge_may_listen_on_all_interfaces():
    ss = "\n".join([
        "LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:((\"sshd\"))",
        "LISTEN 0 4096 0.0.0.0:443 0.0.0.0:*",
        "LISTEN 0 4096 127.0.0.1:80 0.0.0.0:*",
        "LISTEN 0 4096 127.0.0.1:8095 0.0.0.0:*",
        "LISTEN 0 4096 0.0.0.0:5432 0.0.0.0:* users:((\"docker-proxy\"))",
        "LISTEN 0 4096 [::]:6379 [::]:*",
    ])
    bad = preflight.exposed_listeners(ss)
    assert len(bad) == 2 and bad[0].startswith("0.0.0.0:5432") and bad[1].startswith("[::]:6379")


def test_container_published_on_all_interfaces_is_flagged():
    ps = "nginx 127.0.0.1:80->80/tcp\nglitchtip 127.0.0.1:8095->8000/tcp\ndb 0.0.0.0:5432->5432/tcp, :::5432->5432/tcp\napi 8000/tcp"
    assert preflight.published_container_ports(ps) == ["db"]


def test_backup_age_reads_only_encrypted_dumps(tmp_path):
    assert preflight.newest_backup_age_hours(tmp_path) is None
    plain = tmp_path / "db.sql"
    plain.write_text("x")
    assert preflight.newest_backup_age_hours(tmp_path) is None
    enc = tmp_path / "daily" / "db.dump.age"
    enc.parent.mkdir()
    enc.write_text("x")
    old = time.time() - 30 * 3600
    os.utime(enc, (old, old))
    assert 29.9 < preflight.newest_backup_age_hours(tmp_path) < 30.1


def test_tls_days_left():
    now = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
    assert preflight.tls_days_left("Nov 15 12:00:00 2026 GMT", now) == 21


def test_host_scripts_keep_their_safety_properties():
    boot = (ROOT / "scripts" / "host" / "bootstrap_vm.sh").read_text(encoding="utf-8")
    assert "--check" in boot and "Docker bypasses ufw" in boot
    # Password SSH is only locked once a key is installed (no lock-out).
    assert boot.index('if [[ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]]') < boot.index("PasswordAuthentication no\\n")
    render = (ROOT / "scripts" / "host" / "render_env.sh").read_text(encoding="utf-8")
    assert "install -m 600" in render and "placeholder" in render
