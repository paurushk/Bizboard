import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  registerTenant,
  selectPartyOnDocument,
  selectReceiptCustomer,
  unique,
} from './helpers/documents';

/**
 * BUG-725 — a true end-to-end run against the live backend (not mocked
 * data): register a fresh company, create a product and customer, raise a
 * sales invoice, complete it, verify stock decremented, receive payment,
 * allocate it, and download + sanity-check the resulting PDF.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: register -> invoice -> complete -> pay -> pdf', async ({ page }) => {
  test.setTimeout(150_000);
  const id = unique();
  const companyName = `E2E Golden ${id}`;
  const email = `e2e-golden-${id}@example.test`;
  const productName = `Golden Widget ${id}`;
  const productSku = `GW-${id}`;
  const customerName = `Golden Customer ${id}`;

  // 1. Register a fresh, isolated tenant.
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  // 2. Create a product.
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80', gstRate: '0' });

  // 3. Give it opening stock.
  await addStockAdjustment(page, { sku: productSku, quantity: '50' });

  // 4. Create a customer.
  await createCustomer(page, { name: customerName });

  // 5. Raise a sales invoice and complete it.
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, productSku);
  await expect(page.getByText('₹100.00').first()).toBeVisible();

  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  // An open completed invoice shows the payment chip, not the document word Completed.
  await expect(invoiceRow).toContainText('Unpaid');
  await expect(invoiceRow).toContainText('₹100.00');
  const textCells = await invoiceRow.locator('td').allTextContents();
  const invoiceNumber = textCells
    .map((c) => c.trim())
    .find((c) => /^INV-/.test(c))
    ?.split('·')[0]
    .trim();
  expect(invoiceNumber).toMatch(/^INV-/);

  // 6. Stock must have decremented by the invoiced quantity.
  await page.goto('/inventory/stock');
  // "Show lots" owns the row's accessible name; match the product text instead.
  const stockRow = page.getByRole('row').filter({ hasText: productName });
  await expect(stockRow).toContainText('49', { timeout: 20_000 });

  // 7. Receive payment and allocate it to the invoice in one step.
  await page.goto('/sales/receipts');
  await page.getByRole('button', { name: 'New receipt' }).click();
  await selectReceiptCustomer(page, customerName);
  await page.getByLabel('Amount').fill('100');
  const allocateCombo = page.getByRole('combobox', { name: 'Apply to specific invoice (optional)' });
  await allocateCombo.click();
  await page.getByRole('option', { name: new RegExp(invoiceNumber!) }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Receipt created')).toBeVisible();

  // 8. Customer outstanding must now be zero.
  await page.goto('/sales/customers');
  const customerRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(customerRow).toContainText('₹0.00');

  // 9. Download the invoice PDF and sanity-check it's a real PDF.
  await page.goto('/sales/history');
  await page.getByRole('link', { name: invoiceNumber! }).click();
  await expect(page).toHaveURL(/\/sales\/history\/\d+$/);
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  await new Promise<void>((resolve, reject) => {
    stream?.on('data', (chunk) => chunks.push(chunk as Buffer));
    stream?.on('end', () => resolve());
    stream?.on('error', reject);
  });
  const content = Buffer.concat(chunks);
  expect(content.length).toBeGreaterThan(100);
  expect(content.subarray(0, 5).toString('utf-8')).toBe('%PDF-');
});
