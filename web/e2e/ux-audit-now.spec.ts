import { expect, test } from '@playwright/test';

test('Try again leaves the offline shell instead of reloading it', async ({ page }) => {
  await page.goto('/offline.html');
  await expect(page.locator('#try-again')).toHaveAttribute('href', '/');
  await expect(page.locator('#hard-reload')).toHaveAttribute('href', '/');
  const html = await page.content();
  expect(html).not.toContain('/?reload=1');
  expect(html).toContain('unregister');
});
