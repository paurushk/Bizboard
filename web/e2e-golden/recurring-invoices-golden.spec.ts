import { expect, test } from '@playwright/test';
import { createCustomer, createProduct, registerTenant, unique } from './helpers/documents';

/**
 * Recurring invoices: create a quarterly schedule with two lines, edit it,
 * pause and resume it, run it now and follow the link to the generated draft.
 * A real end-to-end run against the live backend.
 *
 * Run with: npm run test:e2e:golden -- recurring-invoices-golden
 */

test('recurring invoices: create, edit, pause, resume, run now and open the draft', async ({ page }) => {
  test.setTimeout(180_000);
  const id = unique();
  const customerName = `Recurring Customer ${id}`;
  const productA = { name: `Retainer ${id}`, sku: `RTA-${id}` };
  const productB = { name: `Support ${id}`, sku: `RTB-${id}` };

  await registerTenant(page, {
    companyName: `E2E Recurring ${id}`,
    email: `e2e-recurring-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await createProduct(page, { ...productA, sellingPrice: '1000', purchasePrice: '0', gstRate: '18', productType: 'SERVICE' });
  await createProduct(page, { ...productB, sellingPrice: '500', purchasePrice: '0', gstRate: '18', productType: 'SERVICE' });
  await createCustomer(page, { name: customerName });

  await page.goto('/sales/recurring');
  await page.getByRole('button', { name: 'New recurring schedule' }).click();
  const drawer = page.getByRole('presentation').filter({ hasText: 'New recurring schedule' });

  // Customer and products are picked by server-side search, not from a capped list.
  await drawer.getByLabel('Customer').fill(customerName);
  await page.getByRole('option', { name: new RegExp(customerName) }).click();
  await drawer.getByLabel('Cadence').click();
  await page.getByRole('option', { name: 'Quarterly' }).click();
  const next = new Date(Date.now() + 40 * 24 * 3600 * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  await drawer.getByLabel('Next run').fill(
    `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}T09:00`,
  );

  await drawer.getByLabel('Product').first().fill(productA.name);
  await page.getByRole('option', { name: new RegExp(productA.sku) }).click();
  await drawer.getByRole('button', { name: 'Add line' }).click();
  await drawer.getByLabel('Product').nth(1).fill(productB.name);
  await page.getByRole('option', { name: new RegExp(productB.sku) }).click();

  // The estimated amount comes from the same engine as the invoice: 1000 + 500 + 18% GST.
  await expect(drawer.getByText('1,770.00')).toBeVisible({ timeout: 15_000 });
  await drawer.getByRole('button', { name: 'Save template' }).click();

  const row = page.getByRole('row').filter({ hasText: customerName });
  await expect(row).toBeVisible({ timeout: 15_000 });
  await expect(row.getByText('Quarterly')).toBeVisible();
  await expect(row.getByText('Active')).toBeVisible();

  // Edit: change the first quantity and see the estimate move.
  await row.getByRole('button', { name: 'Edit' }).click();
  const edit = page.getByRole('presentation').filter({ hasText: 'Edit recurring schedule' });
  await edit.getByLabel('Qty').first().fill('2');
  await expect(edit.getByText('2,950.00')).toBeVisible({ timeout: 15_000 });
  await edit.getByRole('button', { name: 'Save template' }).click();
  await expect(edit).toBeHidden({ timeout: 15_000 });

  // Pause, then resume (the saved date is still ahead, so no date prompt).
  await row.getByRole('button', { name: 'Pause' }).click();
  await expect(row.getByText('Paused')).toBeVisible({ timeout: 15_000 });
  await expect(row.getByRole('button', { name: 'Run now' })).toBeDisabled();
  await row.getByRole('button', { name: 'Resume' }).click();
  await expect(row.getByText('Active')).toBeVisible({ timeout: 15_000 });

  // Run now, then follow the link to the draft it created.
  await row.getByRole('button', { name: 'Run now' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Run now' }).click();
  const done = page.getByRole('alert').filter({ hasText: /Draft created/ });
  await expect(done).toBeVisible({ timeout: 30_000 });
  await done.getByRole('link', { name: 'View' }).click();
  await expect(page).toHaveURL(/\/sales\/history\/\d+/, { timeout: 15_000 });
  await expect(page.getByText('Draft').first()).toBeVisible();

  // The schedule now has history and can no longer be deleted.
  await page.goto('/sales/recurring');
  const again = page.getByRole('row').filter({ hasText: customerName });
  await expect(again.getByRole('button', { name: 'Delete' })).toHaveCount(0);
  await again.getByRole('button', { name: 'History' }).click();
  await expect(page.getByRole('dialog').getByText('Manual')).toBeVisible({ timeout: 15_000 });
});
