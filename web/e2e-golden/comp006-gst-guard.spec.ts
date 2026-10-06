import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createProduct,
  getCsrfToken,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * COMP-006: GST Guard. A real end-to-end run against the live backend.
 *
 * The two new buyer-GSTIN checks are a defense-in-depth safety net: every
 * UI path (the customer form) and the one backend action that can change an
 * already-completed invoice's filing GSTIN (`amend_filing_identity`) both
 * validate GSTIN format strictly and refuse a malformed one — by design, a
 * malformed GSTIN cannot reach a real invoice through the normal
 * application flow. `filing_party_gstin` has no such validator at invoice
 * *create* time, which is the realistic path bad data actually arrives by
 * (a Tally/CSV import, a data migration, a historical record) — so this
 * spec arranges that condition the same way real bad data would reach it
 * (a direct, authenticated API create, the same session the browser is
 * already using) and then asserts the safety net catches it on the
 * Attention page, exactly where a human would see it.
 *
 * Requires: backend migrated, ENABLE_GST_GUARD=1 (set by
 * playwright.golden.config.ts). Run with: npm run test:e2e:golden
 */

test('COMP-006: a malformed buyer GSTIN surfaces as a named Attention row', async ({ page }) => {
  // The assertion below deliberately waits out a real 60s server-side cache
  // TTL (see the comment at that wait) on top of the normal setup steps.
  test.setTimeout(150_000);
  const id = unique();
  const companyName = `E2E GstGuard ${id}`;
  const email = `e2e-gst-guard-${id}@example.test`;
  const productName = `Guard Widget ${id}`;
  const sku = `GG-${id}`;
  const customerName = `Guard Customer ${id}`;
  const badGstin = '29AAAAA0000A1Z6';

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!', gstin: '29AAAAA0000A1ZY' });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '60', hsnCode: '3004', gstRate: '18' });
  // F1-017: /complete/ hard-blocks on insufficient stock (BLOCK policy) for
  // every product, not only batch-tracked ones — confirmed live (a 400
  // "insufficient_stock" from this exact call without it).
  await addStockAdjustment(page, { sku, quantity: '10' });

  await page.goto('/sales/customers');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(customerName);
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: 'Karnataka' }).click();
  await page.getByLabel('GSTIN').fill('29AABCU9603R1ZJ');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(customerName)).toBeVisible();

  // Look up the just-created customer/product ids via the same session the
  // browser is using (cookie auth) — no UI path exposes them directly.
  // F1-017: customers and products are both mounted at the API root (via
  // masters.urls), not under /masters/ or /inventory/ — confirmed against
  // the real requests the app itself makes (GET /api/v1/customers/,
  // GET /api/v1/products/).
  // F1-017: every 2xx JSON response is wrapped as {success, data} by
  // core/renderers.py's EnvelopeJSONRenderer (global, applies to every
  // endpoint) — the frontend's own api client unwraps this transparently,
  // but a raw page.request call gets the envelope as-is.
  const customersRes = await page.request.get('/api/v1/customers/?page_size=200');
  expect(customersRes.ok(), await customersRes.text()).toBeTruthy();
  const customers = (await customersRes.json()).data.results as Array<{ id: number; name: string }>;
  const customerId = customers.find((c) => c.name === customerName)?.id;
  expect(customerId, 'could not find the just-created customer id').toBeTruthy();

  const productsRes = await page.request.get('/api/v1/products/?page_size=200');
  expect(productsRes.ok(), await productsRes.text()).toBeTruthy();
  const products = (await productsRes.json()).data.results as Array<{ id: number; name: string }>;
  const productId = products.find((p) => p.name === productName)?.id;
  expect(productId, 'could not find the just-created product id').toBeTruthy();

  const csrf = await getCsrfToken(page);
  const todayIso = new Date().toISOString().slice(0, 10);
  const createRes = await page.request.post('/api/v1/sales/invoices/', {
    headers: { 'X-CSRFToken': csrf },
    data: {
      customer: customerId,
      invoice_type: 'GST',
      invoice_date: todayIso,
      // F1-017: the real invoice number is auto-assigned by
      // DocumentNumberService at complete time (confirmed live:
      // "INV-2627-A1ZY-00001", nothing like the value sent here) — no point
      // sending one.
      // Malformed on purpose — bad checksum, same shape as this ticket's
      // own backend regression test fixture (BAD_CHECKSUM).
      filing_party_gstin: badGstin,
      items: [{ product: productId, quantity: '1', unit_price: '100' }],
    },
  });
  expect(createRes.ok(), await createRes.text()).toBeTruthy();
  const invoice = (await createRes.json()).data;

  const completeRes = await page.request.post(`/api/v1/sales/invoices/${invoice.id}/complete/`, {
    headers: { 'X-CSRFToken': csrf },
    data: { gst_guard_override_reason: 'Approved by owner for testing' },
  });
  expect(completeRes.ok(), await completeRes.text()).toBeTruthy();

  // B9-012 (backend/insights/attention.py): the raw feed is cached per
  // (company, as_of) for 60s with no invalidation on write — see the fuller
  // explanation in comp002-replenishment.spec.ts. Poll with reloads past the
  // TTL instead of a single fetch.
  const guardrailText = page.getByText(new RegExp(`buyer GSTIN '${badGstin}' fails format or checksum`)).first();
  await expect(async () => {
    await page.goto('/attention');
    await expect(guardrailText).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 75_000, intervals: [5_000] });
});

/**
 * COMP-006 follow-up: the write-time validator (backend/reporting/gst_guard.py
 * validate_document(), wired into SalesService.complete()) is a different
 * mechanism from the read-time buyer-GSTIN check above — it runs at
 * invoice-completion time, not on an already-completed document, and renders
 * its own inline panel on the invoice detail page (InvoiceDetailPage.tsx:
 * billing.gstGuardBlockingTitle / gstGuardOverrideReasonLabel /
 * gstGuardOverrideButton) with an OWNER/MANAGER override instead of the
 * Attention page.
 *
 * The simplest reliable blocking condition to arrange from the UI alone is
 * HSN_MISSING: a B2B line (a customer with a real GSTIN makes the sale B2B)
 * with no HSN code at all. This is distinct from HSN_NOT_IN_MASTER (an HSN
 * absent from the HsnRate master entirely — warning-only) and
 * HSN_RATE_DATE_INVALID (an HSN present in the master but outside its
 * effective-dated window — blocking, but requires seeding HsnRate rows with a
 * specific date range, not reachable through the product/customer UI used
 * here).
 *
 * NewInvoicePage's own "Save & Complete" swallows a failed completion into a
 * generic warning on the history list (draftSavedCompleteFailed) instead of
 * the inline panel — that panel only renders from InvoiceDetailPage's own
 * "Complete" action on an already-saved DRAFT, so this test saves as a draft
 * first (the "Save draft" button) and completes from the detail page.
 */
test('COMP-006: a missing HSN on a B2B invoice line blocks Complete until an OWNER override', async ({ page }) => {
  const id = unique();
  const companyName = `E2E GstGuardBlock ${id}`;
  const email = `e2e-gst-guard-block-${id}@example.test`;
  const productName = `No HSN Widget ${id}`;
  const sku = `NH-${id}`;
  const customerName = `B2B Customer ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!', gstin: '29AAAAA0000A1ZY' });
  // Deliberately no hsnCode — validate_document() blocks a blank HSN on a B2B line.
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '60' });
  // F1-017: /complete/ hard-blocks on insufficient stock (BLOCK policy).
  await addStockAdjustment(page, { sku, quantity: '10' });

  // A customer with a real, valid GSTIN is what makes this invoice B2B.
  await page.goto('/sales/customers');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(customerName);
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: 'Karnataka' }).click();
  await page.getByLabel('GSTIN').fill('29AABCU9603R1ZJ');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(customerName)).toBeVisible();

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  // Registering the company with a GSTIN above defaults its registration_type
  // to REGULAR, which is what makes the GST/Tax/Retail invoice-type options
  // available here — select GST explicitly rather than relying on the page's
  // own default, since GST Guard only runs when tax is enabled (invoice_type
  // != NON_GST — see SalesService.complete()'s tax_enabled gate).
  await page.getByRole('button', { name: 'Change bill type' }).click();
  await page.getByLabel('Invoice type').click();
  await page.getByRole('option', { name: /^GST invoice/i }).click();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });

  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) });
  await expect(invoiceRow).toBeVisible();
  // The invoice-number cell is the only link on the row (see
  // saveAndCompleteSalesInvoice's own comment on this) — it opens the
  // read-only detail view, InvoiceDetailPage, where the GST Guard panel and
  // its own "Complete" action live.
  await invoiceRow.getByRole('link').first().click();
  await expect(page).toHaveURL(/\/sales\/history\/\d+$/);

  const completeButton = page.getByRole('button', { name: 'Complete', exact: true });
  await expect(completeButton).toBeVisible();
  await completeButton.click();

  await expect(page.getByText('GST Guard blocked this invoice')).toBeVisible();
  await expect(page.getByText(/HSN code is required on a B2B invoice line/)).toBeVisible();
  // Still DRAFT — the blocked attempt must not have completed the invoice.
  await expect(completeButton).toBeVisible();

  // OWNER is the default role for the account that ran registerTenant.
  await page
    .getByLabel('Reason for override (required)')
    .fill('HSN pending catalog cleanup — approved by owner');
  await page.getByRole('button', { name: 'Override and complete' }).click();

  await expect(page.getByText('Invoice completed')).toBeVisible();
  // DRAFT-only "Complete" button is gone now that the invoice is COMPLETED.
  await expect(completeButton).toHaveCount(0);
});
