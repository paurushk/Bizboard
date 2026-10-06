"""Run exactly the tests linked to MVP tasks. Expands base ids to the collected (parametrized) node ids."""
import json, glob, subprocess, sys, os
root = os.path.dirname(os.path.abspath(__file__)) + "/../.."
nodes = [l.strip() for l in open(root + "/qos/evidence/all_nodeids.txt", encoding="utf-8")]
want = set()
for f in glob.glob(root + "/qos/evidence/mvp_links/mvp_*.json"):
    for g in json.load(open(f, encoding="utf-8")):
        for t in g["test_ids_resolved"]: want.add(t.replace("backend/", "", 1))
extra = root + "/qos/evidence/new_tests.txt"
if os.path.exists(extra): want |= {l.strip() for l in open(extra) if l.strip()}
sel = [n for n in nodes if n.split("[")[0] in want]
print("selected", len(sel), "of", len(want), "base ids")
cmd = [root + "/backend/.venv/Scripts/python.exe", "-m", "pytest", *sel, "-q", "-p", "no:cacheprovider", "--create-db" if "--create-db" in sys.argv else "--reuse-db",
       "--junitxml=" + root + "/qos/evidence/pytest-junit-linked-2026-10-04.xml", "-o", "junit_family=xunit2"]
sys.exit(subprocess.call(cmd, cwd=root + "/backend"))
