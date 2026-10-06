import json, sys

with open('module_tasks_summary.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

with open('scripts/all_module_details.txt', 'w', encoding='utf-8') as out:
    for mod, tasks in sorted(data.items()):
        contras = [t for t in tasks if t.get('verdict') == 'Contradicted']
        parts = [t for t in tasks if t.get('verdict') == 'Partial']
        out.write(f"MODULE: {mod} | Total: {len(tasks)} | Gaps (Contradicted): {len(contras)} | Partial: {len(parts)}\n")
        if contras:
            out.write("  -- GAPS / CONTRADICTED TASKS --\n")
            for c in contras:
                out.write(f"    * [{c['tid']}] ({c['prio']}) {c['task']}\n      Reason: {c['reason']}\n      Evidence: {c['evidence']}\n")
        if parts:
            out.write("  -- PARTIAL IMPLEMENTATIONS --\n")
            for p in parts:
                out.write(f"    * [{p['tid']}] ({p['prio']}) {p['task']}\n      Reason: {p['reason']}\n      Evidence: {p['evidence']}\n")
        out.write("="*80 + "\n\n")

print("Generated scripts/all_module_details.txt successfully.")
