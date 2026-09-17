import { expect, type Page } from '@playwright/test';

/**
 * Shared golden-suite helpers for the real-backend Playwright lane
 * (e2e-golden/**, run via `npm run test:e2e:golden`).
 *
 * BB-000829 follow-up: every one of these steps used to be copy-pasted
 * inline into each spec file with selectors that had quietly drifted from
 * the actual UI (the product form was redesigned into tabs, the stock
 * adjustment form was redesigned, and the invoice/purchase party selector's
 * accessible name is driven by its placeholder, not a "Customer"/"Bill From"
 * label) — so every golden spec sharing that inline code was failing before
 * it ever reached the assertion it exists to prove. Centralizing the correct,
 * live-verified sequence here means a future UI change only needs fixing in
 * one place, and every spec using it either all pass or all fail together
 * instead of silently drifting apart one file at a time.
 */

export async function registerTenant(
  page: Page,
  opts: { companyName: string; email: string; password: string; state?: string; gstin?: string | false },
) {
  await page.goto('/register');
  await page.getByLabel('Company name').fill(opts.companyName);
  await page.getByLabel('Full name').fill('E2E Tester');
  await page.getByLabel('Email').fill(opts.email);
  await page.getByLabel('Password', { exact: true }).fill(opts.password);
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: opts.state ?? 'Karnataka' }).click();
  if (opts.gstin !== false) {
    const gstin = typeof opts.gstin === 'string' ? opts.gstin : '29AAAAA0000A1ZY';
    await page.getByLabel('GSTIN (optional)').fill(gstin);
  }
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/\/login\?registered=1/, { timeout: 20_000 });
  await expect(page.getByText(/Account created/i)).toBeVisible();
  await page.getByLabel('Password', { exact: true }).fill(opts.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL('/', { timeout: 20_000 });
  await page.getByRole('button', { name: 'Skip for now' }).click({ timeout: 1_500 }).catch(() => undefined);
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });
}

/**
 * Create a product via the current tabbed ItemFormDialog: Name/SKU live on
 * the default "Basic details" tab, but price and GST rate only exist under
 * "Pricing details" — and GST rate is a select (GST_RATE_OPTIONS), not a
 * fillable text field. Defaults to 18% since that's the dialog's own default,
 * so most callers never need to touch the GST rate control at all.
 */
export async function createProduct(
  page: Page,
  opts: {
    name: string;
    sku: string;
    sellingPrice: string;
    purchasePrice: string;
    gstRate?: string;
    hsnCode?: string;
    serialNo?: string;
  },
) {
  await page.goto('/inventory/products');
  const heading = page.getByRole('heading', { name: /^Products$/i });
  const toolbarAdd = page.getByRole('button', { name: 'Add', exact: true });
  const emptyAdd = page.getByRole('button', { name: /Add Products/i });
  // PageTitle is an h1, but empty-state + toolbar both expose an Add* button.
  // Wait for either surface so a heading-role drift cannot stall the suite.
  await expect(heading.or(toolbarAdd).or(emptyAdd)).toBeVisible({ timeout: 20_000 });
  if (await toolbarAdd.count()) {
    await toolbarAdd.first().click();
  } else {
    await emptyAdd.first().click();
  }
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(opts.name);
  await page.getByRole('textbox', { name: 'SKU / Item Code', exact: true }).fill(opts.sku);
  if (opts.hsnCode) {
    await page.getByLabel(/HSN code/i).fill(opts.hsnCode);
  }
  if (opts.serialNo) {
    await page.getByRole('tab', { name: 'Stock details' }).click();
    await page.getByRole('radio', { name: 'Serial' }).click();
    await page.getByLabel('Serial no').fill(opts.serialNo);
  }
  await page.getByRole('tab', { name: 'Pricing details' }).click();
  await page.getByLabel('Selling Price (₹)').fill(opts.sellingPrice);
  await page.getByLabel('Purchase Price (₹)').fill(opts.purchasePrice);
  if (opts.gstRate && opts.gstRate !== '18') {
    await page.getByLabel('GST rate').click();
    await page.getByRole('option', { name: new RegExp(`^${opts.gstRate}%`) }).click();
  }
  await page.getByRole('button', { name: 'Save item' }).click();
  await expect(page.getByText(opts.name)).toBeVisible();
}

/**
 * Post a stock adjustment via the current StockAdjustmentPage: an Add/Reduce
 * toggle plus an unsigned "Quantity to Add" field (not the old signed
 * "Quantity delta (+/-)"), and a preset "Reason for Adjustment" dropdown (not
 * free text). Pass `warehouseName` to target a non-default godown — omit it
 * to use whatever the page auto-selects (the default godown).
 */
export async function addStockAdjustment(
  page: Page,
  opts: { sku: string; quantity: string; warehouseName?: string },
) {
  await page.goto('/inventory/adjustments');
  const productsCombo = page.getByRole('combobox', { name: 'Products', exact: true });
  await productsCombo.click();
  await productsCombo.fill(opts.sku);
  await page.getByRole('option', { name: new RegExp(opts.sku) }).click();
  if (opts.warehouseName) {
    await page.getByLabel('Godowns').click();
    await page.getByRole('option', { name: opts.warehouseName, exact: true }).click();
  }
  await page.getByLabel('Quantity to Add').fill(opts.quantity);
  await page.getByLabel('Reason for Adjustment').click();
  await page.getByRole('option', { name: 'Opening Stock Correction' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Stock adjustment recorded')).toBeVisible();
}

export async function createCustomer(
  page: Page,
  opts: { name: string; state?: string },
) {
  await page.goto('/sales/customers');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(opts.name);
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: opts.state ?? 'Karnataka' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(opts.name)).toBeVisible();
}

export async function createSupplier(
  page: Page,
  opts: { name: string; state?: string },
) {
  await page.goto('/purchases/suppliers');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(opts.name);
  await page.getByLabel('State').click();
  await page.getByRole('option', { name: opts.state ?? 'Karnataka' }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(opts.name)).toBeVisible();
}

/**
 * The customer/supplier picker on the sales and purchase invoice forms
 * (labelled "Bill To" / "Bill From" visually) shares one component whose
 * accessible name is driven by its placeholder, not the visual label —
 * `getByRole('combobox', { name: 'Customer' })` / `{ name: /bill from/i }`
 * never matches it. Match by placeholder instead, which is identical on
 * both forms.
 */
export async function selectPartyOnDocument(page: Page, partyName: string) {
  const partyCombo = page.getByPlaceholder('Search by customer name, phone, or GSTIN');
  await partyCombo.click();
  await partyCombo.fill(partyName);
  await page.getByRole('option', { name: partyName }).click();
}

/**
 * The receipts dialog's customer picker is a *different* component from the
 * invoice/purchase "Bill To"/"Bill From" one — its own placeholder, "Search
 * customer by name or phone…" — so it needs its own matcher rather than
 * reusing selectPartyOnDocument.
 */
export async function selectReceiptCustomer(page: Page, customerName: string) {
  const combo = page.getByPlaceholder('Search customer by name or phone');
  await combo.click();
  await combo.fill(customerName);
  await page.getByRole('option', { name: customerName }).click();
}

/** Select a specific godown on the sales/purchase invoice form's "Godowns" field. */
export async function selectDocumentWarehouse(page: Page, warehouseName: string, isDefault = false) {
  await page.getByLabel('Godowns').click();
  const label = isDefault ? `${warehouseName} (default)` : warehouseName;
  await page.getByRole('option', { name: label, exact: true }).click();
}

export async function addInvoiceItem(page: Page, sku: string) {
  const itemInput = page.getByPlaceholder('+ Add Item / Scan barcode or search SKU / name');
  await itemInput.click();
  await itemInput.fill(sku);
  await page.getByRole('option', { name: new RegExp(sku) }).click();
}

export async function createWarehouse(page: Page, name: string) {
  await page.goto('/inventory/warehouses');
  await page.getByRole('button', { name: 'Add godown' }).click();
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('row', { name: new RegExp(name) })).toBeVisible();
}

/** Read the exact On Hand quantity for one product in one specific godown
 * from the Current Stock page — filtering by godown (rather than reading the
 * default "All godowns" aggregate row) is what actually proves a mutation
 * landed on the right warehouse and not just somewhere in the company. */
export async function readGodownStock(page: Page, warehouseName: string, productName: string): Promise<number> {
  await page.goto('/inventory/stock');
  await page.getByLabel('Godowns').click();
  await page.getByRole('option', { name: warehouseName, exact: true }).click();
  const row = page.getByRole('row', { name: new RegExp(productName) });
  await expect(row).toBeVisible();
  const cells = await row.locator('td').allTextContents();
  // Columns: Name, SKU, Godowns, Nearest expiry, On Hand, Reserved, Available.
  const onHand = cells[4]?.trim();
  expect(onHand, `could not read On Hand from row: ${cells.join(' | ')}`).toBeTruthy();
  return Number(onHand);
}

export async function fillNamedCombobox(
  page: Page,
  label: string,
  value: string,
  optionName?: string | RegExp,
) {
  const combo = page.getByRole('combobox', { name: label, exact: true });
  await combo.click();
  await combo.fill(value);
  await page.getByRole('option', { name: optionName ?? value }).click();
}

export async function completeSalesReturn(page: Page, invoiceNumber: string) {
  await page.goto('/sales/returns');
  await page.getByRole('button', { name: 'New sales return' }).first().click();
  await fillNamedCombobox(page, 'Original invoice', invoiceNumber, new RegExp(invoiceNumber));
  const include = page.getByRole('checkbox').first();
  await expect(include).toBeVisible({ timeout: 15_000 });
  await include.check();
  await page.getByRole('button', { name: 'Complete', exact: true }).click();
  await expect(page.getByText('Sales return completed')).toBeVisible({ timeout: 20_000 });
}

export async function enableAccounting(page: Page) {
  await page.goto('/settings/accounting');
  await page.getByRole('button', { name: 'Enable accounting' }).click();
  await expect(page.getByText(/Accounting enabled|CoA seeded/i)).toBeVisible({ timeout: 60_000 });
}

/** Regular GST close requires a company GSTIN (GSTIN_MISSING_COMPANY is critical). */
export async function saveCompanyGstin(page: Page, gstin = '29AAAAA0000A1ZY') {
  await page.goto('/settings/gst');
  const field = page.getByLabel('Primary GSTIN (15 characters)');
  await expect(field).toBeVisible({ timeout: 20_000 });
  await field.fill(gstin);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('GST settings saved')).toBeVisible({ timeout: 15_000 });
}

/** Local/CI payment links need an explicit sandbox provider (BB-000265). */
export async function enableSandboxPayments(page: Page) {
  await page.goto('/settings/payment-gateway');
  await page.getByLabel('Provider').click();
  await page.getByRole('option', { name: /sandbox/i }).click();
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.getByText('Gateway settings saved')).toBeVisible({ timeout: 15_000 });
}

export async function createQuotationConvertedToOrder(
  page: Page,
  opts: { customerName: string; sku: string },
) {
  await page.goto('/sales/quotations');
  await page.getByRole('button', { name: 'New quotation' }).click();
  await fillNamedCombobox(page, 'Customer', opts.customerName);
  await fillNamedCombobox(page, 'Products', opts.sku, new RegExp(opts.sku));
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('button', { name: 'To Order' })).toBeVisible();
  await page.getByRole('button', { name: 'To Order' }).click();
  const convertDialog = page.getByRole('dialog');
  await expect(convertDialog).toBeVisible();
  await convertDialog.getByRole('button', { name: 'To Order' }).click();
  await expect(page).toHaveURL(/\/sales\/orders/, { timeout: 20_000 });
}

export async function convertDraftOrderToCompletedInvoiceViaChallan(page: Page) {
  await expect(page.getByRole('button', { name: 'To Challan' })).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'To Challan' }).click();
  await expect(page).toHaveURL(/\/sales\/delivery-challans/);
  await expect(page.getByRole('button', { name: 'Complete', exact: true }).first()).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole('button', { name: 'Complete', exact: true }).first().click();
  await expect(page.getByRole('button', { name: 'Convert to invoice' })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Convert to invoice' }).click();
  await expect(page).toHaveURL(/\/sales\/history\/\d+\/edit/);
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/history/, { timeout: 20_000 });
}

export async function completeResidualSalesDebitNote(
  page: Page,
  opts: { invoiceNumber: string; productName: string },
) {
  await page.goto('/sales/debit-notes/new');
  await fillNamedCombobox(page, 'Source invoice', opts.invoiceNumber, new RegExp(opts.invoiceNumber));
  await page.getByRole('button', { name: opts.productName }).click();
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/sales\/debit-notes\/\d+/, { timeout: 20_000 });
  await expect(
    page.getByRole('button', { name: 'Cancel document' }).or(page.getByText('Completed', { exact: true }).first()),
  ).toBeVisible({ timeout: 10_000 });
}

export async function completeResidualPurchaseDebitNote(
  page: Page,
  opts: { supplierName: string; purchaseNumber: string },
) {
  await page.goto('/purchases/debit-notes/new');
  await fillNamedCombobox(page, 'Supplier', opts.supplierName);
  await fillNamedCombobox(
    page,
    'Purchase invoice (optional)',
    opts.purchaseNumber,
    new RegExp(opts.purchaseNumber),
  );
  await page.getByRole('button', { name: 'Save & Complete' }).click();
  await expect(page).toHaveURL(/\/purchases\/debit-notes\/\d+/, { timeout: 20_000 });
  await expect(
    page.getByRole('button', { name: 'Cancel document' }).or(page.getByText('Completed', { exact: true }).first()),
  ).toBeVisible({ timeout: 10_000 });
}

export async function completePurchaseReturn(page: Page, purchaseNumber: string) {
  await page.goto('/purchases/returns');
  await page.getByRole('button', { name: 'New purchase return' }).first().click();
  await fillNamedCombobox(page, 'Original purchase', purchaseNumber, new RegExp(purchaseNumber));
  const include = page.getByRole('checkbox').first();
  await expect(include).toBeVisible({ timeout: 15_000 });
  await include.check();
  await page.getByRole('button', { name: 'Complete', exact: true }).click();
  await expect(page.getByText('Purchase return completed')).toBeVisible({ timeout: 20_000 });
}

export async function createPaymentLinkAndReadPublicPath(page: Page, invoiceNumber: string) {
  await enableSandboxPayments(page);
  await page.goto('/sales/history');
  await page.getByRole('link', { name: invoiceNumber }).click();
  await expect(page).toHaveURL(/\/sales\/history\/\d+/);
  await page.getByRole('button', { name: 'Create payment link' }).click();
  await expect(page.getByText('Payment link created')).toBeVisible({ timeout: 15_000 });
  const href =
    (await page.locator('a[href*="/pay/"]').first().getAttribute('href')) ||
    (await page.getByRole('link', { name: 'Open' }).getAttribute('href'));
  expect(href, 'payment link Open href').toBeTruthy();
  const path = href!.startsWith('http') ? new URL(href!).pathname.replace(/\/sandbox\/.*$/, '') : href!;
  expect(path).toMatch(/\/pay\//);
  return path;
}

export async function posCompleteCashSale(page: Page) {
  await page.getByRole('button', { name: /^Cash — ₹/ }).click();
  const done = page.getByText(/Sale complete/i);
  for (let i = 0; i < 6; i += 1) {
    if (await done.isVisible().catch(() => false)) return;
    const confirm = page.getByRole('button', { name: /Complete as/i }).first();
    if (await confirm.isVisible().catch(() => false)) {
      // Dialogs unmount as soon as they confirm; a long click retry on a
      // detached node ate the whole ARCH-01 budget after the sale already posted.
      await confirm.click({ force: true, timeout: 3_000 }).catch(() => undefined);
      continue;
    }
    await done.waitFor({ state: 'visible', timeout: 2_000 }).catch(() => undefined);
  }
  await expect(done).toBeVisible({ timeout: 20_000 });
}

export function unique() {
  return `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

export async function signOut(page: Page) {
  await page.keyboard.press('Escape').catch(() => undefined);
  const dialog = page.getByRole('dialog');
  if (await dialog.isVisible().catch(() => false)) {
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden({ timeout: 5_000 }).catch(() => undefined);
  }
  const signOutBtn = page.getByRole('button', { name: /^(Sign out|साइन आउट)$/ });
  if (!(await signOutBtn.first().isVisible().catch(() => false))) {
    await page.getByRole('button', { name: /open navigation/i }).click();
  }
  await signOutBtn.first().click({ force: true });
  await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });
}

export async function loginWithPassword(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });
}

/** Invite a staff member with a known password (development invite token path). */
export async function inviteStaff(
  page: Page,
  opts: {
    email: string;
    password: string;
    fullName: string;
    role: 'SALES_STAFF' | 'ACCOUNTANT' | 'INVENTORY_STAFF';
  },
) {
  await page.goto('/settings/users');
  await page.getByRole('button', { name: 'Invite user' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Email').fill(opts.email);
  await dialog.getByLabel('Password', { exact: true }).fill(opts.password);
  await dialog.getByLabel('Full name').fill(opts.fullName);
  await dialog.getByLabel('Role').click();
  const roleLabel =
    opts.role === 'ACCOUNTANT'
      ? 'Accountant'
      : opts.role === 'INVENTORY_STAFF'
        ? 'Inventory staff'
        : 'Sales staff';
  await page.getByRole('option', { name: roleLabel }).click();
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(dialog.getByText(/Account created|They can sign in/i)).toBeVisible({ timeout: 20_000 });
  await dialog.getByRole('button', { name: 'Cancel' }).click();
}

export async function inviteStaffViaToken(page: Page, opts: { email: string; fullName: string }) {
  await page.goto('/settings/users');
  await page.getByRole('button', { name: 'Invite user' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Email').fill(opts.email);
  await dialog.getByLabel('Full name').fill(opts.fullName);
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  const alert = dialog.getByText(/Invite (link|token):/);
  await expect(alert).toBeVisible({ timeout: 20_000 });
  const text = (await alert.textContent()) || '';
  const urlMatch = text.match(/https?:\/\/\S+|\/invite\?[^\s]+/i);
  const tokenMatch = text.match(/Invite token:\s*(\S+)/i);
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toBeHidden({ timeout: 5_000 });
  return { inviteUrl: urlMatch?.[0] ?? null, inviteToken: tokenMatch?.[1] ?? null, raw: text };
}
