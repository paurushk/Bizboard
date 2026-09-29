import { expect, test } from '@playwright/test';
import { createCustomer, createProduct, registerTenant, unique } from './helpers/documents';
import { grantRolloutFlag } from './helpers/grantFlag';

test('a project milestone is added in the browser after the projects flag is granted', async ({ page }) => {
  test.setTimeout(180_000);
  const id = unique();
  const email = `e2e-proj-${id}@example.test`;
  const customerName = `Project Customer ${id}`;
  const serviceName = `Site visit ${id}`;
  await registerTenant(page, { companyName: `E2E Project ${id}`, email, password: 'GoldenPath123!' });
  await page.goto('/projects');
  await expect(page.getByText('This module is not on yet')).toBeVisible();
  grantRolloutFlag(email, 'ENABLE_PROJECTS');
  await createCustomer(page, { name: customerName });
  await createProduct(page, {
    name: serviceName, sku: `SVC-${id}`, sellingPrice: '1500', purchasePrice: '0', productType: 'SERVICE',
  });
  await page.goto('/projects');
  await page.getByRole('combobox', { name: 'Customer', exact: true }).fill(customerName);
  await page.getByRole('option', { name: new RegExp(customerName) }).click();
  await page.getByLabel('Name', { exact: true }).fill(`Fit-out ${id}`);
  await page.getByRole('button', { name: 'Create' }).click();
  await expect(page.getByText(/PRJ-/)).toBeVisible({ timeout: 20_000 });
  await page.getByLabel('Milestone').fill('First visit');
  await page.getByLabel('Amount').fill('1500');
  await page.getByLabel('Service').fill(serviceName);
  await page.getByRole('option', { name: new RegExp(serviceName) }).click();
  await page.getByRole('button', { name: 'Add milestone' }).click();
  await expect(page.getByText(/First visit · PLANNED/)).toBeVisible({ timeout: 20_000 });
});
