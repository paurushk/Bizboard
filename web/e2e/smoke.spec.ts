import { expect, test, type Page } from '@playwright/test';

const mockOwner = {
  id: 1,
  email: 'owner@bizboard.local',
  fullName: 'Demo Owner',
  role: 'OWNER',
  companyId: 1,
  canManageInventory: true,
  canImport: true,
};

/** Seed tokens on every document load so full navigations stay authenticated. */
async function seedMockSession(page: Page) {
  await page.addInitScript((user) => {
    localStorage.setItem('bizboard.access', 'mock-access');
    localStorage.setItem('bizboard.refresh', 'mock-refresh');
    localStorage.setItem('bizboard.user', JSON.stringify(user));
  }, mockOwner);
}

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

  test('authenticated templates route resolves', async ({ page }) => {
    await seedMockSession(page);
    await page.goto('/settings/templates');
    await expect(page).toHaveURL(/\/settings\/templates/);
    await expect(page).not.toHaveURL(/\/settings\/invoice-templates/);
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('purchase bill upload is reachable for import-capable users', async ({ page }) => {
    await seedMockSession(page);
    await page.goto('/purchases/bill-upload');
    await expect(page).toHaveURL(/\/purchases\/bill-upload/);
    await expect(page.getByRole('heading', { name: /bill|upload/i })).toBeVisible({ timeout: 15_000 });
  });

  test('completed invoice edit freezes party Change', async ({ page }) => {
    await seedMockSession(page);
    await page.goto('/sales/history/1/edit');
    await expect(page.getByText(/Rahul Stores/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: /^Change$/i })).toHaveCount(0);
  });

  test('new invoice templates link points to /settings/templates', async ({ page }) => {
    await seedMockSession(page);
    await page.goto('/sales/new');
    await page.getByRole('main').getByRole('button', { name: /settings/i }).click();
    await expect(page.locator('a[href="/settings/templates"]').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('a[href="/settings/invoice-templates"]')).toHaveCount(0);
  });
});
