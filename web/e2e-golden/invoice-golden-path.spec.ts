import { expect, test } from '@playwright/test';

/**
 * BUG-725 — a true end-to-end run against the live backend (not mocked
 * data): register a fresh company, create a product and customer, raise a
 * sales invoice, complete it, verify stock decremented, receive payment,
 * allocate it, and download + sanity-check the resulting PDF.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

function unique() {
  return `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

test('golden path: register -> invoice -> complete -> pay -> pdf', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Golden ${id}`;
  const email = `e2e-golden-${id}@example.test`;
  const productName = `Golden Widget ${id}`;
  const productSku = `GW-${id}`;
  const customerName = `Golden Customer ${id}`;

  // 1. Register a fresh, isolated tenant.
  await page.goto('/register');
  await page.getByLabel('Company name').fill(companyName);
  await page.getByLabel('Full name').fill('E2E Tester');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('GoldenPath123!');
  await page.getByLabel('State').fill('Karnataka');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL('/');

  // 2. Create a product.
  await page.goto('/inventory/products');
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByLabel('Name').fill(productName);
  await page.getByLabel('SKU').fill(productSku);
  await page.getByLabel('GST %').fill('18');
  await page.getByLabel('Purchase price').fill('80');
  await page.getByLabel('Selling price').fill('100');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(productName)).toBeVisible();

  // 3. Give it opening stock.
  await page.goto('/inventory/adjustments');
  const productsCombo = page.getByRole('combobox', { name: 'Products', exact: true });
  await productsCombo.click();
  await productsCombo.fill(productSku);
  await page.getByRole('option', { name: new RegExp(productSku) }).click();
  await page.getByLabel('Quantity delta (+/−)').fill('50');
  await page.getByLabel('Reason').fill('Opening stock for golden-path e2e');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Stock adjustment recorded')).toBeVisible();

  // 4. Create a customer.
  await page.goto('/sales/customers');
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByLabel('Name').fill(customerName);
  await page.getByLabel('State').fill('Karnataka');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(customerName)).toBeVisible();

  // 5. Raise a sales invoice and complete it.
  await page.goto('/sales/new');
  const invoiceCustomerCombo = page.getByRole('combobox', { name: 'Customer', exact: true });
  await invoiceCustomerCombo.click();
  await invoiceCustomerCombo.fill(customerName);
  await page.getByRole('option', { name: customerName }).click();

  const itemInput = page.getByPlaceholder('+ Add Item / Scan barcode or search SKU / name');
  await itemInput.click();
  await itemInput.fill(productSku);
  await page.getByRole('option', { name: new RegExp(productSku) }).click();
  await expect(page.getByText('₹118.00').first()).toBeVisible();

  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page).toHaveURL(/\/sales\/history/);
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(invoiceRow).toContainText('Completed');
  await expect(invoiceRow).toContainText('₹118.00');
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toMatch(/^INV-\d+$/);

  // 6. Stock must have decremented by the invoiced quantity.
  await page.goto('/inventory/stock');
  const stockRow = page.getByRole('row', { name: new RegExp(productName) });
  await expect(stockRow).toContainText('49');

  // 7. Receive payment and allocate it to the invoice in one step.
  await page.goto('/sales/receipts');
  await page.getByRole('button', { name: 'Create' }).click();
  const receiptCustomerCombo = page.getByRole('combobox', { name: 'Customer', exact: true });
  await receiptCustomerCombo.click();
  await receiptCustomerCombo.fill(customerName);
  await page.getByRole('option', { name: customerName }).click();
  await page.getByLabel('Amount').fill('118');
  const allocateCombo = page.getByRole('combobox', { name: 'Allocate to invoice (optional)' });
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
  await page.getByRole('button', { name: 'Download ORIGINAL' }).click();
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
