"""Extract routes from web/src/App.tsx (router is truth) and join menu.ts nav labels.

A line-scanning / brace-aware state machine over hand-written JSX. Public
routes live in the same top-level <Routes> block as protected ones; nested
paths drop their leading slash. Fail loud: unparsed tags abort, and a
committed count floor catches silent undercounts.

    python validation/tools/extract_routes.py --count
    python validation/tools/extract_routes.py --selftest
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import (
    APP_TSX,
    MENU_TS,
    PROTECTED_ROUTES_TS,
    REPO_ROOT,
    ROUTES_YAML,
    ROUTE_COUNT_JSON,
    dump_json,
    dump_yaml,
    load_json,
    normalize_path,
)

_JSX_COMMENT = re.compile(r"\{/\*.*?\*/\}", re.DOTALL)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NAV_PATH = re.compile(r"path:\s*['\"]([^'\"]+)['\"]")
_NAV_LABEL = re.compile(
    r"path:\s*['\"]([^'\"]+)['\"][^}]*?labelKey:\s*['\"]([^'\"]+)['\"]"
    r"|labelKey:\s*['\"]([^'\"]+)['\"][^}]*?path:\s*['\"]([^'\"]+)['\"]",
    re.DOTALL,
)
_PROTECTED_PATH = re.compile(r"['\"](/[^'\"]*)['\"]")
_ALLOW_IDENT = re.compile(r"\ballow=\{([A-Za-z_][A-Za-z0-9_]*)\}")
_NAVIGATE_TO = re.compile(r"\bto=\{?['\"]([^'\"]+)['\"]")


def _strip_comments(src: str) -> str:
    return _JSX_COMMENT.sub("", src)


def _read_balanced(text: str, start: int, open_ch: str, close_ch: str) -> tuple[str, int]:
    if start >= len(text) or text[start] != open_ch:
        raise ValueError(f"expected {open_ch} at {start}")
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
        i += 1
    raise ValueError("unbalanced braces in JSX Route tag")


def _parse_route_tag(text: str, start: int) -> tuple[dict, int]:
    """Parse one <Route ...> or <Route .../> starting at `start`. Returns (info, end)."""
    assert text.startswith("<Route", start)
    i = start + len("<Route")
    brace = 0
    while i < len(text):
        c = text[i]
        if c == "{":
            brace += 1
        elif c == "}":
            brace -= 1
        elif brace == 0 and text.startswith("/>", i):
            inner = text[start + len("<Route") : i]
            return _attrs_from_inner(inner, self_closing=True), i + 2
        elif brace == 0 and c == ">":
            inner = text[start + len("<Route") : i]
            return _attrs_from_inner(inner, self_closing=False), i + 1
        i += 1
    raise ValueError("unterminated <Route tag")


def _attrs_from_inner(inner: str, *, self_closing: bool) -> dict:
    info = {
        "self_closing": self_closing,
        "index": bool(re.search(r"\bindex\b", inner)),
        "path": None,
        "element": None,
        "unparsed_reason": None,
    }
    path_m = re.search(r'\bpath\s*=\s*"([^"]*)"', inner)
    if path_m:
        info["path"] = path_m.group(1)
    else:
        path_expr = re.search(r"\bpath\s*=\s*\{", inner)
        if path_expr:
            info["unparsed_reason"] = "dynamic path={...}"
    elem_m = re.search(r"\belement\s*=\s*\{", inner)
    if elem_m:
        expr, _ = _read_balanced(inner, elem_m.end() - 1, "{", "}")
        info["element"] = expr[1:-1].strip()
    return info


def _component_name(element: str | None) -> str | None:
    if not element:
        return None
    m = re.search(r"<\s*([A-Za-z_][A-Za-z0-9_]*)", element)
    return m.group(1) if m else None


def _guard_label(element: str | None) -> str | None:
    name = _component_name(element)
    if name is None:
        return None
    if name == "Navigate":
        return None
    allow = _ALLOW_IDENT.search(element or "")
    if name == "RoleRoute" and allow:
        return f"RoleRoute:{allow.group(1)}"
    if name == "RoleRoute":
        return "RoleRoute:inline"
    if name in ("ProtectedRoute", "AppShell"):
        return name
    return None


def extract_routes(app_src: str) -> tuple[list[dict], list[dict]]:
    """Return (routes, unparsed)."""
    text = _strip_comments(app_src)
    start = text.find("<Routes>")
    end = text.rfind("</Routes>")
    if start < 0 or end < 0:
        raise ValueError("App.tsx has no <Routes>...</Routes> block")
    block = text[start + len("<Routes>") : end]

    routes: list[dict] = []
    unparsed: list[dict] = []
    stack: list[dict] = []
    i = 0
    while i < len(block):
        if block.startswith("</Route>", i):
            if stack:
                stack.pop()
            i += len("</Route>")
            continue
        if block.startswith("<Route", i):
            try:
                info, nxt = _parse_route_tag(block, i)
            except ValueError as exc:
                unparsed.append({"reason": str(exc), "snippet": block[i : i + 80]})
                break
            if info.get("unparsed_reason"):
                unparsed.append({"reason": info["unparsed_reason"], "snippet": block[i : nxt]})
                i = nxt
                continue
            parent_path = stack[-1]["path"] if stack else ""
            parent_guards = list(stack[-1]["guards"]) if stack else []
            element = info.get("element")
            component = _component_name(element)
            guard = _guard_label(element)
            is_navigate = component == "Navigate"
            is_wrapper = (
                not info["self_closing"]
                and not info["index"]
                and (info["path"] is None or guard in ("ProtectedRoute", "AppShell") or (guard or "").startswith("RoleRoute"))
                and not is_navigate
                and component
                not in (
                    None,
                    "Navigate",
                )
                and (
                    info["path"] is None
                    or guard is not None
                )
            )
            # A wrapper is a Route with children (not self-closing) whose element
            # is a layout/guard, not a page. Page routes are self-closing or have
            # a concrete page component.
            page_component = component not in (None, "ProtectedRoute", "AppShell", "RoleRoute")
            if not info["self_closing"] and not page_component and not info["index"]:
                child_path = parent_path
                if info["path"]:
                    child_path = _join(parent_path, info["path"])
                child_guards = parent_guards + ([guard] if guard else [])
                stack.append({"path": child_path, "guards": child_guards})
                i = nxt
                continue

            if info["index"]:
                path = parent_path or "/"
                route_kind = "index"
            elif info["path"] is None:
                unparsed.append({"reason": "Route with no path/index", "snippet": block[i:nxt]})
                if not info["self_closing"]:
                    stack.append({"path": parent_path, "guards": parent_guards})
                i = nxt
                continue
            else:
                path = _join(parent_path, info["path"])
                route_kind = "redirect" if is_navigate else "page"

            rec = {
                "path": normalize_path(path),
                "component": component or "",
                "guards": parent_guards + ([guard] if guard and page_component and guard not in parent_guards else []),
                "route_kind": route_kind,
            }
            if is_navigate:
                to_m = _NAVIGATE_TO.search(element or "")
                rec["redirect_to"] = to_m.group(1) if to_m else ""
            routes.append(rec)
            if not info["self_closing"] and page_component:
                # Rare: a page Route with nested children. Push so children join.
                stack.append({"path": rec["path"], "guards": rec["guards"]})
            i = nxt
            continue
        i += 1
    return routes, unparsed


def _join(parent: str, child: str) -> str:
    if child.startswith("/"):
        return child
    if child == "*":
        base = parent.rstrip("/") if parent else ""
        return f"{base}/*" if base else "/*"
    if not parent or parent == "/":
        return "/" + child.lstrip("/")
    return parent.rstrip("/") + "/" + child.lstrip("/")


def extract_nav_paths(menu_src: str) -> dict[str, str]:
    """path -> labelKey. Router is truth; this is a join only."""
    labels: dict[str, str] = {}
    for m in _NAV_LABEL.finditer(menu_src):
        if m.group(1) and m.group(2):
            labels[normalize_path(m.group(1).split("?")[0])] = m.group(2)
        elif m.group(3) and m.group(4):
            labels[normalize_path(m.group(4).split("?")[0])] = m.group(3)
    # Fallback: paths without a same-object labelKey still count as nav entries.
    for m in _NAV_PATH.finditer(menu_src):
        p = normalize_path(m.group(1).split("?")[0])
        labels.setdefault(p, "")
    return labels


def extract_protected_smoke_paths(src: str) -> list[str]:
    # Only the exported array, not comments.
    start = src.find("export const PROTECTED_ROUTES")
    chunk = src[start:] if start >= 0 else src
    return [normalize_path(p) for p in _PROTECTED_PATH.findall(chunk)]


def join_nav(routes: list[dict], nav: dict[str, str]) -> list[str]:
    """Attach nav_label. Return nav paths with no matching router path."""
    route_paths = {r["path"] for r in routes}
    # Redirect sources also "exist" as router entries.
    for r in routes:
        r["nav_label"] = nav.get(r["path"]) or None
    missing = []
    for path, label in nav.items():
        if path not in route_paths:
            # A nav item pointing at a redirect source is fine if the source exists.
            missing.append(path if not label else f"{path} ({label})")
    return missing


def apply_floor(routes: list[dict], previous: int) -> str | None:
    n = len(routes)
    if previous and n < previous:
        return (
            f"route count {n} is below committed floor {previous} — parser "
            "almost certainly broke (fail loud, never silent undercount)"
        )
    return None


def build_from_files(
    app_path: Path = APP_TSX,
    menu_path: Path = MENU_TS,
    smoke_path: Path = PROTECTED_ROUTES_TS,
    count_path: Path = ROUTE_COUNT_JSON,
) -> dict:
    routes, unparsed = extract_routes(app_path.read_text(encoding="utf-8"))
    nav = extract_nav_paths(menu_path.read_text(encoding="utf-8")) if menu_path.exists() else {}
    dead_nav = join_nav(routes, nav)
    smoke = extract_protected_smoke_paths(smoke_path.read_text(encoding="utf-8")) if smoke_path.exists() else []
    missing_smoke = [p for p in smoke if p not in {r["path"] for r in routes}]
    previous = 0
    if count_path.exists():
        previous = int(load_json(count_path).get("count") or 0)
    errors: list[str] = []
    if unparsed:
        errors.append(f"{len(unparsed)} unparsed Route tag(s)")
        for u in unparsed:
            errors.append(f"  unparsed: {u['reason']}: {u['snippet'][:120]!r}")
    floor = apply_floor(routes, previous)
    if floor:
        errors.append(floor)
    if missing_smoke:
        errors.append(
            "extractor missed PROTECTED_ROUTES entries (must find at least those): "
            + ", ".join(missing_smoke)
        )
    return {
        "routes": routes,
        "unparsed": unparsed,
        "dead_nav": dead_nav,
        "smoke_paths": smoke,
        "count": len(routes),
        "errors": errors,
    }


def write_catalog(result: dict) -> None:
    dump_yaml(
        {
            "count": result["count"],
            "dead_nav": result["dead_nav"],
            "routes": result["routes"],
        },
        ROUTES_YAML,
    )
    dump_json({"count": result["count"]}, ROUTE_COUNT_JSON)


def _selftest() -> int:
    fixture_dir = Path(__file__).resolve().parent / "_selftest"
    ok = True

    mini = (fixture_dir / "app_routes_min.tsx").read_text(encoding="utf-8")
    routes, unparsed = extract_routes(mini)
    paths = {r["path"] for r in routes}
    expected = {"/login", "/pay/:token", "/", "/sales/new", "/pos"}
    if unparsed:
        print(f"FAIL min fixture unparsed: {unparsed}")
        ok = False
    missing = expected - paths
    if missing:
        print(f"FAIL min fixture missing {missing}; got {sorted(paths)}")
        ok = False
    kinds = {r["path"]: r["route_kind"] for r in routes}
    if kinds.get("/old") != "redirect":
        print(f"FAIL expected /old as redirect, got {kinds}")
        ok = False
    else:
        print("ok    min fixture extracts public + nested + index + redirect")

    floor_err = apply_floor(routes, previous=len(routes) + 5)
    if not floor_err:
        print("FAIL floor check did not fire")
        ok = False
    else:
        print("ok    count floor fails loud on undercount")

    bad = (fixture_dir / "app_routes_unparsed.tsx").read_text(encoding="utf-8")
    _, unparsed_bad = extract_routes(bad)
    if not unparsed_bad:
        print("FAIL unparsed bucket stayed empty on dynamic path")
        ok = False
    else:
        print("ok    unparsed bucket fails on dynamic path={...}")

    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--write", action="store_true", help="write validation/catalog/routes.yaml")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    # Allow --root for the CI guard's planted trees.
    app = args.root / "web" / "src" / "App.tsx"
    menu = args.root / "web" / "src" / "navigation" / "menu.ts"
    smoke = args.root / "web" / "e2e" / "helpers" / "protectedRoutes.ts"
    count_path = args.root / "validation" / "catalog" / "route_count.json"
    if not app.exists():
        # Fall back to repo files when the planted tree only overrides App.tsx.
        result = build_from_files(app_path=app if app.exists() else APP_TSX)
    else:
        result = build_from_files(
            app_path=app,
            menu_path=menu if menu.exists() else MENU_TS,
            smoke_path=smoke if smoke.exists() else PROTECTED_ROUTES_TS,
            count_path=count_path if count_path.exists() else ROUTE_COUNT_JSON,
        )
    if args.count:
        print(result["count"])
        return 0 if not result["errors"] else 1
    if args.write:
        write_catalog(result)
        print(f"wrote {ROUTES_YAML} ({result['count']} routes)")
        if result["dead_nav"]:
            print(f"nav mismatches ({len(result['dead_nav'])}):")
            for d in result["dead_nav"]:
                print(f"  {d}")
    else:
        print(f"{result['count']} routes")
        for r in result["routes"]:
            extra = f" -> {r['redirect_to']}" if r.get("redirect_to") else ""
            print(f"  {r['route_kind']:8} {r['path']:40} {r['component']}{extra}")
    if result["errors"]:
        print("ERRORS:", file=sys.stderr)
        for e in result["errors"]:
            print(f"  {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
