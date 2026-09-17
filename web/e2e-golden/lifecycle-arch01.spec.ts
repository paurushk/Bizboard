import { expect, test } from '@playwright/test';
import {
  addStockAdjustment,
  completeSalesReturn,
  createProduct,
  posCompleteCashSale,
  readGodownStock,
  registerTenant,
  unique,
} from './helpers/documents';

/**
 * Phase 4 / D15: POS sale is an ordinary SalesInvoice; the return UI is
 * `/sales/returns` (Owner can complete it). After return, history/detail/
 * dashboard/stock must not say Paid.
 *
 * Live Django — do not mock `/attention`.
 */

test('lifecycle ARCH-01: POS checkout -> history badge -> Owner sales return -> surfaces agree', async ({ page }) => {
  test.setTimeout(120_000);
  const id = unique();
  const companyName = `E2E LC01 ${id}`;
  const email = `e2e-lc01-${id}@example.test`;
  const productName = `LC01 Widget ${id}`;
  const productSku = `LC01-${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku: productSku, quantity: '10' });
  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(10);

  await page.goto('/pos');
  const itemInput = page.getByPlaceholder('Scan barcode or search product name / SKU');
  await expect(itemInput).toBeVisible({ timeout: 20_000 });
  await itemInput.click();
  await itemInput.fill(productSku);
  await expect(page.getByText(new RegExp(productSku))).toBeVisible();
  await page.getByText(new RegExp(productSku)).click();
  await expect(page.getByRole('button', { name: /^Cash — ₹/ })).toBeVisible();
  await posCompleteCashSale(page);

  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(9);

  await page.goto('/sales/history');
  const invoiceRow = page.getByRole('row').filter({ hasText: /Paid|Completed/ }).first();
  await expect(invoiceRow).toContainText(/₹/);
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toMatch(/^INV-/);

  await completeSalesReturn(page, invoiceNumber!);

  await page.goto('/sales/history');
  const returnedRow = page.getByRole('row', { name: new RegExp(invoiceNumber!) });
  await expect(returnedRow).toContainText(/Returned/i);
  await expect(returnedRow).not.toContainText('Paid');

  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(10);

  await page.goto('/');
  await expect(page.getByText('Customer outstanding').first()).toBeVisible({ timeout: 20_000 });

  await page.goto('/attention');
  await expect(page).toHaveURL(/\/attention/);
  await expect(page.locator('body')).not.toContainText(/something went wrong/i);
  await expect(page.getByText('Needs attention').first()).toBeVisible({ timeout: 20_000 });
});
