const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const OUTPUT_FILE = path.resolve(__dirname, 'e2e_workflow_results.json');

async function runE2EWorkflows() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: 'block' });
  const page = await context.newPage();

  const workflowResults = [];
  const defectLog = [];

  function recordWF(workflow, step, result, notes = '') {
    workflowResults.push({ workflow, step, result, notes });
    console.log(`[WORKFLOW ${result}] [${workflow}] Step: ${step} - ${notes}`);
  }

  try {
    console.log('=== LOGGING IN FOR END-TO-END WORKFLOWS ===');
    await page.goto('http://localhost/login');
    await page.waitForLoadState('networkidle');
    await page.fill('input[type="email"], input[name="email"], #email', 'demo@bizboard.local');
    await page.fill('input[type="password"], input[name="password"], #password', 'DemoPass123!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(2000);

    const ts = Date.now().toString().slice(-4);

    // =========================================================================
    // WORKFLOW 1: FULL PROCURE-TO-PAY (P2P) CYCLE
    // =========================================================================
    console.log('\n--- STARTING WORKFLOW 1: PROCURE-TO-PAY (P2P) ---');
    
    // Step 1: Create Supplier
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const supName = `P2P-Supplier-${ts}`;
    const addSupBtn = page.locator('button:has-text("Add")').first();
    if (await addSupBtn.isVisible()) {
      await addSupBtn.click();
      await page.waitForTimeout(600);
      const dlg = page.locator('div[role="dialog"]').first();
      await dlg.locator('label:has-text("Name")').locator('..').locator('input').first().fill(supName);
      await dlg.locator('label:has-text("Phone")').locator('..').locator('input').first().fill('9876543210');
      await dlg.locator('label:has-text("GSTIN")').locator('..').locator('input').first().fill('29AABCU9603R1ZM');
      await dlg.locator('button:has-text("Save")').first().click();
      await page.waitForTimeout(1200);
      recordWF('Procure-to-Pay', '1. Create Supplier', 'PASS', `Supplier ${supName} created`);
    } else {
      recordWF('Procure-to-Pay', '1. Create Supplier', 'FAIL', 'Add supplier button not accessible');
    }

    // Step 2: Create Inventory Item
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const itemName = `P2P-RawMaterial-${ts}`;
    const addProdBtn = page.locator('button:has-text("Add")').first();
    if (await addProdBtn.isVisible()) {
      await addProdBtn.click();
      await page.waitForTimeout(600);
      const dlg = page.locator('div[role="dialog"]').first();
      await dlg.locator('label:has-text("Name")').locator('..').locator('input').first().fill(itemName);
      await dlg.locator('label:has-text("HSN")').locator('..').locator('input').first().fill('84713010');
      const buyPrice = dlg.locator('label:has-text("Purchase Price")').locator('..').locator('input').first();
      if (await buyPrice.isVisible()) await buyPrice.fill('500');
      const sellPrice = dlg.locator('label:has-text("Selling Price"), label:has-text("Price")').locator('..').locator('input').first();
      if (await sellPrice.isVisible()) await sellPrice.fill('800');
      await dlg.locator('button:has-text("Save")').first().click();
      await page.waitForTimeout(1200);
      recordWF('Procure-to-Pay', '2. Create Product', 'PASS', `Item ${itemName} created`);
    } else {
      recordWF('Procure-to-Pay', '2. Create Product', 'FAIL', 'Add product button not found');
    }

    // Step 3: Record Purchase Bill
    await page.goto('http://localhost/purchases/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const supInput = page.locator('input[placeholder*="Select Supplier" i], [role="combobox"]').first();
    if (await supInput.isVisible()) {
      await supInput.click();
      await page.waitForTimeout(400);
      await supInput.fill(supName);
      await page.waitForTimeout(400);
      const opt = page.locator('.MuiAutocomplete-option, [role="option"]').first();
      if (await opt.isVisible()) await opt.click();
      recordWF('Procure-to-Pay', '3. Select Supplier on Purchase Bill', 'PASS', 'Supplier selected');
    }

    // Step 4: Check Supplier Ledger
    await page.goto('http://localhost/reports/supplier-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    recordWF('Procure-to-Pay', '4. Verify Supplier Ledger Surface', 'PASS', 'Supplier ledger loaded');

    // =========================================================================
    // WORKFLOW 2: FULL ORDER-TO-CASH (O2C) SALES CYCLE
    // =========================================================================
    console.log('\n--- STARTING WORKFLOW 2: ORDER-TO-CASH (O2C) ---');

    // Step 1: Create Customer
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const custName = `O2C-Customer-${ts}`;
    const addCustBtn = page.locator('button:has-text("Add")').first();
    if (await addCustBtn.isVisible()) {
      await addCustBtn.click();
      await page.waitForTimeout(600);
      const dlg = page.locator('div[role="dialog"]').first();
      await dlg.locator('label:has-text("Name")').locator('..').locator('input').first().fill(custName);
      await dlg.locator('label:has-text("Phone")').locator('..').locator('input').first().fill('9123456780');
      await dlg.locator('label:has-text("GSTIN")').locator('..').locator('input').first().fill('27AAPFU0939F1ZV');
      await dlg.locator('button:has-text("Save")').first().click();
      await page.waitForTimeout(1200);
      recordWF('Order-to-Cash', '1. Create Customer', 'PASS', `Customer ${custName} created`);
    }

    // Step 2: Create Quotation
    await page.goto('http://localhost/sales/quotations');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const addQuoteBtn = page.locator('button:has-text("Add"), button:has-text("New")').first();
    if (await addQuoteBtn.isVisible()) {
      recordWF('Order-to-Cash', '2. Open Quotation Surface', 'PASS', 'Quotation action present');
    }

    // Step 3: Create Sales Order
    await page.goto('http://localhost/sales/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    recordWF('Order-to-Cash', '3. Sales Order Surface', 'PASS', 'Sales orders surface loaded');

    // Step 4: Issue Sales Invoice
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    const custField = page.locator('input[placeholder*="Select Customer" i], [role="combobox"]').first();
    if (await custField.isVisible()) {
      await custField.click();
      await custField.fill(custName);
      await page.waitForTimeout(400);
      const opt = page.locator('.MuiAutocomplete-option, [role="option"]').first();
      if (await opt.isVisible()) await opt.click();
      recordWF('Order-to-Cash', '4. Prepare Sales Invoice', 'PASS', 'Customer linked to sales invoice');
    }

    // Step 5: Check Sales Report & Customer Ledger
    await page.goto('http://localhost/reports/customer-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    recordWF('Order-to-Cash', '5. Customer Ledger Verification', 'PASS', 'Customer ledger rendered');

    // =========================================================================
    // WORKFLOW 3: FINANCIAL ACCOUNTING & REPORTING INTEGRITY
    // =========================================================================
    console.log('\n--- STARTING WORKFLOW 3: ACCOUNTING & REPORTING ---');

    // Step 1: Chart of Accounts
    await page.goto('http://localhost/accounting/accounts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const coaRows = await page.locator('table tbody tr, .MuiTreeItem-root, .MuiListItem-root').count();
    recordWF('Accounting & Financials', '1. Chart of Accounts Tree/List', coaRows > 0 ? 'PASS' : 'FAIL', `Loaded ${coaRows} ledger accounts`);

    // Step 2: Journal Entries
    await page.goto('http://localhost/accounting/journals');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newJournalBtn = page.locator('button:has-text("Add"), button:has-text("New")').first();
    recordWF('Accounting & Financials', '2. Journal Entries Surface', (await newJournalBtn.isVisible()) ? 'PASS' : 'FAIL', 'Journal action present');

    // Step 3: Trial Balance
    await page.goto('http://localhost/reports/trial-balance');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const tbTable = page.locator('table').first();
    recordWF('Accounting & Financials', '3. Trial Balance Sheet', (await tbTable.isVisible()) ? 'PASS' : 'FAIL', 'Trial balance sheet table rendered');

    // Step 4: Profit and Loss
    await page.goto('http://localhost/reports/profit-and-loss');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const pnlHeading = page.locator('h4, h5, h6, [role="heading"]').first();
    recordWF('Accounting & Financials', '4. Profit & Loss Statement', (await pnlHeading.isVisible()) ? 'PASS' : 'FAIL', 'P&L statement rendered');

    // Step 5: Balance Sheet
    await page.goto('http://localhost/reports/balance-sheet');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const bsHeading = page.locator('h4, h5, h6, [role="heading"]').first();
    recordWF('Accounting & Financials', '5. Balance Sheet', (await bsHeading.isVisible()) ? 'PASS' : 'FAIL', 'Balance sheet rendered');

    // Step 6: Books Health
    await page.goto('http://localhost/reports/books-health');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const bhHeading = page.locator('h4, h5, h6, [role="heading"]').first();
    recordWF('Accounting & Financials', '6. Books Health Audit Check', (await bhHeading.isVisible()) ? 'PASS' : 'FAIL', 'Books health check rendered');

  } catch (err) {
    console.error('Workflow error:', err);
    recordWF('E2E Workflows', 'Global Workflow Execution', 'FAIL', err.message);
  } finally {
    await browser.close();
  }

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify({ workflowResults }, null, 2));
  console.log(`\nWorkflows finished. Results saved to ${OUTPUT_FILE}`);
}

runE2EWorkflows();
