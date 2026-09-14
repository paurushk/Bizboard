import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  completeSalesReturn,
  createCustomer,
  createProduct,
  posCompleteCashSale,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

test('glossary: POS Paid ≠ invoice Completed ≠ Returned on the same tenant', async ({ page }) => {
  test.setTimeout(150_000);
  const id = unique();
  const productName = `GLOSS Widget ${id}`;
  const sku = `GLOSS-${id}`;
  const customerName = `GLOSS Customer ${id}`;

  await registerTenant(page, {
    companyName: `E2E GLOSS ${id}`,
    email: `e2e-gloss-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '10' });
  await createCustomer(page, { name: customerName });

  await page.goto('/pos');
  const itemInput = page.getByPlaceholder('Scan barcode or search product name / SKU');
  await expect(itemInput).toBeVisible({ timeout: 20_000 });
  await itemInput.click();
  await itemInput.fill(sku);
  await expect(page.getByText(new RegExp(sku))).toBeVisible();
  await page.getByText(new RegExp(sku)).click();
  await posCompleteCashSale(page);

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);

  const completedRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(completedRow).toContainText('Completed');
  await expect(completedRow).not.toContainText('Paid');
  const invoiceNumber = (await completedRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toMatch(/^INV-/);

  await expect(page.getByRole('row').filter({ hasText: /Paid/ }).first()).toBeVisible();

  await completeSalesReturn(page, invoiceNumber!);
  await page.goto('/sales/history');
  await expect(page.getByRole('row', { name: new RegExp(invoiceNumber!) })).toContainText(/Returned/i);
  await expect(page.getByRole('row').filter({ hasText: /Paid/ }).first()).toBeVisible();
});
