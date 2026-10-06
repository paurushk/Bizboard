import AxeBuilder from '@axe-core/playwright';
import { test } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { loginAsOwner, loginViaUi } from './helpers/auth';

/**
 * UX programme, Phase 1: one measurement pass over every routed page in
 * docs/ux/L1_surface_ledger.csv (parameter-free, non-redirect routes only).
 * Runs in mock mode (`--mode e2e`), so it measures layout, semantics and
 * interaction cost, not real data volume. Writes docs/ux/crawl/<project>.json.
 * Opt-in: UX_CRAWL=1 npx playwright test e2e/ux-surface-crawl.spec.ts (real backend: UX_EMAIL, UX_PASSWORD, UX_TAG=-real, E2E_BASE_URL)
 */
const LEDGER = resolve(process.cwd(), '../docs/ux/L1_surface_ledger.csv');
const OUT_DIR = resolve(process.cwd(), '../docs/ux/crawl');

function routes(): string[] {
  const rows = readFileSync(LEDGER, 'utf-8').trim().split(/\r?\n/).slice(1);
  const seen = new Set<string>();
  for (const line of rows) {
    const cols = line.match(/("([^"]|"")*"|[^,]*)(,|$)/g)?.map((c) => c.replace(/,$/, '').replace(/^"|"$/g, '')) ?? [];
    const [, kind, path] = cols;
    if (kind !== 'page' || !path || path.includes(':') || path.includes('*')) continue;
    seen.add(path);
  }
  const only = (process.env.UX_ONLY_PATHS ?? '').split(',').filter(Boolean);
  return [...seen].filter((p) => only.length === 0 || only.includes(p));
}

test.skip(!process.env.UX_CRAWL, 'opt-in: set UX_CRAWL=1');
test.setTimeout(30 * 60_000);

test('crawl surfaces', async ({ page }, testInfo) => {
  // UX_EMAIL/UX_PASSWORD/UX_TAG: run against a real backend (seeded demo user) instead of mock mode.
  if (process.env.UX_EMAIL && process.env.UX_PASSWORD) {
    await loginViaUi(page, { email: process.env.UX_EMAIL, password: process.env.UX_PASSWORD });
  } else {
    await loginAsOwner(page);
  }
  const results: Record<string, unknown>[] = [];
  const vw = page.viewportSize()?.width ?? 0;

  for (const path of routes()) {
    const errors: string[] = [];
    const onErr = (e: Error) => errors.push(e.message);
    const onConsole = (m: { type(): string; text(): string }) => {
      if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 160)}`);
    };
    page.on('pageerror', onErr);
    page.on('console', onConsole);
    const t0 = Date.now();
    let ok = true;
    let metrics: Record<string, unknown> = {};
    try {
      await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 25_000 });
      await page.waitForFunction(() => (document.querySelector('#root')?.innerHTML.length ?? 0) > 200, null, {
        timeout: 15_000,
      });
      await page.waitForTimeout(900);
      const ms = Date.now() - t0;
      const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze();
      metrics = await page.evaluate(() => {
        const vis = (el: Element) => {
          const r = (el as HTMLElement).getBoundingClientRect();
          const s = getComputedStyle(el);
          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const q = (sel: string) => [...document.querySelectorAll(sel)].filter(vis);
        const inputs = q('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea, select, [role=combobox]');
        const buttons = q('button, [role=button], a[href]');
        const small = buttons.filter((b) => {
          const r = (b as HTMLElement).getBoundingClientRect();
          return r.width < 44 || r.height < 44;
        });
        const iconOnlyNoName = q('button, [role=button]').filter((b) => {
          const name = (b.getAttribute('aria-label') || b.getAttribute('aria-labelledby') || (b as HTMLElement).innerText || b.getAttribute('title') || '').trim();
          return !name;
        });
        const text = document.body.innerText || '';
        return {
          h1: document.querySelectorAll('h1').length,
          inputs: inputs.length,
          buttons: buttons.length,
          smallTargets: small.length,
          iconButtonsNoName: iconOnlyNoName.length,
          tables: document.querySelectorAll('table, [role=grid]').length,
          hOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          textLen: text.length,
          emptyStateHint: /no (data|records|results|items)|nothing (here|yet)|get started|add your first/i.test(text),
          errorBoundary: /something went wrong|unexpected error/i.test(text),
          bouncedToLogin: location.pathname.startsWith('/login'),
          finalPath: location.pathname,
          notOnLanding: !/this module is not on yet|welcome to bizboard/i.test(text),
          hasLoadingSpinner: !!document.querySelector('[role=progressbar], .MuiSkeleton-root'),
        };
      });
      results.push({
        path,
        ms,
        vw,
        axeSerious: axe.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
        axeModerate: axe.violations.filter((v) => v.impact === 'moderate' || v.impact === 'minor').map((v) => ({ id: v.id, nodes: v.nodes.length })),
        errors: errors.slice(0, 5),
        ...metrics,
      });
    } catch (e) {
      ok = false;
      results.push({ path, vw, crawlError: String(e).slice(0, 200), errors: errors.slice(0, 5) });
    }
    page.off('pageerror', onErr);
    page.off('console', onConsole);
    void ok;
  }
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(resolve(OUT_DIR, `${testInfo.project.name}${process.env.UX_TAG ?? ''}.json`), JSON.stringify(results, null, 1));
});
