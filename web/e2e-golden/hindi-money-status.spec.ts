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

test('Hindi money-status pass: completed invoice chip is पूर्ण', async ({ page }) => {
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
  await expect(page).toHaveURL(/\/sales\/history/);
  const invoiceRow = page.getByRole('row', { name: new RegExp(`HI Customer ${id}`) });
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toBeTruthy();

  await page.evaluate(() => localStorage.setItem('bizboard:locale', 'hi'));
  await page.reload();
  await page.goto('/sales/history');
  await expect(page.getByText('पूर्ण').first()).toBeVisible();
  await page.goto('/');
  await expect(page.getByText('ग्राहक बकाया').first()).toBeVisible();

  await page.evaluate(() => localStorage.setItem('bizboard:locale', 'en'));
  await page.reload();
  await completeSalesReturn(page, invoiceNumber!);
  await page.goto('/sales/history');
  await expect(page.getByRole('row', { name: new RegExp(invoiceNumber!) })).toContainText(/Returned/i, {
    timeout: 15_000,
  });
  await page.evaluate(() => localStorage.setItem('bizboard:locale', 'hi'));
  await page.reload();
  await page.goto('/sales/history');
  await expect(page.getByText('वापस').first()).toBeVisible({ timeout: 15_000 });
});
