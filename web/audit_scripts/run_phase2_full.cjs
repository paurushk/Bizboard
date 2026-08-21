const { createAuditBrowser } = require('./helper.cjs');

async function runPhase2Full() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;

  try {
    console.log('=== PHASE 1: LOGIN & PRE-FLIGHT ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-001_dashboard_loaded');

    // -------------------------------------------------------------
    // STEP 1: COMPANY SETUP & SETTINGS
    // -------------------------------------------------------------
    console.log('=== STEP 1: COMPANY SETUP & SETTINGS ===');
    await page.goto('http://localhost/settings/company');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-002_company_settings_view');

    // Test invalid GSTIN in company settings
    const gstinField = page.locator('label:has-text("GSTIN")').locator('..').locator('input').first();
    if (await gstinField.count() > 0) {
      await gstinField.fill('INVALID_GSTIN_123');
      const saveCompanyBtn = page.locator('button:has-text("Save"), button:has-text("Update")').first();
      await saveCompanyBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-003_company_gstin_invalid_feedback');

      // Put valid GSTIN for Karnataka: 29AABCU9603R1ZM
      await gstinField.fill('29AABCU9603R1ZM');
      await saveCompanyBtn.click();
      await page.waitForTimeout(1000);
      await takeScreenshot('UXW2-004_company_settings_saved');
    }

    // -------------------------------------------------------------
    // STEP 2: SUPPLIER CREATION (UXWAVE2-Supplier-Alpha)
    // -------------------------------------------------------------
    console.log('=== STEP 2: SUPPLIER CREATION ===');
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-005_suppliers_list_before');

    // Click "Add"
    await page.locator('button:has-text("Add")').first().click();
    await page.waitForTimeout(800);
    await takeScreenshot('UXW2-006_supplier_modal_empty_save_disabled');

    // Fill supplier details
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

    // Click Save
    const suppSaveBtn = page.locator('div[role="dialog"] button:has-text("Save")').first();
    await suppSaveBtn.click();
    await page.waitForTimeout(1500);
    await takeScreenshot('UXW2-009_supplier_created_in_list');

    // -------------------------------------------------------------
    // STEP 3: PRODUCT / INVENTORY SETUP (UXWAVE2-Item-Widget)
    // -------------------------------------------------------------
    console.log('=== STEP 3: PRODUCT / INVENTORY SETUP ===');
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-010_products_list_before');

    // Click "Add"
    await page.locator('button:has-text("Add")').first().click();
    await page.waitForTimeout(800);
    await takeScreenshot('UXW2-011_product_modal_empty');

    const prodNameInput = page.locator('div[role="dialog"] label:has-text("Name")').locator('..').locator('input').first();
    await prodNameInput.fill('UXWAVE2-Item-Widget');

    const prodSkuInput = page.locator('div[role="dialog"] label:has-text("SKU")').locator('..').locator('input').first();
    await prodSkuInput.fill('UXW2-WIDGET-01');

    // Test invalid HSN (3 digits)
    const prodHsnInput = page.locator('div[role="dialog"] label:has-text("HSN")').locator('..').locator('input').first();
    await prodHsnInput.fill('847');
    await page.waitForTimeout(400);
    await takeScreenshot('UXW2-012_product_invalid_hsn_feedback');

    // Fix HSN to 84713010
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

    // Stock Adjustment to set Opening Stock = 10
    console.log('=== SETTING OPENING STOCK (10 units) VIA ADJUSTMENT ===');
    await page.goto('http://localhost/inventory/adjustments');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-015_stock_adjustments_page');

    // Check if adjustment form / button exists
    const addAdjBtn = page.locator('button:has-text("Add"), button:has-text("Adjust"), button:has-text("New")').first();
    if (await addAdjBtn.count() > 0 && await addAdjBtn.isVisible()) {
      await addAdjBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-016_stock_adj_dialog');

      // Select product
      const adjProdInput = page.locator('div[role="dialog"] input').first();
      await adjProdInput.click();
      await adjProdInput.fill('UXWAVE2-Item-Widget');
      await page.waitForTimeout(500);
      const adjProdOpt = page.locator('li:has-text("UXWAVE2-Item-Widget")').first();
      if (await adjProdOpt.isVisible()) await adjProdOpt.click();

      // Enter quantity 10
      const adjQtyInput = page.locator('div[role="dialog"] label:has-text("Quantity"), div[role="dialog"] label:has-text("Qty")').locator('..').locator('input').first();
      if (await adjQtyInput.count() > 0) {
        await adjQtyInput.fill('10');
      }

      const adjReason = page.locator('div[role="dialog"] label:has-text("Reason"), div[role="dialog"] label:has-text("Notes")').locator('..').locator('input, textarea').first();
      if (await adjReason.count() > 0) {
        await adjReason.fill('Opening Stock Wave2');
      }

      await takeScreenshot('UXW2-017_stock_adj_filled');
      const adjSaveBtn = page.locator('div[role="dialog"] button:has-text("Save"), div[role="dialog"] button:has-text("Adjust")').first();
      if (await adjSaveBtn.isVisible()) {
        await adjSaveBtn.click();
        await page.waitForTimeout(1500);
      }
    }

    // Check stock summary
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-018_stock_summary_after_opening');

    // -------------------------------------------------------------
    // STEP 4: PURCHASE INVOICE (20 units from UXWAVE2-Supplier-Alpha)
    // -------------------------------------------------------------
    console.log('=== STEP 4: PURCHASE INVOICE CREATION ===');
    await page.goto('http://localhost/purchases/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-019_purchase_new_empty');

    // Select Supplier: UXWAVE2-Supplier-Alpha
    const suppInput = page.locator('input[placeholder*="Type 2+"]').first();
    await suppInput.focus();
    await suppInput.pressSequentially('Supplier-Alpha', { delay: 100 });
    await page.waitForTimeout(1000);

    const suppOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Supplier-Alpha' }).first();
    if (await suppOpt.count() > 0) {
      await suppOpt.click();
    } else {
      await page.locator('li[role="option"]').first().click();
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-020_purchase_supplier_selected');

    // Add Product: UXWAVE2-Item-Widget
    const prodSearchInput = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
    await prodSearchInput.focus();
    await prodSearchInput.pressSequentially('UXW2-WIDGET', { delay: 100 });
    await page.waitForTimeout(1000);

    const prodSelectOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Item-Widget' }).first();
    if (await prodSelectOpt.count() > 0) {
      await prodSelectOpt.click();
    } else {
      await page.locator('li[role="option"]').first().click();
    }
    await page.waitForTimeout(1000);

    // Edit Quantity to 20
    const purchaseRowQty = page.locator('table tbody tr td').locator('input').nth(1);
    if (await purchaseRowQty.isVisible()) {
      await purchaseRowQty.fill('20');
      await page.keyboard.press('Tab');
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-021_purchase_invoice_20_units_taxes_calculated');

    // Save & Complete Purchase
    const purchaseSaveAction = page.locator('button:has-text("Save & Complete")').first();
    console.log('Purchase Save & Complete disabled:', await purchaseSaveAction.isDisabled());
    await purchaseSaveAction.click();
    await page.waitForTimeout(2500);
    await takeScreenshot('UXW2-022_purchase_invoice_saved_result');

    // Check stock: should be opening stock + 20
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-023_stock_after_purchase');

    // -------------------------------------------------------------
    // STEP 5: CUSTOMER CREATION (UXWAVE2-Customer-Beta)
    // -------------------------------------------------------------
    console.log('=== STEP 5: CUSTOMER CREATION ===');
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-024_customers_list_before');

    await page.locator('button:has-text("Add")').first().click();
    await page.waitForTimeout(800);
    await takeScreenshot('UXW2-025_customer_modal_empty');

    const custNameField = page.locator('div[role="dialog"] label:has-text("Name")').locator('..').locator('input').first();
    await custNameField.fill('UXWAVE2-Customer-Beta');

    const custPhoneField = page.locator('div[role="dialog"] label:has-text("Phone")').locator('..').locator('input').first();
    await custPhoneField.fill('9876501234');

    // Customer in Karnataka (Intra-state for company)
    const custGstinField = page.locator('div[role="dialog"] label:has-text("GSTIN")').locator('..').locator('input').first();
    await custGstinField.fill('29ABCDE1234F1Z5');
    await page.waitForTimeout(500);

    const custAddressField = page.locator('div[role="dialog"] label:has-text("Address")').locator('..').locator('input, textarea').first();
    await custAddressField.fill('123 MG Road, Bengaluru, Karnataka 560001');

    await takeScreenshot('UXW2-026_customer_form_filled');

    const custSaveBtn = page.locator('div[role="dialog"] button:has-text("Save")').first();
    await custSaveBtn.click();
    await page.waitForTimeout(1500);
    await takeScreenshot('UXW2-027_customer_created_in_list');

    // -------------------------------------------------------------
    // STEP 6: SALES INVOICE (5 units to UXWAVE2-Customer-Beta)
    // -------------------------------------------------------------
    console.log('=== STEP 6: SALES INVOICE CREATION ===');
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-028_sales_new_empty');

    // Select Customer: UXWAVE2-Customer-Beta
    const salesPartyInput = page.locator('input[placeholder*="Type 2+"]').first();
    await salesPartyInput.focus();
    await salesPartyInput.pressSequentially('Customer-Beta', { delay: 100 });
    await page.waitForTimeout(1000);

    const custOption = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Customer-Beta' }).first();
    if (await custOption.count() > 0) {
      await custOption.click();
    } else {
      await page.locator('li[role="option"]').first().click();
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-029_sales_customer_selected');

    // Add Product: UXWAVE2-Item-Widget
    const sItemSearch = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
    await sItemSearch.focus();
    await sItemSearch.pressSequentially('UXW2-WIDGET', { delay: 100 });
    await page.waitForTimeout(1000);

    const sProdOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Item-Widget' }).first();
    if (await sProdOpt.count() > 0) {
      await sProdOpt.click();
    } else {
      await page.locator('li[role="option"]').first().click();
    }
    await page.waitForTimeout(1000);

    // Edit Quantity to 5
    const salesRowQty = page.locator('table tbody tr td').locator('input').nth(1);
    if (await salesRowQty.isVisible()) {
      await salesRowQty.fill('5');
      await page.keyboard.press('Tab');
    }
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-030_sales_invoice_5_units_taxes_calculated');

    // Save & Complete Sales Invoice
    const salesSaveAction = page.locator('button:has-text("Save & Complete")').first();
    console.log('Sales Save & Complete disabled:', await salesSaveAction.isDisabled());
    await salesSaveAction.click();
    await page.waitForTimeout(2500);
    await takeScreenshot('UXW2-031_sales_invoice_saved_result');

    // Check stock: should be decreased by 5
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-032_stock_after_sale_decreased');

    // -------------------------------------------------------------
    // STEP 7: REPORTS & LEDGERS VERIFICATION
    // -------------------------------------------------------------
    console.log('=== STEP 7: REPORTS & LEDGERS VERIFICATION ===');
    await page.goto('http://localhost/reports/sales');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-033_sales_register_report');

    await page.goto('http://localhost/reports/purchases');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-034_purchases_register_report');

    await page.goto('http://localhost/reports/customer-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-035_customer_ledger_overview');

    await page.goto('http://localhost/reports/supplier-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-036_supplier_ledger_overview');

    console.log('=== PHASE 2 COMPLETED 100% CLEANLY ===');
  } catch (err) {
    console.error('Error during Phase 2 Full Run:', err);
    await takeScreenshot('UXW2-ERROR_phase2_full');
  } finally {
    await audit.cleanup();
  }
}

runPhase2Full();
