import { expect, test } from '@playwright/test';
import { createProduct, registerTenant, unique } from './helpers/documents';

test('golden path: new quotation creates an inline customer', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Quote ${id}`;
  const email = `e2e-quote-${id}@example.test`;
  const productName = `Quote Widget ${id}`;
  const productSku = `QW-${id}`;
  const customerName = `Inline Party ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });

  await page.goto('/sales/quotations');
  await page.getByRole('button', { name: 'New quotation' }).click();
  // The editor is a page now, not a dialog.
  const dialog = page;
  await expect(page.getByRole('heading', { name: /new quotation/i })).toBeVisible();
  await dialog.getByLabel('Add Party').fill(customerName);
  await dialog.getByRole('button', { name: 'Add', exact: true }).first().click();
  await expect(dialog.getByRole('combobox', { name: 'Customer' })).toHaveValue(customerName, { timeout: 15_000 });

  const productCombo = dialog.getByRole('combobox', { name: 'Products' });
  await productCombo.click();
  await productCombo.fill(productSku);
  await page.getByRole('option', { name: new RegExp(productSku) }).click();
  await dialog.getByRole('button', { name: 'Add', exact: true }).last().click();
  await dialog.getByRole('button', { name: 'Save' }).click();

  await expect(page.getByRole('cell', { name: customerName })).toBeVisible({ timeout: 15_000 });
});
