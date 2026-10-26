import { readdirSync, readFileSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * BB-104 / QOS-0098: a page that fetches data must show something when the request fails, not
 * a blank screen. Every page under src/pages that calls useQuery / useInfiniteQuery must handle
 * the error state itself or render through a shared state wrapper (AsyncSection, Grid, ...).
 * Scanned 2026-10-23: 173 pages, all covered.
 */
const ROOT = resolve(process.cwd(), 'src/pages');

// A page may degrade on purpose instead of showing an error; say why.
const DELIBERATE_FALLBACK: Record<string, string> = {
  // Home only routes: on a failed company fetch it falls back to the signed-in user's company.
  'HomePage.tsx': 'routes with the session company when the fetch fails',
};

const FETCHES = /\buse(?:Infinite)?Query\(/;
const HANDLES_ERROR =
  /\bisError\b|\berror\b|isLoadingError|status === 'error'|\bonError\b|<AsyncSection\b|<Grid\b|<DataGrid\b|ErrorAlert|ErrorState|QueryState|PageStates|LoadState/;

function pageFiles(): string[] {
  return (readdirSync(ROOT, { recursive: true }) as string[])
    .map((rel) => rel.split(sep).join('/'))
    .filter((rel) => rel.endsWith('.tsx') && !/\.(test|stories)\.tsx$/.test(rel) && !rel.includes('__tests__/'));
}

describe('page loading and error states', () => {
  it('every page that fetches data handles a failed request', () => {
    const files = pageFiles();
    let fetching = 0;
    const silent: string[] = [];
    for (const rel of files) {
      const text = readFileSync(resolve(ROOT, rel), 'utf8');
      if (!FETCHES.test(text)) continue;
      fetching += 1;
      if (!HANDLES_ERROR.test(text) && !(rel in DELIBERATE_FALLBACK)) silent.push(rel);
    }
    expect(fetching).toBeGreaterThan(150);
    expect(silent, `pages that show nothing when their request fails:\n${silent.join('\n')}`).toEqual([]);
  });

  it('every listed fallback still exists', () => {
    const files = new Set(pageFiles());
    for (const rel of Object.keys(DELIBERATE_FALLBACK)) expect(files.has(rel), rel).toBe(true);
  });
});
