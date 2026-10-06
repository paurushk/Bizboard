import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('module_tasks_summary.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for mod, tasks in sorted(data.items()):
    contras = [t for t in tasks if t.get('verdict') == 'Contradicted']
    parts = [t for t in tasks if t.get('verdict') == 'Partial']
    print(f"=== MODULE: {mod} (Total: {len(tasks)}, Contradicted: {len(contras)}, Partial: {len(parts)}) ===")
    if contras:
        print("  -- CONTRADICTED (GAPS) --")
        for c in contras:
            print(f"    [{c['tid']}] ({c['prio']}) {c['task']} | Reason: {c['reason']}")
    if parts:
        print("  -- PARTIAL --")
        for p in parts:
            print(f"    [{p['tid']}] ({p['prio']}) {p['task']} | Reason: {p['reason']}")
