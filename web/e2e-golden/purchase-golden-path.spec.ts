import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  createProduct,
  createSupplier,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * The Purchases-domain equivalent of invoice-golden-path.spec.ts — a true
 * end-to-end run against the live backend (not mocked data): register a
 * fresh company, create a product and supplier, raise a purchase bill,
 * complete it, verify stock incremented, pay the supplier, allocate it, and
 * verify the supplier's outstanding balance clears to zero.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: register -> purchase bill -> complete -> pay supplier -> outstanding zero', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Purchase Golden ${id}`;
  const email = `e2e-purchase-golden-${id}@example.test`;
  const productName = `Golden Purchase Widget ${id}`;
  const productSku = `GPW-${id}`;
  const supplierName = `Golden Supplier ${id}`;

  // 1. Register a fresh, isolated tenant.
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  // 2. Create a product.
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '130', purchasePrice: '100' });

  // 3. Create a supplier.
  await createSupplier(page, { name: supplierName });

  // 4. Raise a purchase bill and complete it. A fresh registration defaults
  // to registration_type=UNREGISTERED, so no GST applies: qty 1 @ ₹100 -> ₹100.00 flat.
  await page.goto('/purchases/new');
  await selectPartyOnDocument(page, supplierName);
  await addInvoiceItem(page, productSku);
  await expect(page.getByText('₹100.00').first()).toBeVisible();

  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/history/);
  const billRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(billRow).toContainText('Completed');
  await expect(billRow).toContainText('₹100.00');
  await billRow.getByRole('link').click();
  await expect(page).toHaveURL(/\/purchases\/history\/\d+/);

  // 5. Stock must have incremented by the purchased quantity.
  await page.goto('/inventory/stock');
  const stockRow = page.getByRole('row', { name: new RegExp(productName) });
  await expect(stockRow).toContainText('1');

  // 6. Supplier owes the full bill amount.
  await page.goto('/purchases/suppliers');
  const supplierRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(supplierRow).toContainText('₹100.00');

  // 7. Pay the supplier and allocate it to the bill in one step.
  await page.goto('/purchases/payments');
  await page.getByRole('button', { name: 'New payment' }).first().click();
  const paymentSupplierCombo = page.getByRole('combobox', { name: /supplier/i });
  await paymentSupplierCombo.click();
  await paymentSupplierCombo.fill(supplierName);
  await page.getByRole('option', { name: supplierName }).click();
  await page.getByLabel('Amount').fill('100');
  const allocateCombo = page.getByRole('combobox', { name: /allocate to purchase/i });
  await allocateCombo.click();
  await page.getByRole('option', { name: new RegExp('100') }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Supplier payment created')).toBeVisible();

  // 8. The payment shows the correct allocation, and supplier outstanding
  // must now be zero.
  const paymentRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(paymentRow).toContainText('₹100.00');

  await page.goto('/purchases/suppliers');
  const settledSupplierRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(settledSupplierRow).toContainText('₹0.00');
});
