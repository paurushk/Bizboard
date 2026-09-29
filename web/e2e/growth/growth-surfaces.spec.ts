import { expect, test } from '@playwright/test';
import { loginAsOwner, loginAsViewer } from '../helpers/auth';

/**
 * E2E test suite for newly added Growth OS and BizBoard OS Vision surfaces:
 * - Contracts & AMC (/contracts)
 * - Support Tickets (/support/tickets)
 * - Complaints & RMA (/complaints)
 * - CRM Campaigns (/crm/campaigns)
 * - CRM Opportunity Pipeline (/crm/pipeline)
 * - CRM Referrals (/crm/referrals)
 * - CRM Onboarding Checklist (/crm/onboarding)
 * - Demand Forecasting (/inventory/demand-forecast)
 */

const GROWTH_ROUTES = [
  '/contracts',
  '/support/tickets',
  '/complaints',
  '/crm/campaigns',
  '/crm/pipeline',
  '/crm/referrals',
  '/crm/onboarding',
  '/inventory/demand-forecast',
];

test.describe('Growth OS & Vision surfaces — Authenticated Owner access', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  for (const path of GROWTH_ROUTES) {
    test(`${path} mounts cleanly without page errors or crash boundary`, async ({ page }) => {
      const pageErrors: string[] = [];
      page.on('pageerror', (err) => pageErrors.push(err.message));

      await page.goto(path, { waitUntil: 'domcontentloaded' });

      // Verify the page does not redirect unexpectedly to login
      await expect(page, `${path} should not bounce authenticated owner to /login`).not.toHaveURL(/\/login/);

      // Verify no React error boundary was triggered
      await expect(
        page.getByText(/something went wrong|unexpected error|error boundary/i),
        `${path} triggered error boundary`,
      ).toHaveCount(0);

      expect(pageErrors, `${path} threw unhandled page errors: ${pageErrors.join('; ')}`).toEqual([]);
    });
  }
});

test.describe('Growth OS & Vision surfaces — Unauthenticated redirect to login', () => {
  for (const path of GROWTH_ROUTES) {
    test(`logged-out visit to ${path} bounces to /login with next param`, async ({ page }) => {
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page).toHaveURL(new RegExp(`/login\\?next=.*${encodeURIComponent(path).replace(/\//g, '%2F')}`));
    });
  }
});

test.describe('Growth OS & Vision surfaces — Read-only viewer boundaries', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsViewer(page);
  });

  test('viewer has no mutate or create buttons on growth pages', async ({ page }) => {
    for (const path of ['/contracts', '/support/tickets', '/complaints', '/crm/campaigns']) {
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      // Viewer should either see read-only view or restricted landing, never actionable create buttons
      await expect(page.getByRole('button', { name: /create|add|new|issue/i })).toHaveCount(0);
    }
  });
});
