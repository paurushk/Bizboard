import { expect, test } from '@playwright/test';
import { createCustomer, registerTenant, unique } from './helpers/documents';
import { grantRolloutFlag } from './helpers/grantFlag';

test('a job card is created in the browser after the workshop flag is granted', async ({ page }) => {
  test.setTimeout(150_000);
  const id = unique();
  const email = `e2e-job-${id}@example.test`;
  const customerName = `Job Customer ${id}`;
  await registerTenant(page, { companyName: `E2E Job ${id}`, email, password: 'GoldenPath123!' });
  await page.goto('/workshop/jobs');
  await expect(page.getByText('This module is not on yet')).toBeVisible();
  grantRolloutFlag(email, 'ENABLE_WORKSHOP');
  await createCustomer(page, { name: customerName });
  await page.goto('/workshop/jobs');
  const create = page.getByRole('button', { name: 'Create' });
  await expect(create).toBeDisabled();
  await page.getByRole('combobox', { name: 'Customer', exact: true }).fill(customerName);
  await page.getByRole('option', { name: new RegExp(customerName) }).click();
  await page.getByLabel('Complaint').fill('Brake noise');
  await expect(create).toBeEnabled();
  await create.click();
  await expect(page.getByText(/JOB-.*DRAFT/)).toBeVisible({ timeout: 20_000 });
});
