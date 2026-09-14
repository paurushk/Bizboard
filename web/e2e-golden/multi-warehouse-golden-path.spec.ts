import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  createSupplier,
  createWarehouse,
  readGodownStock,
  registerTenant,
  selectDocumentWarehouse,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * BB-000829 follow-up — the original bug report ("does completing a sale or
 * purchase decrease/increase the EXACT quantity in the right godown") turned
 * out to be only partially covered even by the backend test suite: every
 * existing exact-quantity assertion (backend and the other golden specs)
 * runs in a tenant with a single default warehouse, so a bug that silently
 * mutated the WRONG godown's balance would still pass every one of them.
 *
 * This is the missing case: two godowns, and every mutation asserted on both
 * sides — the selected godown moves by exactly the transacted quantity, and
 * the OTHER godown is provably untouched. Live-verified against the real
 * backend before being written here (not guessed from source reading).
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: sale and purchase against a non-default godown never touch the other godown', async ({ page }) => {
  const id = unique();
  const companyName = `E2E MultiWH ${id}`;
  const email = `e2e-multiwh-${id}@example.test`;
  const productName = `MultiWH Widget ${id}`;
  const productSku = `MWG-${id}`;
  const customerName = `MultiWH Customer ${id}`;
  const supplierName = `MultiWH Supplier ${id}`;
  const branchName = `Branch ${id}`;

  // 1. Register a fresh, isolated tenant (one default godown to start).
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  // 2. Create a second godown.
  await createWarehouse(page, branchName);

  // 3. Create a product, then seed stock into BOTH godowns independently.
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku: productSku, quantity: '10' }); // default godown
  await addStockAdjustment(page, { sku: productSku, quantity: '10', warehouseName: branchName });

  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(10);
  expect(await readGodownStock(page, branchName, productName)).toBe(10);

  // 4. Sell 1 unit explicitly from the BRANCH godown.
  await createCustomer(page, { name: customerName });
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await selectDocumentWarehouse(page, branchName);
  await addInvoiceItem(page, productSku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);

  // Branch decremented by exactly 1; the default godown is untouched.
  expect(await readGodownStock(page, branchName, productName)).toBe(9);
  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(10);

  // 5. Buy 5 units explicitly into the BRANCH godown.
  await createSupplier(page, { name: supplierName });
  await page.goto('/purchases/new');
  await selectPartyOnDocument(page, supplierName);
  await selectDocumentWarehouse(page, branchName);
  await addInvoiceItem(page, productSku);
  // The line's quantity field has no accessible label of its own (a bare
  // NumericField in a table cell) — it's the second <input> in the product's
  // row: the first is the free-text "Description (optional)" field right
  // above it (see components/billing/DraftLineTable.tsx).
  const purchaseRow = page.getByRole('row', { name: new RegExp(productName) });
  await purchaseRow.locator('input').nth(1).fill('5');
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/history/);

  // Branch incremented by exactly 5 (9 + 5 = 14); the default godown is
  // still untouched — this is the actual claim under test: a mutation
  // scoped to one godown must never leak into another.
  expect(await readGodownStock(page, branchName, productName)).toBe(14);
  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(10);
});
