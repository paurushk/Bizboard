import os, re, sys, ast
sys.stdout.reconfigure(encoding='utf-8')

findings = []

def add_finding(module, filename, line, severity, category, title, description):
    findings.append({
        'module': module,
        'file': filename,
        'line': line,
        'severity': severity,
        'category': category,
        'title': title,
        'description': description
    })

# Scan backend files
for root, dirs, files in os.walk('backend'):
    if any(skip in root for skip in ['.venv', '__pycache__', 'migrations', 'tests']):
        continue
    for file in files:
        if not file.endswith('.py'):
            continue
        filepath = os.path.join(root, file)
        rel_path = filepath.replace('\\', '/')
        module = rel_path.split('/')[1]
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception:
            continue

        # Check 1: float usage in financial/tax contexts
        for idx, line in enumerate(lines):
            line_num = idx + 1
            if re.search(r'\bfloat\(', line) and any(kw in line.lower() for kw in ['tax', 'price', 'amount', 'balance', 'total', 'rate', 'discount', 'cogs', 'margin']):
                add_finding(module, rel_path, line_num, 'P1', 'Financial Precision', 
                            'Binary float conversion in financial calculation',
                            f'Code uses float() instead of Decimal in financial/tax calculation: `{line.strip()[:80]}`')

            # Check 2: bare except or except Exception: pass
            if re.search(r'except\s*(Exception)?\s*:\s*pass', line):
                add_finding(module, rel_path, line_num, 'P2', 'Error Handling',
                            'Silent exception swallowing',
                            f'Bare pass in exception block can hide critical database/integrity errors: `{line.strip()[:80]}`')

            # Check 3: Raw SQL without company_id or parameterization
            if 'execute(' in line and ('SELECT' in line or 'UPDATE' in line or 'DELETE' in line):
                if '%s' not in line and 'params' not in line:
                    add_finding(module, rel_path, line_num, 'P0', 'Security / SQLi',
                                'Potential unparameterized raw SQL execution',
                                f'Raw SQL execution without visible parameterization: `{line.strip()[:80]}`')

            # Check 4: Celery task without rls or company_id handling
            if '@shared_task' in line or '@app.task' in line:
                # check next 10 lines
                func_def = '\n'.join(lines[idx:idx+15])
                if 'company_id' not in func_def and 'set_current_company' not in func_def and 'tenant_context' not in func_def:
                    add_finding(module, rel_path, line_num, 'P1', 'Multi-Tenancy',
                                'Celery task lacks company_id parameter or RLS tenant context',
                                f'Celery task defined without explicit company_id parameter or tenant context wrapper.')

print(f"Total initial automated findings: {len(findings)}")
for f in findings[:20]:
    print(f"[{f['severity']}] {f['module']} | {f['file']}:{f['line']} | {f['title']}")
