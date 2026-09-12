import { expect, test } from '@playwright/test';
import { loginAsOwner, loginAsViewer } from './helpers/auth';

test.describe('Bizboard smoke', () => {
  test('login page renders', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    const response = await page.goto('/login', { waitUntil: 'domcontentloaded' });
    expect(response?.ok() || response?.status() === 304).toBeTruthy();
    await expect.poll(async () => page.locator('#root').innerHTML(), { timeout: 30_000 }).not.toBe('');

    if (errors.length) {
      throw new Error(`Page errors while loading /login:\n${errors.join('\n')}`);
    }

    await expect(page).toHaveTitle(/Bizboard/i);
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible();
  });

  test('VIEWER can sign in and the app shell renders (BB-000439 / BB-000528)', async ({ page }) => {
    await loginAsViewer(page);
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // HomePage routes a VIEWER to its first reachable workspace (or the limited
    // landing). The stable contract: authenticated, shell mounted, no crash.
    // Role-scoped nav/CTA hiding is covered exhaustively in
    // e2e/personas/role-boundaries.spec.ts.
    await expect
      .poll(async () => (await page.locator('#root').innerHTML()).length, { timeout: 25_000 })
      .toBeGreaterThan(0);
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByText(/something went wrong|unexpected error/i)).toHaveCount(0);
  });

  test('authenticated templates route resolves', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/settings/templates');
    await expect(page).toHaveURL(/\/settings\/templates/);
    await expect(page).not.toHaveURL(/\/settings\/invoice-templates/);
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('purchase bill upload is reachable for import-capable users', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/bill-upload');
    await expect(page).toHaveURL(/\/purchases\/bill-upload/);
    await expect(page.getByRole('heading', { name: /bill|upload/i })).toBeVisible({ timeout: 15_000 });
  });

  test('completed invoice edit freezes party Change', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/history/1/edit');
    await expect(page.getByText(/Rahul Stores/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: /^Change$/i })).toHaveCount(0);
  });

  test('new invoice templates link points to /settings/templates', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/new');
    await page.getByRole('main').getByRole('button', { name: /settings/i }).click();
    await expect(page.locator('a[href="/settings/templates"]').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('a[href="/settings/invoice-templates"]')).toHaveCount(0);
  });
});
