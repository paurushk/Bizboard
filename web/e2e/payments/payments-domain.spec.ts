import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Payments domain. listAllPaymentLinks / listBankStatementsPage / listRecon /
 * listAccountingBankReconSessions (and the listBankAccounts + getPaymentHealth
 * they depend on) are now wired into withMocks() + src/mocks/data.ts, so these
 * assert the real data view rather than the earlier ErrorState/Retry fallback.
 * The fourth screen (Account Aggregator) is a static "honesty gate" page with
 * no API calls.
 */
test.describe('payments domain', () => {
  test('payment links page lists links with real data', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/links', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('cell', { name: 'INV-2026-0001' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('cell', { name: 'Rahul Stores' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry' })).toHaveCount(0);
  });

  test('bank statements page lists a committed statement', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/statements', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('cell', { name: 'hdfc-july-2026.csv' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: 'Retry' })).toHaveCount(0);
  });

  test('bank reconciliation page shows unmatched lines and a suggestion', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/reconciliation', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByText('UPI/RAHUL STORES/2000')).toBeVisible({ timeout: 15_000 });
    // one line has a suggestion (Rahul Stores receipt), the other has none.
    await expect(page.getByText(/Receipt RCT-0001/)).toBeVisible();
    await expect(page.getByText('No confident suggestions')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry' })).toHaveCount(0);
  });

  test('account aggregator page states the honesty gate (no consent UI built)', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/account-aggregator', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'Account Aggregator' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/no consent ui in this app/i)).toBeVisible();
  });
});
