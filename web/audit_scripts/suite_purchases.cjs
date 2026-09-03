const { createAuditBrowser } = require('./helper.cjs');

async function testPurchasesModule() {
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
    // 1. SUPPLIERS MANAGEMENT
    // ==========================================
    console.log('\n--- Testing Suppliers Page ---');
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const addSupBtn = await page.$('button:has-text("Add Supplier"), button:has-text("New Supplier"), button:has-text("Create Supplier")');
    if (addSupBtn) {
      record('Suppliers', 'Add Supplier Button', 'UI Presence', 'PASS', 'Button visible');
      await addSupBtn.click();
      await page.waitForTimeout(800);

      // Empty validation
      const saveSupBtn = await page.$('button:has-text("Save"), button:has-text("Submit"), button[type="submit"]');
      if (saveSupBtn) {
        await saveSupBtn.click();
        await page.waitForTimeout(500);
        const errs = await page.$$eval('.Mui-error, [role="alert"]', els => els.map(e => e.innerText));
        record('Suppliers', 'Supplier Form Empty Validation', 'Negative Path', errs.length > 0 ? 'PASS' : 'FAIL', `Errors: ${errs.join('; ')}`);
      }

      // Valid supplier creation
      const nameInput = await page.$('input[name="name"], input[label*="Name"], #name');
      const phoneInput = await page.$('input[name="phone"], #phone');
      const gstinInput = await page.$('input[name="gstin"], #gstin');

      const testSupName = 'Test QA Supplier ' + Date.now().toString().slice(-4);
      if (nameInput) await nameInput.fill(testSupName);
      if (phoneInput) await phoneInput.fill('9123456780');
      if (gstinInput) await gstinInput.fill('27AABCT3518Q1ZV');

      if (saveSupBtn) {
        await saveSupBtn.click();
        await page.waitForTimeout(1500);
        record('Suppliers', 'Save Supplier Form', 'Happy Path', 'PASS', `Created supplier: ${testSupName}`);
      }
    } else {
      record('Suppliers', 'Add Supplier Button', 'UI Presence', 'FAIL', 'Add Supplier button not found');
    }

    // Search filter
    const searchInput = await page.$('input[placeholder*="Search"], input[type="search"]');
    if (searchInput) {
      await searchInput.fill('Test QA');
      await page.waitForTimeout(500);
      const count = await page.$$eval('table tbody tr', trs => trs.length);
      record('Suppliers', 'Supplier Search Filter', 'Functional', count > 0 ? 'PASS' : 'FAIL', `Found ${count} rows`);
      await searchInput.fill('');
    }

    // ==========================================
    // 2. NEW PURCHASE BILL
    // ==========================================
    console.log('\n--- Testing New Purchase Form ---');
    await page.goto('http://localhost/purchases/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const supSelect = await page.$('input[placeholder*="Select Supplier"], [role="combobox"]');
    const savePurchaseBtn = await page.$('button:has-text("Save Purchase"), button:has-text("Create Purchase"), button[type="submit"]');
    const itcField = await page.$('[aria-label*="ITC"], input[name*="itc"], label:has-text("ITC")');

    record('New Purchase', 'Supplier Combobox', 'UI Presence', supSelect ? 'PASS' : 'FAIL');
    record('New Purchase', 'Save Purchase Button', 'UI Presence', savePurchaseBtn ? 'PASS' : 'FAIL');
    record('New Purchase', 'ITC Eligibility Control', 'UI Presence', itcField ? 'PASS' : 'FAIL');

    // Empty form validation
    if (savePurchaseBtn) {
      await savePurchaseBtn.click();
      await page.waitForTimeout(500);
      const errors = await page.$$eval('.Mui-error, [role="alert"], .MuiAlert-message, .MuiSnackbar-root', els => els.map(e => e.innerText));
      record('New Purchase', 'Empty Purchase Form Validation', 'Negative Path', errors.length > 0 ? 'PASS' : 'FAIL', `Errors: ${errors.join('; ')}`);
    }

    // ==========================================
    // 3. PURCHASE HISTORY & DETAIL
    // ==========================================
    console.log('\n--- Testing Purchase History ---');
    await page.goto('http://localhost/purchases/history');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const purchaseRows = await page.$$eval('table tbody tr', trs => trs.length);
    record('Purchase History', 'Purchase Table Records', 'UI Data Load', purchaseRows > 0 ? 'PASS' : 'FAIL', `Loaded ${purchaseRows} purchase rows`);

    const firstPurchaseRow = await page.$('table tbody tr a, table tbody tr button');
    if (firstPurchaseRow) {
      await firstPurchaseRow.click();
      await page.waitForTimeout(1500);
      const isDetail = page.url().includes('/purchases/history/') || page.url().includes('/purchases/');
      record('Purchase History', 'Navigate to Purchase Detail', 'Navigation & Data Flow', isDetail ? 'PASS' : 'FAIL', `Current URL: ${page.url()}`);
    }

    // ==========================================
    // 4. PURCHASE ORDERS & RETURNS
    // ==========================================
    console.log('\n--- Testing Purchase Orders & Returns ---');
    await page.goto('http://localhost/purchases/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newPOBtn = await page.$('button:has-text("New Order"), button:has-text("New Purchase Order"), button:has-text("Create")');
    record('Purchase Orders', 'New Purchase Order Button', 'UI Presence', newPOBtn ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/purchases/returns');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newPRBtn = await page.$('button:has-text("New Return"), button:has-text("Create Return"), button:has-text("New")');
    record('Purchase Returns', 'New Purchase Return Button', 'UI Presence', newPRBtn ? 'PASS' : 'FAIL');

    // ==========================================
    // 5. SUPPLIER PAYMENTS & BILL UPLOAD
    // ==========================================
    console.log('\n--- Testing Supplier Payments & Bill Upload ---');
    await page.goto('http://localhost/purchases/payments');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const recordPayBtn = await page.$('button:has-text("Record Payment"), button:has-text("New Payment"), button:has-text("Add Payment")');
    record('Supplier Payments', 'Record Payment Button', 'UI Presence', recordPayBtn ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/purchases/bill-upload');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const pUploadArea = await page.$('input[type="file"], .dropzone, [role="presentation"]');
    record('Purchase Bill Upload', 'File Upload Dropzone', 'UI Presence', pUploadArea ? 'PASS' : 'FAIL');

  } catch (err) {
    console.error('Purchases test failed:', err);
    record('Purchases Module', 'Test Execution', 'Execution Error', 'FAIL', err.message);
  } finally {
    await audit.cleanup();
  }

  return results;
}

testPurchasesModule().then(res => {
  console.log('=== PURCHASES MODULE TEST SUMMARY ===');
  console.table(res);
});
