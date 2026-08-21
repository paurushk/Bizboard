const { createAuditBrowser } = require('./helper.cjs');

async function runSalesPurchasesLoop() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;

  try {
    console.log('=== LOGGING IN FOR SALES & PURCHASES AUDIT ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // =============================================================
    // SALES LOOP: QUOTATIONS
    // =============================================================
    console.log('=== SALES LOOP: QUOTATIONS ===');
    await page.goto('http://localhost/sales/quotations');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-033_quotations_list');

    await page.goto('http://localhost/sales/quotations/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-034_quotation_new_form');

    // Quick select or add customer in quotation
    const newCustLink = page.locator('button:has-text("+ New Customer"), a:has-text("+ New Customer")').first();
    if (await newCustLink.isVisible()) {
      await newCustLink.click();
      await page.waitForTimeout(500);
      await page.locator('div[role="dialog"] label:has-text("Name")').locator('..').locator('input').first().fill('UXWAVE2-Customer-Beta');
      await page.locator('div[role="dialog"] label:has-text("State")').locator('..').locator('input').first().fill('Karnataka');
      await page.locator('div[role="dialog"] button:has-text("Save")').first().click();
      await page.waitForTimeout(1000);
    }

    // Add item to quotation
    const addItemLink = page.locator('button:has-text("+ Add Item"), a:has-text("+ Add Item")').first();
    if (await addItemLink.isVisible()) {
      await addItemLink.click();
      await page.waitForTimeout(500);
      await page.locator('div[role="dialog"] label:has-text("Item Name")').locator('..').locator('input').first().fill('UXWAVE2-Quote-Item');
      await page.locator('div[role="dialog"] label:has-text("SKU")').locator('..').locator('input').first().fill('UXW2-QITEM-01');
      await page.locator('div[role="dialog"] label:has-text("Selling Price")').locator('..').locator('input').first().fill('200');
      await page.locator('div[role="dialog"] button:has-text("Add")').first().click();
      await page.waitForTimeout(1000);
    }
    await takeScreenshot('UXW2-035_quotation_filled');

    // Save quotation
    const saveQuoteBtn = page.locator('button:has-text("Save"), button:has-text("Save & Complete")').first();
    if (!await saveQuoteBtn.isDisabled()) {
      await saveQuoteBtn.click();
      await page.waitForTimeout(2000);
    }
    await takeScreenshot('UXW2-036_quotation_saved');

    // =============================================================
    // SALES LOOP: SALES ORDERS
    // =============================================================
    console.log('=== SALES LOOP: SALES ORDERS ===');
    await page.goto('http://localhost/sales/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-037_sales_orders_list');

    await page.goto('http://localhost/sales/orders/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-038_sales_order_new_form');

    // =============================================================
    // SALES LOOP: DELIVERY CHALLANS
    // =============================================================
    console.log('=== SALES LOOP: DELIVERY CHALLANS ===');
    await page.goto('http://localhost/sales/delivery-challans');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-039_delivery_challans_list');

    await page.goto('http://localhost/sales/delivery-challans/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-040_delivery_challan_new_form');

    // =============================================================
    // SALES LOOP: CREDIT NOTES & DEBIT NOTES
    // =============================================================
    console.log('=== SALES LOOP: CREDIT NOTES & DEBIT NOTES ===');
    await page.goto('http://localhost/sales/credit-notes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-041_credit_notes_list');

    await page.goto('http://localhost/sales/credit-notes/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-042_credit_note_new_form');

    await page.goto('http://localhost/sales/debit-notes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-043_sales_debit_notes_list');

    // =============================================================
    // SALES LOOP: PAYMENT RECEIPTS
    // =============================================================
    console.log('=== SALES LOOP: PAYMENT RECEIPTS ===');
    await page.goto('http://localhost/sales/receipts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-044_payment_receipts_list');

    const addReceiptBtn = page.locator('button:has-text("Add"), button:has-text("Record"), button:has-text("New")').first();
    if (await addReceiptBtn.isVisible()) {
      await addReceiptBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-045_payment_receipt_modal');
    }

    // =============================================================
    // PURCHASES LOOP: PURCHASE ORDERS
    // =============================================================
    console.log('=== PURCHASES LOOP: PURCHASE ORDERS ===');
    await page.goto('http://localhost/purchases/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-046_purchase_orders_list');

    await page.goto('http://localhost/purchases/orders/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-047_purchase_order_new_form');

    // =============================================================
    // PURCHASES LOOP: BILLS & HISTORY
    // =============================================================
    console.log('=== PURCHASES LOOP: BILLS & HISTORY ===');
    await page.goto('http://localhost/purchases/history');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-048_purchases_history_list');

    // =============================================================
    // PURCHASES LOOP: DEBIT NOTES & CREDIT NOTES
    // =============================================================
    console.log('=== PURCHASES LOOP: DEBIT & CREDIT NOTES ===');
    await page.goto('http://localhost/purchases/debit-notes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-049_purchases_debit_notes_list');

    await page.goto('http://localhost/purchases/debit-notes/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-050_purchases_debit_note_new_form');

    await page.goto('http://localhost/purchases/credit-notes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-051_purchases_credit_notes_list');

    // =============================================================
    // PURCHASES LOOP: VENDOR PAYMENTS
    // =============================================================
    console.log('=== PURCHASES LOOP: VENDOR PAYMENTS ===');
    await page.goto('http://localhost/purchases/payments');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-052_vendor_payments_list');

    const addVendorPayBtn = page.locator('button:has-text("Add"), button:has-text("Record"), button:has-text("New")').first();
    if (await addVendorPayBtn.isVisible()) {
      await addVendorPayBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-053_vendor_payment_modal');
    }

    console.log('=== SALES & PURCHASES AUDIT SWEEP COMPLETED SUCCESSFULLY ===');
  } catch (err) {
    console.error('Error during Sales/Purchases sweep:', err);
    await takeScreenshot('UXW2-ERROR_sales_purchases');
  } finally {
    await audit.cleanup();
  }
}

runSalesPurchasesLoop();
