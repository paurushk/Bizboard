import { expect, test } from '@playwright/test';

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

function unique() {
  return `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

test('golden path: register -> enable accounting -> post journal -> trial balance + P&L reflect it', async ({ page }) => {
  const id = unique();
  const companyName = `E2E Accounting ${id}`;
  const email = `e2e-accounting-${id}@example.test`;
  const narration = `Bank charges e2e ${id}`;

  // 1. Register a fresh, isolated tenant.
  await page.goto('/register');
  await page.getByLabel('Company name').fill(companyName);
  await page.getByLabel('Full name').fill('E2E Tester');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('GoldenPath123!');
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: 'Karnataka' }).click();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/\/login\?registered=1/);
  await expect(page.getByText(/Account created/i)).toBeVisible();
  await page.getByLabel('Password', { exact: true }).fill('GoldenPath123!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL('/');

  // 2. Enable accounting — seeds the chart of accounts synchronously, so
  // "1100 — Cash" and "5200 — Bank Charges" exist immediately. A full
  // page.goto() (not a client-side link) is required afterwards for
  // AuthContext to re-fetch /auth/me and pick up company.accountingEnabled
  // — it's a one-time boot fetch, not react-query.
  await page.goto('/settings/accounting');
  await page.getByRole('button', { name: 'Enable accounting' }).click();
  await expect(page.getByText('Accounting enabled — CoA seeded.')).toBeVisible();

  // 3. Post a balanced manual journal: Dr 5200 Bank Charges / Cr 1100 Cash,
  // ₹500 — a realistic "paid bank charges from the till" entry.
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

  // 4. Post it.
  await journalRow.getByRole('button', { name: 'Post' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Post' }).click();
  await expect(journalRow).toContainText('POSTED');

  // 5. Trial balance: this is the ONLY posting this tenant has ever made,
  // so the totals are exact, not just "balanced within tolerance".
  await page.goto('/reports/trial-balance');
  await expect(page.getByText('Total debit ₹500.00 · Total credit ₹500.00')).toBeVisible();
  await expect(page.getByRole('row', { name: /\b5200\b/ })).toContainText('₹500.00');
  await expect(page.getByRole('row', { name: /\b1100\b/ })).toContainText('₹500.00');

  // 6. P&L: the ₹500 Bank Charges expense must show up (Income stays ₹0 —
  // no sales have happened in this tenant).
  await page.goto('/reports/profit-and-loss');
  await expect(page.getByText(/Income ₹0\.00/)).toBeVisible();
  await expect(page.getByText(/Expenses ₹500\.00/)).toBeVisible();
});
