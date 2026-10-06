"""Validate the agent verdicts before they are written to the register.

Checks per chunk: every Task ID in chunks/chunk_NN.json appears exactly once; verdict is one of the four
labels; every evidence path exists and (when a symbol is given) the symbol occurs in that file.
Prints a per-chunk summary and writes verdicts_validated.json with an 'evidence_ok' flag per task.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "qos" / "evidence"
OK = {"Confirmed", "Partial", "Contradicted", "Unclear"}
out, problems = [], []
for chunk in sorted((EV / "chunks").glob("chunk_*.json")):
    vf = EV / "verdicts" / chunk.name
    want = [r["Task ID"] for r in json.loads(chunk.read_text(encoding="utf-8"))]
    if not vf.exists():
        problems.append(f"{chunk.name}: no verdict file yet")
        continue
    got = json.loads(vf.read_text(encoding="utf-8"))
    ids = [g.get("task_id") for g in got]
    if sorted(ids) != sorted(want):
        problems.append(f"{chunk.name}: id mismatch missing={sorted(set(want)-set(ids))[:5]} extra={sorted(set(ids)-set(want))[:5]} dup={len(ids)-len(set(ids))}")
    for g in got:
        if g.get("verdict") not in OK:
            problems.append(f"{g.get('task_id')}: bad verdict {g.get('verdict')!r}")
        ev = str(g.get("evidence", ""))
        items = [e.strip() for e in ev.split(";") if e.strip() and not e.strip().lower().startswith("none found")]
        bad = []
        for item in items:
            path, _, sym = item.partition(":")
            if re.match(r"^[A-Za-z]$", path) and sym[:1] in "\\/":  # windows drive letter
                path, _, sym = item[2:].partition(":")
                path = item[:2] + path
            p = ROOT / path.strip().replace("\\", "/")
            if not p.is_file():
                bad.append(f"missing file {path}")
                continue
            sym = sym.strip().split("(")[0].split(".")[-1].strip()
            if sym and sym not in p.read_text(encoding="utf-8", errors="ignore"):
                bad.append(f"symbol {sym} not in {path}")
        g["evidence_ok"] = not bad and (bool(items) or g["verdict"] in ("Contradicted", "Unclear"))
        g["evidence_problems"] = bad
        g["chunk"] = chunk.name
        out.append(g)
(EV / "verdicts_validated.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
from collections import Counter
print("tasks", len(out), Counter(g["verdict"] for g in out))
print("evidence ok", sum(g["evidence_ok"] for g in out), "of", len(out))
for p in problems: print("PROBLEM", p)
for g in out:
    if not g["evidence_ok"]: print("  evidence?", g["task_id"], g["verdict"], g["evidence_problems"][:2])
