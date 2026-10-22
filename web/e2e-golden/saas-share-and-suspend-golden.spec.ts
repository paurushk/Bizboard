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
  await expect(page.getByText(/No tickets have been shared with you yet/)).toBeVisible();

  await page.goto('/settings/billing');
  // Suspending lives in the collapsed Danger zone and asks for a reason, the company name and the password.
  await page.getByRole('button', { name: 'Danger zone' }).click();
  await page.getByRole('button', { name: 'Suspend workspace…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Suspend this workspace?' });
  const suspend = dialog.getByRole('button', { name: 'Suspend workspace', exact: true });
  await expect(suspend).toBeDisabled();
  await dialog.getByLabel('Churn reason').fill('Closed the shop');
  await dialog.getByLabel(/Type the company name to confirm/).fill(companyName);
  await dialog.getByLabel('Your password').fill('GoldenPath123!');
  await expect(suspend).toBeEnabled();
  const suspended = page.waitForResponse(
    (res) => res.url().includes('/billing/subscription/') && res.request().method() === 'POST',
  );
  await suspend.click();
  const response = await suspended;
  const raw = await response.text();
  expect(response.ok(), raw).toBeTruthy();
  const body = JSON.parse(raw) as { data?: { winBackName?: string } };
  expect(body.data?.winBackName).toBe(`Win-back ${companyName}`);
  await expect(page.getByText(/status: suspended/i)).toBeVisible({ timeout: 20_000 });
});
