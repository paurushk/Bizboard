import { expect, test } from '@playwright/test';

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

function unique() {
  return `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

test('golden path: register -> purchase bill -> complete -> pay supplier -> outstanding zero', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Purchase Golden ${id}`;
  const email = `e2e-purchase-golden-${id}@example.test`;
  const productName = `Golden Purchase Widget ${id}`;
  const productSku = `GPW-${id}`;
  const supplierName = `Golden Supplier ${id}`;

  // 1. Register a fresh, isolated tenant.
  await page.goto('/register');
  await page.getByLabel('Company name').fill(companyName);
  await page.getByLabel('Full name').fill('E2E Tester');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('GoldenPath123!');
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: 'Karnataka' }).click();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/\/login\?registered=1/);
  await expect(page.getByText(/Account created/i)).toBeVisible();
  await page.getByLabel('Password', { exact: true }).fill('GoldenPath123!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL('/');

  // 2. Create a product.
  await page.goto('/inventory/products');
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByLabel('Name').fill(productName);
  await page.getByLabel('SKU').fill(productSku);
  await page.getByLabel('GST %').fill('18');
  await page.getByLabel('Purchase price').fill('100');
  await page.getByLabel('Selling price').fill('130');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(productName)).toBeVisible();

  // 3. Create a supplier.
  await page.goto('/purchases/suppliers');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByLabel('Name').fill(supplierName);
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: 'Karnataka' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(supplierName)).toBeVisible();

  // 4. Raise a purchase bill and complete it.
  await page.goto('/purchases/new');
  const supplierCombo = page.getByRole('combobox', { name: /bill from/i });
  await supplierCombo.click();
  await supplierCombo.fill(supplierName);
  await page.getByRole('option', { name: supplierName }).click();

  const itemInput = page.getByPlaceholder('+ Add Item / Scan barcode or search SKU / name');
  await itemInput.click();
  await itemInput.fill(productSku);
  await page.getByRole('option', { name: new RegExp(productSku) }).click();
  // qty 1 x purchase price 100, 18% GST -> taxable 100, tax 18, total 118.
  await expect(page.getByText('₹118.00').first()).toBeVisible();

  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/history/);
  const billRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(billRow).toContainText('Completed');
  await expect(billRow).toContainText('₹118.00');

  // 5. Stock must have incremented by the purchased quantity.
  await page.goto('/inventory/stock');
  const stockRow = page.getByRole('row', { name: new RegExp(productName) });
  await expect(stockRow).toContainText('1');

  // 6. Supplier owes the full bill amount.
  await page.goto('/purchases/suppliers');
  const supplierRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(supplierRow).toContainText('₹118.00');

  // 7. Pay the supplier and allocate it to the bill in one step.
  await page.goto('/purchases/payments');
  await page.getByRole('button', { name: 'New payment' }).click();
  const paymentSupplierCombo = page.getByRole('combobox', { name: /supplier/i });
  await paymentSupplierCombo.click();
  await paymentSupplierCombo.fill(supplierName);
  await page.getByRole('option', { name: supplierName }).click();
  await page.getByLabel('Amount').fill('118');
  const allocateCombo = page.getByRole('combobox', { name: /allocate to purchase/i });
  await allocateCombo.click();
  await page.getByRole('option', { name: new RegExp('118') }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Supplier payment created')).toBeVisible();

  // 8. Supplier outstanding must now be zero.
  await page.goto('/purchases/suppliers');
  const settledSupplierRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(settledSupplierRow).toContainText('₹0.00');
});
