import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { COMPLETE_GATES } from './catalog';

const ROOT = resolve(__dirname, '../../..');
const PLAN = resolve(ROOT, 'docs/COMPLETE_GATE_VISIBILITY_PLAN.md');
const COVERAGE = resolve(ROOT, 'docs/FREEZE_SCOPE_COVERAGE.md');
const CG_RE = /CG-\d+/g;

describe('Complete-gate catalog index (G-complete-gate)', () => {
  const plan = readFileSync(PLAN, 'utf8');
  const coverage = readFileSync(COVERAGE, 'utf8');
  const planIds = [...new Set(plan.match(CG_RE) ?? [])].sort();
  const catalogIds = COMPLETE_GATES.map((row) => row.id).sort();

  it('catalog IDs match the plan document', () => {
    expect(catalogIds).toEqual(planIds);
  });

  it('every CG id is cited in FREEZE_SCOPE_COVERAGE.md', () => {
    const missing = catalogIds.filter((id) => !coverage.includes(id));
    expect(missing).toEqual([]);
  });

  it('gated rows cite an existing test file that mentions the id', () => {
    const missing: string[] = [];
    for (const row of COMPLETE_GATES) {
      if (row.status !== 'gated') continue;
      if (!row.testFile) {
        missing.push(`${row.id} gated without testFile`);
        continue;
      }
      const abs = resolve(ROOT, row.testFile);
      const body = readFileSync(abs, 'utf8');
      if (!body.includes(row.id)) {
        missing.push(`${row.id} not cited in ${row.testFile}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it('gap rows do not claim a testFile', () => {
    const wronglyGated = COMPLETE_GATES.filter((row) => row.status === 'gap' && row.testFile);
    expect(wronglyGated.map((row) => row.id)).toEqual([]);
  });
});
