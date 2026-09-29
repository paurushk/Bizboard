import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  completePurchaseInvoice,
  createProduct,
  createSupplier,
  registerTenant,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * COMP-007: supplier price history. A real end-to-end run against the live
 * backend — two purchase invoices for the same supplier+product at
 * different prices, then the price-history dialog on the Suppliers page
 * shows both, in date order, with no score/rank/reliability UI element.
 *
 * Requires: backend migrated, ENABLE_SUPPLIER_PRICE_HISTORY=1 (set by
 * playwright.golden.config.ts). Run with: npm run test:e2e:golden
 */

test('COMP-007: price-history dialog shows a real price jump across two purchases', async ({ page }) => {
  const id = unique();
  const companyName = `E2E PriceHistory ${id}`;
  const email = `e2e-price-history-${id}@example.test`;
  const productName = `Price Widget ${id}`;
  const sku = `PH-${id}`;
  const supplierName = `Price Supplier ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku, sellingPrice: '50', purchasePrice: '10' });
  await createSupplier(page, { name: supplierName });

  await completePurchaseInvoice(page, { supplierName, sku, productName, unitPrice: '10', quantity: '1' });
  await completePurchaseInvoice(page, { supplierName, sku, productName, unitPrice: '14', quantity: '1' });

  await page.goto('/purchases/suppliers');
  const supplierRow = page.getByRole('row', { name: new RegExp(supplierName) });
  await supplierRow.getByRole('button', { name: 'Price history' }).click();
  await expect(page.getByRole('heading', { name: new RegExp(`Price history — ${supplierName}`) })).toBeVisible();

  // F1-016/F1-017: getByLabel('Product') (non-exact) also matches the global
  // search bar's aria-label ("Search invoices, customers, products…"), and
  // once opened, the option listbox is *also* labelled "Product" (via
  // aria-labelledby) — exact:true alone still resolves to 2 elements, so
  // this must be scoped to the combobox role specifically.
  const productCombo = page.getByRole('combobox', { name: 'Product', exact: true });
  await productCombo.click();
  await productCombo.fill(productName);
  await page.getByRole('option', { name: new RegExp(productName) }).click();

  await expect(page.getByText('₹10.00')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('₹14.00')).toBeVisible();
  for (const banned of [/score/i, /\brank\b/i, /reliab/i]) {
    await expect(page.getByText(banned)).toHaveCount(0);
  }
});

/**
 * COMP-007 follow-up: the price-history *dialog* above is a passive report.
 * NewPurchasePage.tsx also reads the same history live while composing a new
 * bill and shows an inline, non-blocking "price-jump note" under the rate
 * field (DraftLineTable.tsx's renderPriceHint) whenever the entered rate is
 * strictly higher than the last PURCHASE_INVOICE rate for that supplier+
 * product — never for an equal or lower rate (see NewPurchasePage.tsx's
 * priceJumpNote(): `Number(line.unitPrice) > Number(lastRate)`).
 *
 * The note text is literally `last bill was ₹{rate} on {date}` (see
 * NewPurchasePage.priceJumpNote.test.tsx for the exact format), where `date`
 * is the prior invoice's own invoice_date — NewPurchasePage.tsx defaults a
 * new purchase's own date to the *local* today (lineHelpers.ts's todayIso(),
 * not UTC), so this test mirrors that exact computation rather than
 * `Date#toISOString()` to avoid a timezone-boundary mismatch.
 */
function localTodayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

test('COMP-007: a higher rate than history shows a price-jump note; equal or lower shows none', async ({ page }) => {
  const id = unique();
  const companyName = `E2E PriceJump ${id}`;
  const email = `e2e-price-jump-${id}@example.test`;
  const productName = `Jump Widget ${id}`;
  const sku = `PJ-${id}`;
  const supplierName = `Jump Supplier ${id}`;
  const todayIso = localTodayIso();

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: productName, sku, sellingPrice: '50', purchasePrice: '10' });
  await createSupplier(page, { name: supplierName });

  // One COMPLETED purchase at ₹10 — the history the note reads.
  await completePurchaseInvoice(page, { supplierName, sku, productName, unitPrice: '10', quantity: '1' });

  await page.goto('/purchases/new');
  await selectPartyOnDocument(page, supplierName);
  await addInvoiceItem(page, sku);
  const row = page.getByRole('row', { name: new RegExp(productName) });
  // See helpers/documents.ts's completePurchaseInvoice comment: the row's
  // real <input> order is [0] Quantity, [1] Unit price, [2] Discount %.
  const unitPriceInput = row.locator('input').nth(1);

  // Higher than the ₹10.00 history -> the note appears with the prior rate/date.
  await unitPriceInput.fill('15');
  await expect(page.getByText(`last bill was ₹10.00 on ${todayIso}`)).toBeVisible({ timeout: 15_000 });

  // Equal to history -> no note (a jump note is about paying MORE, not the same).
  await unitPriceInput.fill('10');
  await expect(page.getByText(/last bill was/)).toHaveCount(0);

  // Lower than history -> no note either.
  await unitPriceInput.fill('8');
  await expect(page.getByText(/last bill was/)).toHaveCount(0);
});
