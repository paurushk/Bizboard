import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  createCustomer,
  createProduct,
  registerTenant,
  saveAndCompleteSalesInvoice,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

/**
 * COMP-002: replenishment suggestion. A real end-to-end run against the live
 * backend — register a tenant, give a product a reorder level, sell enough
 * of it to drop below that level, and confirm the resulting Attention row
 * carries a computed suggested purchase quantity (not just the pre-existing
 * bare "below reorder" alert).
 *
 * Requires: backend migrated, ENABLE_REPLENISHMENT=1 (set by
 * playwright.golden.config.ts). Run with: npm run test:e2e:golden
 */

test('COMP-002: low-stock Attention row shows a suggested purchase quantity', async ({ page }) => {
  // The assertion below deliberately waits out a real 60s server-side cache
  // TTL (see the comment at that wait) on top of the normal setup steps.
  test.setTimeout(180_000);
  const id = unique();
  const companyName = `E2E Replenish ${id}`;
  const email = `e2e-replenish-${id}@example.test`;
  const productName = `Replenish Widget ${id}`;
  const sku = `RPL-${id}`;
  const customerName = `Replenish Customer ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });

  // Product-level reorder threshold — the only reorder configuration
  // reachable via the UI today (no per-warehouse override screen exists
  // yet), so the replenishment suggestion falls back to
  // `reorder_level - available` for this tenant.
  await createProduct(page, {
    name: productName, sku, sellingPrice: '100', purchasePrice: '60', reorderLevel: '5',
  });

  await createCustomer(page, { name: customerName });

  // Give the product 10 units, then sell 6 of them — available drops to 4,
  // below the reorder level of 5, and the sale keeps it inside the "sold
  // in the last 14 days" window _low_stock() also requires.
  await page.goto('/inventory/adjustments');
  const productsCombo = page.getByRole('combobox', { name: 'Products', exact: true });
  await productsCombo.click();
  await productsCombo.fill(sku);
  await page.getByRole('option', { name: new RegExp(sku) }).click();
  await page.getByLabel('Quantity to Add').fill('10');
  await page.getByLabel('Reason for Adjustment').click();
  await page.getByRole('option', { name: 'Opening Stock Correction' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Stock adjustment recorded')).toBeVisible();

  await page.goto('/sales/new');
  await selectPartyOnDocument(page, customerName);
  await addInvoiceItem(page, sku);
  const lineRow = page.getByRole('row', { name: new RegExp(productName) });
  // F1-017: the row's "Description (optional)" field is a <textarea>, not an
  // <input>, so it doesn't shift indices — the QTY field has its own
  // aria-label ("QTY") and is more robust than a positional input index.
  await lineRow.getByLabel('QTY').fill('6');
  await saveAndCompleteSalesInvoice(page, new RegExp(customerName));

  // The Attention page is the generic renderer for every alert code,
  // including LOW_STOCK_FAST_MOVER — not a dedicated low-stock widget.
  //
  // B9-012 (backend/insights/attention.py): the raw feed is cached per
  // (company, as_of) for 60s with no invalidation on write — an intentional
  // perf tradeoff, not a bug. The dashboard's own attention call right after
  // login (well before this test creates any stock/sales data) seeds that
  // cache with an empty result, so a single post-sale fetch inside the
  // cache's 60s window will deterministically see the stale empty response.
  // Poll with reloads (each one a fresh request) until past the TTL.
  // The row's full message renders twice (a truncated-text <span> alongside
  // the visible <p>, both carrying the complete string) — .first() avoids a
  // strict-mode violation.
  const attentionRow = page.getByText(new RegExp(`${productName} is below reorder`)).first();
  await expect(async () => {
    await page.goto('/attention');
    await expect(attentionRow).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 75_000, intervals: [5_000] });
  // reorder_level (5) - available (10 - 6 = 4) = 1 — the enriched
  // LOW_STOCK_FAST_MOVER message, not the bare pre-COMP-002 text.
  await expect(page.getByText(/Suggested purchase 1(\.000)?\.?/).first()).toBeVisible();
});
