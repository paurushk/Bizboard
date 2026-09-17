import { expect, test } from '@playwright/test';
import {
  createProduct,
  createSupplier,
  fillNamedCombobox,
  registerTenant,
  unique,
} from './helpers/documents';

/**
 * V2 — freeze A6 purchase-order workflow: create a PO, then the list shows
 * a real status (not a heading-only visit of /purchases/orders).
 */
test('golden path: create purchase order → list shows DRAFT', async ({ page }) => {
  test.setTimeout(120_000);
  const id = unique();
  const productName = `PO Widget ${id}`;
  const sku = `POW-${id}`;
  const supplierName = `PO Supplier ${id}`;

  await registerTenant(page, {
    companyName: `E2E PO ${id}`,
    email: `e2e-po-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '130', purchasePrice: '100' });
  await createSupplier(page, { name: supplierName });

  await page.goto('/purchases/orders/new');
  await fillNamedCombobox(page, 'Supplier', supplierName);
  await fillNamedCombobox(page, 'Products', sku, new RegExp(sku));
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page).toHaveURL(/\/purchases\/orders\/\d+/, { timeout: 20_000 });

  await page.goto('/purchases/orders');
  const row = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(row).toBeVisible();
  await expect(row).toContainText(/draft/i);
});
