import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Manufacturing, Payroll, CRM — 6 routes, zero coverage before this pass,
 * lowest priority of the e2e-coverage batches since all three modules are
 * `OFF (dark)` per docs/FREEZE_SCOPE.md's flag table (not in the ARCH-03
 * pilot's frozen scope). ENABLE_MANUFACTURING/ENABLE_PAYROLL/ENABLE_CRM all
 * default false (src/config/featureFlags.ts), so every route here lands on
 * LimitedAccessLanding's generic "This module is not on yet" state, not the
 * page itself — the correct behavior for a dark module, asserted directly.
 */
const ROUTES = [
  '/manufacturing/boms',
  '/manufacturing/work-orders',
  '/payroll/employees',
  '/payroll/pay-runs',
  '/crm/leads',
  '/crm/opportunities',
];

test.describe('dark modules (Manufacturing / Payroll / CRM — all OFF by default)', () => {
  for (const path of ROUTES) {
    test(`${path} shows the module-not-on landing, not the page or a crash`, async ({ page }) => {
      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page).not.toHaveURL(/\/login/);
      await expect(page.getByText('This module is not on yet')).toBeVisible({ timeout: 15_000 });
    });
  }
});
