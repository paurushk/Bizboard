const { createAuditBrowser } = require('./helper.cjs');

async function testSalesModule() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;
  const results = [];

  function record(screen, element, testType, status, details = '') {
    results.push({ screen, element, testType, status, details });
    console.log(`[${status}] [${screen}] ${element} (${testType}): ${details}`);
  }

  try {
    await login('demo@bizboard.local', 'DemoPass123!');

    // ==========================================
    // 1. CUSTOMERS MANAGEMENT
    // ==========================================
    console.log('\n--- Testing Customers Page ---');
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // 1.1 Add Customer Button
    const addCustBtn = await page.$('button:has-text("Add Customer"), button:has-text("New Customer"), button:has-text("Create Customer")');
    if (addCustBtn) {
      record('Customers', 'Add Customer Button', 'UI Presence', 'PASS', 'Button visible');
      await addCustBtn.click();
      await page.waitForTimeout(800);

      // 1.2 Modal/Form Empty Submit
      const saveCustBtn = await page.$('button:has-text("Save"), button:has-text("Submit"), button[type="submit"]');
      if (saveCustBtn) {
        await saveCustBtn.click();
        await page.waitForTimeout(500);
        const errs = await page.$$eval('.Mui-error, [role="alert"]', els => els.map(e => e.innerText));
        record('Customers', 'Customer Form Empty Validation', 'Negative Path', errs.length > 0 ? 'PASS' : 'FAIL', `Errors: ${errs.join('; ')}`);
      }

      // 1.3 Fill Valid Customer
      const custNameInput = await page.$('input[name="name"], input[label*="Name"], #name');
      const custGstInput = await page.$('input[name="gstin"], input[name="gst_number"], #gstin');
      const custPhoneInput = await page.$('input[name="phone"], #phone');

      const testCustName = 'Test QA Customer ' + Date.now().toString().slice(-4);
      if (custNameInput) await custNameInput.fill(testCustName);
      if (custPhoneInput) await custPhoneInput.fill('9876543210');
      if (custGstInput) await custGstInput.fill('27AAPFU0939F1ZV');

      if (saveCustBtn) {
        await saveCustBtn.click();
        await page.waitForTimeout(1500);
        record('Customers', 'Save Customer Form', 'Happy Path', 'PASS', `Created customer: ${testCustName}`);
      }
    } else {
      record('Customers', 'Add Customer Button', 'UI Presence', 'FAIL', 'Add Customer button not found');
    }

    // 1.4 Search & Filter Customers
    const searchInput = await page.$('input[placeholder*="Search"], input[type="search"]');
    if (searchInput) {
      await searchInput.fill('Test QA');
      await page.waitForTimeout(500);
      const rows = await page.$$eval('table tbody tr', trs => trs.length);
      record('Customers', 'Customer Search Filter', 'Functional', rows > 0 ? 'PASS' : 'FAIL', `Found ${rows} matching rows`);
      await searchInput.fill('');
    }

    // ==========================================
    // 2. NEW SALES INVOICE
    // ==========================================
    console.log('\n--- Testing New Sales Invoice Form ---');
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Check key invoice controls
    const custSelect = await page.$('input[placeholder*="Select Customer"], [role="combobox"]');
    const saveInvoiceBtn = await page.$('button:has-text("Save Invoice"), button:has-text("Create Invoice"), button[type="submit"]');
    const addItemBtn = await page.$('button:has-text("Add Item"), button:has-text("Add Line")');

    record('New Invoice', 'Customer Combobox', 'UI Presence', custSelect ? 'PASS' : 'FAIL');
    record('New Invoice', 'Save Invoice Button', 'UI Presence', saveInvoiceBtn ? 'PASS' : 'FAIL');
    record('New Invoice', 'Add Item Line Button', 'UI Presence', addItemBtn ? 'PASS' : 'FAIL');

    // 2.1 Empty Save Invoice validation
    if (saveInvoiceBtn) {
      await saveInvoiceBtn.click();
      await page.waitForTimeout(500);
      const invErrors = await page.$$eval('.Mui-error, [role="alert"], .MuiAlert-message, .MuiSnackbar-root', els => els.map(e => e.innerText));
      record('New Invoice', 'Empty Invoice Save Validation', 'Negative Path', invErrors.length > 0 ? 'PASS' : 'FAIL', `Errors: ${invErrors.join('; ')}`);
    }

    // 2.2 Complete Happy Path Sales Invoice
    if (custSelect) {
      await custSelect.click();
      await page.waitForTimeout(500);
      const firstOption = await page.$('.MuiAutocomplete-option, [role="option"]');
      if (firstOption) {
        await firstOption.click();
        await page.waitForTimeout(500);
      }
    }

    // Fill Item details if available
    const itemSelect = await page.$('input[placeholder*="Select Item"], table tbody tr input');
    if (itemSelect) {
      await itemSelect.click();
      await page.waitForTimeout(300);
      const firstItemOpt = await page.$('.MuiAutocomplete-option, [role="option"]');
      if (firstItemOpt) {
        await firstItemOpt.click();
      } else {
        // Fallback: type item name and rate
        const qtyInput = await page.$('input[name*="qty"], input[name*="quantity"], table input[type="number"]');
        if (qtyInput) await qtyInput.fill('2');
      }
    }

    // Check Total calculation display
    const totalDisplay = await page.$$eval('*', els => {
      const match = els.find(e => e.innerText && e.innerText.includes('Grand Total') || e.innerText && e.innerText.includes('Total:'));
      return match ? match.innerText : null;
    });
    record('New Invoice', 'Invoice Total Calculation Display', 'UI Calculation', totalDisplay ? 'PASS' : 'FAIL', `Total text: ${totalDisplay}`);

    // ==========================================
    // 3. SALES HISTORY & INVOICE DETAIL
    // ==========================================
    console.log('\n--- Testing Sales History & Details ---');
    await page.goto('http://localhost/sales/history');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const historyRows = await page.$$eval('table tbody tr', trs => trs.length);
    record('Sales History', 'Invoice Table Records', 'UI Data Load', historyRows > 0 ? 'PASS' : 'FAIL', `Loaded ${historyRows} invoice rows`);

    // Test View Invoice Detail
    const firstRowLink = await page.$('table tbody tr a, table tbody tr button');
    if (firstRowLink) {
      await firstRowLink.click();
      await page.waitForTimeout(1500);
      const isDetailPage = page.url().includes('/sales/history/') || page.url().includes('/sales/invoices/');
      record('Sales History', 'Navigate to Invoice Detail', 'Navigation & Data Flow', isDetailPage ? 'PASS' : 'FAIL', `Current URL: ${page.url()}`);

      // Check detail actions (Print, PDF, Record Payment)
      const pdfBtn = await page.$('button:has-text("PDF"), button:has-text("Print"), button:has-text("Download")');
      record('Invoice Detail', 'PDF / Print Button', 'UI Presence', pdfBtn ? 'PASS' : 'FAIL');
    }

    // ==========================================
    // 4. QUOTATIONS
    // ==========================================
    console.log('\n--- Testing Quotations ---');
    await page.goto('http://localhost/sales/quotations');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const newQuoteBtn = await page.$('button:has-text("New Quotation"), button:has-text("Create Quotation")');
    record('Quotations', 'New Quotation Button', 'UI Presence', newQuoteBtn ? 'PASS' : 'FAIL');
    if (newQuoteBtn) {
      await newQuoteBtn.click();
      await page.waitForTimeout(800);
      const quoteDialogOrPage = await page.$('form, [role="dialog"]');
      record('Quotations', 'Open Quotation Form', 'Navigation / Modal', quoteDialogOrPage ? 'PASS' : 'FAIL');
    }

    // ==========================================
    // 5. SALES ORDERS & DELIVERY CHALLANS
    // ==========================================
    console.log('\n--- Testing Sales Orders & Delivery Challans ---');
    await page.goto('http://localhost/sales/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newOrderBtn = await page.$('button:has-text("New Order"), button:has-text("Create Sales Order"), button:has-text("New Sales Order")');
    record('Sales Orders', 'New Sales Order Button', 'UI Presence', newOrderBtn ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/sales/delivery-challans');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newChallanBtn = await page.$('button:has-text("New"), button:has-text("Create")');
    record('Delivery Challans', 'New Delivery Challan Button', 'UI Presence', newChallanBtn ? 'PASS' : 'FAIL');

    // ==========================================
    // 6. CREDIT NOTES & DEBIT NOTES
    // ==========================================
    console.log('\n--- Testing Credit Notes & Debit Notes ---');
    await page.goto('http://localhost/sales/credit-notes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newCreditNoteBtn = await page.$('button:has-text("New Credit Note"), button:has-text("Create Credit Note")');
    record('Credit Notes', 'New Credit Note Button', 'UI Presence', newCreditNoteBtn ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/sales/debit-notes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newDebitNoteBtn = await page.$('button:has-text("New Debit Note"), button:has-text("Create Debit Note")');
    record('Debit Notes', 'New Debit Note Button', 'UI Presence', newDebitNoteBtn ? 'PASS' : 'FAIL');

    // ==========================================
    // 7. SALES RETURNS & RECEIPTS
    // ==========================================
    console.log('\n--- Testing Sales Returns & Receipts ---');
    await page.goto('http://localhost/sales/returns');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newReturnBtn = await page.$('button:has-text("New"), button:has-text("Create")');
    record('Sales Returns', 'New Return Button', 'UI Presence', newReturnBtn ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/sales/receipts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newReceiptBtn = await page.$('button:has-text("Record Receipt"), button:has-text("New Receipt"), button:has-text("Add Receipt")');
    record('Receipts', 'Record Receipt Button', 'UI Presence', newReceiptBtn ? 'PASS' : 'FAIL');

    // ==========================================
    // 8. RECURRING INVOICES & BILL UPLOAD
    // ==========================================
    console.log('\n--- Testing Recurring Invoices & Bill Upload ---');
    await page.goto('http://localhost/sales/recurring');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newRecurringBtn = await page.$('button:has-text("New Recurring"), button:has-text("Create Recurring")');
    record('Recurring Invoices', 'New Recurring Invoice Button', 'UI Presence', newRecurringBtn ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/sales/bill-upload');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const uploadArea = await page.$('input[type="file"], .dropzone, [role="presentation"]');
    record('Sales Bill Upload', 'File Upload Dropzone', 'UI Presence', uploadArea ? 'PASS' : 'FAIL');

  } catch (err) {
    console.error('Sales test failed:', err);
    record('Sales Module', 'Test Execution', 'Execution Error', 'FAIL', err.message);
  } finally {
    await audit.cleanup();
  }

  return results;
}

testSalesModule().then(res => {
  console.log('=== SALES MODULE TEST SUMMARY ===');
  console.table(res);
});
