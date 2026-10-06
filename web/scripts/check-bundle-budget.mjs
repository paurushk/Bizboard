#!/usr/bin/env node
/**
 * Bundle budget gate (perf programme A7 / decision D13).
 *
 * Reads the production build in ./dist and enforces two limits, both on GZIP size:
 *
 *   initial  - sum of every JS/CSS file referenced by dist/index.html (the entry
 *              script, modulepreload'ed vendor chunks and stylesheets). This is what a
 *              first-time visitor on a slow phone downloads before anything renders.
 *   perChunk - the largest single lazy chunk (anything not in the initial set), with
 *              an explicit allow-list for chunks that are legitimately big.
 *
 * Budgets live in bundle-budget.json and work as a RATCHET: set at measured + ~10 %,
 * lowered when the bundle shrinks, never raised to make a failure pass.
 *
 *   node scripts/check-bundle-budget.mjs            # check (CI)
 *   node scripts/check-bundle-budget.mjs --report   # print the numbers, never fail
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
// BUNDLE_BUDGET_DIST / BUNDLE_BUDGET_FILE exist so the script itself can be tested against a synthetic build.
const dist = process.env.BUNDLE_BUDGET_DIST || join(root, 'dist');
const reportOnly = process.argv.includes('--report');

if (!existsSync(join(dist, 'index.html'))) {
  console.error('bundle-budget: dist/index.html not found - run `npm run build` first.');
  process.exit(2);
}

const budget = JSON.parse(readFileSync(process.env.BUNDLE_BUDGET_FILE || join(root, 'bundle-budget.json'), 'utf8'));
const kb = (n) => n / 1024;
const gz = (file) => gzipSync(readFileSync(join(dist, file.replace(/^\//, '')))).length;

const html = readFileSync(join(dist, 'index.html'), 'utf8');
const initialFiles = [
  ...new Set([...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1])),
];
const initialSet = new Set(initialFiles.map((f) => f.replace(/^\/assets\//, '')));

const initial = initialFiles.map((f) => ({ file: f.replace(/^\/assets\//, ''), gz: gz(f) }));
const initialTotal = initial.reduce((s, x) => s + x.gz, 0);

const lazy = readdirSync(join(dist, 'assets'))
  .filter((f) => /\.(js|css)$/.test(f) && !initialSet.has(f))
  .map((f) => ({ file: f, gz: gz(`/assets/${f}`) }))
  .sort((a, b) => b.gz - a.gz);

console.log('bundle-budget: initial load (gzip)');
for (const x of initial) console.log(`  ${kb(x.gz).toFixed(1).padStart(8)} KB  ${x.file}`);
console.log(`  ${kb(initialTotal).toFixed(1).padStart(8)} KB  TOTAL  (budget ${budget.initialGzipKB} KB)`);
console.log('bundle-budget: largest lazy chunks (gzip)');
for (const x of lazy.slice(0, 5)) console.log(`  ${kb(x.gz).toFixed(1).padStart(8)} KB  ${x.file}`);

const problems = [];
if (kb(initialTotal) > budget.initialGzipKB) {
  problems.push(
    `initial load is ${kb(initialTotal).toFixed(1)} KB gzip, budget ${budget.initialGzipKB} KB. ` +
      'Lazy-load the new code, or justify and (rarely) raise the budget in bundle-budget.json in the same PR.',
  );
}
const allow = new Set(budget.allowLargeChunks ?? []);
for (const x of lazy) {
  // Chunk file names are content-hashed; the allow-list matches on the stable prefix.
  const stem = x.file.replace(/-[A-Za-z0-9_]{6,}\.(js|css)$/, '');
  if (kb(x.gz) > budget.perChunkGzipKB && !allow.has(stem)) {
    problems.push(
      `lazy chunk ${x.file} is ${kb(x.gz).toFixed(1)} KB gzip (limit ${budget.perChunkGzipKB} KB). ` +
        `Split it, or add "${stem}" to allowLargeChunks with a reason.`,
    );
  }
}

if (problems.length) {
  console.error('\nbundle-budget: FAILED');
  for (const p of problems) console.error(`  - ${p}`);
  if (!reportOnly) process.exit(1);
} else {
  console.log('\nbundle-budget: OK');
}
