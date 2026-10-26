import { readdirSync, readFileSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * BB-101 / QOS-0096 (UX-N07): a table that scrolls sideways on a phone must be reachable by
 * keyboard, or its hidden columns cannot be read without a mouse. The theme makes every
 * TableContainer focusable; a hand-made Paper or Box with `overflow: 'auto'` that wraps a
 * <Table> must do the same with tabIndex={0} and a labelled region (DocumentListPage pattern).
 * Found 2026-10-24: the sales and purchase return detail tables were text-only and unreachable.
 */
const ROOT = resolve(process.cwd(), 'src');
const OPENING = /<(Paper|Box)\b[^>]*overflow:\s*'auto'[^>]*>/g;

function tsxFiles(): string[] {
  return (readdirSync(ROOT, { recursive: true }) as string[])
    .map((rel) => rel.split(sep).join('/'))
    .filter((rel) => rel.endsWith('.tsx') && !/\.(test|stories)\.tsx$/.test(rel));
}

describe('scrollable tables are keyboard-reachable', () => {
  it('every overflow container that wraps a Table is focusable', () => {
    const offenders: string[] = [];
    for (const rel of tsxFiles()) {
      const text = readFileSync(resolve(ROOT, rel), 'utf8');
      for (const match of text.matchAll(OPENING)) {
        const after = text.slice(match.index + match[0].length, match.index + match[0].length + 400);
        const wrapsTable = /^\s*(?:\{[^}]*\}\s*)?(?:<Typography[\s\S]*?<\/Typography>\s*)?(?:\{[^\n]*\?\s*\(\s*)?<Table\b/.test(after);
        if (wrapsTable && !/tabIndex=/.test(match[0])) {
          const line = text.slice(0, match.index).split('\n').length;
          offenders.push(`${rel}:${line}`);
        }
      }
    }
    expect(offenders, `add tabIndex={0} role="region" aria-label to:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('the theme keeps table containers focusable and phone touch targets at 44px', () => {
    const theme = readFileSync(resolve(ROOT, 'theme/index.ts'), 'utf8');
    expect(theme).toMatch(/MuiTableContainer:\s*\{\s*defaultProps:\s*\{\s*tabIndex:\s*0\s*\}/);
    expect(theme).toMatch(/MuiIconButton:[\s\S]{0,200}minWidth:\s*44,\s*minHeight:\s*44/);
  });
});
