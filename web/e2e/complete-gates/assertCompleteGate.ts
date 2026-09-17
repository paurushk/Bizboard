import { expect, type Page } from '@playwright/test';

/**
 * Shared assertions for Complete-gate visibility cases (CG-*).
 * Party + ≥1 line is already on the form before calling these.
 *
 * Reasons are often repeated (banner + party panel + tax summary). Strict
 * page-wide getByText then fails; the named copy still has to be visible.
 */
export async function assertDraftEnabledCompleteDisabled(
  page: Page,
  reason: RegExp | string,
) {
  await expect(page.getByRole('button', { name: /save draft/i })).toBeEnabled();
  await expect(page.getByRole('button', { name: /save & complete/i })).toBeDisabled();
  await expect(page.getByText(reason).first()).toBeVisible();
}

export async function assertCompleteEnabled(page: Page) {
  await expect(page.getByRole('button', { name: /save & complete/i })).toBeEnabled();
}

/** Line qty lives in the items table (pending "add" qty is a separate spinbutton). */
export async function fillLineQty(page: Page, value: string) {
  const table = page.locator('table');
  const qty = table
    .getByRole('textbox', { name: /^(qty|quantity)$/i })
    .or(table.getByRole('spinbutton', { name: /^(qty|quantity)$/i }))
    .first();
  await qty.fill(value);
}
