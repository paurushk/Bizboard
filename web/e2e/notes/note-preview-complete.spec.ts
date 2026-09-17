/**
 * CG-25 — note preview does not strand Complete (mocks now return client totals).
 * CG-26 / CG-27 — zero qty and over-cap named Complete reasons.
 */
import { expect, test, type Page } from '@playwright/test';
import { fillLineQty } from '../complete-gates/assertCompleteGate';
import { loginAsOwner } from '../helpers/auth';

async function clearDrafts(page: Page) {
  await page.goto('/');
  await page.evaluate(() => {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k && (k.includes('outbox') || k.includes('draft'))) {
          localStorage.removeItem(k);
        }
      }
    } catch {
      /* ignore */
    }
  });
}

test.describe('Note editor — complete gates', () => {
  test('CG-25: source invoice + line still enables Complete (mock preview does not strand)', async ({
    page,
  }) => {
    await loginAsOwner(page);
    await clearDrafts(page);
    await page.goto('/sales/credit-notes/new', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /credit note/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByLabel(/source invoice/i).click();
    await page.getByRole('option', { name: /INV-2026-0001/i }).click();
    await page.getByRole('button', { name: /Premium Tea 500g/i }).click();

    await expect(page.getByRole('button', { name: /save & complete/i })).toBeEnabled({ timeout: 15_000 });
  });

  test('CG-26: note qty 0 disables Complete with a named reason', async ({ page }) => {
    await loginAsOwner(page);
    await clearDrafts(page);
    await page.goto('/sales/credit-notes/new', { waitUntil: 'domcontentloaded' });
    await page.getByLabel(/source invoice/i).click();
    await page.getByRole('option', { name: /INV-2026-0001/i }).click();
    await page.getByRole('button', { name: /Premium Tea 500g/i }).click();

    await fillLineQty(page, '0');
    await expect(page.getByRole('button', { name: /save & complete/i })).toBeDisabled();
    await expect(page.getByText(/quantity greater than zero/i).first()).toBeVisible();
  });

  test('CG-27: note qty above source cap disables Complete with a named reason', async ({ page }) => {
    await loginAsOwner(page);
    await clearDrafts(page);
    await page.goto('/sales/credit-notes/new', { waitUntil: 'domcontentloaded' });
    await page.getByLabel(/source invoice/i).click();
    await page.getByRole('option', { name: /INV-2026-0001/i }).click();
    await page.getByRole('button', { name: /Premium Tea 500g/i }).click();

    await fillLineQty(page, '11');
    await expect(page.getByRole('button', { name: /save & complete/i })).toBeDisabled();
    await expect(page.getByText(/source document quantity/i).first()).toBeVisible();
  });

  test('CG-27: purchase note qty above source cap disables Complete', async ({ page }) => {
    await loginAsOwner(page);
    await clearDrafts(page);
    await page.goto('/purchases/credit-notes/new', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /credit note/i })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByLabel(/purchase invoice/i).click();
    await page.getByRole('option', { name: /PUR-2026-0001/i }).click();
    await fillLineQty(page, '6');
    await expect(page.getByRole('button', { name: /save & complete/i })).toBeDisabled();
    await expect(page.getByText(/source document quantity/i).first()).toBeVisible();
  });
});
