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

  test('create payment link: invoice and customer pickers show the picked value, not the raw query', async ({ page }) => {
    // Regression guard: these Autocompletes only set the invoice/customer
    // object on select (BankingPhasePages' PaymentLinksPage), so the box must
    // display the picked label — a stale query here looks exactly like the
    // click did nothing.
    await loginAsOwner(page);
    await page.goto('/payments/links', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: /create link/i }).click();
    await expect(page.getByRole('dialog').getByText(/create payment link/i)).toBeVisible();

    // Customer first — picking an invoice below disables this field.
    const customerCombo = page.getByRole('combobox', { name: /customer \(if no invoice\)/i });
    await customerCombo.click();
    await customerCombo.fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await expect(customerCombo).toHaveValue(/Rahul Stores/i);

    const invoiceCombo = page.getByRole('combobox', { name: /sales invoice/i });
    await invoiceCombo.click();
    await invoiceCombo.fill('INV-2026-0001');
    await page.getByRole('option', { name: /INV-2026-0001/i }).click();
    await expect(invoiceCombo).toHaveValue(/INV-2026-0001/i);
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
