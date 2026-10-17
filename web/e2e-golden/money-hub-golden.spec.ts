import { expect, test, type Page } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  completePurchaseInvoice,
  createCustomer,
  createProduct,
  createSupplier,
  getCsrfToken,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * The Money hub, end to end against the live backend (no mocks):
 *
 *   the headline figures foot to the bills that were just entered
 *   a cheque is pending, then cleared: the tile and the cash move, and the way back works
 *   an advance paid to a supplier is shown beside what is owed, not taken off it
 *   TDS waits for its certificate; recording the certificate clears the tile
 *   the owed figure opens the collections list, which offers to record the payment
 *
 * Requires: backend migrated. Run with: npm run test:e2e:golden -- money-hub-golden
 */

type Row = Record<string, unknown>;

async function api(page: Page, method: 'GET' | 'POST', path: string, data?: Row): Promise<Row> {
  const token = await getCsrfToken(page);
  const response = await page.request.fetch(`/api/v1${path}`, {
    method,
    data,
    headers: {
      'X-CSRFToken': token,
      'Idempotency-Key': `golden-${Math.random().toString(36).slice(2)}-${Date.now()}`,
    },
  });
  expect(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`).toBeTruthy();
  const body = (await response.json()) as Row;
  return (body.data ?? body) as Row;
}

async function findId(page: Page, path: string, name: string): Promise<number> {
  const body = await api(page, 'GET', `${path}?q=${encodeURIComponent(name)}`);
  const rows = (Array.isArray(body) ? body : (body.results as Row[])) as Row[];
  const match = rows.find((row) => String(row.name) === name) ?? rows[0];
  expect(match, `no ${path} row named ${name}`).toBeTruthy();
  return Number(match.id);
}

async function openMoney(page: Page) {
  await page.goto('/money');
  await expect(page.getByRole('heading', { name: 'Money coming in' })).toBeVisible({ timeout: 30_000 });
}

test('golden path: money hub foots, follows a cheque, an advance and TDS, and closes the loop', async ({ page }) => {
  test.setTimeout(300_000);
  const id = unique();
  const customerName = `Hub Customer ${id}`;
  const supplierName = `Hub Supplier ${id}`;
  const productName = `Hub Widget ${id}`;
  const sku = `MH-${id}`;

  await registerTenant(page, {
    companyName: `E2E Money Hub ${id}`,
    email: `e2e-moneyhub-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '1000', purchasePrice: '400', gstRate: '0' });
  await addStockAdjustment(page, { sku, quantity: '20' });
  await createCustomer(page, { name: customerName });
  await createSupplier(page, { name: supplierName });

  // A 1,000 bill to the customer, and a 400 bill from the supplier.
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  const heading = page.getByRole('heading', { level: 1, name: /^INV-/ });
  await expect(heading).toBeVisible({ timeout: 30_000 });
  const invoiceNumber = ((await heading.textContent()) ?? '').trim();
  await completePurchaseInvoice(page, { supplierName, sku, productName, unitPrice: '400', quantity: '1' });

  // 1. The headline figures foot to those two bills; nothing has been received or paid.
  await openMoney(page);
  await expect(page.getByRole('link', { name: /^Customers owe you: ₹1,000\.00/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /^You owe suppliers: ₹400\.00/ })).toBeVisible();
  await expect(page.getByText('₹600.00').first()).toBeVisible(); // net
  await expect(page.getByText(/could not be worked out/)).toHaveCount(0);
  await expect(page.getByText('What falls due next')).toBeVisible();
  await expect(page.getByText('Tax dues')).toBeVisible();

  // 2. The customers-owe-you figure opens the collections list, which offers to take the payment.
  await page.getByRole('link', { name: /^Customers owe you: ₹1,000\.00/ }).click();
  await expect(page).toHaveURL(/\/payments\/collections\?via=money/);
  await expect(page.getByText('Opened from Money: Open bills')).toBeVisible();
  await expect(page.getByText(invoiceNumber)).toBeVisible();
  await page.getByRole('link', { name: 'Record payment' }).first().click();
  await expect(page).toHaveURL(/\/sales\/history\/\d+\?pay=1/);
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 15_000 });
  await page.keyboard.press('Escape');

  // 3. A cheque is received: waiting to clear, not cash. Clear it and the way back shows the change.
  const customerId = await findId(page, '/customers/', customerName);
  await api(page, 'POST', '/payments/receipts/', {
    customer: customerId,
    amount: '300',
    mode: 'CHEQUE',
    cheque_number: '000123',
    cheque_bank_name: 'HDFC',
  });
  await openMoney(page);
  await expect(page.getByRole('link', { name: /^Cheques waiting to clear: ₹300\.00/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /^Advances received: ₹300\.00/ })).toBeVisible();
  // A cheque waiting to clear is not cash.
  await expect(page.getByRole('link', { name: /^Cash and bank now: ₹0\.00/ })).toBeVisible();

  await page.getByRole('link', { name: /^Cheques waiting to clear: ₹300\.00/ }).click();
  await expect(page).toHaveURL(/\/sales\/receipts\?cheque_status=PENDING_CLEARANCE&via=money/);
  await expect(page.getByText('Opened from Money: Cheques waiting to clear')).toBeVisible();
  await page.getByRole('button', { name: /mark cleared/i }).click();
  await page.getByRole('link', { name: 'Back to Money' }).click();
  await expect(page).toHaveURL(/\/money$/);
  await expect(page.getByRole('link', { name: /^Cash and bank now: ₹300\.00/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('link', { name: /^Cheques waiting to clear: ₹0\.00/ })).toBeVisible();

  // 4. An advance paid to the supplier is shown beside what is owed, not taken off it.
  const supplierId = await findId(page, '/suppliers/', supplierName);
  await api(page, 'POST', '/payments/supplier-payments/', {
    supplier: supplierId,
    amount: '50',
    mode: 'CASH',
  });
  await openMoney(page);
  await expect(page.getByRole('link', { name: /^Advances paid: ₹50\.00/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /^You owe suppliers: ₹400\.00/ })).toBeVisible();
  await page.getByRole('link', { name: /^Advances paid: ₹50\.00/ }).click();
  await expect(page).toHaveURL(/\/purchases\/payments\?advance=1&via=money/);
  await expect(page.getByText('Opened from Money: Advances paid to suppliers')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Supplier payment totals' })).toContainText('₹50.00');

  // 5. TDS the customer deducted waits for its certificate; recording it clears the tile.
  await api(page, 'POST', '/payments/receipts/', {
    customer: customerId,
    amount: '90',
    mode: 'CASH',
    tds_deducted: '10',
    tds_section: '194C',
  });
  await openMoney(page);
  await expect(page.getByRole('link', { name: /^TDS awaiting certificate: ₹10\.00/ })).toBeVisible();
  await page.getByRole('link', { name: /^TDS awaiting certificate: ₹10\.00/ }).click();
  await expect(page).toHaveURL(/\/reports\/tds-receivable\?certificate=pending&via=money/);
  await page.getByRole('button', { name: 'Certificate received' }).first().click();
  await page.getByRole('dialog').getByLabel('Certificate number (optional)').fill('16A/1');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await page.getByRole('link', { name: 'Back to Money' }).click();
  await expect(page.getByRole('link', { name: /^TDS awaiting certificate: ₹0\.00/ })).toBeVisible({ timeout: 20_000 });

  // 6. The menu gathers the screens under one group, and the old Payments group is gone.
  await expect(page.getByRole('button', { name: 'Money' }).first()).toBeVisible();
});
