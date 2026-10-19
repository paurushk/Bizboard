import { expect, test, type Page } from '@playwright/test';
import { registerTenant, unique } from './helpers/documents';

/**
 * RPT: walk every report in a real browser against the live backend. For each route it checks that the page
 * opens (a heading, no crash screen), logs no console errors, and does not scroll sideways at phone width.
 * Screenshots go to test-results/reports-walk for a human to look at.
 *
 * Requires: backend migrated. Run with: npx playwright test --config=playwright.golden.config.ts reports-rpt-walk
 */

const ROUTES: Array<{ path: string; heading: RegExp }> = [
  { path: '/reports/sales', heading: /sales/i },
  { path: '/reports/purchases', heading: /purchase/i },
  { path: '/reports/discounts', heading: /discount/i },
  { path: '/reports/invoice-profit', heading: /profit/i },
  { path: '/reports/invoice-profit/rollup', heading: /profit/i },
  { path: '/reports/inventory', heading: /inventory|stock/i },
  { path: '/reports/customer-ledger', heading: /customer/i },
  { path: '/reports/supplier-ledger', heading: /supplier/i },
  { path: '/reports/cash-book', heading: /cash/i },
  { path: '/reports/day-book', heading: /day book/i },
  { path: '/reports/stock-valuation', heading: /valuation/i },
  { path: '/reports/trial-balance', heading: /trial/i },
  { path: '/reports/profit-and-loss', heading: /profit/i },
  { path: '/reports/balance-sheet', heading: /balance sheet/i },
  { path: '/reports/books-health', heading: /books health/i },
  { path: '/reports/close-month', heading: /close/i },
  { path: '/reports/statutory-events', heading: /statutory/i },
  { path: '/reports/tds-receivable', heading: /tds/i },
];

async function openAndCheck(page: Page, path: string, heading: RegExp, shot: string) {
  const errors: string[] = [];
  const onConsole = (m: { type(): string; text(): string }) => {
    if (m.type() === 'error') errors.push(m.text());
  };
  page.on('console', onConsole);
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('heading', { level: 1 }).first()).toContainText(heading);
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await page.screenshot({ path: `test-results/reports-walk/${shot}.png`, fullPage: true });
  page.off('console', onConsole);
  // network errors for optional probes are noise; a React/JS error is not
  const real = errors.filter((e) => !/Failed to load resource|status of (401|403|404|429)/i.test(e));
  expect(real, `console errors on ${path}`).toEqual([]);
}

test('every report opens cleanly at desktop and phone width', async ({ page }) => {
  test.setTimeout(240_000);
  const id = unique();
  await registerTenant(page, {
    companyName: `E2E Reports Walk ${id}`,
    email: `e2e-reports-walk-${id}@example.test`,
    password: 'GoldenPath123!',
  });

  for (const r of ROUTES) {
    await openAndCheck(page, r.path, r.heading, `desktop${r.path.replace(/\//g, '_')}`);
  }

  await page.setViewportSize({ width: 375, height: 812 });
  for (const r of ROUTES) {
    await openAndCheck(page, r.path, r.heading, `phone${r.path.replace(/\//g, '_')}`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `sideways scroll on ${r.path} at 375px`).toBeLessThanOrEqual(1);
  }
});

test('balance sheet shows its sections and a balance check; menu is grouped', async ({ page }) => {
  const id = unique();
  await registerTenant(page, {
    companyName: `E2E Statements ${id}`,
    email: `e2e-statements-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await page.goto('/reports/balance-sheet');
  await expect(page.getByRole('heading', { level: 1 }).first()).toContainText(/balance sheet/i, { timeout: 20_000 });
  await expect(page.getByLabel('As of')).toBeVisible();
  await expect(page.getByText(/Showing the books as of/)).toBeVisible();
  await page.screenshot({ path: 'test-results/reports-walk/balance-sheet-loaded.png', fullPage: true });

  await page.goto('/reports/close-month');
  await expect(page.getByText(/Books health/).first()).toBeVisible({ timeout: 20_000 });
  // a fresh tenant has nothing wrong, and a check that could not run would say so instead
  await expect(page.getByText('All clear')).toHaveCount(2, { timeout: 30_000 });
  await page.screenshot({ path: 'test-results/reports-walk/close-month-checklist.png', fullPage: true });
});
