import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  completePurchaseReturn,
  completeResidualPurchaseDebitNote,
  createProduct,
  createSupplier,
  enableAccounting,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * S2a — purchase residual lifecycle: complete bill → partial supplier payment →
 * full return → residual purchase DN → AP aging → period still open.
 */
test('lifecycle purchase residual: bill, partial pay, return, residual DN, AP, period open', async ({
  page,
}) => {
  test.setTimeout(180_000);
  page.on('dialog', (dialog) => dialog.accept());
  const id = unique();
  const productName = `PURL Widget ${id}`;
  const sku = `PURL-${id}`;
  const supplierName = `PURL Supplier ${id}`;

  await registerTenant(page, {
    companyName: `E2E PURL ${id}`,
    email: `e2e-purl-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await enableAccounting(page);
  await createProduct(page, { name: productName, sku, sellingPrice: '130', purchasePrice: '100' });
  await createSupplier(page, { name: supplierName });

  await page.goto('/purchases/new');
  await selectPartyOnDocument(page, supplierName);
  await addInvoiceItem(page, sku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/history/);
  const billRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(billRow).toContainText('Completed');
  const purchaseNumber = (await billRow.locator('td').nth(1).textContent())?.trim();
  expect(purchaseNumber).toBeTruthy();
  await billRow.getByRole('link').click();
  await expect(page).toHaveURL(/\/purchases\/history\/\d+/);

  await page.goto('/purchases/payments');
  await page.getByRole('button', { name: 'New payment' }).first().click();
  const paymentSupplierCombo = page.getByRole('combobox', { name: /supplier/i });
  await paymentSupplierCombo.click();
  await paymentSupplierCombo.fill(supplierName);
  await page.getByRole('option', { name: supplierName }).click();
  await page.getByLabel('Amount').fill('40');
  const allocateCombo = page.getByRole('combobox', { name: /allocate to purchase/i });
  await allocateCombo.click();
  await page.getByRole('option', { name: new RegExp(purchaseNumber!)}).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Supplier payment created')).toBeVisible();

  await completePurchaseReturn(page, purchaseNumber!);
  await completeResidualPurchaseDebitNote(page, {
    supplierName,
    purchaseNumber: purchaseNumber!,
  });

  await page.goto('/');
  await expect(page.getByText('Supplier payables').first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.locator('div').filter({ hasText: /^Supplier payables/ }).getByText(/₹[1-9]/).first(),
  ).toBeVisible();

  await page.goto('/attention');
  await expect(page.getByText('Needs attention').first()).toBeVisible({ timeout: 20_000 });

  await page.goto('/accounting/periods');
  await expect(page.getByText(/CLOSED/i)).toHaveCount(0);
});
