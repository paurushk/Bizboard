"""SR0-06 / WP-C3 — hosted Compose overlays must run the app as the RLS-bound role.

The owner in POSTGRES_USER is a superuser and bypasses FORCE ROW LEVEL SECURITY. On the
staging and production overlays, api/worker/beat must connect as APP_DB_USER
(NOSUPERUSER NOBYPASSRLS, scripts/db-app-role.sh), and POSTGRES_RLS_ENABLED must not be
able to default to 0. Every Celery worker must also consume every queue routed in
config/celery.py, or tasks routed there wait forever.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "compose_rls"
CONSEQUENCE = (
    "A hosted overlay that connects as the DB owner, or lets POSTGRES_RLS_ENABLED default to 0, "
    "turns tenant row-level security off in production; a queue with no consumer silently drops work."
)

_OVERLAYS = ("docker-compose.prod.yml", "docker-compose.staging.yml")
_APP_SERVICES = ("api", "worker", "beat")
_ROUTE_QUEUE = re.compile(r"""\{\s*["']queue["']\s*:\s*["']([a-z_]+)["']\s*\}""")
_WORKER_QUEUES = re.compile(r"celery\s+-A\s+config\s+worker[^\n\"]*?-Q\s+([a-z_,]+)")


def _load(path: Path):
    import yaml

    class _Loader(yaml.SafeLoader):
        """Compose tags such as !reset and !override load as plain values."""

    def _plain(loader, _suffix, node):
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        return loader.construct_scalar(node)

    _Loader.add_multi_constructor("!", _plain)
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader) or {}  # noqa: S506 - SafeLoader subclass


def _env(service: dict) -> dict:
    env = service.get("environment") or {}
    if isinstance(env, list):
        return dict(item.split("=", 1) if "=" in item else (item, "") for item in env)
    return env


def _routed_queues(root: Path) -> set[str]:
    celery_py = root / "backend" / "config" / "celery.py"
    if not celery_py.exists():
        return set()
    return set(_ROUTE_QUEUE.findall(celery_py.read_text(encoding="utf-8"))) | {"celery"}


def check(root: Path) -> list[str]:
    violations: list[str] = []
    for name in _OVERLAYS:
        path = root / name
        if not path.exists():
            continue
        services = (_load(path).get("services") or {})
        for svc in _APP_SERVICES:
            if svc not in services:
                violations.append(f"{name}: service '{svc}' missing from the overlay")
                continue
            env = _env(services[svc])
            url = str(env.get("DATABASE_URL", ""))
            if "APP_DB_USER" not in url:
                violations.append(f"{name}:{svc}: DATABASE_URL must use ${{APP_DB_USER}}, got {url[:60]!r}")
            rls = str(env.get("POSTGRES_RLS_ENABLED", ""))
            if not rls or ":-0" in rls or rls.strip() in ("0", "false", "False"):
                violations.append(f"{name}:{svc}: POSTGRES_RLS_ENABLED must default to 1, got {rls!r}")
    routed = _routed_queues(root)
    for name in ("docker-compose.yml", "docker-compose.staging.yml"):
        path = root / name
        if not path.exists() or not routed:
            continue
        text = path.read_text(encoding="utf-8")
        for m in _WORKER_QUEUES.finditer(text):
            consumed = set(m.group(1).split(","))
            missing = sorted(routed - consumed)
            if missing:
                violations.append(f"{name}: worker -Q {m.group(1)} does not consume routed queue(s) {missing}")
    return violations


def make_bad_tree(tmp: Path) -> None:
    (tmp / "docker-compose.prod.yml").write_text(
        "services:\n"
        "  api:\n    environment:\n      DATABASE_URL: postgresql://${POSTGRES_USER}:x@db/bb\n"
        "      POSTGRES_RLS_ENABLED: ${POSTGRES_RLS_ENABLED:-0}\n"
        "  worker:\n    environment: {}\n"
        "  beat:\n    environment: {}\n",
        encoding="utf-8",
    )
    cfg = tmp / "backend" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "celery.py").write_text('ROUTES = {"x.y": {"queue": "agents"}}\n', encoding="utf-8")
    (tmp / "docker-compose.yml").write_text(
        "services:\n  worker:\n    command: celery -A config worker -l info -Q celery,reports\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print(f"  - {v}")
        sys.exit(1)
    print(f"GUARD OK {NAME}")
