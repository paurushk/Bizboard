import { describe, expect, it } from 'vitest';
import { en } from './en';
import { hi } from './hi';

// F1-023: moneyParity.test.ts only checked 5 namespaces (billing, pos,
// einvoice, receipts, inventory) — a key missing from `hi` anywhere else
// falls through `t()`'s `en` fallback silently, so nothing ever signalled a
// drift outside those 5 roots. `hi` is the only catalog meant to be a full
// second locale (`ta`/`gu` are deliberately partial — see i18n/index.ts,
// which won't even select them as the active locale), so this checks the
// whole tree.

function leafKeys(obj: unknown, prefix = ''): string[] {
  if (typeof obj === 'string') return prefix ? [prefix] : [];
  if (!obj || typeof obj !== 'object') return [];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    leafKeys(v, prefix ? `${prefix}.${k}` : k),
  );
}

describe('F1-023 full i18n catalog parity', () => {
  it('hi has every en leaf key', () => {
    const enKeys = leafKeys(en);
    const hiKeys = new Set(leafKeys(hi as Record<string, unknown>));
    const missing = enKeys.filter((k) => !hiKeys.has(k));
    expect(missing, `keys missing in hi: ${missing.join(', ')}`).toEqual([]);
  });

  it('en has every hi leaf key (no orphaned hi-only keys)', () => {
    const hiKeys = leafKeys(hi as Record<string, unknown>);
    const enKeys = new Set(leafKeys(en));
    const extra = hiKeys.filter((k) => !enKeys.has(k));
    expect(extra, `keys only in hi (missing in en): ${extra.join(', ')}`).toEqual([]);
  });
});
