import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  enableAccounting,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * V4 95 add-on — pre-accounting completed invoices are not surprise UX.
 * Enable books after a completed sale and the backfill banner must appear.
 */
test('enabling books after a completed invoice shows the backfill warning', async ({ page }) => {
  test.setTimeout(150_000);
  const id = unique();
  const productName = `BF Widget ${id}`;
  const sku = `BF-${id}`;
  const customerName = `BF Customer ${id}`;

  await registerTenant(page, {
    companyName: `E2E Backfill ${id}`,
    email: `e2e-bf-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '5' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
  await expect(page.getByRole('row', { name: new RegExp(customerName) })).toContainText('Completed');

  await enableAccounting(page);
  await page.goto('/reports/books-health');
  await expect(
    page.getByText('Accounting is on, but this company has completed invoices and no journals'),
  ).toBeVisible({ timeout: 20_000 });
});
