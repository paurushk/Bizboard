import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Accounting domain — before this pass only /accounting/journals had any
 * coverage (access-control only, via personas/role-boundaries.spec.ts).
 * Every /accounting/* route is gated by allowAccounting() in App.tsx,
 * requiring company.accountingEnabled — the mocked company fixture doesn't
 * set it, so (correctly — this mirrors a real never-turned-on-books tenant)
 * every route in this domain renders LimitedAccessLanding with a working
 * "Open accounting settings" link, not the page itself or an error state.
 * Asserts that real, current behavior rather than assuming ErrorState (an
 * earlier draft of this spec did, and was wrong — books-off is gated
 * before the page component is even reached).
 */
const ROUTES = [
  '/accounting/accounts',
  '/accounting/bank-reconciliation',
  '/accounting/cost-centers',
  '/accounting/fixed-assets',
  '/accounting/periods',
];

test.describe('accounting domain (books off — the mocked-company default)', () => {
  for (const path of ROUTES) {
    test(`${path} offers to enable accounting rather than erroring`, async ({ page }) => {
      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page).not.toHaveURL(/\/login/);
      const enableLink = page.getByRole('link', { name: 'Open accounting settings' });
      await expect(enableLink).toBeVisible({ timeout: 15_000 });
      await expect(enableLink).toHaveAttribute('href', '/settings/accounting');
    });
  }
});
