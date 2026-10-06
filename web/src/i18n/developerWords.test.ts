import { describe, expect, it } from 'vitest';
import { en } from './en';

/**
 * UX guard (GM-07): user-visible copy must not leak backend vocabulary.
 * Flags ALL_CAPS_WITH_UNDERSCORE codes, archetype codes such as ARCH-05, and API jargon.
 * `KNOWN` is a ratchet: entries may only be removed. A new leak fails the test.
 */
const PATTERNS: Array<[string, RegExp]> = [
  ['backend code', /\b[A-Z]{2,}(?:_[A-Z0-9]+)+\b/],
  ['archetype code', /\bARCH-\d{2}\b/],
  ['api jargon', /\bsupported: (?:true|false)\b|\bAPI name\b|\bpayload\b/i],
];

const KNOWN = new Set<string>([
  // Owner/ops-facing or technical by design; remove an entry when its copy is rewritten.
  'common.mockBanner',
  'pos.disabled',
  'reports.tdsOwnerOnly',
  'settings.backupEncryptedHelp',
  'settings.backupKeyWarning',
  'einvoice.payloadOnlyHelp',
  'einvoice.preparePayload',
  'einvoice.payloadReady',
  'einvoice.ewayPayloadReady',
  'gstHonesty.rawPayload',
  'reports.payloadSummary',
]);

function walk(node: unknown, path: string, out: Array<[string, string]>) {
  if (typeof node === 'string') out.push([path, node]);
  else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) walk(v, path ? `${path}.${k}` : k, out);
  }
}

describe('developer words in user-visible copy', () => {
  it('has no new backend vocabulary in en.ts', () => {
    const strings: Array<[string, string]> = [];
    walk(en, '', strings);
    const hits: string[] = [];
    for (const [path, value] of strings) {
      for (const [name, re] of PATTERNS) {
        if (re.test(value) && !KNOWN.has(path)) hits.push(`${path} [${name}]: ${value.slice(0, 90)}`);
      }
    }
    expect(hits, `Leaks:\n${hits.join('\n')}`).toEqual([]);
  });
});
