import { expect, test } from '@playwright/test';
import {
  addStockAdjustment,
  createProduct,
  createWarehouse,
  readGodownStock,
  registerTenant,
  unique,
} from './helpers/documents';

test('inventory ops: stock count session + transfer between godowns', async ({ page }) => {
  const id = unique();
  const productName = `OPS Widget ${id}`;
  const sku = `OPS-${id}`;
  const branch = `Branch ${id}`;

  await registerTenant(page, {
    companyName: `E2E OPS ${id}`,
    email: `e2e-ops-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createWarehouse(page, branch);
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '8' });
  await addStockAdjustment(page, { sku, quantity: '2', warehouseName: branch });

  await page.goto('/inventory/stock-counts');
  await page.getByRole('button', { name: 'New count' }).click();
  await page.getByLabel('Godown').click();
  await page.getByRole('option', { name: 'Default Godown' }).click();
  await page.getByRole('button', { name: 'Start count' }).click();
  await expect(page.getByRole('button', { name: 'Count' }).first()).toBeVisible({ timeout: 15_000 });

  await page.goto('/inventory/transfers');
  await page.getByRole('button', { name: 'New transfer' }).click();
  await page.getByLabel('From godown').click();
  await page.getByRole('option', { name: /Default Godown/ }).click();
  await page.getByLabel('To godown').click();
  await page.getByRole('option', { name: branch }).click();
  const productBox = page.getByLabel(/product/i).first();
  await productBox.click();
  await productBox.fill(sku);
  await page.getByRole('option', { name: new RegExp(sku) }).click();
  await page.getByLabel(/quantity/i).fill('1');
  await page.getByRole('button', { name: /create draft|save/i }).click();
  await expect(page.getByRole('button', { name: 'Complete' }).first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Complete' }).first().click();

  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(7);
  expect(await readGodownStock(page, branch, productName)).toBe(3);
});
