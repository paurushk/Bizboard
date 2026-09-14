import { expect, test } from '@playwright/test';
import {
  addStockAdjustment,
  createProduct,
  posCompleteCashSale,
  readGodownStock,
  registerTenant,
  unique,
} from './helpers/documents';

/**
 * BB-000829 follow-up — POS checkout hits the exact same SalesService.complete()
 * path a regular invoice does, but no existing golden spec (nor the mocked
 * web/e2e/ pos-friction.spec.ts, which never completes a real sale) proves a
 * POS sale actually decrements stock in the real backend. This does: complete
 * a real cash sale through the counter UI at /pos, then verify the exact
 * quantity dropped from the specific godown that was selling from.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: POS cash checkout decrements exact stock in the selected godown', async ({ page }) => {
  test.setTimeout(90_000);
  const id = unique();
  const companyName = `E2E POS Golden ${id}`;
  const email = `e2e-pos-golden-${id}@example.test`;
  const productName = `POS Widget ${id}`;
  const productSku = `POSW-${id}`;

  // 1. Register a fresh, isolated tenant.
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  // 2. Create a product and give it opening stock in the default godown.
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku: productSku, quantity: '20' });
  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(20);

  // 3. Complete a cash sale at the counter. No customer is selected — POS
  // auto-creates a walk-in "Cash Customer" on checkout for a tenant that
  // doesn't have one yet, so this is the actual zero-friction counter flow
  // a first-time cashier gets, not a contrived setup step.
  const checkoutStarted = Date.now();
  await page.goto('/pos');
  const itemInput = page.getByPlaceholder('Scan barcode or search product name / SKU');
  await expect(itemInput).toBeVisible({ timeout: 20_000 });
  await itemInput.click();
  await itemInput.fill(productSku);
  await expect(page.getByText(new RegExp(productSku))).toBeVisible();
  await page.getByText(new RegExp(productSku)).click();

  await expect(page.getByRole('button', { name: /^Cash — ₹/ })).toBeVisible();
  await posCompleteCashSale(page);
  expect(
    Date.now() - checkoutStarted,
    'live POS checkout must stay under the H-02 35s budget',
  ).toBeLessThan(35_000);

  // 4. Stock must have decremented by exactly the sold quantity, in the
  // godown the counter was actually selling from.
  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(19);
});

test('golden path: POS cash checkout against a non-default godown only moves that godown', async ({ page }) => {
  const id = unique();
  const companyName = `E2E POS MultiWH ${id}`;
  const email = `e2e-pos-multiwh-${id}@example.test`;
  const productName = `POS MultiWH Widget ${id}`;
  const productSku = `PMW-${id}`;
  const branchName = `Counter ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  await page.goto('/inventory/warehouses');
  await page.getByRole('button', { name: 'Add godown' }).click();
  await page.getByLabel('Name', { exact: true }).fill(branchName);
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('row', { name: new RegExp(branchName) })).toBeVisible();

  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku: productSku, quantity: '10' }); // default godown
  await addStockAdjustment(page, { sku: productSku, quantity: '10', warehouseName: branchName });

  await page.goto('/pos');
  await expect(page.getByPlaceholder('Scan barcode or search product name / SKU')).toBeVisible({
    timeout: 20_000,
  });
  await page.getByLabel('Godown').click();
  await page.getByRole('option', { name: branchName, exact: true }).click();

  const itemInput = page.getByPlaceholder('Scan barcode or search product name / SKU');
  await itemInput.click();
  await itemInput.fill(productSku);
  await expect(page.getByText(new RegExp(productSku))).toBeVisible();
  await page.getByText(new RegExp(productSku)).click();

  await expect(page.getByRole('button', { name: /^Cash — ₹/ })).toBeVisible();
  await posCompleteCashSale(page);

  // The counter godown drops by exactly 1; the default godown it was never
  // selling from is untouched.
  expect(await readGodownStock(page, branchName, productName)).toBe(9);
  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(10);
});
