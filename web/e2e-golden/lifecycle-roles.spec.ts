import { expect, test } from '@playwright/test';
import {
  addStockAdjustment,
  completeSalesReturn,
  createProduct,
  enableAccounting,
  inviteStaff,
  loginWithPassword,
  posCompleteCashSale,
  registerTenant,
  signOut,
  unique,
} from './helpers/documents';

/**
 * S4 + S5a — Owner + Cashier (SALES_STAFF) + Accountant, one company.
 * Same POS invoice number: cashier Paid, cannot Complete return; Owner returns;
 * cashier then sees Returned; accountant reads TB and 403s on close; Owner closes.
 */
test('lifecycle roles: cashier POS Paid, Owner return, cashier Returned, accountant 403 close', async ({
  page,
}) => {
  test.setTimeout(300_000);
  page.on('dialog', (dialog) => dialog.accept());
  const id = unique();
  const password = 'GoldenPath123!';
  const ownerEmail = `e2e-roles-owner-${id}@example.test`;
  const cashierEmail = `e2e-roles-cash-${id}@example.test`;
  const acctEmail = `e2e-roles-acct-${id}@example.test`;
  const productName = `ROLE Widget ${id}`;
  const productSku = `ROLE-${id}`;

  await registerTenant(page, {
    companyName: `E2E Roles ${id}`,
    email: ownerEmail,
    password,
  });
  await enableAccounting(page);
  await createProduct(page, { name: productName, sku: productSku, sellingPrice: '100', purchasePrice: '80', hsnCode: '7318' });
  await addStockAdjustment(page, { sku: productSku, quantity: '10' });
  await inviteStaff(page, {
    email: cashierEmail,
    password,
    fullName: `Cashier ${id}`,
    role: 'SALES_STAFF',
  });
  await inviteStaff(page, {
    email: acctEmail,
    password,
    fullName: `Accountant ${id}`,
    role: 'ACCOUNTANT',
  });

  await signOut(page);
  await loginWithPassword(page, cashierEmail, password);

  await page.goto('/pos');
  const itemInput = page.getByPlaceholder('Scan barcode or search product name / SKU');
  await expect(itemInput).toBeVisible({ timeout: 20_000 });
  await itemInput.click();
  await itemInput.fill(productSku);
  await expect(page.getByText(new RegExp(productSku))).toBeVisible();
  await page.getByText(new RegExp(productSku)).click();
  await expect(page.getByRole('button', { name: /^Cash — ₹/ })).toBeVisible();
  await posCompleteCashSale(page);

  await page.goto('/sales/history');
  const paidRow = page.getByRole('row').filter({ hasText: /Paid/ }).first();
  await expect(paidRow).toBeVisible();
  const invoiceNumber = (await paidRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toMatch(/^INV-/);

  await page.goto('/sales/returns');
  await page.getByRole('button', { name: 'New sales return' }).first().click();
  await expect(page.getByText(/Only the Owner/i)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Complete', exact: true })).toBeDisabled();
  await page.keyboard.press('Escape');

  await signOut(page);
  await loginWithPassword(page, ownerEmail, password);
  await completeSalesReturn(page, invoiceNumber!);

  await signOut(page);
  await loginWithPassword(page, cashierEmail, password);
  await page.goto('/sales/history');
  const returnedRow = page.getByRole('row', { name: new RegExp(invoiceNumber!) });
  await expect(returnedRow).toContainText(/Returned/i);
  await expect(returnedRow).not.toContainText('Paid');

  await signOut(page);
  await loginWithPassword(page, acctEmail, password);
  await page.goto('/reports/trial-balance');
  await expect(page.getByText(/Total debit/i)).toBeVisible({ timeout: 20_000 });

  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  await signOut(page);
  await loginWithPassword(page, ownerEmail, password);
  await page.goto('/accounting/periods');
  await page.getByLabel('Name', { exact: true }).fill(`Roles close ${id}`);
  await page.getByLabel('Start', { exact: true }).fill(today);
  await page.getByLabel('End', { exact: true }).fill(today);
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.getByText(`Roles close ${id}`)).toBeVisible({ timeout: 15_000 });

  await signOut(page);
  await loginWithPassword(page, acctEmail, password);
  await page.goto('/accounting/periods');
  await page.getByRole('button', { name: 'Close', exact: true }).first().click();
  await expect(page.getByText(/permission|not allowed|owner|403|cannot/i).first()).toBeVisible({
    timeout: 15_000,
  });
  const periodRow = page.getByRole('row', { name: new RegExp(`Roles close ${id}`) });
  await expect(periodRow.getByText('OPEN', { exact: true })).toBeVisible();
  await expect(periodRow.getByText('CLOSED', { exact: true })).toHaveCount(0);

  await signOut(page);
  await loginWithPassword(page, ownerEmail, password);
  await page.goto('/accounting/periods');
  await page.getByRole('button', { name: 'Close', exact: true }).first().click();
  await expect(periodRow.getByText('CLOSED', { exact: true })).toBeVisible({ timeout: 20_000 });
});
