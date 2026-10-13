import { expect, test, type Page } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  completePurchaseInvoice,
  createCustomer,
  createProduct,
  createSupplier,
  fillNamedCombobox,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * Sales and purchase returns against the live backend (no mocks): save a draft, resume
 * it, complete it, return the rest (the bill flips to Returned), cancel one (it reopens),
 * and check the server's own headroom after each step.
 *
 * Requires: backend migrated. Run with: npm run test:e2e:golden
 */

async function apiJson(page: Page, path: string) {
  const res = await page.request.get(path);
  expect(res.ok(), `${path} -> ${res.status()}`).toBeTruthy();
  const body = await res.json();
  return body?.data ?? body;
}

test('golden: sales return lifecycle (draft, resume, complete, return the rest, cancel)', async ({ page }) => {
  test.setTimeout(300_000);
  const id = unique();
  const sku = `RG-${id}`;
  const productName = `Return Widget ${id}`;
  const customerName = `Return Customer ${id}`;

  await registerTenant(page, {
    companyName: `E2E Returns ${id}`,
    email: `e2e-returns-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80', gstRate: '0' });
  await addStockAdjustment(page, { sku, quantity: '50' });
  await createCustomer(page, { name: customerName });

  // A completed invoice for 5 units.
  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  await page.getByRole('row', { name: new RegExp(productName) }).getByLabel('QTY').fill('5');
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  // The invoice, as the server has it (polling until it is completed).
  let invoice: { id: number; number: string; status: string } | undefined;
  await expect
    .poll(
      async () => {
        const list = await apiJson(page, '/api/v1/sales/invoices/?status=COMPLETED');
        invoice = (list.results ?? list)[0];
        return invoice?.status;
      },
      { timeout: 30_000 },
    )
    .toBe('COMPLETED');
  const invoiceNumber = invoice!.number;
  const invoiceId = String(invoice!.id);
  expect(invoiceNumber).toMatch(/^INV-/);

  // First return: 2 of 5. Save as a draft, resume it, then complete it.
  await page.goto(`/sales/returns?create=1&invoice=${invoiceId}`);
  const dialog = page.getByRole('dialog', { name: /new sales return/i });
  await expect(dialog.getByRole('combobox', { name: /original invoice/i })).toHaveValue(new RegExp(invoiceNumber), {
    timeout: 20_000,
  });
  await dialog.getByRole('checkbox').first().check();
  await dialog.getByRole('spinbutton', { name: /qty/i }).fill('2');
  const preview = dialog.getByTestId('return-preview');
  await expect(preview).toContainText('₹200.00', { timeout: 15_000 });
  await expect(preview).toContainText(/exact figures/i);
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Sales return draft saved')).toBeVisible({ timeout: 20_000 });

  const draftRow = page.getByRole('row').filter({ hasText: 'Draft' }).first();
  await expect(draftRow).toContainText(invoiceNumber);
  await draftRow.getByRole('button', { name: 'Edit' }).click();
  const editDialog = page.getByRole('dialog', { name: /edit sales return draft/i });
  await expect(editDialog).toBeVisible();
  await expect(editDialog.getByRole('spinbutton', { name: /qty/i })).toHaveValue('2');
  await editDialog.getByRole('button', { name: 'Complete', exact: true }).click();
  await expect(page.getByText('Sales return completed')).toBeVisible({ timeout: 20_000 });

  const doneRow = page.getByRole('row').filter({ hasText: 'Completed' }).first();
  await expect(doneRow).toContainText(/SRN-/);
  await expect(doneRow.getByRole('link', { name: /SCN-/ })).toBeVisible();

  let lines = await apiJson(page, `/api/v1/sales/invoices/${invoiceId}/returnable-lines/`);
  expect(Number(lines[0].returned)).toBe(2);
  expect(Number(lines[0].returnable)).toBe(3);
  expect((await apiJson(page, `/api/v1/sales/invoices/${invoiceId}/`)).status).toBe('COMPLETED');

  // The rest (3): nothing is left, so the bill becomes Returned.
  await page.getByRole('button', { name: 'New sales return' }).first().click();
  const second = page.getByRole('dialog', { name: /new sales return/i });
  await fillNamedCombobox(page, 'Original invoice', invoiceNumber, new RegExp(invoiceNumber));
  await second.getByRole('checkbox').first().check();
  const qty = second.getByRole('spinbutton', { name: /qty/i });
  await expect(qty).toHaveAttribute('max', '3');
  await qty.fill('3');
  await second.getByRole('button', { name: 'Complete', exact: true }).click();
  await expect
    .poll(async () => (await apiJson(page, `/api/v1/sales/invoices/${invoiceId}/`)).status, { timeout: 30_000 })
    .toBe('RETURNED');

  // Cancelling that second return puts the 3 units back on the bill and reopens it.
  // The 3-unit return is the one worth ₹300.00 (the first was 2 units, ₹200.00).
  await page
    .getByRole('row')
    .filter({ hasText: '₹300.00' })
    .getByRole('button', { name: 'Cancel return' })
    .click();
  const cancelDialog = page.getByRole('dialog', { name: /cancel document/i });
  await cancelDialog.getByRole('button', { name: 'Cancel return' }).click();
  await expect(page.getByText('Sales return cancelled')).toBeVisible({ timeout: 20_000 });
  await expect
    .poll(async () => (await apiJson(page, `/api/v1/sales/invoices/${invoiceId}/`)).status, { timeout: 30_000 })
    .toBe('COMPLETED');
  lines = await apiJson(page, `/api/v1/sales/invoices/${invoiceId}/returnable-lines/`);
  expect(Number(lines[0].returnable)).toBe(3);
});

test('golden: purchase return lifecycle (preview, complete, credit note, cancel)', async ({ page }) => {
  test.setTimeout(300_000);
  const id = unique();
  const sku = `RP-${id}`;
  const productName = `Return Part ${id}`;
  const supplierName = `Return Supplier ${id}`;

  await registerTenant(page, {
    companyName: `E2E Purchase Returns ${id}`,
    email: `e2e-preturns-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { name: productName, sku, sellingPrice: '100', purchasePrice: '80', gstRate: '0' });
  await createSupplier(page, { name: supplierName });
  await completePurchaseInvoice(page, { supplierName, sku, productName, quantity: '5', unitPrice: '80' });

  const billRow = page.getByRole('row', { name: new RegExp(supplierName) });
  const purchaseNumber = (await billRow.locator('td').nth(1).textContent())?.trim();
  expect(purchaseNumber).toBeTruthy();

  await page.goto('/purchases/returns');
  await page.getByRole('button', { name: 'New purchase return' }).first().click();
  const dialog = page.getByRole('dialog', { name: /new purchase return/i });
  await fillNamedCombobox(page, 'Original purchase', purchaseNumber!, new RegExp(purchaseNumber!));
  await dialog.getByRole('checkbox').first().check();
  const qty = dialog.getByRole('spinbutton', { name: /qty/i });
  await expect(qty).toHaveAttribute('max', '5');
  await qty.fill('2');
  await expect(dialog.getByTestId('return-preview')).toContainText('₹160.00', { timeout: 15_000 });
  await dialog.getByRole('button', { name: 'Complete', exact: true }).click();
  await expect(page.getByText('Purchase return completed')).toBeVisible({ timeout: 20_000 });

  const row = page.getByRole('row').filter({ hasText: 'Completed' }).first();
  await expect(row.getByRole('link', { name: /PCN-/ })).toBeVisible();
  const billHref = await row.getByRole('link', { name: purchaseNumber! }).getAttribute('href');
  const billId = billHref!.split('/').pop()!;
  let lines = await apiJson(page, `/api/v1/purchases/invoices/${billId}/returnable-lines/`);
  expect(Number(lines[0].returned)).toBe(2);
  expect(Number(lines[0].returnable)).toBe(3);

  await row.getByRole('button', { name: 'Cancel return' }).click();
  await page.getByRole('dialog', { name: /cancel document/i }).getByRole('button', { name: 'Cancel return' }).click();
  await expect(page.getByText('Purchase return cancelled')).toBeVisible({ timeout: 20_000 });
  lines = await apiJson(page, `/api/v1/purchases/invoices/${billId}/returnable-lines/`);
  expect(Number(lines[0].returnable)).toBe(5);
});
