import { expect, test } from '@playwright/test';
import {
  completePurchaseInvoice,
  createProduct,
  createSupplier,
  registerTenant,
  unique,
} from './helpers/documents';

/**
 * COMP-007: supplier price history. A real end-to-end run against the live
 * backend — two purchase invoices for the same supplier+product at
 * different prices, then the price-history dialog on the Suppliers page
 * shows both, in date order, with no score/rank/reliability UI element.
 *
 * Requires: backend migrated, ENABLE_SUPPLIER_PRICE_HISTORY=1 (set by
 * playwright.golden.config.ts). Run with: npm run test:e2e:golden
 */

test('COMP-007: price-history dialog shows a real price jump across two purchases', async ({ page }) => {
  const id = unique();
  const companyName = `E2E PriceHistory ${id}`;
  const email = `e2e-price-history-${id}@example.test`;
  const productName = `Price Widget ${id}`;
  const sku = `PH-${id}`;
  const supplierName = `Price Supplier ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku, sellingPrice: '50', purchasePrice: '10' });
  await createSupplier(page, { name: supplierName });

  await completePurchaseInvoice(page, { supplierName, sku, productName, unitPrice: '10', quantity: '1' });
  await completePurchaseInvoice(page, { supplierName, sku, productName, unitPrice: '14', quantity: '1' });

  await page.goto('/purchases/suppliers');
  const supplierRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await supplierRow.getByRole('button', { name: 'Price history' }).click();
  await expect(page.getByRole('heading', { name: new RegExp(`Price history — ${supplierName}`) })).toBeVisible();

  // F1-016/F1-017: getByLabel('Product') (non-exact) also matches the global
  // search bar's aria-label ("Search invoices, customers, products…"), and
  // once opened, the option listbox is *also* labelled "Product" (via
  // aria-labelledby) — exact:true alone still resolves to 2 elements, so
  // this must be scoped to the combobox role specifically.
  const productCombo = page.getByRole('combobox', { name: 'Product', exact: true });
  await productCombo.click();
  await productCombo.fill(productName);
  await page.getByRole('option', { name: new RegExp(productName) }).click();

  await expect(page.getByText('₹10.00')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('₹14.00')).toBeVisible();
  for (const banned of [/score/i, /\brank\b/i, /reliab/i]) {
    await expect(page.getByText(banned)).toHaveCount(0);
  }
});
