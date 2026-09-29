import { expect, test } from '@playwright/test';
import { registerTenant, unique } from './helpers/documents';
import { ensureE2eTrial, grantRolloutFlag, markE2eVendor } from './helpers/grantFlag';

test('shared tickets stay empty, and suspend records a win-back after a reason', async ({ page }) => {
  test.setTimeout(120_000);
  const id = unique();
  const companyName = `E2E SaaS ${id}`;
  const email = `e2e-saas-${id}@example.test`;
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  markE2eVendor(email);
  ensureE2eTrial(email);

  grantRolloutFlag(email, 'ENABLE_SUPPORT_TICKETS');
  await page.goto('/support/shared');
  await expect(page.getByText('No shared tickets.')).toBeVisible();

  await page.goto('/settings/billing');
  const suspend = page.getByRole('button', { name: 'Suspend' });
  await expect(suspend).toBeDisabled();
  await page.getByLabel('Churn reason').fill('Closed the shop');
  await expect(suspend).toBeEnabled();
  await suspend.click();
  await expect(page.getByText(/status: suspended/i)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(`Win-back ${companyName}`)).toBeVisible();
});
