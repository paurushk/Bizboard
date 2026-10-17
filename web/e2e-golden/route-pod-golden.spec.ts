import { expect, test } from '@playwright/test';
import {
  completePurchaseInvoice, createCustomer, createProduct, createSupplier, confirmOrderInList, createQuotationConvertedToOrder, pickOrderForRoute, registerTenant, unique,
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
  // Confirming an order reserves stock, and only confirmed orders can go on a route.
  const supplierName = `Route Supplier ${id}`;
  await createSupplier(page, { name: supplierName });
  await completePurchaseInvoice(page, {
    supplierName, sku, productName: `Route Widget ${id}`, unitPrice: '40', quantity: '10',
  });
  await createCustomer(page, { name: customerName });
  await createQuotationConvertedToOrder(page, { customerName, sku });
  await confirmOrderInList(page, customerName);

  await page.goto('/sales/delivery-routes');
  await page.getByRole('button', { name: 'New delivery route' }).click();
  await pickOrderForRoute(page, customerName);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page).toHaveURL(/\/sales\/delivery-routes\/\d+/, { timeout: 20_000 });
  await page.getByRole('button', { name: 'Start route' }).click();
  await expect(page.getByLabel('Received by')).toBeVisible({ timeout: 15_000 });

  // Delivered is refused until someone is named as the receiver.
  await page.getByRole('button', { name: 'Record outcome' }).click();
  await expect(page.getByRole('alert').filter({ hasText: /receiv/i }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Received by:/)).toHaveCount(0);

  // With a name (recorded by the office, no customer code) it goes through.
  await page.getByLabel('Received by').fill('Ravi');
  await page.getByLabel('The customer gave a delivery code (driver’s phone)').uncheck();
  await page.getByRole('button', { name: 'Record outcome' }).click();
  await expect(page.getByText(/Received by:/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Ravi')).toBeVisible();
});
