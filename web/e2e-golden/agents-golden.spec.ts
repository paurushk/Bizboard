import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { createCustomer, createProduct, registerTenant, unique } from './helpers/documents';
import { grantRolloutFlag } from './helpers/grantFlag';

/**
 * Business agents against the live backend (no mocks): paste an order and see the wording learned.
 * Flags are granted per company with the e2e-only management command, the way a pilot would be switched on.
 */

function watchErrors(page: Page) {
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const text = m.text();
    if (/favicon|Failed to load resource|net::ERR/.test(text)) return;
    problems.push(`console: ${text}`);
  });
  return problems;
}

async function pasteOrder(page: Page, text: string) {
  await page.goto('/sales/quick-entry');
  const open = page.getByRole('button', { name: 'Paste', exact: true });
  await expect(open).toBeVisible({ timeout: 30_000 });
  await open.click();
  await page.getByLabel('Customer message').fill(text);
  await page.getByRole('button', { name: 'Read order' }).click();
  await expect(page.getByRole('dialog', { name: 'Review draft' })).toBeVisible({ timeout: 30_000 });
}

test('Order Intake: paste an order, fix one line, create a draft order, and the next paste needs no fix', async ({ page }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const id = unique();
  const email = `e2e-agents-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Agents ${id}`, email, password: 'GoldenPath123!' });
  await createProduct(page, { name: 'Sugar 50kg bag', sku: 'SUG50', sellingPrice: '2400', purchasePrice: '2000', gstRate: '5' });
  await createProduct(page, { name: 'Toor Dal 1kg', sku: 'DAL1', sellingPrice: '150', purchasePrice: '120', gstRate: '5' });
  await createCustomer(page, { name: 'Sharma Traders' });
  for (const flag of ['ENABLE_AGENTS', 'AGENT_ORDER_INTAKE', 'QUICK_ENTRY_ORDER_MODE']) grantRolloutFlag(email, flag);

  // First paste: the customer and "toor dal" are matched; "chini" is not, so the person picks the product.
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });
  await pasteOrder(page, 'From: Sharma Traders\n3 toor dal 1kg\n2 chini');
  const review = page.getByRole('dialog', { name: 'Review draft' });
  await expect(review.getByText('Written: 2 chini')).toBeVisible();
  await expect(review.getByRole('button', { name: 'Create draft order' })).toBeDisabled();
  const product = review.getByRole('combobox', { name: /Product: 2 chini/ });
  await product.click();
  await product.fill('Sugar');
  await page.getByRole('option', { name: 'Sugar 50kg bag' }).click();
  await review.getByRole('button', { name: 'Save changes' }).click();
  await expect(review.getByRole('button', { name: 'Create draft order' })).toBeEnabled({ timeout: 15_000 });

  const axe = await new AxeBuilder({ page }).include('[role="dialog"]').disableRules(['color-contrast']).analyze();
  expect(axe.violations.map((v) => v.id)).toEqual([]);

  await review.getByRole('button', { name: 'Create draft order' }).click();
  await expect(page.getByText(/Draft order .* created\./)).toBeVisible({ timeout: 20_000 });
  await page.getByRole('link', { name: 'Open it' }).click();
  await expect(page).toHaveURL(/\/sales\/orders\/\d+/);
  await expect(page.getByRole('combobox', { name: 'Customer', exact: true })).toHaveValue('Sharma Traders', { timeout: 15_000 });
  // Priced by the usual rules from the item master, with the quantities read from the message.
  await expect(page.getByRole('row', { name: /Sugar 50kg bag 2 2400/ })).toBeVisible();
  await expect(page.getByRole('row', { name: /Toor Dal 1kg 3 150/ })).toBeVisible();

  // Second paste with the same wording: matched from what was learned, nothing to fix.
  await pasteOrder(page, 'From: Sharma Traders\n5 chini');
  const again = page.getByRole('dialog', { name: 'Review draft' });
  await expect(again.getByRole('button', { name: 'Create draft order' })).toBeEnabled({ timeout: 15_000 });
  await expect(again.getByRole('combobox', { name: /Product: 5 chini/ })).toHaveValue('Sugar 50kg bag');
  expect(problems).toEqual([]);
});

test('Order Intake: the paste panel is absent when the agent is off', async ({ page }) => {
  test.setTimeout(180_000);
  const id = unique();
  const email = `e2e-agents-off-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Agents Off ${id}`, email, password: 'GoldenPath123!' });
  grantRolloutFlag(email, 'QUICK_ENTRY_ORDER_MODE');
  await page.goto('/sales/quick-entry');
  await expect(page.getByLabel(/search a customer/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'Paste', exact: true })).toHaveCount(0);
});
