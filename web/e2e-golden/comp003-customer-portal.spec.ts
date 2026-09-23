import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  enableSandboxPayments,
  registerTenant,
  saveAndCompleteSalesInvoice,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * COMP-003: customer self-service portal, the real request -> link ->
 * invoice-list -> PDF -> pay flow against the live backend, in a separate
 * browser context (simulating an actual customer, not the logged-in owner
 * session). The mock-mode suite (e2e/payments/customer-portal.spec.ts)
 * covers only the logged-out UI shell, since mock mode has no portal API —
 * this is the one that actually exercises the backend.
 *
 * Requires: backend migrated, ENABLE_CUSTOMER_PORTAL=1 and
 * PORTAL_DEBUG_ECHO=1 (both set by playwright.golden.config.ts — the debug
 * echo is what lets this spec read the magic-link token from the response
 * instead of an inbox, same posture as the register flow's Dev OTP).
 * Run with: npm run test:e2e:golden
 */

test('COMP-003: customer requests a link, views invoices, downloads a PDF, and pays', async ({ page, browser }) => {
  const id = unique();
  const companyName = `E2E Portal ${id}`;
  const email = `e2e-portal-${id}@example.test`;
  const productName = `Portal Widget ${id}`;
  const sku = `PTL-${id}`;
  const customerName = `Portal Customer ${id}`;
  const customerEmail = `portal-customer-${id}@example.test`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  // gstRate: '0' keeps the invoice amount exactly ₹250 — the portal's own
  // amount column renders the invoice grand total (formatMoney(invoice.amount)
  // in CustomerPortalPage.tsx), which would be ₹295 (250 + the dialog's
  // default 18% GST) if left unset, not the ₹250 asserted below.
  await createProduct(page, { name: productName, sku, sellingPrice: '250', purchasePrice: '150', gstRate: '0' });
  // F1-017: a fresh product has zero stock, and Complete is BLOCK-policy
  // gated on stock — the invoice below would never become completable
  // without this.
  await addStockAdjustment(page, { sku, quantity: '10' });
  await enableSandboxPayments(page);

  await page.goto('/sales/customers');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(customerName);
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: 'Karnataka' }).click();
  await page.getByLabel('Email').fill(customerEmail);
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(customerName)).toBeVisible();

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await saveAndCompleteSalesInvoice(page, new RegExp(customerName));
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  const invoiceNumberText = (await invoiceRow.locator('td').first().textContent()) ?? '';

  // A fresh, isolated browser context — no owner session, no shared
  // cookies — standing in for the actual customer's own device.
  const customerContext = await browser.newContext();
  const customerPage = await customerContext.newPage();
  try {
    await customerPage.goto('/portal');
    await customerPage.getByLabel('Email').fill(customerEmail);
    await customerPage.getByRole('button', { name: 'Send link' }).click();
    await expect(customerPage.getByText('If we found a matching customer, we sent a link.')).toBeVisible();

    const hint = customerPage.getByTestId('portal-debug-hint');
    await expect(hint).toBeVisible({ timeout: 10_000 });
    const hintText = (await hint.textContent()) ?? '';
    const token = hintText.match(/\/portal\/(\S+)/)?.[1];
    expect(token, `could not read portal token from hint "${hintText}"`).toBeTruthy();

    await customerPage.goto(`/portal/${token}`);
    await expect(customerPage.getByRole('heading', { name: 'Your invoices' })).toBeVisible();
    if (invoiceNumberText.trim()) {
      await expect(customerPage.getByText(new RegExp(invoiceNumberText.trim()))).toBeVisible();
    }
    await expect(customerPage.getByText('₹250.00').first()).toBeVisible();

    const download = customerPage.waitForEvent('download');
    await customerPage.getByRole('button', { name: 'Download PDF' }).click();
    const downloaded = await download;
    expect(downloaded.suggestedFilename()).toMatch(/\.pdf$/i);

    await customerPage.getByRole('button', { name: 'Pay' }).click();
    await expect(customerPage).toHaveURL(/\/pay\//, { timeout: 15_000 });
  } finally {
    await customerContext.close();
  }
});
