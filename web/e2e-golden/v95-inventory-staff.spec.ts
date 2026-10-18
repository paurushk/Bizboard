import { expect, test } from '@playwright/test';
import {
  addStockAdjustment,
  createProduct,
  createWarehouse,
  enableAccounting,
  inviteStaff,
  loginWithPassword,
  readGodownStock,
  registerTenant,
  signOut,
  unique,
} from './helpers/documents';

/**
 * V5 — P4 inventory staff can complete an inter-godown transfer (their stock
 * job) and cannot close a period or post a journal (B13).
 */
test('inventory staff transfers stock and is denied journals / period close', async ({ page }) => {
  test.setTimeout(240_000);
  page.on('dialog', (dialog) => dialog.accept());
  const id = unique();
  const password = 'GoldenPath123!';
  const ownerEmail = `e2e-inv-owner-${id}@example.test`;
  const staffEmail = `e2e-inv-staff-${id}@example.test`;
  const productName = `INV Staff Widget ${id}`;
  const sku = `INVST-${id}`;
  const branch = `Branch ${id}`;

  await registerTenant(page, {
    companyName: `E2E InvStaff ${id}`,
    email: ownerEmail,
    password,
  });
  await enableAccounting(page);
  await createWarehouse(page, branch);
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '8' });
  await addStockAdjustment(page, { sku, quantity: '2', warehouseName: branch });
  await inviteStaff(page, {
    email: staffEmail,
    password,
    fullName: `Inventory ${id}`,
    role: 'INVENTORY_STAFF',
  });

  await signOut(page);
  await loginWithPassword(page, staffEmail, password);

  await page.goto('/inventory/transfers');
  await page.getByRole('button', { name: 'New transfer' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('From godown').click();
  await page.getByRole('option', { name: /Default Godown/ }).click();
  await dialog.getByLabel('To godown').click();
  await page.getByRole('option', { name: branch }).click();
  const productBox = dialog.getByRole('combobox', { name: 'Product', exact: true });
  await productBox.click();
  await productBox.fill(sku);
  await page.getByRole('option', { name: new RegExp(sku) }).click();
  await dialog.getByLabel('Quantity').fill('1');
  await dialog.getByRole('button', { name: 'Create draft' }).click();
  // A draft is dispatched (after a confirm), then received from the destination's row.
  const dispatchButton = page.getByRole('button', { name: 'Dispatch' }).first();
  await expect(dispatchButton).toBeVisible({ timeout: 15_000 });
  await dispatchButton.click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  const rowReceive = page.getByRole('button', { name: 'Receive' }).first();
  await expect(rowReceive).toBeVisible({ timeout: 15_000 });
  await rowReceive.click();
  const receiveDialog = page.getByRole('dialog');
  await expect(receiveDialog).toBeVisible({ timeout: 15_000 });
  await receiveDialog.getByRole('button', { name: 'Receive' }).click();
  await expect(receiveDialog).toBeHidden({ timeout: 15_000 });
  expect(await readGodownStock(page, 'Default Godown', productName)).toBe(7);
  expect(await readGodownStock(page, branch, productName)).toBe(3);

  await page.goto('/accounting/journals');
  await expect(page.getByText(/limited access/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('button', { name: 'New voucher' })).toHaveCount(0);
  await page.goto('/accounting/periods');
  await expect(page.getByText(/limited access/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('heading', { name: 'Accounting periods' })).toHaveCount(0);
});
