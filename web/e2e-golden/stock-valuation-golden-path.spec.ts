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
 * The Stock Valuation report showed per-row values but no running total —
 * a gap no suite caught because reports-domain.spec.ts (the only prior
 * coverage of this route) only asserts "renders a heading or degrades to
 * Retry, doesn't crash," never a number. This is a true end-to-end run
 * against the live backend: register a fresh tenant, buy two products at
 * known cost and quantity, then read the same numbers back off
 * /reports/stock-valuation — both per-row and the header total.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: stock valuation total reflects purchased cost x quantity', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Valuation Golden ${id}`;
  const email = `e2e-valuation-golden-${id}@example.test`;
  const productAName = `Valuation Widget A ${id}`;
  const productASku = `VWA-${id}`;
  const productBName = `Valuation Widget B ${id}`;
  const productBSku = `VWB-${id}`;
  const supplierName = `Valuation Supplier ${id}`;

  // 1. Register a fresh, isolated tenant. Defaults to registration_type=
  // UNREGISTERED, so purchases carry no GST and the stock's running cost
  // is exactly the entered purchase price — nothing to back out.
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  // 2. Two products with distinct, known purchase costs.
  await createProduct(page, { name: productAName, sku: productASku, sellingPrice: '130', purchasePrice: '100' });
  await createProduct(page, { name: productBName, sku: productBSku, sellingPrice: '300', purchasePrice: '250' });
  await createSupplier(page, { name: supplierName });

  // 3. Buy 3 of A (@ ₹100) and 2 of B (@ ₹250): 300 + 500 = ₹800 total cost.
  await page.goto('/purchases/new');
  await selectPartyOnDocument(page, supplierName);
  await addInvoiceItem(page, productASku);
  const purchaseRowA = page.getByRole('row', { name: new RegExp(productAName) });
  await purchaseRowA.locator('input').nth(1).fill('3');
  await addInvoiceItem(page, productBSku);
  const purchaseRowB = page.getByRole('row', { name: new RegExp(productBName) });
  await purchaseRowB.locator('input').nth(1).fill('2');
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/history/);

  // 4. Each row values at its WAVG cost (== the entered purchase price,
  // since this is each product's first-ever movement)...
  await page.goto('/reports/stock-valuation');
  const valuationRowA = page.getByRole('row', { name: new RegExp(productAName) });
  await expect(valuationRowA).toContainText('₹100.00');
  await expect(valuationRowA).toContainText('₹300.00');

  const valuationRowB = page.getByRole('row', { name: new RegExp(productBName) });
  await expect(valuationRowB).toContainText('₹250.00');
  await expect(valuationRowB).toContainText('₹500.00');

  // ...and the header total is their sum, not zero, not one row's value,
  // and not silently missing.
  await expect(page.getByText('Total stock value')).toBeVisible();
  await expect(page.getByText('₹800.00', { exact: true })).toBeVisible();
});
