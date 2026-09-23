import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

test('golden path: complete invoice then share from history row menu', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Share ${id}`;
  const email = `e2e-share-${id}@example.test`;
  const productName = `Share Widget ${id}`;
  const productSku = `SW-${id}`;
  const customerName = `Share Customer ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku: productSku, quantity: '10' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, productSku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);

  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(invoiceRow).toContainText('Completed');
  await invoiceRow.getByRole('button', { name: 'Actions' }).click();
  await page.getByRole('menuitem', { name: 'Share' }).click();

  const dialog = page.getByRole('dialog', { name: 'Share invoice' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Email' }).click();
  await dialog.getByLabel('Email').fill(`share-${id}@example.test`);
  await dialog.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByText(/Share ready|Sent/i).first()).toBeVisible({ timeout: 15_000 });
});
