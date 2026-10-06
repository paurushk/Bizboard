"""Aggregate JUnit XML files into qos/evidence/test_results.json: {'backend/tests/x.py::Class::test': 'pass'|'fail'|'skip'}.
Parametrized cases roll up to their base id (any fail -> fail; all skip -> skip). Later files override earlier ones.
usage: python build_results.py junit1.xml [junit2.xml ...]"""
import json, sys, xml.etree.ElementTree as ET
from pathlib import Path
out = {}
for path in sys.argv[1:]:
    agg = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        parts = case.get("classname", "").split(".")
        i = max((k for k, p in enumerate(parts) if p.startswith("test_")), default=None)
        if i is None: continue
        file = "backend/" + "/".join(parts[: i + 1]) + ".py"
        cls = parts[i + 1:]
        name = case.get("name", "").split("[")[0]
        key = "::".join([file, *cls, name])
        sk = case.find("skipped")
        xfail = sk is not None and sk.get("type") == "pytest.xfail"  # a strict xfail records a known product gap
        o = "fail" if (case.find("failure") is not None or case.find("error") is not None or xfail) else "skip" if sk is not None else "pass"
        agg.setdefault(key, []).append(o)
    for k, v in agg.items():
        out[k] = "fail" if "fail" in v else ("pass" if "pass" in v else "skip")
Path(__file__).with_name("test_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
from collections import Counter
print(len(out), Counter(out.values()))
