import { expect, test } from '@playwright/test';

test('online deep link is the app shell, not the offline page', async ({ page }) => {
  await page.goto('/sales/new', { waitUntil: 'networkidle' });
  await expect(page.locator('#offline-title')).toHaveCount(0);
  await expect(page).toHaveTitle(/Bizboard/i);
});
