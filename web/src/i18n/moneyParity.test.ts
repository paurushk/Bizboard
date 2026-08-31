import { describe, expect, it } from 'vitest';
import { en } from './en';
import { hi } from './hi';

const MONEY_ROOTS = ['billing', 'pos', 'einvoice', 'receipts', 'inventory'] as const;

function leafKeys(obj: unknown, prefix = ''): string[] {
  if (typeof obj === 'string') return prefix ? [prefix] : [];
  if (!obj || typeof obj !== 'object') return [];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    leafKeys(v, prefix ? `${prefix}.${k}` : k),
  );
}

describe('A-02 money namespace parity', () => {
  it('hi has every en key for billing, pos, einvoice, receipts, inventory', () => {
    for (const root of MONEY_ROOTS) {
      const enKeys = leafKeys((en as Record<string, unknown>)[root], root);
      const hiKeys = new Set(leafKeys((hi as Record<string, unknown>)[root], root));
      const missing = enKeys.filter((k) => !hiKeys.has(k));
      expect(missing, `${root} missing in hi: ${missing.join(', ')}`).toEqual([]);
    }
  });

  it('ta and gu have every en key for money namespaces (A-02b)', async () => {
    const { ta } = await import('./ta');
    const { gu } = await import('./gu');
    for (const root of MONEY_ROOTS) {
      const enKeys = leafKeys((en as Record<string, unknown>)[root], root);
      const taKeys = new Set(leafKeys((ta as Record<string, unknown>)[root], root));
      const guKeys = new Set(leafKeys((gu as Record<string, unknown>)[root], root));
      expect(enKeys.filter((k) => !taKeys.has(k))).toEqual([]);
      expect(enKeys.filter((k) => !guKeys.has(k))).toEqual([]);
    }
  });
});
