import os, re, sys, ast
sys.stdout.reconfigure(encoding='utf-8')

app_issues = []

def record(app, fpath, line, level, title, detail):
    app_issues.append({
        'app': app,
        'path': fpath.replace('\\', '/'),
        'line': line,
        'level': level,
        'title': title,
        'detail': detail
    })

# 1. Unbounded queries (missing pagination / .all() on huge tables in views)
for root, dirs, files in os.walk('backend'):
    if any(skip in root for skip in ['.venv', '__pycache__', 'migrations', 'tests']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        filepath = os.path.join(root, f)
        app = filepath.replace('\\', '/').split('/')[1]
        try:
            with open(filepath, 'r', encoding='utf-8') as src:
                lines = src.readlines()
        except:
            continue

        for idx, line in enumerate(lines):
            lno = idx + 1
            # Check direct request.data access in views without serializer
            if 'views.py' in f or 'view' in f:
                if re.search(r'request\.data\.get\(', line) and 'serializer' not in line:
                    # check if serializer is used nearby
                    surrounding = ''.join(lines[max(0, idx-5):min(len(lines), idx+6)])
                    if 'serializer' not in surrounding and 'Serializer' not in surrounding:
                        record(app, filepath, lno, 'P2', 'Direct request.data unvalidated access',
                               f'View accesses raw request.data directly without schema validation: {line.strip()[:70]}')

            # Check for lack of transaction.atomic on multiple DB creates/updates
            if 'def ' in line and any(action in line.lower() for action in ['create', 'post', 'complete', 'cancel', 'process', 'reconcile']):
                block = ''.join(lines[idx:min(len(lines), idx+30)])
                creates = block.count('.objects.create(') + block.count('.save()')
                if creates >= 2 and 'transaction.atomic' not in block:
                    record(app, filepath, lno, 'P1', 'Missing atomic transaction block on multiple writes',
                           f'Method performs multiple database mutations without explicit @transaction.atomic: {line.strip()[:70]}')

            # Check for unhandled division by zero
            if '/' in line and not line.strip().startswith('#') and not '//' in line:
                if re.search(r'/\s*[a-zA-Z_][a-zA-Z0-9_]*', line) and 'Decimal(' in line:
                    surrounding = ''.join(lines[max(0, idx-4):idx+1])
                    if 'if ' not in surrounding and 'or Decimal(' not in line and 'max(' not in line:
                        record(app, filepath, lno, 'P2', 'Potential division by zero',
                               f'Decimal division without zero-divisor guard: {line.strip()[:70]}')

            # Check for missing company filter on bulk updates / deletes
            if re.search(r'\.objects\.filter\(.*?\)\.delete\(', line) or re.search(r'\.objects\.filter\(.*?\)\.update\(', line):
                if 'company' not in line and 'company_id' not in line and app not in ['config']:
                    record(app, filepath, lno, 'P1', 'Bulk update/delete without explicit company scope',
                           f'Bulk query mutation missing explicit company/company_id filter: {line.strip()[:70]}')

print(f"Total potential issues detected: {len(app_issues)}")
import json
with open('scripts/deep_scan_results.json', 'w', encoding='utf-8') as out:
    json.dump(app_issues, out, indent=2)

print("Saved to scripts/deep_scan_results.json")
