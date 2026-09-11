import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Payments domain — zero e2e coverage before this pass. Three of the four
 * screens (links/statements/reconciliation) call list endpoints that aren't
 * wired into the mocked API layer (web/src/api/legacy/payments.ts's
 * listAllPaymentLinks / listBankStatementsPage / listRecon skip withMocks()),
 * so in light/mocked mode they genuinely hit an unreachable proxy target and
 * render their ErrorState branch rather than the full data view — this spec
 * asserts that degrades gracefully (a Retry affordance, not a blank/crashed
 * page), which is itself a real and previously-unasserted behavior. The
 * fourth (Account Aggregator) is a static "honesty gate" page with no API
 * calls, so it gets a full content assertion.
 *
 * Deeper interaction coverage (opening the create-link dialog with real
 * data, uploading a statement, accepting a recon suggestion) needs these
 * three endpoints wired into src/mocks/data.ts + withMocks() first, or a
 * golden/real-backend spec — left for a follow-up batch.
 */
test.describe('payments domain', () => {
  test('payment links page reaches its error state gracefully (endpoint not mocked)', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/links', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible({ timeout: 15_000 });
  });

  test('bank statements page reaches its error state gracefully (endpoint not mocked)', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/statements', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible({ timeout: 15_000 });
  });

  test('bank reconciliation page reaches its error state gracefully (endpoint not mocked)', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/reconciliation', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible({ timeout: 15_000 });
  });

  test('account aggregator page states the honesty gate (no consent UI built)', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/payments/account-aggregator', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'Account Aggregator' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/no consent ui in this app/i)).toBeVisible();
  });
});
