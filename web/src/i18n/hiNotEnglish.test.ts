import { describe, expect, it } from 'vitest';
import { en } from './en';
import { hi } from './hi';

/**
 * BB-103: a Hindi screen must not show an English phrase. Key parity is checked elsewhere
 * (fullParity.test.ts); this checks the values. Measured 2026-10-24: 7 of 7,584 strings are the
 * same in both languages, all tax acronyms or product names that are not translated.
 */
const SAME_ON_PURPOSE = new Set([
  'purchaseDetail.rcmCgst',
  'purchaseDetail.rcmSgst',
  'purchaseDetail.rcmIgst',
  'gstr3b.gstnJson',
  'gstSettings.gspCleartax',
  'gstSettings.gspMaster',
  'legacyImport.sources.marg',
]);

type Tree = { [key: string]: unknown };

function flatten(tree: Tree, prefix = '', out: Record<string, string> = {}): Record<string, string> {
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object') flatten(value as Tree, path, out);
    else if (typeof value === 'string') out[path] = value;
  }
  return out;
}

describe('Hindi strings are translated', () => {
  it('no English phrase of two or more words is copied into hi', () => {
    const english = flatten(en as Tree);
    const hindi = flatten(hi as Tree);
    expect(Object.keys(english).length).toBeGreaterThan(7000);
    const copied = Object.keys(english).filter(
      (key) =>
        hindi[key] === english[key] && /[a-z]{3,}\s+[a-z]{3,}/i.test(english[key]) && !SAME_ON_PURPOSE.has(key),
    );
    expect(copied, `translate these in hi.ts:\n${copied.join('\n')}`).toEqual([]);
  });

  it('every allowed exception still exists', () => {
    const english = flatten(en as Tree);
    for (const key of SAME_ON_PURPOSE) expect(english[key], key).toBeDefined();
  });
});
