import { expect, test } from '@playwright/test';
import { addStockAdjustment, createProduct, getCsrfToken, registerTenant, unique } from './helpers/documents';

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
