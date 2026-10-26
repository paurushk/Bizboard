import { expect, test, type Page } from '@playwright/test';
import {
  addStockAdjustment,
  createCustomer,
  createProduct,
  getCsrfToken,
  posCompleteCashSale,
  registerTenant,
  unique,
} from './helpers/documents';
import { grantRolloutFlag } from './helpers/grantFlag';

/**
 * Stabilization WP-6: the lead-pilot journeys in qos/journeys.yaml (ARCH-01, ARCH-03) that had
 * backend coverage but no live-browser walk. Each test names its journey id. Live Django, no mocks.
 */

async function freshTenant(page: Page, tag: string) {
  const id = unique();
  const email = `e2e-${tag.toLowerCase()}-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E ${tag} ${id}`, email, password: 'GoldenPath123!' });
  return { id, email };
}

async function idByName(page: Page, path: string, name: string): Promise<number> {
  const res = await page.request.get(`${path}?page_size=200`);
  expect(res.ok(), await res.text()).toBeTruthy();
  const rows = (await res.json()).data.results as Array<{ id: number; name: string }>;
  const id = rows.find((r) => r.name === name)?.id;
  expect(id, `no ${path} row named ${name}`).toBeTruthy();
  return id as number;
}

function rupees(text: string): number {
  return Number(text.replace(/[^0-9.-]/g, ''));
}

test('J-RETAIL-P1-DAYCLOSE + J-RETAIL-P2-THERMAL: open till, sell with no printer, count notes, close till', async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { id } = await freshTenant(page, 'DAY');
  const sku = `DAY-${id}`;
  await createProduct(page, { name: `Day Widget ${id}`, sku, sellingPrice: '100', purchasePrice: '80' });
  await addStockAdjustment(page, { sku, quantity: '5' });

  await page.goto('/pos');
  const itemInput = page.getByPlaceholder('Scan barcode or search product name / SKU');
  await expect(itemInput).toBeVisible({ timeout: 20_000 });
  const openTill = page.getByRole('button', { name: 'Open till' });
  if (await openTill.isVisible().catch(() => false)) {
    await page.getByLabel('Opening float').fill('500');
    await openTill.click();
  }
  await itemInput.click();
  await itemInput.fill(sku);
  await page.getByText(new RegExp(sku)).click();
  // No thermal printer is attached in CI: the sale must still complete (the slip is a PDF).
  await posCompleteCashSale(page);
  await expect(page.getByText(/thermal print failed/i)).toHaveCount(0);

  // The till's expected cash must include the sale (opening float 500 + the cash taken).
  const expectedLine = page.getByText(/^Expected cash ₹/).first();
  let expected = 0;
  await expect(async () => {
    await page.reload();
    await expect(expectedLine).toBeVisible({ timeout: 10_000 });
    expected = rupees((await expectedLine.textContent()) ?? '');
    expect(expected).toBeGreaterThan(500);
  }).toPass({ timeout: 45_000, intervals: [3_000] });

  // Count one ₹500 note short of the drawer, so the variance is visible and exact.
  await page.getByLabel('Note count 500').fill('1');
  await page.getByRole('button', { name: 'Close till' }).click();
  // The closed till reads "Expected cash ₹X · Counted ₹500.00 · Variance -₹Y".
  const summary = page.getByText(/Counted ₹[\d,.]+ · Variance/).first();
  await expect(summary).toBeVisible({ timeout: 15_000 });
  const text = (await summary.textContent()) ?? '';
  expect(rupees(text.split('Counted')[1].split('·')[0])).toBe(500);
  const variance = rupees(text.split('Variance')[1].replace('₹', ''));
  expect(variance).toBeCloseTo(500 - expected, 2);
});

test('J-TRADE-P3-CREDITBLOCK: an invoice over the customer credit limit is refused with the reason', async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { id } = await freshTenant(page, 'CRB');
  const customerName = `Credit Buyer ${id}`;
  const productName = `Credit Widget ${id}`;
  await createProduct(page, { name: productName, sku: `CRB-${id}`, sellingPrice: '1000', purchasePrice: '800' });
  await addStockAdjustment(page, { sku: `CRB-${id}`, quantity: '5' });
  await createCustomer(page, { name: customerName });
  const customer = await idByName(page, '/api/v1/customers/', customerName);
  const product = await idByName(page, '/api/v1/products/', productName);
  const csrf = await getCsrfToken(page);

  const limit = await page.request.patch(`/api/v1/customers/${customer}/`, {
    headers: { 'X-CSRFToken': csrf },
    data: { credit_limit: '100.00', credit_limit_action: 'BLOCK' },
  });
  expect(limit.ok(), await limit.text()).toBeTruthy();
  const draft = await page.request.post('/api/v1/sales/invoices/', {
    headers: { 'X-CSRFToken': csrf },
    data: {
      customer,
      invoice_type: 'GST',
      invoice_date: new Date().toLocaleDateString('en-CA'),
      items: [{ product, quantity: '1', unit_price: '1000' }],
    },
  });
  expect(draft.ok(), await draft.text()).toBeTruthy();
  const invoiceId = (await draft.json()).data.id as number;

  await page.goto(`/sales/history/${invoiceId}`);
  await page.getByRole('button', { name: 'Complete', exact: true }).click();
  const confirm = page.getByRole('dialog').getByRole('button', { name: /^(Complete|Confirm|Yes)/ });
  if (await confirm.first().isVisible({ timeout: 3_000 }).catch(() => false)) await confirm.first().click();
  // The salesperson sees why, in words, and the invoice stays a draft (nothing half-posted).
  await expect(page.getByText(/credit limit/i).first()).toBeVisible({ timeout: 15_000 });
  const after = await page.request.get(`/api/v1/sales/invoices/${invoiceId}/`);
  expect((await after.json()).data.status).toBe('DRAFT');
});

test('J-TRADE-P5-MONTHEND: close-the-month checklist opens and GSTR-1 downloads', async ({ page }) => {
  test.setTimeout(150_000);
  const { email } = await freshTenant(page, 'MEND');
  // GSTR returns are a module granted per company (ENABLE_GSTR); a pilot doing month end has it.
  grantRolloutFlag(email, 'ENABLE_GSTR');
  await page.goto('/reports/close-month');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('body')).not.toContainText(/something went wrong/i);

  await page.goto('/reports/gstr1');
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 20_000 });
  const download = page.waitForEvent('download', { timeout: 30_000 });
  await page.getByRole('button', { name: /JSON|Download|Export/i }).first().click();
  expect((await download).suggestedFilename()).toMatch(/\.(json|xlsx|csv|zip)$/i);
});

test('J-TRADE-P5-TCS: the TDS / TCS worksheet opens with its TCS side', async ({ page }) => {
  test.setTimeout(120_000);
  await freshTenant(page, 'TCS');
  await page.goto('/reports/tds-tcs');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('body')).not.toContainText(/something went wrong/i);
  await expect(page.getByText(/TCS/).first()).toBeVisible();
});

test('J-TRADE-P5-DUNNING: reminder days are saved and an overdue invoice is on the collections list', async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { id } = await freshTenant(page, 'DUN');
  const customerName = `Late Payer ${id}`;
  const productName = `Dun Widget ${id}`;
  await createProduct(page, { name: productName, sku: `DUN-${id}`, sellingPrice: '500', purchasePrice: '400' });
  await addStockAdjustment(page, { sku: `DUN-${id}`, quantity: '5' });
  await createCustomer(page, { name: customerName });

  await page.goto('/settings/money-in');
  const days = page.getByLabel('Reminder days after due date');
  await expect(days).toBeVisible({ timeout: 20_000 });
  await days.fill('3, 7, 14');
  // One Save per section; the other sections' Save stays disabled until they change.
  await page.locator('button:enabled', { hasText: /^Save$/ }).first().click();
  await expect(page.getByText(/saved/i).first()).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByLabel('Reminder days after due date')).toHaveValue(/3,\s*7,\s*14/);

  const customer = await idByName(page, '/api/v1/customers/', customerName);
  const product = await idByName(page, '/api/v1/products/', productName);
  const csrf = await getCsrfToken(page);
  const past = new Date(Date.now() - 20 * 86_400_000).toLocaleDateString('en-CA');
  const draft = await page.request.post('/api/v1/sales/invoices/', {
    headers: { 'X-CSRFToken': csrf },
    data: {
      customer,
      invoice_type: 'GST',
      invoice_date: past,
      due_date: past,
      items: [{ product, quantity: '1', unit_price: '500' }],
    },
  });
  expect(draft.ok(), await draft.text()).toBeTruthy();
  const done = await page.request.post(`/api/v1/sales/invoices/${(await draft.json()).data.id}/complete/`, {
    headers: { 'X-CSRFToken': csrf },
    data: {},
  });
  expect(done.ok(), await done.text()).toBeTruthy();

  await page.goto('/payments/collections');
  await expect(page.getByText(customerName).first()).toBeVisible({ timeout: 20_000 });
});

test('J-TRADE-P5-BANKREC: a statement line is matched to its receipt on the reconciliation screen', async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { id } = await freshTenant(page, 'BREC');
  const customerName = `Bank Payer ${id}`;
  await createCustomer(page, { name: customerName });
  const customer = await idByName(page, '/api/v1/customers/', customerName);
  const csrf = await getCsrfToken(page);
  const headers = { 'X-CSRFToken': csrf };

  const bank = await page.request.post('/api/v1/payments/bank-accounts/', {
    headers,
    data: { name: `HDFC ${id}`, account_type: 'CURRENT', is_default: true },
  });
  expect(bank.ok(), await bank.text()).toBeTruthy();
  const bankId = (await bank.json()).data.id as number;
  const utr = `UTR${id.replace(/\D/g, '').slice(-10)}`;
  const today = new Date();
  const receipt = await page.request.post('/api/v1/payments/receipts/', {
    headers: { ...headers, 'Idempotency-Key': `e2e-brec-${id}` },
    data: {
      customer, amount: '2500.00', mode: 'UPI', utr, bank_account: bankId,
      receipt_date: today.toLocaleDateString('en-CA'),
    },
  });
  expect(receipt.ok(), await receipt.text()).toBeTruthy();

  const dd = String(today.getDate()).padStart(2, '0');
  const mm = String(today.getMonth() + 1).padStart(2, '0');
  const csv = `Date,Credit,Debit,Narration,Ref No\n${dd}/${mm}/${today.getFullYear()},2500,,PAYMENT FROM ${utr},${utr}\n`;
  const upload = await page.request.post('/api/v1/payments/statements/upload/', {
    headers,
    multipart: {
      bank_account: String(bankId),
      preset: 'generic',
      file: { name: 'statement.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) },
    },
  });
  expect(upload.ok(), await upload.text()).toBeTruthy();
  const commit = await page.request.post(`/api/v1/payments/statements/${(await upload.json()).data.id}/commit/`, {
    headers,
  });
  expect(commit.ok(), await commit.text()).toBeTruthy();

  // The bookkeeper confirms the suggested match on screen.
  await page.goto('/payments/reconciliation');
  const line = page.getByText(`PAYMENT FROM ${utr} · UTR ${utr}`);
  await expect(line).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(new RegExp(`receipt RCT-.* · ${customerName} · ₹2,500[.]00`))).toBeVisible();
  await page.getByRole('button', { name: 'Confirm', exact: true }).first().click();
  // Matched lines leave the unmatched queue, and the API agrees.
  await expect(line).toHaveCount(0, { timeout: 15_000 });
  const open = await page.request.get('/api/v1/payments/recon/');
  expect(open.ok()).toBeTruthy();
  expect(JSON.stringify(await open.json())).not.toContain(utr);
});
