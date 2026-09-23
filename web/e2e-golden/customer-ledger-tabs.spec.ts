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

test('golden path: customer ledger four tabs and excel export', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Ledger ${id}`;
  const email = `e2e-ledger-${id}@example.test`;
  const productName = `Ledger Widget ${id}`;
  const productSku = `LW-${id}`;
  const customerName = `Ledger Customer ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku: productSku, quantity: '10' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, productSku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);

  await page.goto('/reports/customer-ledger');
  const customerCombo = page.getByRole('combobox', { name: 'Customer' });
  await customerCombo.click();
  await customerCombo.fill(customerName);
  await page.getByRole('option', { name: customerName }).click();

  await expect(page.getByRole('tab', { name: /transactions/i })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('tab', { name: /profile/i })).toBeVisible();
  await expect(page.getByRole('tab', { name: /item-wise/i })).toBeVisible();
  await expect(page.getByRole('tab', { name: /statement/i })).toBeVisible();
  await expect(page.getByRole('button', { name: /download excel/i })).toBeVisible();

  await page.getByRole('tab', { name: /profile/i }).click();
  await expect(page.getByLabel(/^name$/i).first()).toHaveValue(customerName);
  await page.getByRole('tab', { name: /item-wise/i }).click();
  await page.getByRole('tab', { name: /statement/i }).click();
  await expect(page.getByText('Sr No')).toBeVisible();
});
