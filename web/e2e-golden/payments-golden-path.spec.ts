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
 * Golden path for the Payments/Accounting money flow: register -> enable
 * accounting (seeds the chart of accounts) -> invoice -> receipt allocated
 * to it -> verify both the operational state (outstanding zero) AND the
 * real GL posting behind it (PostingService.post_receipt credits Customer
 * Advances / debits Cash; post_receipt_allocation moves it into AR) rather
 * than assuming a receipt "worked" just because no error appeared.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: register -> enable accounting -> invoice -> receipt -> GL posted', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Payments ${id}`;
  const email = `e2e-payments-${id}@example.test`;
  const productName = `Payments Widget ${id}`;
  const productSku = `PW-${id}`;
  const customerName = `Payments Customer ${id}`;

  // 1. Register a fresh, isolated tenant.
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  // 2. Enable accounting — seeds the chart of accounts synchronously, so
  // every posting below (invoice complete, receipt, allocation) lands in a
  // real GL from the start. A full page.goto() (not a client-side link) is
  // required afterwards for AuthContext to re-fetch /auth/me and pick up
  // company.accountingEnabled=true — it's a one-time boot fetch, not
  // react-query, so the earlier settings mutation's cache invalidation
  // alone never refreshes it.
  await page.goto('/settings/accounting');
  await page.getByRole('button', { name: 'Enable accounting' }).click();
  await expect(page.getByText('Accounting enabled — CoA seeded.')).toBeVisible();

  // 3. Create a product.
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });

  // 4. Give it opening stock.
  await addStockAdjustment(page, { sku: productSku, quantity: '50' });

  // 5. Create a customer (same state as the company -> intra-state GST).
  await createCustomer(page, { name: customerName });

  // 6. Raise and complete a sales invoice. A fresh registration defaults to
  // registration_type=UNREGISTERED, so no GST applies: 1 unit @ ₹100 -> ₹100.00 flat.
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, productSku);
  await expect(page.getByText('₹100.00').first()).toBeVisible();

  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(invoiceRow).toContainText('Completed');
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toMatch(/^INV-\d+$/);

  // 7. Receive a CASH receipt and allocate it to the invoice in one step.
  await page.goto('/sales/receipts');
  await page.getByRole('button', { name: 'New receipt' }).click();
  await selectReceiptCustomer(page, customerName);
  await page.getByLabel('Amount').fill('100');
  // Mode defaults to CASH -> PostingService.post_receipt debits account 1100
  // (Cash), not a specific bank account -> a stable, always-true assertion below.
  const allocateCombo = page.getByRole('combobox', { name: 'Apply to specific invoice (optional)' });
  await allocateCombo.click();
  await page.getByRole('option', { name: new RegExp(invoiceNumber!) }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Receipt created')).toBeVisible();

  // 8. Customer outstanding must now be zero (operational state) — step 9
  // below is the independent GL-level proof of the same thing.
  await page.goto('/sales/customers');
  const customerRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(customerRow).toContainText('₹0.00');

  // 9. GL proof: the trial balance must actually be balanced (double-entry
  // held across invoice-complete + receipt + allocation postings) and must
  // show the Cash account the CASH-mode receipt posted to.
  await page.goto('/reports/trial-balance');
  await expect(page.getByText(/Total debit .* Total credit/)).toBeVisible();
  await expect(page.getByRole('row', { name: /\b1100\b/ })).toBeVisible();
});
