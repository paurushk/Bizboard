import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  completeResidualSalesDebitNote,
  completeSalesReturn,
  convertDraftOrderToCompletedInvoiceViaChallan,
  createCustomer,
  createPaymentLinkAndReadPublicPath,
  createProduct,
  createQuotationConvertedToOrder,
  createSupplier,
  enableAccounting,
  registerTenant,
  saveCompanyGstin,
  selectPartyOnDocument,
  selectReceiptCustomer,
  unique,
} from './helpers/documents';

/**
 * Phase 4 ARCH-03 + P5 + 7.3: purchase inward → quote → SO → challan → SI →
 * partial receipt → full return → residual debit note → public pay live
 * outstanding → attention walk → period close keeps historical truth.
 */

test('lifecycle ARCH-03: quote-SO-challan-SI-return-residual DN-pay-attention-close', async ({ page }) => {
  test.setTimeout(240_000);
  page.on('dialog', (dialog) => dialog.accept());

  const id = unique();
  const companyName = `E2E LC03 ${id}`;
  const email = `e2e-lc03-${id}@example.test`;
  const productName = `LC03 Widget ${id}`;
  const productSku = `LC03-${id}`;
  const supplierName = `LC03 Supplier ${id}`;
  const customerName = `LC03 Customer ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await saveCompanyGstin(page);
  await enableAccounting(page);
  await createProduct(page, {
    name: productName,
    sku: productSku,
    sellingPrice: '100',
    purchasePrice: '80',
    hsnCode: '7318',
  });
  await createSupplier(page, { name: supplierName });
  await createCustomer(page, { name: customerName });

  await page.goto('/purchases/new');
  await selectPartyOnDocument(page, supplierName);
  await addInvoiceItem(page, productSku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/history/);
  await expect(page.getByRole('row', { name: new RegExp(supplierName) })).toContainText('Completed');

  await createQuotationConvertedToOrder(page, { customerName, sku: productSku });
  await convertDraftOrderToCompletedInvoiceViaChallan(page);

  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(invoiceRow).toContainText('Completed');
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toMatch(/^INV-/);

  const payPath = await createPaymentLinkAndReadPublicPath(page, invoiceNumber!);

  await page.goto('/sales/receipts');
  await page.getByRole('button', { name: 'New receipt' }).first().click();
  await selectReceiptCustomer(page, customerName);
  await page.getByLabel('Amount').fill('40');
  const allocateCombo = page.getByRole('combobox', { name: 'Apply to specific invoice (optional)' });
  await allocateCombo.click();
  await page.getByRole('option', { name: new RegExp(invoiceNumber!) }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Receipt created')).toBeVisible();

  await completeSalesReturn(page, invoiceNumber!);

  await page.goto('/sales/history');
  const returnedRow = page.getByRole('row', { name: new RegExp(invoiceNumber!) });
  await expect(returnedRow).toContainText(/Returned/i);
  await expect(returnedRow).not.toContainText('Paid');

  await page.goto(payPath);
  await expect(page.getByText(/₹0\.00/)).toBeVisible({ timeout: 15_000 });

  await page.goto('/');
  await completeResidualSalesDebitNote(page, { invoiceNumber: invoiceNumber!, productName });

  await page.goto(payPath);
  await expect(page.getByText(/₹0\.00/)).toHaveCount(0);
  await expect(page.getByText(/₹\d/)).toBeVisible({ timeout: 15_000 });

  await page.goto('/');
  await expect(page.getByText('Customer outstanding').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/₹[1-9]/).first()).toBeVisible();

  await page.goto('/attention');
  await expect(page.getByText(/residual balance after return/i).first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole('link', { name: 'Open invoice' }).or(page.getByRole('button', { name: 'Open invoice' })).first().click();
  await expect(page).toHaveURL(new RegExp(`/sales/history/`));
  await expect(page.getByText(invoiceNumber!).first()).toBeVisible();

  await page.goto('/reports/customer-ledger');
  await expect(page.getByText(/ledger|customer/i).first()).toBeVisible();

  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  await page.goto('/accounting/periods');
  await page.getByLabel('Name', { exact: true }).fill(`FY-close ${id}`);
  await page.getByLabel('Start', { exact: true }).fill(today);
  await page.getByLabel('End', { exact: true }).fill(today);
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.getByText(`FY-close ${id}`)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Close', exact: true }).first().click();
  await expect(page.getByText(/CLOSED/i).first()).toBeVisible({ timeout: 20_000 });

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, productSku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page.getByText(/cannot amend|closed|period|not allowed|cannot/i).first()).toBeVisible({
    timeout: 15_000,
  });

  await page.goto('/sales/history');
  await expect(page.getByRole('row', { name: new RegExp(invoiceNumber!) })).toContainText(/Returned/i);

  await page.goto('/reports/trial-balance');
  const tbFoot = page.getByText(/Total debit/i).first();
  await expect(tbFoot).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Total credit/i)).toBeVisible();
  const footText = (await tbFoot.textContent()) ?? '';
  const amounts = [...footText.matchAll(/₹[\d,.]+/g)].map((m) => m[0]);
  expect(amounts.length, footText).toBeGreaterThanOrEqual(2);
  expect(amounts[0]).toBe(amounts[1]);
});
