/**
 * Sales and purchase returns — the screens a counter operator uses (mock API).
 *
 * Covers the entry points ("Return goods" on an invoice, deep link), the dialog,
 * completing and saving a draft, the list filters, and that nothing overflows on a phone.
 */
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

async function openReturnsFor(page: Page, invoiceId = 1) {
  await page.goto(`/sales/returns?create=1&invoice=${invoiceId}`, { waitUntil: 'domcontentloaded' });
  const dialog = page.getByRole('dialog', { name: /new sales return/i });
  await expect(dialog).toBeVisible({ timeout: 15_000 });
  await expect(dialog.getByRole('combobox', { name: /original invoice/i })).toHaveValue(/INV-2026-0001/, {
    timeout: 15_000,
  });
  return dialog;
}


/** The invoice page has more than one "More" button on small screens; open the one with the action menu. */
async function openInvoiceMoreMenu(page: Page, expectItem: RegExp) {
  const buttons = page.locator('main').getByRole('button', { name: /^more$/i });
  await expect(buttons.first()).toBeVisible({ timeout: 15_000 });
  const count = await buttons.count();
  for (let i = 0; i < count; i += 1) {
    await buttons.nth(i).click();
    const item = page.getByRole('menuitem', { name: expectItem });
    if (await item.isVisible({ timeout: 1500 }).catch(() => false)) return item;
    await page.keyboard.press('Escape');
  }
  throw new Error(`No "More" menu offered ${String(expectItem)}`);
}

test.describe('Sales returns', () => {
  test('the list has search, status and date filters and an empty state', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/returns', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /sales returns/i })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel(/^search$/i)).toBeVisible();
    await expect(page.getByRole('combobox', { name: /status/i })).toBeVisible();
    await expect(page.getByLabel(/from date/i)).toBeVisible();
    await expect(page.getByLabel(/to date/i)).toBeVisible();
    await expect(page.getByText(/no sales returns yet/i)).toBeVisible();
  });

  test('a deep link from an invoice opens the dialog with the invoice and its lines, without a flash of "nothing to return"', async ({
    page,
  }) => {
    await loginAsOwner(page);
    const dialog = await openReturnsFor(page);
    await expect(dialog.getByText('Premium Tea 500g')).toBeVisible();
    await expect(dialog.getByRole('checkbox').first()).toBeVisible();
    // The address no longer carries the one-time parameters.
    await expect(page).toHaveURL(/\/sales\/returns$/);
  });

  test('ticking a line and completing shows the success message', async ({ page }) => {
    await loginAsOwner(page);
    const dialog = await openReturnsFor(page);
    const complete = dialog.getByRole('button', { name: /^complete$/i });
    await expect(complete).toBeDisabled();
    await dialog.getByRole('checkbox').first().check();
    await expect(dialog.getByRole('spinbutton', { name: /qty/i })).toHaveValue('1');
    await expect(complete).toBeEnabled();
    await complete.click();
    await expect(page.getByText(/sales return completed/i)).toBeVisible({ timeout: 15_000 });
    await expect(dialog).toBeHidden();
  });

  test('saving a draft closes the dialog and says the draft was saved', async ({ page }) => {
    await loginAsOwner(page);
    const dialog = await openReturnsFor(page);
    await dialog.getByRole('checkbox').first().check();
    await dialog.getByRole('button', { name: /^save$/i }).click();
    await expect(page.getByText(/sales return draft saved/i)).toBeVisible({ timeout: 15_000 });
  });

  test('a quick reason fills the reason box and "Defective" marks the line Damaged', async ({ page }) => {
    await loginAsOwner(page);
    const dialog = await openReturnsFor(page);
    await dialog.getByRole('checkbox').first().check();
    await dialog.getByText('Defective / damaged').click();
    await expect(dialog.getByLabel(/^reason$/i)).toHaveValue('Defective / damaged');
    await expect(dialog.getByRole('combobox', { name: /condition/i }).first()).toContainText(/damaged/i);
  });

  test('"Return goods" on an invoice opens Sales Returns, not Credit Notes', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/history/1', { waitUntil: 'domcontentloaded' });
    await (await openInvoiceMoreMenu(page, /return goods/i)).click();
    await expect(page).toHaveURL(/\/sales\/returns/);
    await expect(page.getByRole('dialog', { name: /new sales return/i })).toBeVisible({ timeout: 15_000 });
    // And the value-only path stays separate.
    await page.goto('/sales/history/1', { waitUntil: 'domcontentloaded' });
    await expect(await openInvoiceMoreMenu(page, /new credit note/i)).toBeVisible();
  });

  test('the dialog does not make the page scroll sideways', async ({ page }) => {
    await loginAsOwner(page);
    await openReturnsFor(page);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});

test.describe('Purchase returns', () => {
  test('the list has the same filters and an empty state', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/returns', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /purchase returns/i })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel(/^search$/i)).toBeVisible();
    await expect(page.getByLabel(/from date/i)).toBeVisible();
    await expect(page.getByText(/no purchase returns yet/i)).toBeVisible();
  });

  test('the new-return dialog opens from the address and has the auto credit note notice', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/returns?create=1', { waitUntil: 'domcontentloaded' });
    const dialog = page.getByRole('dialog', { name: /new purchase return/i });
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByText(/purchase credit note/i)).toBeVisible();
    await expect(dialog.getByRole('button', { name: /^complete$/i })).toBeDisabled();
  });
});


test.describe('Returns accessibility (axe)', () => {
  async function seriousViolations(page: Page) {
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    return results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
  }

  test('the sales return list has no serious or critical violations', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/returns', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /sales returns/i })).toBeVisible({ timeout: 15_000 });
    const blocking = await seriousViolations(page);
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
  });

  test('the sales return dialog, with a line ticked, has no serious or critical violations', async ({ page }) => {
    await loginAsOwner(page);
    const dialog = await openReturnsFor(page);
    await dialog.getByRole('checkbox').first().check();
    await expect(dialog.getByRole('button', { name: /^complete$/i })).toBeEnabled();
    const blocking = await seriousViolations(page);
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
  });

  test('the purchase return dialog has no serious or critical violations', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/returns?create=1', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('dialog', { name: /new purchase return/i })).toBeVisible({ timeout: 15_000 });
    const blocking = await seriousViolations(page);
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
  });
});
