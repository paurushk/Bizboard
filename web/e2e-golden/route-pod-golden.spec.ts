import { expect, test } from '@playwright/test';
import {
  createCustomer, createProduct, createQuotationConvertedToOrder, registerTenant, unique,
} from './helpers/documents';

test('Delivered stays unavailable until Received by is filled', async ({ page }) => {
  test.setTimeout(180_000);
  const id = unique();
  const customerName = `Route Customer ${id}`;
  const sku = `POD-${id}`;
  await registerTenant(page, {
    companyName: `E2E Route ${id}`,
    email: `e2e-route-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: `Route Widget ${id}`, sku, sellingPrice: '100', purchasePrice: '40' });
  await createCustomer(page, { name: customerName });
  await createQuotationConvertedToOrder(page, { customerName, sku });

  await page.goto('/sales/delivery-routes');
  await page.getByRole('button', { name: 'New delivery route' }).click();
  await expect(page.getByText(new RegExp(customerName))).toBeVisible({ timeout: 15_000 });
  await page.getByText(new RegExp(customerName)).locator('..').getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page).toHaveURL(/\/sales\/delivery-routes\/\d+/, { timeout: 20_000 });
  await page.getByRole('button', { name: 'Start route' }).click();
  await expect(page.getByLabel('Received by')).toBeVisible({ timeout: 15_000 });

  const status = page.locator('table').getByRole('combobox');
  await status.click();
  const blocked = page.getByRole('option', { name: 'Delivered' });
  await expect(blocked).toHaveAttribute('aria-disabled', 'true');
  await page.keyboard.press('Escape');
  await page.getByLabel('Received by').fill('Ravi');
  await status.click();
  await expect(page.getByRole('option', { name: 'Delivered' })).not.toHaveAttribute('aria-disabled', 'true');
});
