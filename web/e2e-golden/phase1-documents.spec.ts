import { expect, test, type Page } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * Phase 1 golden extensions: multi-line return, sales CN + PDF, SO→invoice convert.
 */

async function createProductWithStock(page: Page, id: string, skuSuffix: string) {
  const productName = `P1 Widget ${skuSuffix} ${id}`;
  const productSku = `P1-${skuSuffix}-${id}`;
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '50', gstRate: '0' });
  await addStockAdjustment(page, { sku: productSku, quantity: '20' });
  return { productName, productSku };
}

async function completeInvoiceWithProducts(
  page: Page,
  customerName: string,
  skus: string[],
) {
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await page.getByLabel('Invoice type').click();
  await page.getByRole('option', { name: /Non-GST/i }).click();

  for (const sku of skus) {
    await addInvoiceItem(page, sku);
  }
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) }).first();
  await expect(invoiceRow).toContainText('Completed');
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toBeTruthy();
  return invoiceNumber!;
}

test('phase1: multi-line return + credit note PDF + SO convert', async ({ page }) => {
  const id = unique();
  const companyName = `E2E P1 ${id}`;
  const email = `e2e-p1-${id}@example.test`;
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  const a = await createProductWithStock(page, id, 'A');
  const b = await createProductWithStock(page, id, 'B');
  const customerName = `P1 Customer ${id}`;
  await createCustomer(page, { name: customerName });

  const invoiceNumber = await completeInvoiceWithProducts(page, customerName, [
    a.productSku,
    b.productSku,
  ]);

  // Multi-line sales return — include both lines via checkboxes.
  await page.goto('/sales/returns');
  await page.getByRole('button', { name: 'New sales return' }).first().click();
  const invCombo = page.getByPlaceholder('Search by invoice # or customer');
  await invCombo.click();
  await invCombo.fill(invoiceNumber);
  await page.getByRole('option', { name: new RegExp(invoiceNumber) }).click();
  const checkboxes = page.getByRole('checkbox');
  await expect(checkboxes).toHaveCount(2, { timeout: 10_000 });
  await checkboxes.nth(0).check();
  await checkboxes.nth(1).check();
  await page.getByLabel('Reason').fill('Multi-line return e2e');
  await page.getByRole('button', { name: 'Complete' }).click();
  await expect(page.getByText(/Sales return completed/i)).toBeVisible({ timeout: 15_000 });

  // Credit note + PDF ready.
  const cnSource = await completeInvoiceWithProducts(page, customerName, [a.productSku]);
  await page.goto('/sales/credit-notes/new');
  const source = page.getByRole('combobox', { name: 'Source invoice' });
  await source.click();
  await source.fill(cnSource);
  await page.getByRole('option', { name: new RegExp(cnSource) }).click();
  await page.getByRole('button', { name: new RegExp(a.productName) }).click();
  await page.getByRole('button', { name: /Save & Complete/i }).click();
  await expect(page.getByRole('button', { name: /Download|Print/i }).first()).toBeVisible({
    timeout: 45_000,
  });

  // SO → invoice convert.
  await page.goto('/sales/orders/new');
  const soCustomer = page.getByRole('combobox', { name: 'Customer', exact: true });
  await soCustomer.click();
  await soCustomer.fill(customerName);
  await page.getByRole('option', { name: customerName }).click();
  const soProduct = page.getByRole('combobox', { name: 'Products', exact: true });
  await soProduct.click();
  await soProduct.fill(a.productSku);
  await page.getByRole('option', { name: new RegExp(a.productSku) }).click();
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page).toHaveURL(/\/sales\/orders\/\d+/);
  await page.getByRole('button', { name: /Convert/ }).click();
  await expect(page).toHaveURL(/\/sales\/history/);
});
