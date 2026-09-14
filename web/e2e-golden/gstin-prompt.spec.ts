import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  registerTenant,
  saveCompanyGstin,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

test('B14: Regular empty GSTIN blocks GST Complete until GSTIN is saved', async ({ page }) => {
  test.setTimeout(150_000);
  const id = unique();
  const sku = `GSTIN-${id}`;
  const customerName = `GSTIN Customer ${id}`;

  await registerTenant(page, {
    companyName: `E2E GSTIN ${id}`,
    email: `e2e-gstin-${id}@example.test`,
    password: 'GoldenPath123!',
    gstin: false,
  });
  await createProduct(page, {
    name: `GSTIN Widget ${id}`,
    sku,
    sellingPrice: '100',
    purchasePrice: '80',
    hsnCode: '7318',
  });
  await addStockAdjustment(page, { sku, quantity: '5' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await expect(
    page.getByText('Save the company GSTIN in GST settings before completing a GST invoice.'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeDisabled();
  await expect(page.getByText('GST settings').first()).toBeVisible();

  await saveCompanyGstin(page);
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeEnabled();
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
  await expect(page.getByRole('row', { name: new RegExp(customerName) })).toContainText('Completed');
});
