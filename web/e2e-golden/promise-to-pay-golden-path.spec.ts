import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  getCsrfToken,
  registerTenant,
  saveAndCompleteSalesInvoice,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * Promise-to-pay (backend/payments/promise_to_pay.py: create_promise /
 * list_open_promises / resolve_promise, exposed as PaymentPromiseViewSet in
 * backend/payments/views.py at POST/GET /api/v1/payments/promises/ and
 * POST /api/v1/payments/promises/{id}/resolve/).
 *
 * IMPORTANT FINDING, confirmed before writing this spec: there is currently
 * NO frontend UI anywhere in web/src for creating or listing payment
 * promises. Grepping web/src for "promise" / "PaymentPromise" /
 * "payments/promises" turns up nothing outside the generated
 * web/src/api/openapi-types.ts — no page, no component, no api/resources.ts
 * wrapper. Neither CollectionsWorklistPage.tsx nor any page under
 * web/src/pages/insights/ has a promise-to-pay entry point, and
 * Customer360Page.tsx (the obvious place for it) doesn't reference it
 * either. This is a real product gap this task exists to surface, not
 * something to paper over: today, a staff member has no in-app way to
 * record a promise-to-pay — only direct API access (or a future admin tool)
 * can create one.
 *
 * Given that, this spec follows the suite's established hybrid pattern for
 * exactly this situation (see comp006-gst-guard.spec.ts, which arranges a
 * malformed GSTIN the same way because no UI path can produce one either):
 * create the promise via a direct, authenticated API call using the same
 * session/cookie the page already has, then prove the READ side that IS
 * wired up — the Attention feed (backend/insights/attention.py's
 * `_promise_to_pay_rows`, unconditionally included in `_build_raw_rows`,
 * gated by no feature flag) actually renders it with the exact title text
 * the builder produces ("{customer} promised to pay today") — plus a direct
 * check that the list-open-promises endpoint itself reflects the new row.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('promise-to-pay: created via API (no UI exists yet), surfaces on the Attention feed as due today', async ({
  page,
}) => {
  // The Attention-feed assertion below deliberately waits out a real 60s
  // server-side cache TTL on top of the normal setup steps (same B9-012
  // caveat as comp006-gst-guard.spec.ts).
  test.setTimeout(150_000);
  const id = unique();
  const companyName = `E2E Promise ${id}`;
  const email = `e2e-promise-${id}@example.test`;
  const productName = `Promise Widget ${id}`;
  const sku = `PP-${id}`;
  const customerName = `Promise Customer ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '10' });
  await createCustomer(page, { name: customerName });

  // Raise and complete a sales invoice, left unpaid, so the promise below is
  // against a customer with a real outstanding balance.
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await saveAndCompleteSalesInvoice(page, new RegExp(customerName));
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) }).first();
  const textCells = await invoiceRow.locator('td').allTextContents();
  const invoiceNumber = textCells.map((c) => c.trim()).find((c) => /^INV-/.test(c));
  expect(invoiceNumber).toMatch(/^INV-/);

  // Look up the customer/invoice ids via the same authenticated session the
  // browser is already using (cookie auth) — no UI path exposes them
  // directly, same F1-017 pattern as comp006-gst-guard.spec.ts.
  const customersRes = await page.request.get('/api/v1/customers/?page_size=200');
  expect(customersRes.ok(), await customersRes.text()).toBeTruthy();
  const customers = (await customersRes.json()).data.results as Array<{ id: number; name: string }>;
  const customerId = customers.find((c) => c.name === customerName)?.id;
  expect(customerId, 'could not find the just-created customer id').toBeTruthy();

  const invoicesRes = await page.request.get('/api/v1/sales/invoices/?page_size=200');
  expect(invoicesRes.ok(), await invoicesRes.text()).toBeTruthy();
  const invoices = (await invoicesRes.json()).data.results as Array<{ id: number; number: string }>;
  const invoiceId = invoices.find((inv) => inv.number === invoiceNumber)?.id;
  expect(invoiceId, 'could not find the just-created invoice id').toBeTruthy();

  // Create the promise-to-pay for TODAY — the only way one can be created
  // right now, since no UI exists (see the file-header finding above).
  const csrf = await getCsrfToken(page);
  const todayIso = new Date().toISOString().slice(0, 10);
  const note = `Promised over phone call, ${id}`;
  const createRes = await page.request.post('/api/v1/payments/promises/', {
    headers: { 'X-CSRFToken': csrf },
    data: {
      customer: customerId,
      invoice: invoiceId,
      promised_date: todayIso,
      note,
    },
  });
  expect(createRes.ok(), await createRes.text()).toBeTruthy();
  const promise = (await createRes.json()).data;
  expect(promise.resolved).toBe(false);

  // (a) The read-only list-open-promises endpoint reflects it — the closest
  // thing to a "list view" this feature currently has (no frontend consumes
  // it yet).
  const listRes = await page.request.get('/api/v1/payments/promises/');
  expect(listRes.ok(), await listRes.text()).toBeTruthy();
  const openPromises = (await listRes.json()).data.results as Array<{ id: number; customer: number }>;
  expect(openPromises.some((p) => p.id === promise.id && p.customer === customerId)).toBe(true);

  // (b) It appears on the Attention feed as "{customer} promised to pay
  // today" — the exact title backend/insights/attention.py's
  // `_promise_to_pay_rows` builds. The raw feed is cached per
  // (company, as_of) for 60s with no invalidation on write; poll with
  // reloads past the TTL instead of a single fetch.
  const promiseRowText = page.getByText(new RegExp(`${customerName} promised to pay today`)).first();
  await expect(async () => {
    await page.goto('/attention');
    await expect(promiseRowText).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 75_000, intervals: [5_000] });
});
