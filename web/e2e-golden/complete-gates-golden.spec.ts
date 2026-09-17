import { expect, test } from '@playwright/test';
import {
  addInvoiceItem,
  addStockAdjustment,
  createCustomer,
  createProduct,
  createSupplier,
  enableAccounting,
  registerTenant,
  saveCompanyGstin,
  selectPartyOnDocument,
  unique,
} from './helpers/documents';

test.describe('Complete-gate goldens (live Django)', () => {
  test('CG-20: Regular empty GSTIN blocks purchase Complete until GSTIN is saved', async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const id = unique();
    const sku = `CG20-${id}`;
    const supplierName = `CG20 Supplier ${id}`;

    await registerTenant(page, {
      companyName: `E2E CG20 ${id}`,
      email: `e2e-cg20-${id}@example.test`,
      password: 'GoldenPath123!',
      gstin: false,
    });
    await createProduct(page, {
      name: `CG20 Widget ${id}`,
      sku,
      sellingPrice: '100',
      purchasePrice: '80',
      hsnCode: '7318',
    });
    await createSupplier(page, { name: supplierName });

    await page.goto('/purchases/new');
    await selectPartyOnDocument(page, supplierName);
    await addInvoiceItem(page, sku);
    await expect(
      page.getByText('Save the company GSTIN in GST settings before completing a GST invoice.'),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeDisabled();

    await saveCompanyGstin(page);
    await page.goto('/purchases/new');
    await selectPartyOnDocument(page, supplierName);
    await addInvoiceItem(page, sku);
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeEnabled();
  });

  test('CG-03: stock BLOCK disables sales Complete when qty exceeds on-hand', async ({ page }) => {
    test.setTimeout(150_000);
    const id = unique();
    const sku = `CG03-${id}`;
    const customerName = `CG03 Customer ${id}`;

    await registerTenant(page, {
      companyName: `E2E CG03 ${id}`,
      email: `e2e-cg03-${id}@example.test`,
      password: 'GoldenPath123!',
    });
    await page.goto('/settings/gst');
    await page.getByLabel('Out-of-Stock Billing Policy').click();
    await page.getByRole('option', { name: /Block Billing/i }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByText('GST settings saved')).toBeVisible({ timeout: 15_000 });

    await createProduct(page, {
      name: `CG03 Widget ${id}`,
      sku,
      sellingPrice: '100',
      purchasePrice: '80',
      hsnCode: '7318',
    });
    await addStockAdjustment(page, { sku, quantity: '1' });
    await createCustomer(page, { name: customerName });

    await page.goto('/sales/new');
    await selectPartyOnDocument(page, customerName);
    await addInvoiceItem(page, sku);
    await page.getByRole('spinbutton').first().fill('5');
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeDisabled();
    await expect(page.getByText(/Insufficient stock/i)).toBeVisible();

    await page.getByRole('spinbutton').first().fill('1');
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeEnabled();
  });

  test('CG-21: purchase Complete with no supplier GSTIN and RCM off shows confirm-no-RCM', async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const id = unique();
    const sku = `CG21-${id}`;
    const supplierName = `CG21 Unreg ${id}`;

    await registerTenant(page, {
      companyName: `E2E CG21 ${id}`,
      email: `e2e-cg21-${id}@example.test`,
      password: 'GoldenPath123!',
    });
    await createProduct(page, {
      name: `CG21 Widget ${id}`,
      sku,
      sellingPrice: '100',
      purchasePrice: '80',
      hsnCode: '7318',
    });
    await createSupplier(page, { name: supplierName });

    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toMatch(/GSTIN|reverse charge|RCM/i);
      await dialog.accept();
    });

    await page.goto('/purchases/new');
    await selectPartyOnDocument(page, supplierName);
    await addInvoiceItem(page, sku);
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeEnabled();
    await page.getByRole('button', { name: 'Save & Complete' }).click();
    await expect(page).toHaveURL(/\/purchases\/history/, { timeout: 30_000 });
  });

  test('CG-22: duplicate supplier bill number prompts before Complete', async ({ page }) => {
    test.setTimeout(180_000);
    const id = unique();
    const sku = `CG22-${id}`;
    const supplierName = `CG22 Supplier ${id}`;
    const billNo = `DUP-${id}`;

    await registerTenant(page, {
      companyName: `E2E CG22 ${id}`,
      email: `e2e-cg22-${id}@example.test`,
      password: 'GoldenPath123!',
    });
    await createProduct(page, {
      name: `CG22 Widget ${id}`,
      sku,
      sellingPrice: '100',
      purchasePrice: '80',
      hsnCode: '7318',
    });
    await createSupplier(page, { name: supplierName });

    await page.goto('/purchases/new');
    await selectPartyOnDocument(page, supplierName);
    await addInvoiceItem(page, sku);
    await page.getByLabel(/supplier bill/i).fill(billNo);
    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });
    await page.getByRole('button', { name: 'Save & Complete' }).click();
    await expect(page).toHaveURL(/\/purchases\/history/, { timeout: 30_000 });

    await page.goto('/purchases/new');
    await selectPartyOnDocument(page, supplierName);
    await addInvoiceItem(page, sku);
    await page.getByLabel(/supplier bill/i).fill(billNo);
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toMatch(/already exists|duplicate/i);
      await dialog.dismiss();
    });
    await page.getByRole('button', { name: 'Save & Complete' }).click();
    await expect(page).toHaveURL(/\/purchases\/new/);
  });

  test('CG-11 / CG-23: closed GST period click-fails Complete with a named error', async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const id = unique();
    const sku = `CG11-${id}`;
    const customerName = `CG11 Customer ${id}`;
    const supplierName = `CG11 Supplier ${id}`;

    await registerTenant(page, {
      companyName: `E2E CG11 ${id}`,
      email: `e2e-cg11-${id}@example.test`,
      password: 'GoldenPath123!',
    });
    await enableAccounting(page);
    const now = new Date();
    const start = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
    const endDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const end = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(endDay).padStart(2, '0')}`;

    await page.goto('/accounting/periods');
    await page.getByLabel(/period name|^name$/i).fill(`CG11 ${id}`);
    await page.getByLabel(/start/i).fill(start);
    await page.getByLabel(/end/i).first().fill(end);
    await page.getByRole('button', { name: /^Create$/i }).click();
    await expect(page.getByText(`CG11 ${id}`)).toBeVisible({ timeout: 15_000 });
    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });
    await page.getByRole('button', { name: /^Close$/i }).click();
    await expect(page.getByText(/CLOSED/i).first()).toBeVisible({ timeout: 15_000 });

    await createProduct(page, {
      name: `CG11 Widget ${id}`,
      sku,
      sellingPrice: '100',
      purchasePrice: '80',
      hsnCode: '7318',
    });
    await addStockAdjustment(page, { sku, quantity: '5' });
    await createCustomer(page, { name: customerName });
    await createSupplier(page, { name: supplierName });

    await page.goto('/sales/new');
    await selectPartyOnDocument(page, customerName);
    await addInvoiceItem(page, sku);
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeEnabled();
    await page.getByRole('button', { name: 'Save & Complete' }).click();
    await expect(page.getByText(/closed|period/i).first()).toBeVisible({ timeout: 20_000 });

    await page.goto('/purchases/new');
    await selectPartyOnDocument(page, supplierName);
    await addInvoiceItem(page, sku);
    await expect(page.getByRole('button', { name: 'Save & Complete' })).toBeEnabled();
    await page.getByRole('button', { name: 'Save & Complete' }).click();
    await expect(page.getByText(/closed|period/i).first()).toBeVisible({ timeout: 20_000 });
  });
});
