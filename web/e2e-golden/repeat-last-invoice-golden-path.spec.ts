import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  registerTenant,
  saveAndCompleteSalesInvoice,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * Golden path for "Repeat last invoice" — Customer360Page.tsx's
 * repeatMutation, which POSTs to /api/v1/sales/invoices/repeat-last/
 * (backend/sales/views.py `repeat_last`, calling
 * SalesService.repeat_last_invoice in backend/sales/services.py).
 *
 * Confirmed against the real code before writing this spec:
 * - Customer360Page.tsx ALWAYS renders the "Repeat last invoice" button —
 *   it is not conditional on the customer having any prior invoice at all —
 *   and on success navigates to `/sales/history/:id/edit`, the very same
 *   SalesInvoiceEditor route App.tsx wires up for `/sales/new`, so the new
 *   draft is immediately, fully editable.
 * - SalesService.repeat_last_invoice copies the most recent COMPLETED
 *   invoice's lines (product, quantity, unit_price, discount, gst_rate, …)
 *   into a brand-new DRAFT invoice and raises
 *   BusinessRuleError("This customer has no completed invoice to repeat.")
 *   when there is none — Customer360Page surfaces that as inline
 *   `repeatError` text, not a crash or a silent no-op.
 * - Customer360Page (route `sales/customers/:id`) and the "Customer 360"
 *   link on CustomersPage both only render when ENABLE_CUSTOMER_360 is on
 *   (backend/insights/customer_360.py returns None otherwise) — this is a
 *   ROLLOUT_GRANTABLE_KEYS env-default flag with no per-company UI toggle
 *   yet, same as the COMP-* flags already in this suite's shared
 *   playwright.golden.config.ts, so it's been added there too.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: repeat last invoice copies lines into a new editable draft, original invoice untouched', async ({
  page,
}) => {
  const id = unique();
  const companyName = `E2E Repeat ${id}`;
  const email = `e2e-repeat-${id}@example.test`;
  const productName = `Repeat Widget ${id}`;
  const sku = `RW-${id}`;
  const customerName = `Repeat HasInvoices ${id}`;
  const emptyCustomerName = `Repeat NoInvoices ${id}`;

  // 1. Register a fresh tenant and set up a product + two customers: one
  // will get a completed invoice, the other never will (edge case below).
  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80', gstRate: '0' });
  await addStockAdjustment(page, { sku, quantity: '50' });
  await createCustomer(page, { name: customerName });
  await createCustomer(page, { name: emptyCustomerName });

  // 2. Raise and complete a sales invoice: 2 units @ ₹100 -> ₹200.00.
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  const newItemRow = page.getByRole('row', { name: new RegExp(productName) });
  await newItemRow.getByLabel('QTY').fill('2');
  await expect(page.getByText('₹200.00').first()).toBeVisible();
  await saveAndCompleteSalesInvoice(page, new RegExp(customerName));
  const originalInvoiceRow = page.getByRole('row', { name: new RegExp(customerName) }).first();
  const originalCells = await originalInvoiceRow.locator('td').allTextContents();
  const originalInvoiceNumber = originalCells.map((c) => c.trim()).find((c) => /^INV-/.test(c));
  expect(originalInvoiceNumber).toMatch(/^INV-/);

  // 3. Navigate to the customer's 360 page via the real UI entry point (the
  // "Customer 360" link on the customers list — a RouterLink-backed Button,
  // whose implicit ARIA role is "link", not "button").
  await page.goto('/sales/customers');
  await page
    .getByRole('row', { name: new RegExp(customerName) })
    .getByRole('link', { name: /Customer (360|Snapshot)/i })
    .click();
  await expect(page).toHaveURL(/\/sales\/customers\/\d+$/);

  // 4. Click "Repeat last invoice" -> lands on a new DRAFT invoice's edit page.
  await page.getByRole('button', { name: 'Repeat last invoice' }).click();
  await expect(page).toHaveURL(/\/sales\/history\/\d+\/edit/, { timeout: 20_000 });

  // 5. The new draft must be pre-filled with the same product/quantity/price
  // as the original completed invoice (2 units @ ₹100 -> ₹200.00).
  const draftRow = page.getByRole('row', { name: new RegExp(productName) });
  await expect(draftRow).toBeVisible();
  await expect(draftRow.getByLabel('QTY')).toHaveValue('2');
  await expect(draftRow.locator('input').nth(1)).toHaveValue('100');
  await expect(page.getByText('₹200.00').first()).toBeVisible();

  // 6. Edit the new draft (bump quantity to 5 -> ₹500.00, a total distinct
  // from the original ₹200.00 so the two invoices are unambiguous on the
  // history list below) and complete it.
  await draftRow.getByLabel('QTY').fill('5');
  await expect(page.getByText('₹500.00').first()).toBeVisible();
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
  let newInvoiceRow = page.getByRole('row', { name: new RegExp(customerName) }).filter({ hasText: '₹500.00' });
  await expect(newInvoiceRow).toBeVisible({ timeout: 15_000 });
  // Same transient SQLite "database is locked" retry as
  // saveAndCompleteSalesInvoice in helpers/documents.ts (can't reuse that
  // helper directly here since it takes a single name matcher and two
  // invoices now share this customer's name).
  const completedNow = await newInvoiceRow
    .getByText('Completed')
    .isVisible()
    .catch(() => false);
  if (!completedNow) {
    await newInvoiceRow.getByRole('link').first().click();
    await page.getByRole('link', { name: 'Edit', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: 'Save & Complete' }).click();
    await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
    newInvoiceRow = page.getByRole('row', { name: new RegExp(customerName) }).filter({ hasText: '₹500.00' });
  }
  await expect(newInvoiceRow).toContainText('Completed', { timeout: 15_000 });
  const newCells = await newInvoiceRow.locator('td').allTextContents();
  const newInvoiceNumber = newCells.map((c) => c.trim()).find((c) => /^INV-/.test(c));
  expect(newInvoiceNumber).toMatch(/^INV-/);
  expect(newInvoiceNumber).not.toBe(originalInvoiceNumber);

  // 7. The original invoice itself must be completely unchanged — fetch it
  // straight from the API (independent of the list UI) and check its line
  // still says 2 units @ ₹100, not 5.
  const invoicesRes = await page.request.get('/api/v1/sales/invoices/?page_size=200');
  expect(invoicesRes.ok(), await invoicesRes.text()).toBeTruthy();
  const invoices = (await invoicesRes.json()).data.results as Array<{
    id: number;
    number: string;
    items: Array<{ quantity: string; unit_price?: string; unitPrice?: string }>;
  }>;
  const originalInvoice = invoices.find((inv) => inv.number === originalInvoiceNumber);
  expect(originalInvoice, `original invoice ${originalInvoiceNumber} not found via API`).toBeTruthy();
  expect(originalInvoice!.items).toHaveLength(1);
  expect(Number(originalInvoice!.items[0].quantity)).toBe(2);
  const originalPrice = originalInvoice!.items[0].unitPrice ?? originalInvoice!.items[0].unit_price;
  expect(Number(originalPrice)).toBe(100);
  await expect(page.getByRole('row', { name: new RegExp(originalInvoiceNumber!) })).toContainText('₹200.00');

  // 8. Edge case: a customer with NO prior completed invoice at all. The
  // button is NOT conditionally hidden (confirmed in Customer360Page.tsx —
  // it always renders), so clicking it must surface the backend's clear
  // error message instead of crashing or silently navigating anywhere.
  await page.goto('/sales/customers');
  await page
    .getByRole('row', { name: new RegExp(emptyCustomerName) })
    .getByRole('link', { name: /Customer (360|Snapshot)/i })
    .click();
  await expect(page).toHaveURL(/\/sales\/customers\/\d+$/);
  const noInvoicesUrl = page.url();
  await page.getByRole('button', { name: 'Repeat last invoice' }).click();
  await expect(page.getByText('This customer has no completed invoice to repeat.')).toBeVisible({
    timeout: 15_000,
  });
  expect(page.url()).toBe(noInvoicesUrl);
});
