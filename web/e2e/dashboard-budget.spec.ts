import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

/**
 * G-15 / G-16 — dashboard first content must appear under a friction budget.
 * Mock e2e is the regression guard; live H-02/H-03 stay pilot (L7).
 */
test('dashboard heading is visible within 4s of navigation', async ({ page }) => {
  await loginAsOwner(page);
  const started = Date.now();
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible({ timeout: 4_000 });
  expect(Date.now() - started, 'dashboard first heading exceeded 4s budget').toBeLessThan(4_000);
});
