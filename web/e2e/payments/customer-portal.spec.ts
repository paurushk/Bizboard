import { expect, test } from '@playwright/test';

/**
 * COMP-003 public portal. These routes sit outside the login shell.
 * Mock mode has no portal API, so an unknown token must show the
 * expired-link state instead of bouncing to /login or the error boundary.
 */
test.describe('customer portal, logged out', () => {
  test('request form renders and does not redirect to login', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/portal', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'Get a link to your invoices' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send link' })).toBeDisabled();
    await expect(page).not.toHaveURL(/\/login/);
    expect(errors).toEqual([]);
  });

  test('an unknown token shows the expired link, not the error boundary', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/portal/not-a-real-token', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /unavailable or has expired/i })).toBeVisible({ timeout: 20_000 });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByText(/something went wrong|unexpected error|error boundary/i)).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});
