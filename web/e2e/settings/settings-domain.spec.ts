import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Settings long tail — 13 screens with zero e2e coverage before this pass
 * (company, templates, items, users, help already had something). Mirrors
 * the reports-domain.spec.ts strategy: assert one of the known-good states
 * (own heading, ErrorState Retry, or the RoleRoute LimitedAccessLanding for
 * a flag-gated screen like Tally) rather than guessing a single pattern for
 * 13 differently-built pages. Real crashes / blank pages still fail this.
 */
const ROUTES = [
  '/settings/series',
  '/settings/units',
  '/settings/bank-accounts',
  '/settings/payment-gateway',
  '/settings/billing',
  '/settings/price-lists',
  '/settings/backup',
  '/settings/ai',
  '/settings/accounting',
  '/settings/gst',
  '/settings/statutory-licences',
  '/settings/import',
  '/settings/tally',
];

test.describe('settings domain (long tail)', () => {
  for (const path of ROUTES) {
    test(`${path} renders its own content or degrades gracefully (no crash, no blank page)`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));

      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page).not.toHaveURL(/\/login/);

      const heading = page.getByRole('heading').first();
      const retry = page.getByRole('button', { name: 'Retry' });
      const limitedAccess = page.getByText(/module|workspace/i).first();
      await expect(heading.or(retry).or(limitedAccess).first()).toBeVisible({ timeout: 15_000 });

      await expect(
        page.getByText(/something went wrong|unexpected error|error boundary/i),
      ).toHaveCount(0);
      expect(errors, `${path} threw: ${errors.join(' | ')}`).toEqual([]);
    });
  }

  test('statutory licences page (D15/QOS-0027) reaches its own list or error state', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/settings/statutory-licences', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(
      page.getByRole('heading', { name: 'Statutory licences' }).or(page.getByRole('button', { name: 'Retry' })).first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});
