import { expect, test, type Page } from '@playwright/test';

/**
 * Phase 1 golden extensions: multi-line return, sales CN + PDF, SO→invoice convert.
 */

function unique() {
  return `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

async function registerTenant(page: Page, id: string) {
  await page.goto('/register');
  await page.getByLabel('Company name').fill(`E2E P1 ${id}`);
  await page.getByLabel('Full name').fill('E2E Tester');
  await page.getByLabel('Email').fill(`e2e-p1-${id}@example.test`);
  await page.getByLabel('Password').fill('GoldenPath123!');
  await page.getByLabel('State').fill('Karnataka');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL('/');
}

async function createProductWithStock(page: Page, id: string, skuSuffix: string) {
  const productName = `P1 Widget ${skuSuffix} ${id}`;
  const productSku = `P1-${skuSuffix}-${id}`;
  await page.goto('/inventory/products');
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByLabel('Name').fill(productName);
  await page.getByLabel('SKU').fill(productSku);
  await page.getByLabel('GST %').fill('0');
  await page.getByLabel('Purchase price').fill('50');
  await page.getByLabel('Selling price').fill('100');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(productName)).toBeVisible();

  await page.goto('/inventory/adjustments');
  const productsCombo = page.getByRole('combobox', { name: 'Products', exact: true });
  await productsCombo.click();
  await productsCombo.fill(productSku);
  await page.getByRole('option', { name: new RegExp(productSku) }).click();
  await page.getByLabel('Quantity delta (+/−)').fill('20');
  await page.getByLabel('Reason').fill('Opening stock phase1 e2e');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Stock adjustment recorded')).toBeVisible();
  return { productName, productSku };
}

async function createCustomer(page: Page, id: string) {
  const customerName = `P1 Customer ${id}`;
  await page.goto('/sales/customers');
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByLabel('Name').fill(customerName);
  await page.getByLabel('State').fill('Karnataka');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(customerName)).toBeVisible();
  return customerName;
}

async function completeInvoiceWithProducts(
  page: Page,
  customerName: string,
  skus: string[],
) {
  await page.goto('/sales/new');
  const invoiceCustomerCombo = page.getByRole('combobox', { name: 'Customer', exact: true });
  await invoiceCustomerCombo.click();
  await invoiceCustomerCombo.fill(customerName);
  await page.getByRole('option', { name: customerName }).click();
  await page.getByLabel('Invoice type').click();
  await page.getByRole('option', { name: /Non-GST/i }).click();

  const itemInput = page.getByPlaceholder('+ Add Item / Scan barcode or search SKU / name');
  for (const sku of skus) {
    await itemInput.click();
    await itemInput.fill(sku);
    await page.getByRole('option', { name: new RegExp(sku) }).click();
  }
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);
  const invoiceRow = page.getByRole('row', { name: new RegExp(customerName) }).first();
  await expect(invoiceRow).toContainText('Completed');
  const invoiceNumber = (await invoiceRow.locator('td').nth(1).textContent())?.trim();
  expect(invoiceNumber).toBeTruthy();
  return invoiceNumber!;
}

test('phase1: multi-line return + credit note PDF + SO convert', async ({ page }) => {
  const id = unique();
  await registerTenant(page, id);
  const a = await createProductWithStock(page, id, 'A');
  const b = await createProductWithStock(page, id, 'B');
  const customerName = await createCustomer(page, id);

  const invoiceNumber = await completeInvoiceWithProducts(page, customerName, [
    a.productSku,
    b.productSku,
  ]);

  // Multi-line sales return — include both lines via checkboxes.
  await page.goto('/sales/returns');
  await page.getByRole('button', { name: 'Create' }).click();
  const invCombo = page.getByLabel('Original invoice');
  await invCombo.click();
  await invCombo.fill(invoiceNumber);
  await page.getByRole('option', { name: new RegExp(invoiceNumber) }).click();
  const checkboxes = page.getByRole('checkbox');
  await expect(checkboxes).toHaveCount(2, { timeout: 10_000 });
  await checkboxes.nth(0).check();
  await checkboxes.nth(1).check();
  await page.getByLabel('Reason').fill('Multi-line return e2e');
  await page.getByRole('button', { name: 'Complete' }).click();
  await expect(page.getByText(/Sales return completed/i)).toBeVisible({ timeout: 15_000 });

  // Credit note + PDF ready.
  const cnSource = await completeInvoiceWithProducts(page, customerName, [a.productSku]);
  await page.goto('/sales/credit-notes/new');
  const source = page.getByLabel('Source invoice');
  await source.click();
  await source.fill(cnSource);
  await page.getByRole('option', { name: new RegExp(cnSource) }).click();
  await page.getByRole('button', { name: new RegExp(a.productName) }).click();
  await page.getByRole('button', { name: /Save & Complete/i }).click();
  await expect(page.getByRole('button', { name: /Download|Print/i }).first()).toBeVisible({
    timeout: 45_000,
  });

  // SO → invoice convert.
  await page.goto('/sales/orders/new');
  const soCustomer = page.getByRole('combobox', { name: 'Customer', exact: true });
  await soCustomer.click();
  await soCustomer.fill(customerName);
  await page.getByRole('option', { name: customerName }).click();
  const soProduct = page.getByRole('combobox', { name: 'Products' });
  await soProduct.click();
  await soProduct.fill(a.productSku);
  await page.getByRole('option', { name: new RegExp(a.productSku) }).click();
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page).toHaveURL(/\/sales\/orders\/\d+/);
  await page.getByRole('button', { name: 'Convert' }).click();
  await expect(page).toHaveURL(/\/sales\/history/);
});
