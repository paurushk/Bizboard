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

  test('VIEWER sees limited home landing (BB-000439 / BB-000528)', async ({ page }) => {
    await loginAsViewer(page);
    await page.goto('/');
    await expect(page.getByText(/welcome to bizboard|limited access/i).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/access denied|forbidden|403/i)).toHaveCount(0);
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
