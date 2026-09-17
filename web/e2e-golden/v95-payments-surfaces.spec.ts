import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createPaymentLinkAndReadPublicPath,
  createProduct,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * V2 — /payments/links and /payments/statements are freeze workflows.
 * A link created from invoice detail must appear on the list; a CSV upload
 * must produce a statement row (not a heading-only visit).
 */
test('payment links list shows a link created from the invoice', async ({ page }) => {
  test.setTimeout(180_000);
  const id = unique();
  const productName = `Link Widget ${id}`;
  const sku = `LNK-${id}`;
  const customerName = `Link Customer ${id}`;

  await registerTenant(page, {
    companyName: `E2E Links ${id}`,
    email: `e2e-links-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '10' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(invoiceRow).toContainText('Completed');
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toMatch(/^INV-/);

  await createPaymentLinkAndReadPublicPath(page, invoiceNumber!);
  await page.goto('/payments/links');
  await expect(page.getByRole('row', { name: new RegExp(customerName) })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole('row', { name: new RegExp(customerName) })).toContainText(/INV-/);
});

test('bank statement CSV upload appears on the statements list', async ({ page }) => {
  test.setTimeout(120_000);
  const id = unique();
  const accountName = `Ops Bank ${id}`;

  await registerTenant(page, {
    companyName: `E2E Stmt ${id}`,
    email: `e2e-stmt-${id}@example.test`,
    password: 'GoldenPath123!',
  });

  await page.goto('/settings/bank-accounts');
  await page.getByRole('button', { name: 'Add account' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('textbox', { name: 'Name', exact: true }).fill(accountName);
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText(accountName)).toBeVisible({ timeout: 15_000 });

  await page.goto('/payments/statements');
  await page.getByLabel('Bank account').click();
  await page.getByRole('option', { name: new RegExp(accountName) }).click();
  const today = new Date();
  const dd = String(today.getDate()).padStart(2, '0');
  const mm = String(today.getMonth() + 1).padStart(2, '0');
  const yyyy = today.getFullYear();
  const csv = `Date,Credit,Debit,Narration,Ref No\n${dd}/${mm}/${yyyy},2500,,PAYMENT FROM CUST V95UTR,V95UTR\n`;
  await page.locator('input[type="file"]').setInputFiles({
    name: `v95-stmt-${id}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from(csv),
  });
  await page.getByRole('button', { name: 'Upload' }).click();
  await expect(page.getByText(new RegExp(`v95-stmt-${id}`))).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/PREVIEW|preview/i).first()).toBeVisible();
});
