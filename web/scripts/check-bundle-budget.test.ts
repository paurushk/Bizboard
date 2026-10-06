// @vitest-environment node
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

// perf programme A7 / D13: the bundle budget gate must fail when it should, and only then.
// Incompressible (random) bytes make gzip size ~= raw size, so sizes in the tests are predictable.

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'check-bundle-budget.mjs');
const KB = 1024;

let dir: string;

function write(rel: string, bytes: number | string) {
  const path = join(dir, 'dist', rel);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, typeof bytes === 'string' ? bytes : randomBytes(bytes));
}

function build(opts: { initial: Record<string, number>; lazy?: Record<string, number>; budget?: object }) {
  const tags = Object.keys(opts.initial)
    .map((f) => (f.endsWith('.css') ? `<link rel="stylesheet" href="/assets/${f}">` : `<script type="module" src="/assets/${f}"></script>`))
    .join('');
  write('index.html', `<html><head>${tags}</head><body></body></html>`);
  for (const [f, n] of Object.entries(opts.initial)) write(`assets/${f}`, n);
  for (const [f, n] of Object.entries(opts.lazy ?? {})) write(`assets/${f}`, n);
  writeFileSync(
    join(dir, 'budget.json'),
    JSON.stringify(opts.budget ?? { initialGzipKB: 100, perChunkGzipKB: 50, allowLargeChunks: [] }),
  );
}

function run(args: string[] = []) {
  return spawnSync('node', [SCRIPT, ...args], {
    env: { ...process.env, BUNDLE_BUDGET_DIST: join(dir, 'dist'), BUNDLE_BUDGET_FILE: join(dir, 'budget.json') },
    encoding: 'utf8',
  });
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'bb-budget-'));
});
afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe('check-bundle-budget', () => {
  it('passes when the initial load and every lazy chunk are inside budget', () => {
    build({ initial: { 'index-AAAAAAAA.js': 40 * KB, 'vendor-BBBBBBBB.js': 30 * KB }, lazy: { 'Page-CCCCCCCC.js': 20 * KB } });
    const r = run();
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('bundle-budget: OK');
  });

  it('fails when the initial load exceeds its budget, naming the number', () => {
    build({ initial: { 'index-AAAAAAAA.js': 80 * KB, 'vendor-BBBBBBBB.js': 60 * KB } });
    const r = run();
    expect(r.status).toBe(1);
    expect(r.stderr).toMatch(/initial load is 1[0-9][0-9]\.\d KB gzip, budget 100 KB/);
  });

  it('counts stylesheets and preloaded vendor chunks in the initial load, not just the entry', () => {
    // entry alone (60) is under 100, but entry + vendor + css (60+30+20) is over.
    build({ initial: { 'index-AAAAAAAA.js': 60 * KB, 'vendor-BBBBBBBB.js': 30 * KB, 'index-CCCCCCCC.css': 20 * KB } });
    expect(run().status).toBe(1);
  });

  it('does NOT count lazy chunks in the initial load', () => {
    build({ initial: { 'index-AAAAAAAA.js': 40 * KB }, lazy: { 'A-11111111.js': 45 * KB, 'B-22222222.js': 45 * KB, 'C-33333333.js': 45 * KB } });
    expect(run().status).toBe(0);
  });

  it('fails on an oversized lazy chunk and names the file', () => {
    build({ initial: { 'index-AAAAAAAA.js': 10 * KB }, lazy: { 'Huge-DDDDDDDD.js': 80 * KB } });
    const r = run();
    expect(r.status).toBe(1);
    expect(r.stderr).toContain('Huge-DDDDDDDD.js');
    expect(r.stderr).toContain('allowLargeChunks');
  });

  it('lets an allow-listed chunk exceed the per-chunk limit (matched on the stable prefix)', () => {
    build({
      initial: { 'index-AAAAAAAA.js': 10 * KB },
      lazy: { 'Huge-DDDDDDDD.js': 80 * KB },
      budget: { initialGzipKB: 100, perChunkGzipKB: 50, allowLargeChunks: ['Huge'] },
    });
    expect(run().status).toBe(0);
  });

  it('--report prints the numbers but never fails', () => {
    build({ initial: { 'index-AAAAAAAA.js': 200 * KB } });
    const r = run(['--report']);
    expect(r.status).toBe(0);
    expect(r.stderr).toContain('FAILED'); // still says what is wrong
  });

  it('exits 2 with a clear message when there is no build to check', () => {
    writeFileSync(join(dir, 'budget.json'), JSON.stringify({ initialGzipKB: 1, perChunkGzipKB: 1 }));
    const r = run();
    expect(r.status).toBe(2);
    expect(r.stderr).toContain('npm run build');
  });
});

describe('the committed budget file', () => {
  it('is valid and keeps a sane ratchet (not silently loosened)', async () => {
    const budget = JSON.parse(
      (await import('node:fs')).readFileSync(join(dirname(SCRIPT), '..', 'bundle-budget.json'), 'utf8'),
    ) as { initialGzipKB: number; perChunkGzipKB: number; allowLargeChunks: string[] };
    expect(budget.initialGzipKB).toBeGreaterThan(0);
    // Measured 481.7 KB on 2026-10-02 with ~10% headroom. If this fails because someone raised the
    // budget, that is the point: raise it deliberately, with a reason, in this assertion too.
    expect(budget.initialGzipKB).toBeLessThanOrEqual(530);
    expect(budget.perChunkGzipKB).toBeLessThanOrEqual(150);
  });
});
