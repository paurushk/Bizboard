import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * S6 leftover: dunning/collection walk from customers → ledger, plus the
 * Owner credit-hold switch. Residual-today does not appear on
 * CollectionAttentionCard (31+ day buckets only); ARCH-03 already walks
 * /attention → Open invoice. This spec covers the other collection surfaces.
 */

test('collection walk: outstanding ledger + credit-hold setting', async ({ page }) => {
  test.setTimeout(120_000);
  page.on('dialog', (dialog) => void dialog.accept());

  const id = unique();
  const companyName = `E2E Collect ${id}`;
  const email = `e2e-collect-${id}@example.test`;
  const productName = `Collect Widget ${id}`;
  const productSku = `CL-${id}`;
  const customerName = `Collect Customer ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, {
    name: productName,
    sku: productSku,
    sellingPrice: '100',
    purchasePrice: '80',
    hsnCode: '7318',
  });
  await addStockAdjustment(page, { sku: productSku, quantity: '10' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, productSku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });

  await page.goto('/settings/company');
  await page.getByLabel('Enable automatic reminders').click();
  await page.getByLabel('Auto credit hold on severe overdue').click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Company settings saved')).toBeVisible({ timeout: 15_000 });

  await page.goto('/sales/customers');
  const row = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(row).toContainText(/₹[1-9]/);
  await row.getByRole('link', { name: /Statement \/ Ledger/i }).click();
  await expect(page).toHaveURL(/\/reports\/customer-ledger/);
  await expect(page.getByText(customerName).first()).toBeVisible({ timeout: 15_000 });

  await page.goto('/');
  await expect(page.getByText('Customer outstanding').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/₹[1-9]/).first()).toBeVisible();
});
