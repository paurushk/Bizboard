/**
 * §H1 — the invoice editor's client-side guards mirror the backend's completion
 * rules, so a user never gets to submit a document the API would reject.
 *
 * Backend contract (SalesService.complete): a document needs >= 1 line and a
 * customer. The FE gates "Save & Complete" and "Save draft" on
 * `canSave = lines>0 && customerId` (NewInvoicePage.tsx).
 */
import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/** A prior spec may have left an autosaved invoice draft in localStorage; a
 * fresh `/sales/new` would restore it and enable the save buttons. */
async function freshEditor(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.evaluate(() => {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k && (k.includes('invoice-outbox') || k.includes('invoice-draft') || k.includes('draft'))) {
          localStorage.removeItem(k);
        }
      }
    } catch {
      /* ignore */
    }
  });
  await page.goto('/sales/new');
}

test.describe('Invoice editor — FE↔BE validation parity', () => {
  test('a fresh invoice cannot be completed or saved as draft', async ({ page }) => {
    await loginAsOwner(page);
    await freshEditor(page);
    await expect(page).toHaveURL(/\/sales\/new/);

    await expect(page.getByRole('button', { name: /save & complete/i })).toBeDisabled();
    await expect(page.getByRole('button', { name: /save draft/i })).toBeDisabled();
  });

  test('choosing only a customer is still not enough — a line is required', async ({ page }) => {
    await loginAsOwner(page);
    await freshEditor(page);

    await page.getByRole('combobox', { name: /bill to/i }).click();
    await page.getByRole('option', { name: /Rahul Stores/i }).click();

    // customer set, no line -> both save paths stay disabled (BE: >= 1 line)
    await expect(page.getByRole('button', { name: /save & complete/i })).toBeDisabled();
    await expect(page.getByRole('button', { name: /save draft/i })).toBeDisabled();
  });
});

test.describe('§H1 — offline draft outbox', () => {
  test('the offline outbox page renders and shows the empty state when idle', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/offline-outbox');
    await expect(page).toHaveURL(/\/offline-outbox/);
    await expect(page.getByRole('heading', { name: /offline outbox/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/no pending offline drafts/i)).toBeVisible();
    await expect(page.getByText(/something went wrong|unexpected error/i)).toHaveCount(0);
  });
});
