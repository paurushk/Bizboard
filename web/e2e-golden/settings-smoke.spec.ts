import { expect, test } from '@playwright/test';
import { registerTenant, unique } from './helpers/documents';

/**
 * Settings programme smoke: the overview, the grouped menu, and one real save with its "next step"
 * banner and history, against the live backend.
 */
test('Settings: hub, groups, a saved change with next step and recent changes', async ({ page }) => {
  const id = unique();
  await registerTenant(page, {
    companyName: `E2E Settings ${id}`,
    email: `e2e-settings-${id}@example.test`,
    password: 'GoldenPath123!',
  });

  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Business profile' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Settings health' })).toBeVisible();

  await page.getByRole('link', { name: /Company/ }).first().click();
  await expect(page).toHaveURL(/\/settings\/company$/);
  const city = page.getByLabel('City');
  await city.fill(`Pune ${id}`);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Saved. Next in set-up:')).toBeVisible();

  await page.getByRole('button', { name: 'Recent changes' }).click();
  await expect(page.getByText(new RegExp(`Pune ${id}`))).toBeVisible();
});
