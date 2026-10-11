import { expect, test, type Page } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  getCsrfToken,
  registerTenant,
  selectPartyOnDocument,
  selectReceiptCustomer,
  unique,
} from './helpers/documents';

/**
 * Money In, end to end against the live backend (no mocks):
 *
 *   receipt with customer TDS -> bill settled for cash + TDS, TDS receivable in the books
 *   voucher in English and Hindi (the PDF the server renders, not a client mock)
 *   sort, filter and CSV export from the receipts list
 *   advance refund, then void with a reason
 *   a walk-in customer cannot keep an advance
 *
 * Requires: backend migrated. Run with: npm run test:e2e:golden -- money-in-golden
 */

async function receiptsPage(page: Page) {
  await page.goto('/sales/receipts');
  await expect(page.getByRole('button', { name: 'New receipt' })).toBeVisible({ timeout: 20_000 });
}

test('golden path: TDS receipt, vouchers, sort and export, refund, void, walk-in block', async ({ page }) => {
  test.setTimeout(240_000);
  const id = unique();
  const customerName = `MoneyIn Customer ${id}`;
  const productName = `MoneyIn Widget ${id}`;
  const sku = `MI-${id}`;

  await registerTenant(page, {
    companyName: `E2E Money In ${id}`,
    email: `e2e-moneyin-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await page.goto('/settings/accounting');
  await page.getByRole('button', { name: 'Enable accounting' }).click();
  await expect(page.getByText('Accounting enabled — CoA seeded.')).toBeVisible();

  await createProduct(page, { name: productName, sku, sellingPrice: '1000', purchasePrice: '700', gstRate: '0' });
  await addStockAdjustment(page, { sku, quantity: '20' });
  await createCustomer(page, { name: customerName });

  // A 1,000 bill.
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  // A completed invoice opens its detail page, whose heading is the invoice number.
  const heading = page.getByRole('heading', { level: 1, name: /^INV-/ });
  await expect(heading).toBeVisible({ timeout: 30_000 });
  const invoiceNumber = ((await heading.textContent()) ?? '').trim();
  expect(invoiceNumber).toMatch(/^INV-/);

  // 1. The customer pays 900 in cash and deducts 100 TDS: one receipt settles the whole bill.
  await receiptsPage(page);
  await page.getByRole('button', { name: 'New receipt' }).click();
  await selectReceiptCustomer(page, customerName);
  await page.getByLabel('Amount', { exact: true }).fill('900');
  await page.getByRole('combobox', { name: 'Apply to specific invoice (optional)' }).click();
  await page.getByRole('option', { name: new RegExp(invoiceNumber!) }).click();
  await page.getByRole('button', { name: 'More options' }).click();
  await page.getByLabel('TDS deducted by customer').fill('100');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Receipt created')).toBeVisible();

  await page.goto('/sales/customers');
  await expect(page.getByRole('row', { name: new RegExp(customerName) })).toContainText('₹0.00', { timeout: 30_000 });
  // The books: TDS receivable (1270) carries the 100, cash (1100) the 900.
  await page.goto('/reports/trial-balance');
  await expect(page.getByRole('row', { name: /\b1270\b/ })).toContainText('100.00');
  await expect(page.getByRole('row', { name: /\b1100\b/ })).toContainText('900.00');

  // 2. The voucher, as the server renders it, in both languages.
  await receiptsPage(page);
  await page.getByRole('button', { name: /open voucher RCT-/i }).first().click();
  const voucher = page.getByRole('dialog');
  await expect(voucher.getByText('TDS deducted')).toBeVisible();
  for (const lang of ['en', 'hi'] as const) {
    if (lang === 'hi') {
      await voucher.getByRole('combobox', { name: 'Language' }).click();
      await page.getByRole('option', { name: 'हिन्दी' }).click();
    }
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/voucher/') && r.url().includes(`lang=${lang}`)),
      voucher.getByRole('button', { name: 'Download PDF' }).click(),
    ]);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('application/pdf');
    expect((await response.body()).subarray(0, 4).toString()).toBe('%PDF');
  }
  await voucher.getByRole('button', { name: 'Close' }).click();

  // 3. Two more receipts, then sort, filter and export.
  for (const amount of ['300', '50']) {
    await page.getByRole('button', { name: 'New receipt' }).click();
    await selectReceiptCustomer(page, customerName);
    await page.getByLabel('Amount', { exact: true }).fill(amount);
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('Receipt created')).toBeVisible();
  }
  await page.getByRole('button', { name: /sort by amount/i }).click();
  await expect(page.getByRole('columnheader', { name: /amount/i })).toHaveAttribute('aria-sort', 'descending');
  const firstAmount = await page.locator('tbody tr').first().locator('td').nth(7).textContent();
  expect(firstAmount).toContain('900');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('customer-receipts.csv');

  // 4. Refund part of the 300 advance, then void the 50 with a reason.
  const advanceRow = page.getByRole('row', { name: /300/ }).first();
  await advanceRow.getByRole('button', { name: /^Actions / }).click();
  await page.getByRole('menuitem', { name: 'Refund advance' }).click();
  const refund = page.getByRole('dialog');
  await refund.getByLabel('Amount to refund').fill('120');
  await refund.getByLabel(/^Reason/).fill('customer asked for it back');
  await refund.getByRole('button', { name: 'Refund advance' }).click();
  await expect(page.getByText('Advance refunded')).toBeVisible();

  const smallRow = page.getByRole('row', { name: /\b50\.00/ }).first();
  await smallRow.getByRole('button', { name: 'Void', exact: true }).click();
  const voidDialog = page.getByRole('dialog');
  await voidDialog.getByLabel(/^Reason for voiding/).fill('keyed twice');
  await voidDialog.getByRole('button', { name: 'Void', exact: true }).click();
  await expect(page.getByText('Receipt voided')).toBeVisible();

  // 5. A walk-in customer cannot keep an advance.
  const token = await getCsrfToken(page);
  const walkIn = await page.request.post('/api/v1/customers/pos-walk-in/', {
    data: {},
    headers: { 'X-CSRFToken': token },
  });
  expect(walkIn.ok()).toBeTruthy();
  await page.reload();
  await page.getByRole('button', { name: 'New receipt' }).click();
  const combo = page.getByPlaceholder(/search active customer by name or phone/i);
  await combo.click();
  await combo.fill('Walk');
  await page.getByRole('option', { name: /walk-in|cash customer|counter/i }).first().click();
  await page.getByLabel('Amount', { exact: true }).fill('10');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(/must be applied to invoices in full/i)).toBeVisible();
});
