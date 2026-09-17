import { expect, test } from '@playwright/test';
import { createProduct, enableAccounting, registerTenant, unique } from './helpers/documents';

/** 7.11 — label print, price lists, statutory events, cost centers are real Owner journeys. */

test('low-traffic money-adjacent surfaces: create + one action each', async ({ page }) => {
  test.setTimeout(120_000);
  const id = unique();
  const productName = `SURF Widget ${id}`;
  const sku = `SURF-${id}`;
  const listName = `SURF list ${id}`;
  const centerName = `SURF CC ${id}`;

  await registerTenant(page, {
    companyName: `E2E SURF ${id}`,
    email: `e2e-surf-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await enableAccounting(page);

  await page.goto('/inventory/labels');
  const addProduct = page.getByLabel('Add a product');
  await addProduct.click();
  await addProduct.fill(sku);
  await page.getByRole('option', { name: new RegExp(sku) }).click();
  await expect(page.getByRole('button', { name: /Print 1 label/i })).toBeEnabled();
  await expect(page.getByRole('cell', { name: productName })).toBeVisible();

  await page.goto('/settings/price-lists');
  await page.getByRole('button', { name: 'New list' }).click();
  await page.getByLabel('Name').fill(listName);
  await page.getByRole('button', { name: 'Create' }).click();
  await expect(page.getByRole('cell', { name: listName })).toBeVisible();

  await page.goto('/accounting/cost-centers');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByLabel('Name').fill(centerName);
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('row', { name: new RegExp(centerName) })).toBeVisible();

  await page.goto('/reports/statutory-events');
  await expect(page.getByRole('heading', { name: /statutory events/i })).toBeVisible();
  await page.getByLabel(/event type/i).click();
  await page.getByRole('option', { name: /all/i }).click();
  await expect(page.locator('body')).not.toContainText(/something went wrong/i);
});
