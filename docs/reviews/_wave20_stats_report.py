#!/usr/bin/env python3
import json
import re
from collections import Counter
from pathlib import Path

stats = json.loads(Path("_stats.json").read_text(encoding="utf-8"))
print("TOTAL", stats["total"])
print("OPEN", stats["open_count"])
print("SEV", json.dumps(stats["severity"]))
print("PRI", json.dumps(stats["priority"]))
print("STATUS", json.dumps(stats["status"]))

days = 0.0
n = 0
for f in ("_wave19_issues.py", "_wave19_missed_issues.py", "_wave20_issues.py"):
    src = Path(f).read_text(encoding="utf-8")
    for m in re.finditer(r'effort="([^"]+)"', src):
        raw = m.group(1).strip().lower()
        n += 1
        nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)d", raw)]
        if not nums:
            continue
        if "-" in raw and len(nums) >= 2:
            days += (nums[0] + nums[1]) / 2
        else:
            days += sum(nums)

print("OPEN_EFFORT_ISSUES", n, "DAYS", round(days, 1))

open_iss = [i for i in stats["issues"] if i.get("status") == "Open"]
print("OPEN_LIST_LEN", len(open_iss))
print("OPEN_SEV", dict(Counter(i["severity"] for i in open_iss)))
print("OPEN_PRI", dict(Counter(i["priority"] for i in open_iss)))
print("OPEN_CAT", dict(Counter(i["category"] for i in open_iss).most_common()))
print("OPEN_MOD", dict(Counter(i["module"] for i in open_iss).most_common()))
print("ALL_CAT", dict(Counter(stats["category"]).most_common()))
print("ALL_MOD_TOP", dict(Counter(stats["module"]).most_common(20)))
