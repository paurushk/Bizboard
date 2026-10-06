import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * A catalog sentence with a {placeholder} must be called with a values object.
 * Calling t('key') on it prints the braces to the user ("They owe {amount}").
 */
const SRC = join(__dirname, '..');

function catalogPlaceholderKeys(): Set<string> {
  const text = readFileSync(join(__dirname, 'en.ts'), 'utf8');
  const keys = new Set<string>();
  let group = '';
  for (const line of text.split('\n')) {
    const g = /^ {2}(\w+): \{\s*$/.exec(line);
    if (g) {
      group = g[1];
      continue;
    }
    const entry = /^ {4}(\w+): '(.*)',?\s*$/.exec(line);
    if (entry && group && /\{\w+\}/.test(entry[2])) keys.add(`${group}.${entry[1]}`);
  }
  return keys;
}

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name === 'i18n' || name === 'node_modules') continue;
      sourceFiles(path, out);
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) {
      out.push(path);
    }
  }
  return out;
}

describe('i18n placeholders', () => {
  it('never renders a sentence with {placeholders} through a single-argument t()', () => {
    const withPlaceholders = catalogPlaceholderKeys();
    expect(withPlaceholders.size).toBeGreaterThan(50);
    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const text = readFileSync(file, 'utf8');
      for (const match of text.matchAll(/\bt\('([\w.]+)'\)/g)) {
        if (withPlaceholders.has(match[1])) offenders.push(`${file.replace(SRC, 'src')}: ${match[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
