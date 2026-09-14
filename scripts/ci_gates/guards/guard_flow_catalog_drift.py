"""Advisory Graph 1 drift guard (P1-T7).

Fails if live App.tsx routes are missing from validation/catalog/routes.yaml,
if the extractor left an unparsed bucket, or if the count dropped below the
committed floor.

ADVISORY=True until 2 consecutive green CI weeks, then the web lead flips
this to False (same low-ceremony pattern as load-harness). run_guards.py
skips advisory guards unless --include-advisory.
"""

from __future__ import annotations

import sys
from pathlib import Path

NAME = "flow_catalog_drift"
CONSEQUENCE = (
    "A route exists in App.tsx but not in validation/catalog/routes.yaml "
    "(or the extractor undercounted / left unparsed tags). Graph 1 is lying."
)
ADVISORY = True

_TOOLS = Path(__file__).resolve().parents[3] / "validation" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def check(root: Path) -> list[str]:
    from extract_routes import build_from_files

    import yaml

    app = root / "web" / "src" / "App.tsx"
    catalog = root / "validation" / "catalog" / "routes.yaml"
    count_path = root / "validation" / "catalog" / "route_count.json"
    if not app.exists():
        return [f"{NAME}: {app} missing"]
    if not catalog.exists():
        return [f"{NAME}: {catalog} missing — run python validation/tools/extract_routes.py --write"]

    stored = yaml.safe_load(catalog.read_text(encoding="utf-8")) or {}
    stored_paths = {r["path"] for r in stored.get("routes") or []}
    menu = root / "web" / "src" / "navigation" / "menu.ts"
    smoke = root / "web" / "e2e" / "helpers" / "protectedRoutes.ts"
    # Stay inside `root` so --selftest planted trees don't read the real repo.
    result = build_from_files(
        app_path=app,
        menu_path=menu,
        smoke_path=smoke,
        count_path=count_path,
    )
    violations: list[str] = list(result["errors"])
    live_paths = {r["path"] for r in result["routes"]}
    missing = sorted(live_paths - stored_paths)
    if missing:
        violations.append("live routes missing from catalog: " + ", ".join(missing[:12]))
    return violations


def make_bad_tree(tmp: Path) -> None:
    app = tmp / "web" / "src" / "App.tsx"
    app.parent.mkdir(parents=True, exist_ok=True)
    app.write_text(
        """
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/brand-new-untracked" element={<NewPage />} />
    </Routes>
  );
}
""",
        encoding="utf-8",
    )
    catalog = tmp / "validation" / "catalog" / "routes.yaml"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(
        "count: 1\nroutes:\n  - path: /login\n    component: LoginPage\n    guards: []\n    route_kind: page\n",
        encoding="utf-8",
    )
    (tmp / "validation" / "catalog" / "route_count.json").write_text(
        '{"count": 1}\n', encoding="utf-8"
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print("  ", v)
        sys.exit(1)
    print(f"GUARD OK {NAME}")
