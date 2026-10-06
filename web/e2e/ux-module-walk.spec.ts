import { test } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { loginViaUi } from './helpers/auth';

/**
 * UX programme: read-only walk of the flag-gated module screens on a real backend.
 * For each route: headings, buttons, table headers, empty/error text, then open the
 * first create action (never submit) and list its fields. Screenshots to docs/ux/walk/.
 * Opt-in: UX_CRAWL=1 UX_EMAIL=... UX_PASSWORD=... E2E_BASE_URL=http://127.0.0.1
 */
const LEDGER = resolve(process.cwd(), '../docs/ux/L1_surface_ledger.csv');
const OUT = resolve(process.cwd(), '../docs/ux/walk');

function gatedRoutes(): { path: string; phase: string }[] {
  const rows = readFileSync(LEDGER, 'utf-8').trim().split(/\r?\n/);
  const head = rows[0].split(',');
  const iPath = head.indexOf('path');
  const iPhase = head.indexOf('phase');
  const out: { path: string; phase: string }[] = [];
  for (const line of rows.slice(1)) {
    const cols = line.match(/("([^"]|"")*"|[^,]*)(,|$)/g)?.map((c) => c.replace(/,$/, '').replace(/^"|"$/g, '')) ?? [];
    if (cols[1] === 'page' && cols[iPhase] && cols[iPath] && !cols[iPath].includes(':')) {
      out.push({ path: cols[iPath], phase: cols[iPhase] });
    }
  }
  return out;
}

test.skip(!process.env.UX_CRAWL || !process.env.UX_EMAIL, 'opt-in: set UX_CRAWL=1 and UX_EMAIL/UX_PASSWORD');
test.setTimeout(25 * 60_000);

test('walk gated modules', async ({ page }, testInfo) => {
  await loginViaUi(page, { email: process.env.UX_EMAIL!, password: process.env.UX_PASSWORD! });
  mkdirSync(OUT, { recursive: true });
  const results: Record<string, unknown>[] = [];
  const tag = testInfo.project.name + (process.env.UX_WALK_TAG ?? '');
  const only = (process.env.UX_ONLY ?? '').split(',').filter(Boolean);
  for (const { path, phase } of gatedRoutes().filter((r) => only.length === 0 || only.includes(r.path) || only.includes(r.phase))) {
    const rec: Record<string, unknown> = { path, phase, project: tag };
    try {
      await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 25_000 });
      await page.waitForTimeout(1800);
      const snap = await page.evaluate(() => {
        const vis = (el: Element) => {
          const r = (el as HTMLElement).getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        };
        const txt = (sel: string, n = 30) =>
          [...document.querySelectorAll(sel)].filter(vis).map((e) => (e as HTMLElement).innerText.trim()).filter(Boolean).slice(0, n);
        const main = document.querySelector('main') as HTMLElement | null;
        return {
          title: document.title,
          landing: /this module is not on yet/i.test(document.body.innerText),
          headings: txt('main h1, main h2, main h3, main h4', 12),
          buttons: txt('main button, main a[role=button], main a.MuiButton-root', 30),
          tableHeaders: txt('main th', 24),
          tabs: txt('main [role=tab]', 12),
          fieldsVisible: [...document.querySelectorAll('main input:not([type=hidden]), main textarea, main [role=combobox]')].filter(vis).length,
          alerts: txt('main [role=alert], main .MuiAlert-message', 6),
          textHead: (main?.innerText ?? '').replace(/\s+/g, ' ').slice(0, 700),
        };
      });
      Object.assign(rec, snap);
      const cta = page
        .locator('main button, main a.MuiButton-root')
        .filter({ hasText: /^(\+\s*)?(add|new|create|record|log|issue|start|import)\b/i })
        .first();
      if ((await cta.count()) > 0 && (await cta.isVisible().catch(() => false))) {
        const label = (await cta.innerText()).trim();
        await cta.click({ timeout: 4000 }).catch(() => undefined);
        await page.waitForTimeout(900);
        rec.cta = label;
        rec.dialog = await page.evaluate(() => {
          const d = document.querySelector('[role=dialog], .MuiDrawer-paper') as HTMLElement | null;
          const scope: ParentNode = d ?? document.querySelector('main') ?? document;
          const labels = [...scope.querySelectorAll('label')].map((l) => (l as HTMLElement).innerText.trim()).filter(Boolean).slice(0, 40);
          const req = [...scope.querySelectorAll('[required], [aria-required=true]')].length;
          const btns = [...scope.querySelectorAll('button')].map((b) => (b as HTMLElement).innerText.trim()).filter(Boolean).slice(0, 12);
          return { opened: Boolean(d), labels, required: req, buttons: btns, inputs: scope.querySelectorAll('input:not([type=hidden]), textarea, [role=combobox]').length };
        });
        await page.screenshot({ path: resolve(OUT, `${tag}${path.replace(/\//g, '_')}_form.png`) });
        await page.keyboard.press('Escape').catch(() => undefined);
        await page.waitForTimeout(300);
      } else {
        await page.screenshot({ path: resolve(OUT, `${tag}${path.replace(/\//g, '_')}.png`) });
      }
    } catch (e) {
      rec.error = String(e).slice(0, 200);
    }
    results.push(rec);
  }
  writeFileSync(resolve(OUT, `walk-${tag}.json`), JSON.stringify(results, null, 1));
});
