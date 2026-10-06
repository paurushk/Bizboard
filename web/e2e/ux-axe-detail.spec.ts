import AxeBuilder from '@axe-core/playwright';
import { test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { loginAsOwner } from './helpers/auth';

/** UX programme: selector-level detail for serious/critical axe findings. Opt-in via UX_CRAWL=1. */
test.skip(!process.env.UX_CRAWL, 'opt-in: set UX_CRAWL=1');

const PATHS = ['/sales/new', '/purchases/new', '/pos', '/payments/statements', '/settings/bank-accounts'];

test('axe detail', async ({ page }) => {
  await loginAsOwner(page);
  const out: Record<string, unknown[]> = {};
  for (const p of PATHS) {
    await page.goto(p, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze();
    out[p] = r.violations
      .filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => ({
        id: v.id,
        help: v.help,
        nodes: v.nodes.slice(0, 4).map((n) => ({ target: n.target.join(' '), html: n.html.slice(0, 160) })),
      }));
  }
  mkdirSync(resolve(process.cwd(), '../docs/ux/crawl'), { recursive: true });
  writeFileSync(resolve(process.cwd(), '../docs/ux/crawl/axe_detail.json'), JSON.stringify(out, null, 1));
});
