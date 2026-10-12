import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

/**
 * Customers master smoke (mock data): the list renders with its summary strip, the form validates a partial GSTIN
 * before save, and a phone-width viewport does not scroll the page sideways.
 */
test.describe('Customers screen', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/customers');
  });

  test('shows the list, the summary strip and the toolbar', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible();
    await expect(page.getByText('Active customers')).toBeVisible();
    await expect(page.getByLabel('Sort by')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export CSV' })).toBeVisible();
  });

  test('the form refuses a partial GSTIN and a half-filled location, then accepts a valid GSTIN', async ({ page }) => {
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('textbox', { name: /^Name/ }).fill('Smoke Traders');
    const save = dialog.getByRole('button', { name: 'Save' });
    await dialog.getByRole('textbox', { name: 'GSTIN' }).fill('29ABC');
    await expect(dialog.getByText('Enter a valid 15-character GSTIN')).toBeVisible();
    await expect(save).toBeDisabled();
    await dialog.getByRole('textbox', { name: 'GSTIN' }).fill('29ABCDE1234F1ZW');
    await expect(dialog.getByRole('combobox', { name: /State/ })).toContainText('Karnataka');
    await expect(dialog.getByRole('textbox', { name: 'PAN' })).toHaveValue('ABCDE1234F');
    await expect(save).toBeEnabled();
    await dialog.getByRole('button', { name: 'Addresses and location' }).click();
    await dialog.getByRole('textbox', { name: 'Latitude' }).fill('12.97');
    await expect(dialog.getByText('Enter both latitude and longitude, or leave both blank.')).toBeVisible();
    await expect(save).toBeDisabled();
  });

  test('blocking asks for confirmation first, and cancelling changes nothing', async ({ page }) => {
    const block = page.getByRole('button', { name: 'Block', exact: true }).first();
    await block.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('Block this customer?')).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('dialog')).toBeHidden();
    await expect(block).toBeVisible();
  });

  test('selecting customers with a GSTIN offers a batch verify', async ({ page }) => {
    await page.getByRole('checkbox', { name: 'Select all customers with a GSTIN' }).check();
    await expect(page.getByRole('button', { name: /^Verify selected \(\d+\)$/ })).toBeVisible();
  });

  test('the row menu offers Archive, and archiving asks first', async ({ page }) => {
    await page.getByRole('button', { name: /^More actions for/ }).first().click();
    await page.getByRole('menuitem', { name: 'Archive' }).click();
    await expect(page.getByRole('dialog').getByText('Archive this customer?')).toBeVisible();
  });

  test('Escape closes the dialog and focus returns to the button that opened it', async ({ page }) => {
    const add = page.getByRole('button', { name: 'Add', exact: true });
    await add.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
    await expect(add).toBeFocused();
  });

  test('the page does not scroll sideways at a phone width', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/sales/customers');
    await page.waitForLoadState('networkidle');
    const overflow = await page.evaluate(() => {
      const d = document.documentElement;
      return { scrollW: d.scrollWidth, clientW: d.clientWidth };
    });
    expect(overflow.scrollW - overflow.clientW, `${overflow.scrollW}px in ${overflow.clientW}px`).toBeLessThanOrEqual(2);
  });
});
