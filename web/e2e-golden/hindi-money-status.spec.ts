import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  completeSalesReturn,
  createCustomer,
  createProduct,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

test('Hindi money-status pass: open invoice chip is बकाया', async ({ page }) => {
  test.setTimeout(180_000);
  const id = unique();
  await registerTenant(page, {
    companyName: `E2E HI ${id}`,
    email: `e2e-hi-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: `HI Widget ${id}`, sku: `HI-${id}`, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku: `HI-${id}`, quantity: '10' });
  await createCustomer(page, { name: `HI Customer ${id}` });
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, `HI Customer ${id}`);
  await addInvoiceItem(page, `HI-${id}`);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
  const invoiceRow = page.getByRole('row', { name: new RegExp(`HI Customer ${id}`) });
  await expect(invoiceRow).toContainText('Unpaid');
  const textCells = await invoiceRow.locator('td').allTextContents();
  const invoiceNumber = textCells.map(c => c.trim()).find(c => /^INV-/.test(c))?.split('·')[0].trim();
  expect(invoiceNumber).toBeTruthy();

  await page.getByRole('button', { name: 'हिंदी' }).click();
  await page.goto('/sales/history');
  await expect(page.getByRole('row', { name: new RegExp(`HI Customer ${id}`) })).toContainText('बकाया');
  await page.goto('/');
  await expect(page.getByText('ग्राहक बकाया').first()).toBeVisible();

  await page.getByRole('button', { name: 'English' }).click();
  await completeSalesReturn(page, invoiceNumber!);
  await page.goto('/sales/history');
  await expect(page.getByRole('row', { name: new RegExp(invoiceNumber!) })).toContainText(/Returned/i, {
    timeout: 15_000,
  });
  await page.getByRole('button', { name: 'हिंदी' }).click();
  await page.goto('/sales/history');
  await expect(page.getByText('वापस').first()).toBeVisible({ timeout: 15_000 });
});
