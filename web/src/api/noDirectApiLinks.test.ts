// WP-ID2: no <a href>/<img src>/window.open straight to the API. Those requests carry no
// X-Company-Id, so for a user in two companies they would run as whichever company was last
// active. Fetch through apiClient (openAuthenticatedFile / a blob URL) instead.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const SRC = resolve(__dirname, '..');
const PATTERN = /(?:href|src|data)=\{?\s*[`'"]\/api\/|window\.open\(\s*[`'"]\/api\/|\b(?:href|src)=\{\s*\w+\.url\s*\}/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === 'mocks' || name === 'test' ? [] : files(full);
    return /\.(tsx?|jsx?)$/.test(name) && !/\.test\./.test(name) ? [full] : [];
  });
}

describe('no direct API links', () => {
  it('finds none in the web source', () => {
    const allowed = new Set([
      // Already object URLs created from apiClient blobs.
      'pages/imports/bill/SourceBillViewer.tsx',
    ]);
    const hits = files(SRC)
      .map((path) => relative(SRC, path).replace(/\\/g, '/'))
      .filter((rel) => !allowed.has(rel))
      .flatMap((rel) =>
        readFileSync(join(SRC, rel), 'utf-8')
          .split('\n')
          .map((line, i) => (PATTERN.test(line) ? `${rel}:${i + 1}: ${line.trim()}` : ''))
          .filter(Boolean),
      );
    expect(hits).toEqual([]);
  });
});
