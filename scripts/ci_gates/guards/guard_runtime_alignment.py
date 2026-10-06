"""RT-1: the runtime CI tests on is the runtime the images ship.

CI runs the backend suite on one Python and the web suite on one Node. If the
Dockerfiles drift to a different major/minor, every green CI run says nothing
about the artefact customers actually run. This guard reads:

  * ``backend/Dockerfile``  ``FROM python:X.Y...``  vs ``python-version`` in ci.yml
  * ``web/Dockerfile``      ``FROM node:N...``      vs ``node-version``   in ci.yml

and fails on any mismatch (or on a CI value that is not a single consistent
version, which would make the comparison meaningless).
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "runtime_alignment"
CONSEQUENCE = (
    "CI tests one Python/Node version while the Dockerfile ships another; "
    "passing CI does not describe the shipped runtime."
)

_PY_FROM = re.compile(r"^FROM\s+python:(\d+\.\d+)", re.M)
_NODE_FROM = re.compile(r"^FROM\s+node:(\d+)", re.M)
_CI_PY = re.compile(r'python-version:\s*["\']?(\d+\.\d+)')
_CI_NODE = re.compile(r'node-version:\s*["\']?(\d+)')


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def check(root: Path) -> list[str]:
    ci = _read(root / ".github" / "workflows" / "ci.yml")
    problems: list[str] = []
    for label, dockerfile, from_re, ci_re in (
        ("Python", root / "backend" / "Dockerfile", _PY_FROM, _CI_PY),
        ("Node", root / "web" / "Dockerfile", _NODE_FROM, _CI_NODE),
    ):
        image = set(from_re.findall(_read(dockerfile)))
        tested = set(ci_re.findall(ci))
        if not image:
            problems.append(f"{NAME}: no {label} FROM line found in {dockerfile.relative_to(root)}")
        elif not tested:
            problems.append(f"{NAME}: no {label} version found in .github/workflows/ci.yml")
        elif len(tested) != 1:
            problems.append(f"{NAME}: CI uses several {label} versions {sorted(tested)}; pick one")
        elif image != tested:
            problems.append(
                f"{NAME}: {label} image is {sorted(image)} but CI tests {sorted(tested)}"
            )
    return problems


def make_bad_tree(tmp: Path) -> None:
    (tmp / "backend").mkdir(parents=True, exist_ok=True)
    (tmp / "web").mkdir(parents=True, exist_ok=True)
    (tmp / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "Dockerfile").write_text("FROM python:3.14-slim\n", encoding="utf-8")
    (tmp / "web" / "Dockerfile").write_text("FROM node:26-alpine AS build\n", encoding="utf-8")
    (tmp / ".github" / "workflows" / "ci.yml").write_text(
        'python-version: "3.13"\nnode-version: "22"\n', encoding="utf-8"
    )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print("  ", v)
        sys.exit(1)
    print(f"GUARD OK {NAME}")
