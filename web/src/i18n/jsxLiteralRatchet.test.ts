import { readdirSync, readFileSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Text between JSX tags was moved onto en/hi on 2026-10-01; the remaining pages followed on
 * 2026-10-22 (QOS-0098). Every .tsx file under src/ is scanned, so a new English phrase between
 * tags fails here. Brand names and code identifiers stay as they are.
 */
const ROOT = resolve(process.cwd(), 'src');

// The help centre's FAQ is long-form English content with its own translation track, not UI text.
const EXEMPT = new Set(['pages/help/faqContent.tsx']);

function tsxFiles(): string[] {
  return (readdirSync(ROOT, { recursive: true }) as string[])
    .map((rel) => rel.split(sep).join('/'))
    .filter((rel) => rel.endsWith('.tsx'))
    .filter((rel) => !/\.(test|stories)\.tsx$/.test(rel) && !rel.includes('__tests__/') && !rel.startsWith('test/'))
    .filter((rel) => !EXEMPT.has(rel));
}

// Provider and brand names are not translated.
const ALLOWED = new Set(['Cashfree', 'Razorpay']);

// `(?<!=)`: the `>` of an arrow (`=> Promise<void>`) is a type, not a closing tag.
const JSX_TEXT = /(?<!=)([>])\s*([A-Z][a-z]+(?:[ ,.'/&-]+[A-Za-z0-9%()]+){0,8}[.!?:]?)\s*</g;

describe('i18n JSX text ratchet', () => {
  it('keeps every screen free of hard-coded English between tags', () => {
    const files = tsxFiles();
    expect(files.length).toBeGreaterThan(300);
    const hits: string[] = [];
    for (const rel of files) {
      const text = readFileSync(resolve(ROOT, rel), 'utf8');
      for (const match of text.matchAll(JSX_TEXT)) {
        const phrase = match[2];
        if (phrase.length >= 3 && !ALLOWED.has(phrase)) hits.push(`${rel}: ${phrase}`);
      }
    }
    expect(hits).toEqual([]);
  });
});
