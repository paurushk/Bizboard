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
  await page.getByRole('button', { name: 'Start project' }).first().click();
  const start = page.getByRole('dialog');
  await start.getByRole('combobox', { name: 'Customer', exact: true }).fill(customerName);
  await page.getByRole('option', { name: new RegExp(customerName) }).click();
  await start.getByLabel('Name', { exact: false }).fill(`Fit-out ${id}`);
  await start.getByRole('button', { name: 'Start project' }).click();
  // The new project opens on its own page.
  await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 20_000 });
  await expect(page.getByRole('heading', { name: /PRJ-/ })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Add milestone' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Milestone', { exact: false }).fill('First visit');
  await dialog.getByLabel('Amount', { exact: false }).fill('1500');
  await dialog.getByRole('combobox', { name: /Service/ }).fill(serviceName);
  await page.getByRole('option', { name: new RegExp(serviceName) }).click();
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('row', { name: /First visit.*Planned/ })).toBeVisible({ timeout: 20_000 });
});
