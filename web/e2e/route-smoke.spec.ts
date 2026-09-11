import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

/**
 * QOS-0010 — a render + no-page-error + not-bounced-to-login smoke for the
 * highest-traffic screens. Catches the "route crashes / shows the error
 * boundary" class of regression across the app, not just the handful of pages
 * that have a bespoke spec. The long tail of settings screens stays an
 * accepted LIM.
 */
const ROUTES = [
  '/',
  '/pos',
  '/sales/new',
  '/sales/history',
  '/sales/customers',
  '/sales/quotations',
  '/sales/orders',
  '/sales/delivery-challans',
  '/sales/credit-notes',
  '/sales/recurring',
  '/purchases/history',
  '/purchases/bill-upload',
  '/inventory/products',
  '/inventory/stock',
  '/accounting/journals',
  '/accounting/chart-of-accounts',
  '/reports/sales',
  '/insights',
  '/offline-outbox',
  '/settings/company',
];

test.describe('route smoke (top 20)', () => {
  for (const path of ROUTES) {
    test(`${path} renders without a page error`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));

      await page.goto(path, { waitUntil: 'domcontentloaded' });
      // give the SPA a beat to mount / redirect
      await expect
        .poll(async () => (await page.locator('#root').innerHTML()).length, { timeout: 20_000 })
        .toBeGreaterThan(0);

      await expect(page, `${path} bounced to /login`).not.toHaveURL(/\/login/);
      await expect(
        page.getByText(/something went wrong|unexpected error|error boundary/i),
        `${path} rendered the error boundary`,
      ).toHaveCount(0);
      expect(errors, `${path} threw: ${errors.join(' | ')}`).toEqual([]);
    });
  }
});

test.beforeEach(async ({ page }) => {
  await loginAsOwner(page);
});
