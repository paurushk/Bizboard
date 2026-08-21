const { createAuditBrowser } = require('./helper.cjs');

async function runPhase1And2() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;

  try {
    console.log('=== PHASE 1: PRE-FLIGHT & LOGIN ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await takeScreenshot('UXW2-001_phase1_dashboard');

    console.log('=== PHASE 2.1: COMPANY SETTINGS & GSTIN VALIDATION ===');
    await page.goto('http://localhost/settings/company');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-002_company_settings_initial');

    console.log('=== PHASE 2.2: SUPPLIER CREATION ===');
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-003_suppliers_list');

    console.log('=== PHASE 2.3: PRODUCT / INVENTORY SETUP ===');
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-005_products_list');

    console.log('=== PHASE 2.4: PURCHASE INVOICE ===');
    await page.goto('http://localhost/purchases/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-007_new_purchase_invoice');

    console.log('=== PHASE 2.5: CUSTOMER CREATION ===');
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-008_customers_list');

    console.log('=== PHASE 2.6: SALES INVOICE ===');
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-009_new_sales_invoice');

    console.log('=== PHASE 2.7: REPORTS & LEDGERS ===');
    await page.goto('http://localhost/reports/sales');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-010_sales_report');

    await page.goto('http://localhost/reports/purchases');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-011_purchases_report');

    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-012_stock_summary');

    await page.goto('http://localhost/reports/customer-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-013_customer_ledger');

    await page.goto('http://localhost/reports/supplier-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-014_supplier_ledger');

    console.log('Probe run completed successfully!');
  } catch (err) {
    console.error('Error during probe run:', err);
    await takeScreenshot('UXW2-ERROR_phase1_2');
  } finally {
    await audit.cleanup();
  }
}

runPhase1And2();
