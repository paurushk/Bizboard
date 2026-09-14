import { expect, test } from '@playwright/test';
import { enableAccounting, registerTenant, unique } from './helpers/documents';

/**
 * Golden path for the manual-journal -> trial-balance -> P&L chain: register
 * -> enable accounting (seeds the chart of accounts) -> post a balanced
 * manual journal -> verify both reports actually reflect it, not just that
 * the journal itself shows POSTED.
 *
 * This is the only posting the fresh tenant ever makes, so the trial
 * balance's totals are asserted exactly (₹500.00 debit == ₹500.00 credit) —
 * not a tolerance-based check, a real reconciliation.
 *
 * Requires: backend migrated (`cd backend && python manage.py migrate`).
 * Run with: npm run test:e2e:golden
 */

test('golden path: register -> enable accounting -> post journal -> trial balance + P&L reflect it', async ({
  page,
}) => {
  test.setTimeout(120_000);
  const id = unique();
  const companyName = `E2E Accounting ${id}`;
  const email = `e2e-accounting-${id}@example.test`;
  const narration = `Bank charges e2e ${id}`;

  await registerTenant(page, { companyName, email, password: 'GoldenPath123!' });
  await enableAccounting(page);

  await page.goto('/accounting/journals');
  await page.getByRole('button', { name: 'New voucher' }).click();
  await page.getByLabel('Narration').fill(narration);

  const accountSelects = page.getByRole('dialog').getByLabel('Account');
  await accountSelects.nth(0).click();
  await page.getByRole('option', { name: /^5200/ }).click();
  await page.getByRole('dialog').getByLabel('Debit').first().fill('500');

  await accountSelects.nth(1).click();
  await page.getByRole('option', { name: /^1100/ }).click();
  await page.getByRole('dialog').getByLabel('Credit').nth(1).fill('500');

  await expect(page.getByText('Balanced')).toBeVisible();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  const journalRow = page.getByRole('row', { name: new RegExp(narration) });
  await expect(journalRow).toContainText('DRAFT');

  await journalRow.getByRole('button', { name: 'Post' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Post' }).click();
  await expect(journalRow).toContainText('POSTED');

  await page.goto('/reports/trial-balance');
  await expect(page.getByText('Total debit ₹500.00 · Total credit ₹500.00')).toBeVisible();
  await expect(page.getByRole('row', { name: /\b5200\b/ })).toContainText('₹500.00');
  await expect(page.getByRole('row', { name: /\b1100\b/ })).toContainText('₹500.00');

  await page.goto('/reports/profit-and-loss');
  await expect(page.getByText(/Income ₹0\.00/)).toBeVisible();
  await expect(page.getByText(/Expenses ₹500\.00/)).toBeVisible();
});
