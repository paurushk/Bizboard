/**
 * MT-001 gate. Run after `npm run build`.
 * The generated worker must:
 * 1. not register a NavigationRoute whose handler is offline.html
 * 2. not register a NavigationRoute that serves precached index.html
 * 3. keep navigate NetworkFirst (bizboard-pages, 10s) with an offline.html error fallback
 * 4. not NetworkFirst-cache /api
 */
import fs from 'node:fs';
import path from 'node:path';

const dist = path.resolve('dist');
if (!fs.existsSync(dist)) {
  console.error('dist/ is missing. Run npm run build first.');
  process.exit(1);
}

const swPath = path.join(dist, 'sw.js');
if (!fs.existsSync(swPath)) {
  console.error('dist/sw.js is missing. Run npm run build first.');
  process.exit(1);
}

// Route registration lives in sw.js. The workbox runtime also mentions
// NetworkFirst and createHandlerBoundToURL, so scanning it false-fails or
// hides a bad sw.js.
const text = fs.readFileSync(swPath, 'utf8');
const failures = [];

if (/createHandlerBoundToURL\(\s*["']\/?offline\.html["']\s*\)/.test(text)) {
  failures.push('NavigationRoute handler is bound to offline.html');
}
if (/navigateFallback["']?\s*[:=]\s*["'][^"']*offline\.html["']/.test(text)) {
  failures.push('navigateFallback still points at offline.html');
}
if (/new\s+\w*\.?NavigationRoute\(/.test(text) || /NavigationRoute\(/.test(text)) {
  failures.push('a NavigationRoute is registered (navigateFallback must stay null)');
}
if (!text.includes('NetworkFirst')) failures.push('NetworkFirst handler is missing');
if (!text.includes('bizboard-pages')) failures.push('cache name bizboard-pages is missing');
if (!/networkTimeoutSeconds\s*:\s*10\b/.test(text)) {
  failures.push('navigate networkTimeoutSeconds is not 10');
}
if (!text.includes('offline.html')) {
  failures.push('offline.html error fallback is missing from the worker');
}
if (/\/api\//.test(text) && /NetworkFirst/.test(text)) {
  const apiNearNetworkFirst = /\/api\/[\s\S]{0,180}NetworkFirst|NetworkFirst[\s\S]{0,180}\/api\//.test(text);
  if (apiNearNetworkFirst) failures.push('NetworkFirst is paired with an /api route');
}

if (failures.length) {
  console.error('Service worker navigate gate failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  console.error('Checked: sw.js');
  process.exit(1);
}

console.log('Service worker navigate gate passed (sw.js).');
