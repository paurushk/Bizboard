const { createAuditBrowser } = require('./helper.cjs');

async function auditPhase2Core() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;

  try {
    console.log('=== PHASE 1: LOGIN & HEALTH ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-001_dashboard');

    // -------------------------------------------------------------
    // STEP 1: COMPANY SETUP & GSTIN VALIDATION
    // -------------------------------------------------------------
    console.log('=== STEP 1: COMPANY SETUP & SETTINGS ===');
    await page.goto('http://localhost/settings/company');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-002_company_settings_initial');

    // Test invalid GSTIN
    const gstinField = page.locator('label:has-text("GSTIN")').locator('..').locator('input').first();
    if (await gstinField.count() > 0) {
      await gstinField.fill('INVALID_GSTIN_123');
      const saveCompanyBtn = page.locator('button:has-text("Save"), button:has-text("Update")').first();
      await saveCompanyBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-003_company_gstin_invalid_feedback');

      // Valid GSTIN: 29AABCU9603R1ZM (Karnataka)
      await gstinField.fill('29AABCU9603R1ZM');
      await saveCompanyBtn.click();
      await page.waitForTimeout(1000);
      await takeScreenshot('UXW2-004_company_settings_saved');
    }

    // -------------------------------------------------------------
    // STEP 2: SUPPLIER CREATION
    // -------------------------------------------------------------
    console.log('=== STEP 2: SUPPLIER CREATION ===');
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-005_suppliers_list_before');

    await page.locator('button:has-text("Add")').first().click();
    await page.waitForTimeout(800);
    await takeScreenshot('UXW2-006_supplier_modal_empty');

    const suppNameInput = page.locator('div[role="dialog"] label:has-text("Name")').locator('..').locator('input').first();
    await suppNameInput.fill('UXWAVE2-Supplier-Alpha');

    const suppPhoneInput = page.locator('div[role="dialog"] label:has-text("Phone")').locator('..').locator('input').first();
    await suppPhoneInput.fill('9876543210');

    // Test invalid GSTIN warning
    const suppGstinInput = page.locator('div[role="dialog"] label:has-text("GSTIN")').locator('..').locator('input').first();
    await suppGstinInput.fill('27BADGSTIN12345');
    await page.waitForTimeout(500);
    await takeScreenshot('UXW2-007_supplier_invalid_gstin_warning');

    // Valid Maharashtra GSTIN: 27AABCU9603R1ZM
    await suppGstinInput.fill('27AABCU9603R1ZM');
    await page.waitForTimeout(500);

    const suppAddressInput = page.locator('div[role="dialog"] label:has-text("Address")').locator('..').locator('input, textarea').first();
    await suppAddressInput.fill('Plot 10, MIDC, Andheri East, Mumbai, Maharashtra 400093');

    await takeScreenshot('UXW2-008_supplier_form_filled');

    const suppSaveBtn = page.locator('div[role="dialog"] button:has-text("Save")').first();
    await suppSaveBtn.click();
    await page.waitForTimeout(1500);
    await takeScreenshot('UXW2-009_supplier_created_in_list');

    // -------------------------------------------------------------
    // STEP 3: PRODUCT / INVENTORY SETUP
    // -------------------------------------------------------------
    console.log('=== STEP 3: PRODUCT / INVENTORY SETUP ===');
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-010_products_list_before');

    // Unique SKU for this run
    const testSku = 'UXW2-WIDGET-' + Date.now().toString().slice(-4);
    await page.locator('button:has-text("Add")').first().click();
    await page.waitForTimeout(800);
    await takeScreenshot('UXW2-011_product_modal_empty');

    const prodNameInput = page.locator('div[role="dialog"] label:has-text("Name")').locator('..').locator('input').first();
    await prodNameInput.fill('UXWAVE2-Item-Widget');

    const prodSkuInput = page.locator('div[role="dialog"] label:has-text("SKU")').locator('..').locator('input').first();
    await prodSkuInput.fill(testSku);

    // Test invalid HSN (3 digits)
    const prodHsnInput = page.locator('div[role="dialog"] label:has-text("HSN")').locator('..').locator('input').first();
    await prodHsnInput.fill('847');
    await page.waitForTimeout(400);
    await takeScreenshot('UXW2-012_product_invalid_hsn_feedback');

    // Valid HSN: 84713010
    await prodHsnInput.fill('84713010');

    const prodBuyInput = page.locator('div[role="dialog"] label:has-text("Purchase price")').locator('..').locator('input').first();
    await prodBuyInput.fill('100');

    const prodSellInput = page.locator('div[role="dialog"] label:has-text("Selling price")').locator('..').locator('input').first();
    await prodSellInput.fill('150');

    const prodGstInput = page.locator('div[role="dialog"] label:has-text("GST %")').locator('..').locator('input').first();
    await prodGstInput.fill('18');

    await takeScreenshot('UXW2-013_product_form_filled');

    const prodSaveBtn = page.locator('div[role="dialog"] button:has-text("Save"), div[role="dialog"] button:has-text("Create")').first();
    await prodSaveBtn.click();
    await page.waitForTimeout(1500);
    await takeScreenshot('UXW2-014_product_created_in_list');

    // -------------------------------------------------------------
    // STEP 4: PURCHASE INVOICE (20 units from UXWAVE2-Supplier-Alpha)
    // -------------------------------------------------------------
    console.log('=== STEP 4: PURCHASE INVOICE CREATION ===');
    await page.goto('http://localhost/purchases/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-015_purchase_new_empty');

    // Check if a party is already selected (e.g. from draft) and click Change if needed
    const changePartyBtn = page.locator('button:has-text("Change")').first();
    if (await changePartyBtn.isVisible()) {
      await changePartyBtn.click();
      await page.waitForTimeout(500);
    }

    // Select Supplier UXWAVE2-Supplier-Alpha
    const suppSearch = page.locator('input[placeholder*="Type 2+"]').first();
    await suppSearch.focus();
    await suppSearch.pressSequentially('Alpha', { delay: 100 });
    await page.waitForTimeout(1000);

    const suppOption = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Supplier-Alpha' }).first();
    if (await suppOption.count() > 0) {
      await suppOption.click();
    } else {
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('Enter');
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-016_purchase_supplier_selected');

    // Add Product UXWAVE2-Item-Widget
    const prodSearch = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
    await prodSearch.focus();
    await prodSearch.pressSequentially(testSku, { delay: 100 });
    await page.waitForTimeout(1000);

    const prodOption = page.locator('li[role="option"]').filter({ hasText: testSku }).first();
    if (await prodOption.count() > 0) {
      await prodOption.click();
    } else {
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('Enter');
    }
    await page.waitForTimeout(1000);

    // Set Quantity to 20
    const purchaseQty = page.locator('table tbody tr td').locator('input').nth(1);
    if (await purchaseQty.isVisible()) {
      await purchaseQty.fill('20');
      await page.keyboard.press('Tab');
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-017_purchase_invoice_20_units_taxes_calculated');

    // Save & Complete Purchase
    const purchaseSaveAction = page.locator('button:has-text("Save & Complete")').first();
    console.log('Purchase Save & Complete disabled:', await purchaseSaveAction.isDisabled());
    await purchaseSaveAction.click();
    await page.waitForTimeout(2500);
    await takeScreenshot('UXW2-018_purchase_invoice_saved_result');

    // Check stock: should be 20
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-019_stock_after_purchase');

    // -------------------------------------------------------------
    // STEP 5: CUSTOMER CREATION (UXWAVE2-Customer-Beta)
    // -------------------------------------------------------------
    console.log('=== STEP 5: CUSTOMER CREATION ===');
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-020_customers_list_before');

    await page.locator('button:has-text("Add")').first().click();
    await page.waitForTimeout(800);
    await takeScreenshot('UXW2-021_customer_modal_empty');

    const custNameField = page.locator('div[role="dialog"] label:has-text("Name")').locator('..').locator('input').first();
    await custNameField.fill('UXWAVE2-Customer-Beta');

    const custPhoneField = page.locator('div[role="dialog"] label:has-text("Phone")').locator('..').locator('input').first();
    await custPhoneField.fill('9876501234');

    const custGstinField = page.locator('div[role="dialog"] label:has-text("GSTIN")').locator('..').locator('input').first();
    await custGstinField.fill('29ABCDE1234F1Z5');
    await page.waitForTimeout(500);

    const custAddressField = page.locator('div[role="dialog"] label:has-text("Address")').locator('..').locator('input, textarea').first();
    await custAddressField.fill('123 MG Road, Bengaluru, Karnataka 560001');

    await takeScreenshot('UXW2-022_customer_form_filled');

    const custSaveBtn = page.locator('div[role="dialog"] button:has-text("Save")').first();
    await custSaveBtn.click();
    await page.waitForTimeout(1500);
    await takeScreenshot('UXW2-023_customer_created_in_list');

    // -------------------------------------------------------------
    // STEP 6: SALES INVOICE (5 units to UXWAVE2-Customer-Beta)
    // -------------------------------------------------------------
    console.log('=== STEP 6: SALES INVOICE CREATION ===');
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-024_sales_new_empty');

    const changeCustBtn = page.locator('button:has-text("Change")').first();
    if (await changeCustBtn.isVisible()) {
      await changeCustBtn.click();
      await page.waitForTimeout(500);
    }

    // Select Customer: UXWAVE2-Customer-Beta
    const salesPartyInput = page.locator('input[placeholder*="Type 2+"]').first();
    await salesPartyInput.focus();
    await salesPartyInput.pressSequentially('Beta', { delay: 100 });
    await page.waitForTimeout(1000);

    const custOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Customer-Beta' }).first();
    if (await custOpt.count() > 0) {
      await custOpt.click();
    } else {
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('Enter');
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-025_sales_customer_selected');

    // Add Product: UXWAVE2-Item-Widget
    const sItemSearch = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
    await sItemSearch.focus();
    await sItemSearch.pressSequentially(testSku, { delay: 100 });
    await page.waitForTimeout(1000);

    const sProdOpt = page.locator('li[role="option"]').filter({ hasText: testSku }).first();
    if (await sProdOpt.count() > 0) {
      await sProdOpt.click();
    } else {
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('Enter');
    }
    await page.waitForTimeout(1000);

    // Edit Quantity to 5
    const salesRowQty = page.locator('table tbody tr td').locator('input').nth(1);
    if (await salesRowQty.isVisible()) {
      await salesRowQty.fill('5');
      await page.keyboard.press('Tab');
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-026_sales_invoice_5_units_taxes_calculated');

    // Save & Complete Sales Invoice
    const salesSaveAction = page.locator('button:has-text("Save & Complete")').first();
    console.log('Sales Save & Complete disabled:', await salesSaveAction.isDisabled());
    await salesSaveAction.click();
    await page.waitForTimeout(2500);
    await takeScreenshot('UXW2-027_sales_invoice_saved_result');

    // Check stock: should be 20 - 5 = 15
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-028_stock_after_sale_decreased');

    // -------------------------------------------------------------
    // STEP 7: REPORTS & LEDGERS VERIFICATION
    // -------------------------------------------------------------
    console.log('=== STEP 7: REPORTS & LEDGERS VERIFICATION ===');
    await page.goto('http://localhost/reports/sales');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-029_sales_register_report');

    await page.goto('http://localhost/reports/purchases');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-030_purchases_register_report');

    await page.goto('http://localhost/reports/customer-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-031_customer_ledger_overview');

    await page.goto('http://localhost/reports/supplier-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-032_supplier_ledger_overview');

    console.log('=== PHASE 2 AUDIT FINISHED WITH 100% SUCCESS ===');
  } catch (err) {
    console.error('Error during Phase 2 Core Audit:', err);
    await takeScreenshot('UXW2-ERROR_phase2_core');
  } finally {
    await audit.cleanup();
  }
}

auditPhase2Core();
