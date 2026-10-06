import { describe, expect, it } from 'vitest';
import { en } from './en';
import { hi } from './hi';

// F1-023: moneyParity.test.ts only checked 5 namespaces (billing, pos,
// einvoice, receipts, inventory) — a key missing from `hi` anywhere else
// falls through `t()`'s `en` fallback silently, so nothing ever signalled a
// drift outside those 5 roots. `hi` is the only full second locale (R-084:
// ta/gu catalogs were deleted; switcher is en/hi only).

function leafKeys(obj: unknown, prefix = ''): string[] {
  if (typeof obj === 'string') return prefix ? [prefix] : [];
  if (!obj || typeof obj !== 'object') return [];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    leafKeys(v, prefix ? `${prefix}.${k}` : k),
  );
}

function leafEntries(obj: unknown, prefix = ''): Record<string, string> {
  if (typeof obj === 'string') return prefix ? { [prefix]: obj } : {};
  if (!obj || typeof obj !== 'object') return {};
  return Object.entries(obj as Record<string, unknown>).reduce<Record<string, string>>((acc, [k, v]) => {
    Object.assign(acc, leafEntries(v, prefix ? `${prefix}.${k}` : k));
    return acc;
  }, {});
}

describe('F1-023 full i18n catalog parity', () => {
  it('hi has every en leaf key', () => {
    const enKeys = leafKeys(en);
    const hiKeys = new Set(leafKeys(hi as Record<string, unknown>));
    const missing = enKeys.filter((k) => !hiKeys.has(k));
    expect(missing, `keys missing in hi: ${missing.join(', ')}`).toEqual([]);
  });

  it('identical English sentences of 3+ words are translated', () => {
    const allow = new Set(
      ['GST', 'GSTIN', 'PAN', 'HSN', 'SAC', 'POS', 'UPI', 'IFSC', 'OK', 'PDF', 'QR', 'email', 'SMS'].map((s) =>
        s.toLowerCase(),
      ),
    );
    const enLeaves = leafEntries(en);
    const hiLeaves = leafEntries(hi as Record<string, unknown>);
    const failures: string[] = [];
    for (const [key, value] of Object.entries(enLeaves)) {
      const hindi = hiLeaves[key];
      if (hindi === undefined || hindi !== value) continue;
      if (!/[A-Za-z]{3,}/.test(value)) continue;
      const words = value.trim().split(/\s+/).filter(Boolean);
      if (words.length < 3) continue;
      const allowable = (word: string) => {
        const token = word.toLowerCase().replace(/[^a-z0-9]/gi, '');
        if (!token) return true;
        if (allow.has(token)) return true;
        return word === word.toUpperCase() && /[A-Z]/.test(word);
      };
      if (words.every(allowable)) continue;
      failures.push(`${key}: ${value}`);
    }
    expect(failures, `Hindi copies English:\n${failures.join('\n')}`).toEqual([]);
  });

  it('en has every hi leaf key (no orphaned hi-only keys)', () => {
    const hiKeys = leafKeys(hi as Record<string, unknown>);
    const enKeys = new Set(leafKeys(en));
    const extra = hiKeys.filter((k) => !enKeys.has(k));
    expect(extra, `keys only in hi (missing in en): ${extra.join(', ')}`).toEqual([]);
  });
});
