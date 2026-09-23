import { expect, test } from '@playwright/test';
import {
  completePurchaseInvoice,
  convertDraftOrderToCompletedInvoiceViaChallan,
  createCustomer,
  createProduct,
  createQuotationConvertedToOrder,
  createSupplier,
  registerTenant,
  unique,
} from './helpers/documents';

/**
 * COMP-005: route profit. A real end-to-end run against the live backend —
 * register a tenant, take a sales order through to a completed invoice,
 * attach it to a delivery route while it's still a DRAFT order (the route's
 * "add orders" dialog only lists DRAFT orders), complete the route with an
 * actual logistics cost, and confirm the route detail screen shows the
 * frozen trip profit and the invoiced-stop count.
 *
 * Requires: backend migrated, ENABLE_ROUTE_PROFIT=1 (set by
 * playwright.golden.config.ts). Run with: npm run test:e2e:golden
 */

test('COMP-005: completing a route with an invoiced stop shows trip profit', async ({ page }) => {
  // A long sequential chain (register -> product -> supplier -> purchase ->
  // customer -> quotation -> order -> route -> challan -> invoice -> route
  // complete) against a real backend routinely runs past the 90s default.
  test.setTimeout(180_000);
  const id = unique();
  const companyName = `E2E Route ${id}`;
  const email = `e2e-route-${id}@example.test`;
  const productName = `Route Widget ${id}`;
  const sku = `RTE-${id}`;
  const customerName = `Route Customer ${id}`;

  const supplierName = `Route Supplier ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku, sellingPrice: '200', purchasePrice: '120' });
  await createSupplier(page, { name: supplierName });
  // Explicit, unambiguous unit cost via a real purchase invoice — a single
  // stock layer at ₹120/unit, so the route's COGS figure is not left to
  // whatever a stock adjustment might default its cost to.
  await completePurchaseInvoice(page, {
    supplierName, sku, productName, unitPrice: '120', quantity: '10',
  });
  await createCustomer(page, { name: customerName });

  // Quotation -> Order lands on the order detail page, status DRAFT — the
  // shape the delivery-route "add orders" picker filters on.
  await createQuotationConvertedToOrder(page, { customerName, sku });
  const orderUrl = page.url();

  await page.goto('/sales/delivery-routes');
  await page.getByRole('button', { name: 'New delivery route' }).click();
  await expect(page.getByText(new RegExp(customerName))).toBeVisible({ timeout: 15_000 });
  await page.getByText(new RegExp(customerName)).locator('..').getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page).toHaveURL(/\/sales\/delivery-routes\/\d+/, { timeout: 20_000 });
  const routeUrl = page.url();

  // Convert the same order to a completed invoice — the route stop's FK to
  // the order persists regardless of the order's own status changing.
  await page.goto(orderUrl);
  await convertDraftOrderToCompletedInvoiceViaChallan(page, customerName);

  await page.goto(routeUrl);
  await page.getByRole('button', { name: 'Start route' }).click();
  await expect(page.getByLabel('Actual logistics cost')).toBeVisible({ timeout: 15_000 });
  await page.getByLabel('Actual logistics cost').fill('20');
  await page.getByRole('button', { name: 'Complete', exact: true }).click();

  // Revenue 200 (taxable, unregistered tenant so no GST), COGS 1 x purchase
  // price 120, logistics 20 -> profit 60. One of one stops invoiced.
  await expect(page.getByText(/Trip profit: ₹60\.00/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Stops invoiced: 1\/1/)).toBeVisible();
});
