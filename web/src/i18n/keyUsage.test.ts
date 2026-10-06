import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { en } from './en';

// MessageKey is `string`, so the compiler cannot tell a typo from a real key, and a missing key
// shows the user its raw dot-path ("common.none"). This reads every literal t('...') call in the
// app source and checks the key exists in en.ts. fullParity.test.ts only compares en with hi.

const SRC = join(__dirname, '..');

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === 'node_modules' || name === 'i18n' || name === 'test' || name === 'mocks') continue;
      out.push(...sourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

function has(tree: unknown, path: string): boolean {
  let node = tree as Record<string, unknown> | string | undefined;
  for (const part of path.split('.')) {
    if (node === undefined || typeof node === 'string') return false;
    node = (node as Record<string, unknown>)[part] as typeof node;
  }
  return typeof node === 'string';
}

describe('t() call sites', () => {
  it('only use keys that exist in the English catalogue', () => {
    const missing: string[] = [];
    const call = /(?<![A-Za-z0-9_.])t\(\s*'([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)'/g;
    for (const file of sourceFiles(SRC)) {
      const text = readFileSync(file, 'utf8');
      for (const match of text.matchAll(call)) {
        if (!has(en, match[1])) missing.push(`${file.slice(SRC.length + 1)}: ${match[1]}`);
      }
    }
    expect(missing).toEqual([]);
  });
});
