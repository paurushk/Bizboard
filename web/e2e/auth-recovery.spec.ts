import { expect, test } from '@playwright/test';

/**
 * Phase 7.4 — forgot/reset password UI journey.
 * Mock e2e (requestPasswordReset short-circuits in shouldUseMocks).
 * Proves the public recovery screens render, submit, and never crash.
 */
test.describe('auth recovery', () => {
  test('forgot-password submits and shows the dispatched copy', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));

    await page.goto('/forgot-password', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /reset password/i })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByLabel(/email or mobile/i).fill('owner@bizboard.local');
    await page.getByRole('button', { name: /send reset link/i }).click();
    await expect(page.getByText(/if an account exists/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: /return to login/i })).toBeVisible();
    expect(errors, errors.join(' | ')).toEqual([]);
  });

  test('reset-password without a token tells the user to request a new link', async ({ page }) => {
    await page.goto('/reset-password', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /set a new password/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/missing a token/i)).toBeVisible();
    await expect(page.getByRole('link', { name: /request a new link/i }).or(page.getByRole('button', { name: /request a new link/i }))).toBeVisible();
  });
});
