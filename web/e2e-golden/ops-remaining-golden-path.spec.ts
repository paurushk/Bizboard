import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  fillNamedCombobox,
  completePurchaseReturn,
  createCustomer,
  createProduct,
  createSupplier,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

test('serial: opening serial is AVAILABLE then SOLD after invoice complete', async ({ page }) => {
  test.setTimeout(90_000);
  const id = unique();
  const productName = `SER Widget ${id}`;
  const sku = `SER-${id}`;
  const serialNo = `SN-${id}`;
  const customerName = `SER Customer ${id}`;

  await registerTenant(page, {
    companyName: `E2E SER ${id}`,
    email: `e2e-ser-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, {
    name: productName,
    sku,
    sellingPrice: '100',
    purchasePrice: '80',
    serialNo,
  });
  await createCustomer(page, { name: customerName });

  await page.goto('/inventory/serials');
  await expect(page.getByRole('row', { name: new RegExp(serialNo) })).toContainText('AVAILABLE');

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await page.getByPlaceholder('SN-001, SN-002').fill(serialNo);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);

  await page.goto('/inventory/serials');
  await expect(page.getByRole('row', { name: new RegExp(serialNo) })).toContainText('SOLD');
});

test('challan cancel after complete returns the document to Cancelled', async ({ page }) => {
  test.setTimeout(90_000);
  page.on('dialog', (dialog) => dialog.accept());
  const id = unique();
  const productName = `DC Widget ${id}`;
  const sku = `DC-${id}`;
  const customerName = `DC Customer ${id}`;

  await registerTenant(page, {
    companyName: `E2E DC ${id}`,
    email: `e2e-dc-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '5' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/delivery-challans/new');
  await fillNamedCombobox(page, 'Customer', customerName);
  await fillNamedCombobox(page, 'Products', sku, new RegExp(sku));
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page.getByRole('button', { name: 'Cancel document' })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Cancel document' }).click();
  await expect(page).toHaveURL(/\/sales\/delivery-challans/);
  await expect(page.getByRole('row', { name: new RegExp(customerName) })).toContainText(/Cancelled/i);
});

test('purchase residual debit note after full return on a RETURNED bill', async ({ page }) => {
  test.setTimeout(90_000);
  page.on('dialog', (dialog) => dialog.accept());
  const id = unique();
  const productName = `PDN Widget ${id}`;
  const sku = `PDN-${id}`;
  const supplierName = `PDN Supplier ${id}`;

  await registerTenant(page, {
    companyName: `E2E PDN ${id}`,
    email: `e2e-pdn-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await createSupplier(page, { name: supplierName });

  await page.goto('/purchases/new');
  await selectPartyOnDocument(page, supplierName);
  await addInvoiceItem(page, sku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/history/);
  const purchaseRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await expect(purchaseRow).toContainText('Completed');
  const purchaseNumber = (await purchaseRow.locator('td').nth(1).textContent())?.trim();
  expect(purchaseNumber).toBeTruthy();

  await completePurchaseReturn(page, purchaseNumber!);

  await page.goto('/purchases/debit-notes/new');
  await fillNamedCombobox(page, 'Supplier', supplierName);
  await fillNamedCombobox(page, 'Purchase invoice (optional)', purchaseNumber!, new RegExp(purchaseNumber!));
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/debit-notes\/\d+/, { timeout: 20_000 });
  await expect(
    page.getByRole('button', { name: 'Cancel document' }).or(page.getByText('Completed', { exact: true }).first()),
  ).toBeVisible({ timeout: 10_000 });
});
