const { createAuditBrowser } = require('./helper.cjs');

async function auditCoreChain() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login, consoleLogs, networkErrors } = audit;
  const issues = [];

  try {
    console.log('=== STEP 1: LOGIN & PRE-FLIGHT ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-001_dashboard_loaded');

    // -------------------------------------------------------------
    // STEP 2: COMPANY SETUP & SETTINGS
    // -------------------------------------------------------------
    console.log('=== STEP 2: COMPANY SETTINGS & GSTIN VALIDATION ===');
    await page.goto('http://localhost/settings/company');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-015_company_settings_view');

    // Test invalid GSTIN in Company Settings
    const gstinField = page.locator('input[name="gstin"], #gstin, label:has-text("GSTIN") ~ div input, input[placeholder*="GSTIN"]').first();
    if (await gstinField.isVisible()) {
      await gstinField.fill('INVALID_GSTIN_123');
      const saveBtn = page.locator('button:has-text("Save"), button:has-text("Update")').first();
      await saveBtn.click();
      await page.waitForTimeout(1000);
      await takeScreenshot('UXW2-016_company_gstin_invalid_feedback');
    }

    // -------------------------------------------------------------
    // STEP 3: SUPPLIER CREATION
    // -------------------------------------------------------------
    console.log('=== STEP 3: SUPPLIER CREATION ===');
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Click Add Supplier
    const addSuppBtn = page.locator('button:has-text("Add Supplier"), button:has-text("New Supplier"), button:has-text("Create")').first();
    if (await addSuppBtn.isVisible()) {
      await addSuppBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-017_supplier_dialog_empty');

      // Test empty submit
      const dialogSaveBtn = page.locator('div[role="dialog"] button:has-text("Save"), div[role="dialog"] button:has-text("Create"), div[role="dialog"] button[type="submit"]').first();
      if (await dialogSaveBtn.isVisible()) {
        await dialogSaveBtn.click();
        await page.waitForTimeout(600);
        await takeScreenshot('UXW2-018_supplier_empty_submit_validation');
      }

      // Test invalid GSTIN
      const suppGstinInput = page.locator('div[role="dialog"] input[name="gstin"], div[role="dialog"] label:has-text("GSTIN") ~ div input').first();
      if (await suppGstinInput.isVisible()) {
        await suppGstinInput.fill('12345BADGST');
        if (await dialogSaveBtn.isVisible()) await dialogSaveBtn.click();
        await page.waitForTimeout(600);
        await takeScreenshot('UXW2-019_supplier_invalid_gstin_validation');
      }

      // Fill valid supplier
      const suppNameInput = page.locator('div[role="dialog"] input[name="name"], div[role="dialog"] label:has-text("Name") ~ div input, div[role="dialog"] label:has-text("Supplier Name") ~ div input').first();
      if (await suppNameInput.isVisible()) {
        await suppNameInput.fill('UXWAVE2-Supplier-Alpha');
      }
      if (await suppGstinInput.isVisible()) {
        await suppGstinInput.fill('27AABCU9603R1ZM');
      }
      
      const suppPhoneInput = page.locator('div[role="dialog"] input[name="phone"], div[role="dialog"] label:has-text("Phone") ~ div input').first();
      if (await suppPhoneInput.isVisible()) {
        await suppPhoneInput.fill('9876543210');
      }

      const suppAddressInput = page.locator('div[role="dialog"] textarea[name="address"], div[role="dialog"] input[name="address"], div[role="dialog"] label:has-text("Address") ~ div textarea').first();
      if (await suppAddressInput.isVisible()) {
        await suppAddressInput.fill('Plot 10, MIDC, Andheri East, Mumbai, Maharashtra 400093');
      }

      const suppStateInput = page.locator('div[role="dialog"] input[name="state"], div[role="dialog"] #state, div[role="dialog"] label:has-text("State") ~ div input').first();
      if (await suppStateInput.isVisible()) {
        await suppStateInput.fill('Maharashtra');
      }

      await takeScreenshot('UXW2-020_supplier_form_filled');
      if (await dialogSaveBtn.isVisible()) {
        await dialogSaveBtn.click();
        await page.waitForTimeout(1500);
      }
      await takeScreenshot('UXW2-021_supplier_created_list');
    }

    // -------------------------------------------------------------
    // STEP 4: PRODUCT / INVENTORY SETUP
    // -------------------------------------------------------------
    console.log('=== STEP 4: PRODUCT / INVENTORY SETUP ===');
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const addProdBtn = page.locator('button:has-text("Add Product"), button:has-text("New Product"), button:has-text("Add Item")').first();
    if (await addProdBtn.isVisible()) {
      await addProdBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-022_product_dialog_empty');

      // Test empty submit
      const prodSaveBtn = page.locator('div[role="dialog"] button:has-text("Save"), div[role="dialog"] button:has-text("Create"), div[role="dialog"] button[type="submit"]').first();
      if (await prodSaveBtn.isVisible()) {
        await prodSaveBtn.click();
        await page.waitForTimeout(600);
        await takeScreenshot('UXW2-023_product_empty_validation');
      }

      // Enter Product details: UXWAVE2-Item-Widget (Opening: 10, Buy: ₹100, Sell: ₹150, GST: 18%)
      const prodName = page.locator('div[role="dialog"] input[name="name"], div[role="dialog"] label:has-text("Item Name") ~ div input, div[role="dialog"] label:has-text("Product Name") ~ div input').first();
      if (await prodName.isVisible()) await prodName.fill('UXWAVE2-Item-Widget');

      const prodSku = page.locator('div[role="dialog"] input[name="sku"], div[role="dialog"] label:has-text("SKU") ~ div input').first();
      if (await prodSku.isVisible()) await prodSku.fill('UXW2-WIDGET-01');

      const prodHsn = page.locator('div[role="dialog"] input[name="hsn_code"], div[role="dialog"] input[name="hsnCode"], div[role="dialog"] label:has-text("HSN") ~ div input').first();
      if (await prodHsn.isVisible()) await prodHsn.fill('84713010');

      const prodBuyPrice = page.locator('div[role="dialog"] input[name="purchase_price"], div[role="dialog"] input[name="purchasePrice"], div[role="dialog"] label:has-text("Purchase Price") ~ div input, div[role="dialog"] label:has-text("Buy Price") ~ div input').first();
      if (await prodBuyPrice.isVisible()) await prodBuyPrice.fill('100');

      const prodSellPrice = page.locator('div[role="dialog"] input[name="selling_price"], div[role="dialog"] input[name="sellingPrice"], div[role="dialog"] label:has-text("Selling Price") ~ div input, div[role="dialog"] label:has-text("Sale Price") ~ div input').first();
      if (await prodSellPrice.isVisible()) await prodSellPrice.fill('150');

      const prodTaxRate = page.locator('div[role="dialog"] input[name="tax_rate"], div[role="dialog"] input[name="taxRate"], div[role="dialog"] label:has-text("GST") ~ div input, div[role="dialog"] label:has-text("Tax Rate") ~ div input, div[role="dialog"] div[id*="tax"], div[role="dialog"] div[id*="gst"]').first();
      if (await prodTaxRate.isVisible()) {
        try {
          await prodTaxRate.click();
          const opt18 = page.locator('li:has-text("18%"), li[data-value="18"], li:has-text("18")').first();
          if (await opt18.isVisible()) await opt18.click();
        } catch (e) {
          console.log('Tax rate select issue:', e.message);
        }
      }

      const prodOpeningStock = page.locator('div[role="dialog"] input[name="opening_stock"], div[role="dialog"] input[name="openingStock"], div[role="dialog"] label:has-text("Opening Stock") ~ div input').first();
      if (await prodOpeningStock.isVisible()) await prodOpeningStock.fill('10');

      await takeScreenshot('UXW2-024_product_form_filled');
      if (await prodSaveBtn.isVisible()) {
        await prodSaveBtn.click();
        await page.waitForTimeout(1500);
      }
      await takeScreenshot('UXW2-025_product_created_list');
    }

    // -------------------------------------------------------------
    // STEP 5: PURCHASE INVOICE (20 units from UXWAVE2-Supplier-Alpha)
    // -------------------------------------------------------------
    console.log('=== STEP 5: PURCHASE INVOICE CREATION ===');
    await page.goto('http://localhost/purchases/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-026_purchase_new_page');

    // Select Supplier UXWAVE2-Supplier-Alpha
    // Let's inspect supplier selector / party select panel
    const supplierSelect = page.locator('input[placeholder*="Select Supplier"], input[placeholder*="Search supplier"], label:has-text("Supplier") ~ div input, div:has-text("Select Supplier")').first();
    if (await supplierSelect.isVisible()) {
      await supplierSelect.click();
      await page.keyboard.type('UXWAVE2-Supplier-Alpha');
      await page.waitForTimeout(500);
      const suppOption = page.locator('li:has-text("UXWAVE2-Supplier-Alpha"), div[role="option"]:has-text("UXWAVE2-Supplier-Alpha")').first();
      if (await suppOption.isVisible()) {
        await suppOption.click();
      }
    }

    await takeScreenshot('UXW2-027_purchase_supplier_selected');

    // Add item: UXWAVE2-Item-Widget, Qty: 20, Buy Price: 100
    // Look for add item or item input
    const itemSearch = page.locator('input[placeholder*="Search item"], input[placeholder*="Select item"], input[placeholder*="Item name"], table tbody tr input').first();
    if (await itemSearch.isVisible()) {
      await itemSearch.click();
      await itemSearch.fill('UXWAVE2-Item-Widget');
      await page.waitForTimeout(500);
      const itemOption = page.locator('li:has-text("UXWAVE2-Item-Widget"), div[role="option"]:has-text("UXWAVE2-Item-Widget")').first();
      if (await itemOption.isVisible()) {
        await itemOption.click();
      }
    }

    // Look for quantity input
    const qtyInput = page.locator('input[name*="quantity"], input[aria-label*="Quantity"], table tbody tr td:nth-child(3) input, input[placeholder*="Qty"]').first();
    if (await qtyInput.isVisible()) {
      await qtyInput.fill('20');
    }

    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-028_purchase_invoice_item_added');

    // Check tax calculation
    const purchaseSaveBtn = page.locator('button:has-text("Save Purchase"), button:has-text("Save Bill"), button:has-text("Save Invoice"), button:has-text("Record Purchase"), button[type="submit"]:has-text("Save")').first();
    if (await purchaseSaveBtn.isVisible()) {
      await purchaseSaveBtn.click();
      await page.waitForTimeout(2000);
    }
    await takeScreenshot('UXW2-029_purchase_invoice_saved_result');

    // Verify stock at /inventory/stock
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-030_stock_after_purchase');

    // -------------------------------------------------------------
    // STEP 6: CUSTOMER CREATION
    // -------------------------------------------------------------
    console.log('=== STEP 6: CUSTOMER CREATION ===');
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const addCustBtn = page.locator('button:has-text("Add Customer"), button:has-text("New Customer"), button:has-text("Create")').first();
    if (await addCustBtn.isVisible()) {
      await addCustBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-031_customer_dialog_empty');

      const custSaveBtn = page.locator('div[role="dialog"] button:has-text("Save"), div[role="dialog"] button:has-text("Create"), div[role="dialog"] button[type="submit"]').first();
      // Test empty submit
      if (await custSaveBtn.isVisible()) {
        await custSaveBtn.click();
        await page.waitForTimeout(600);
        await takeScreenshot('UXW2-032_customer_empty_validation');
      }

      // Fill customer details
      const custName = page.locator('div[role="dialog"] input[name="name"], div[role="dialog"] label:has-text("Customer Name") ~ div input, div[role="dialog"] label:has-text("Name") ~ div input').first();
      if (await custName.isVisible()) await custName.fill('UXWAVE2-Customer-Beta');

      const custPhone = page.locator('div[role="dialog"] input[name="phone"], div[role="dialog"] label:has-text("Phone") ~ div input').first();
      if (await custPhone.isVisible()) await custPhone.fill('9876501234');

      const custState = page.locator('div[role="dialog"] input[name="state"], div[role="dialog"] #state, div[role="dialog"] label:has-text("State") ~ div input').first();
      if (await custState.isVisible()) await custState.fill('Maharashtra');

      const custAddress = page.locator('div[role="dialog"] textarea[name="address"], div[role="dialog"] input[name="address"], div[role="dialog"] label:has-text("Address") ~ div textarea').first();
      if (await custAddress.isVisible()) await custAddress.fill('123 MG Road, Pune, Maharashtra 411001');

      await takeScreenshot('UXW2-033_customer_form_filled');
      if (await custSaveBtn.isVisible()) {
        await custSaveBtn.click();
        await page.waitForTimeout(1500);
      }
      await takeScreenshot('UXW2-034_customer_created_list');
    }

    // -------------------------------------------------------------
    // STEP 7: SALES INVOICE (5 units to UXWAVE2-Customer-Beta)
    // -------------------------------------------------------------
    console.log('=== STEP 7: SALES INVOICE CREATION ===');
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-035_sales_new_page');

    // Select Customer UXWAVE2-Customer-Beta
    const custSelect = page.locator('input[placeholder*="Select Customer"], input[placeholder*="Search customer"], label:has-text("Customer") ~ div input, div:has-text("Select Customer")').first();
    if (await custSelect.isVisible()) {
      await custSelect.click();
      await page.keyboard.type('UXWAVE2-Customer-Beta');
      await page.waitForTimeout(500);
      const custOption = page.locator('li:has-text("UXWAVE2-Customer-Beta"), div[role="option"]:has-text("UXWAVE2-Customer-Beta")').first();
      if (await custOption.isVisible()) {
        await custOption.click();
      }
    }

    await takeScreenshot('UXW2-036_sales_customer_selected');

    // Add item: UXWAVE2-Item-Widget, Qty: 5, Rate: 150
    const salesItemSearch = page.locator('input[placeholder*="Search item"], input[placeholder*="Select item"], input[placeholder*="Item name"], table tbody tr input').first();
    if (await salesItemSearch.isVisible()) {
      await salesItemSearch.click();
      await salesItemSearch.fill('UXWAVE2-Item-Widget');
      await page.waitForTimeout(500);
      const itemOption = page.locator('li:has-text("UXWAVE2-Item-Widget"), div[role="option"]:has-text("UXWAVE2-Item-Widget")').first();
      if (await itemOption.isVisible()) {
        await itemOption.click();
      }
    }

    const salesQtyInput = page.locator('input[name*="quantity"], input[aria-label*="Quantity"], table tbody tr td:nth-child(3) input, input[placeholder*="Qty"]').first();
    if (await salesQtyInput.isVisible()) {
      await salesQtyInput.fill('5');
    }

    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-037_sales_invoice_item_added');

    // Save sales invoice
    const salesSaveBtn = page.locator('button:has-text("Save Invoice"), button:has-text("Create Invoice"), button:has-text("Generate Invoice"), button[type="submit"]:has-text("Save")').first();
    if (await salesSaveBtn.isVisible()) {
      await salesSaveBtn.click();
      await page.waitForTimeout(2000);
    }
    await takeScreenshot('UXW2-038_sales_invoice_saved_result');

    // Verify stock at /inventory/stock (should be 25)
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-039_stock_after_sale_should_be_25');

    // -------------------------------------------------------------
    // STEP 8: REPORTS & LEDGERS VERIFICATION
    // -------------------------------------------------------------
    console.log('=== STEP 8: REPORTS & LEDGERS VERIFICATION ===');
    await page.goto('http://localhost/reports/sales');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-040_sales_register_verification');

    await page.goto('http://localhost/reports/purchases');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-041_purchases_register_verification');

    await page.goto('http://localhost/reports/customer-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-042_customer_ledger_verification');

    await page.goto('http://localhost/reports/supplier-ledger');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-043_supplier_ledger_verification');

    console.log('=== CORE BUSINESS PRIORITY CHAIN AUDIT COMPLETE ===');

  } catch (err) {
    console.error('Audit failed with error:', err);
    await takeScreenshot('UXW2-ERROR_core_chain');
  } finally {
    await audit.cleanup();
  }
}

auditCoreChain();
