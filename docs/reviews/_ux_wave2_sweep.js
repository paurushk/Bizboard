/**
 * UX Wave 2 — lightweight route sweep (Chrome channel).
 * Login + visit routes + screenshots + error sniff. No API token files.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost';
const OUT = path.resolve(__dirname, 'screenshots_wave2');
const META = path.resolve(__dirname, '_wave2_sweep_meta.json');
fs.mkdirSync(OUT, { recursive: true });

const ROUTES = [
  '/',
  '/settings/company',
  '/settings/gst',
  '/settings/users',
  '/settings/bank-accounts',
  '/settings/payment-gateway',
  '/purchases/suppliers',
  '/inventory/products',
  '/inventory/stock',
  '/inventory/adjustments',
  '/inventory/low-stock',
  '/inventory/transfers',
  '/inventory/serials',
  '/inventory/warehouses',
  '/purchases/new',
  '/purchases/orders',
  '/purchases/history',
  '/purchases/debit-notes',
  '/purchases/payments',
  '/sales/customers',
  '/sales/new',
  '/sales/quotations',
  '/sales/orders',
  '/sales/delivery-challans',
  '/sales/history',
  '/sales/credit-notes',
  '/sales/receipts',
  '/payments/links',
  '/payments/statements',
  '/payments/reconciliation',
  '/reports/sales',
  '/reports/purchases',
  '/reports/inventory',
  '/reports/customer-ledger',
  '/reports/supplier-ledger',
  '/reports/cash-book',
  '/reports/gstr1',
  '/reports/gstr3b',
  '/reports/profit-and-loss',
  '/reports/balance-sheet',
  '/reports/trial-balance',
  '/accounting/accounts',
  '/accounting/journals',
];

async function main() {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const results = [];

  async function sweep(viewport, tag) {
    const context = await browser.newContext({
      viewport,
      ignoreHTTPSErrors: true,
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    const netErrors = [];
    page.on('response', (res) => {
      if (res.status() >= 400 && /\/api\//.test(res.url())) {
        netErrors.push(`${res.status()} ${res.request().method()} ${res.url()}`);
      }
    });
    page.on('pageerror', (e) => netErrors.push(`pageerror: ${e.message}`));

    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.getByLabel(/email/i).fill('demo@bizboard.local');
    await page.getByLabel(/password/i).fill('DemoPass123!');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForTimeout(2000);

    for (const route of ROUTES) {
      const entry = { tag, route, ok: true, title: '', issues: [], api: [] };
      const before = netErrors.length;
      try {
        await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.waitForTimeout(1400);
        const text = await page.locator('body').innerText();
        entry.title = (await page.locator('h4, h1').first().innerText().catch(() => '')).slice(0, 80);
        const file = `UXW2-SWEEP_${tag}_${route.replace(/\\//g, '_').replace(/^_/, '') || 'home'}.png`;
        await page.screenshot({ path: path.join(OUT, file) });
        entry.shot = file;
        if (/you.?re offline|something went wrong|traceback|unhandled|failed to fetch/i.test(text)) {
          entry.ok = false;
          entry.issues.push('error-like page copy');
        }
        if (/403|forbidden|not authorized|access denied/i.test(text)) {
          entry.issues.push('auth/forbidden copy visible');
        }
        // table overflow heuristic (mobile)
        if (viewport.width <= 400) {
          const overflow = await page.evaluate(() => {
            const el = document.querySelector('table, .MuiTable-root');
            if (!el) return null;
            return { sw: el.scrollWidth, cw: el.clientWidth };
          });
          if (overflow && overflow.sw > overflow.cw + 16) {
            entry.issues.push(`table overflow ${overflow.sw}>${overflow.cw}`);
          }
        }
        entry.snippet = text.replace(/\\s+/g, ' ').slice(0, 220);
      } catch (e) {
        entry.ok = false;
        entry.issues.push(String(e.message || e));
      }
      entry.api = netErrors.slice(before);
      results.push(entry);
      console.log(`${tag} ${route} ok=${entry.ok} issues=${entry.issues.join('|') || '-'}`);
    }
    await context.close();
  }

  await sweep({ width: 1280, height: 800 }, 'D');
  await sweep({ width: 375, height: 812 }, 'M');

  fs.writeFileSync(META, JSON.stringify(results, null, 2));
  console.log('DONE', results.length, 'META', META);
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
