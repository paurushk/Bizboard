"""Versioned prompt files: agents/catalog/<agent>/prompts/<name>.v<N>.md. A change is a new file."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

CATALOG_DIR = Path(__file__).parent / "catalog"
_VERSION_RE = re.compile(r"^(?P<name>.+)\.v(?P<n>\d+)\.md$")


@lru_cache(maxsize=256)
def load_prompt(agent_dirname: str, name: str) -> tuple[str, str]:
    """Return (text, version) for the highest version of ``name``. ``agent_dirname`` is the catalog package name."""
    folder = CATALOG_DIR / agent_dirname / "prompts"
    best: tuple[int, Path] | None = None
    for path in folder.glob(f"{name}.v*.md"):
        m = _VERSION_RE.match(path.name)
        if m and m.group("name") == name:
            n = int(m.group("n"))
            if best is None or n > best[0]:
                best = (n, path)
    if best is None:
        raise FileNotFoundError(f"No prompt {name} for agent {agent_dirname}")
    return best[1].read_text(encoding="utf-8"), f"{name}.v{best[0]}"


def prompt_exists(agent_dirname: str, name: str) -> bool:
    try:
        load_prompt(agent_dirname, name)
        return True
    except FileNotFoundError:
        return False
