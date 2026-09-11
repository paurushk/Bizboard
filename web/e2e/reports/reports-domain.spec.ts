import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Reports domain — 20 routes, almost entirely uncovered before this pass
 * (only /reports/sales via route-smoke, /reports/profit-and-loss via
 * a11y.spec.ts + role-boundaries.spec.ts). App.tsx gates this domain into
 * 4 role/flag groups (canViewFinancialReports, allowTdsReports,
 * allowAccounting, allowGstrReports); the mocked owner user/company clears
 * the role checks but not accountingEnabled, and most report pages' list
 * endpoints aren't withMocks()-wired (same finding as Payments/Accounting).
 * So a route here lands on exactly one of three known-good states: its own
 * heading (endpoint happens to be mocked, or renders unconditionally), an
 * ErrorState Retry affordance (endpoint unmocked), or the accounting-gate
 * landing (books off). This asserts "one of those three", not a blank page
 * or crash — accurate across the mix rather than guessing per-page.
 */
const ACCOUNTING_GATED = [
  '/reports/trial-balance',
  '/reports/profit-and-loss',
  '/reports/balance-sheet',
  '/reports/books-health',
];

const OTHER_REPORT_ROUTES = [
  '/attention',
  '/reports/purchases',
  '/reports/inventory',
  '/reports/customer-ledger',
  '/reports/supplier-ledger',
  '/reports/statutory-events',
  '/reports/cash-book',
  '/reports/stock-valuation',
  '/reports/tds-tcs',
  '/reports/gstr1',
  '/reports/gstr3b',
  '/reports/gstr4',
  '/reports/cmp08',
  '/reports/gstr6',
  '/reports/gstr7',
  '/reports/gstr8',
  '/reports/gstr9',
  '/reports/gstr2b',
  '/reports/missing-documents',
  '/reports/gst-health',
  '/reports/gst-rate-exposure',
];

test.describe('reports domain', () => {
  for (const path of ACCOUNTING_GATED) {
    test(`${path} offers to enable accounting rather than erroring`, async ({ page }) => {
      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page).not.toHaveURL(/\/login/);
      const enableLink = page.getByRole('link', { name: 'Open accounting settings' });
      await expect(enableLink).toBeVisible({ timeout: 15_000 });
      await expect(enableLink).toHaveAttribute('href', '/settings/accounting');
    });
  }

  for (const path of OTHER_REPORT_ROUTES) {
    test(`${path} renders its own content or degrades gracefully (no crash, no blank page)`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));

      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page).not.toHaveURL(/\/login/);

      // Exactly one of: the page's own heading rendered, or it degraded to
      // a Retry affordance — never neither (a blank #root / crash).
      const heading = page.getByRole('heading').first();
      const retry = page.getByRole('button', { name: 'Retry' });
      await expect(heading.or(retry).first()).toBeVisible({ timeout: 15_000 });

      await expect(
        page.getByText(/something went wrong|unexpected error|error boundary/i),
      ).toHaveCount(0);
      expect(errors, `${path} threw: ${errors.join(' | ')}`).toEqual([]);
    });
  }
});
