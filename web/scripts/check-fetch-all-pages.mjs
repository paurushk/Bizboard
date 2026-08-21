#!/usr/bin/env node
/**
 * BB-000463 CI guard: fetchAllPages must not appear outside resources.ts masters helper.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = join(import.meta.dirname, '..', 'src');
const banned = 'fetchAllPages';
const allowed = 'fetchAllPagesMasters';
const hits = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const st = statSync(path);
    if (st.isDirectory()) {
      walk(path);
      continue;
    }
    if (!/\.(ts|tsx)$/.test(name)) continue;
    const text = readFileSync(path, 'utf8');
    if (!text.includes(banned)) continue;
    const rel = path.replace(/\\/g, '/');
    const lines = text.split('\n');
    lines.forEach((line, i) => {
      if (line.includes(banned) && !line.includes(allowed)) {
        hits.push(`${rel}:${i + 1}: ${line.trim()}`);
      }
    });
  }
}

walk(root);
if (hits.length) {
  console.error('Banned fetchAllPages usage (BB-000463):\n' + hits.join('\n'));
  process.exit(1);
}
console.log('check-fetch-all-pages: OK');
