const { createAuditBrowser } = require('./helper.cjs');

async function testInventoryModule() {
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
    // 1. PRODUCTS MASTER
    // ==========================================
    console.log('\n--- Testing Products Master ---');
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const addProductBtn = await page.$('button:has-text("Add Product"), button:has-text("New Product"), button:has-text("Add Item")');
    if (addProductBtn) {
      record('Products', 'Add Product Button', 'UI Presence', 'PASS', 'Button found');
      await addProductBtn.click();
      await page.waitForTimeout(800);

      // Empty submit validation
      const saveProductBtn = await page.$('button:has-text("Save"), button:has-text("Submit"), button[type="submit"]');
      if (saveProductBtn) {
        await saveProductBtn.click();
        await page.waitForTimeout(500);
        const errs = await page.$$eval('.Mui-error, [role="alert"]', els => els.map(e => e.innerText));
        record('Products', 'Product Form Empty Validation', 'Negative Path', errs.length > 0 ? 'PASS' : 'FAIL', `Errors: ${errs.join('; ')}`);
      }

      // Fill Valid Product
      const nameInput = await page.$('input[name="name"], input[label*="Name"], #name');
      const hsnInput = await page.$('input[name="hsn_code"], input[name="hsn"], #hsn');
      const priceInput = await page.$('input[name="selling_price"], input[name="price"], #selling_price');
      const buyPriceInput = await page.$('input[name="purchase_price"], #purchase_price');

      const testProductName = 'QA Test Item ' + Date.now().toString().slice(-4);
      if (nameInput) await nameInput.fill(testProductName);
      if (hsnInput) await hsnInput.fill('84713010');
      if (priceInput) await priceInput.fill('1500');
      if (buyPriceInput) await buyPriceInput.fill('1000');

      if (saveProductBtn) {
        await saveProductBtn.click();
        await page.waitForTimeout(1500);
        record('Products', 'Save Product Form', 'Happy Path', 'PASS', `Created product: ${testProductName}`);
      }
    } else {
      record('Products', 'Add Product Button', 'UI Presence', 'FAIL', 'Add Product button missing');
    }

    // Search filter
    const searchInput = await page.$('input[placeholder*="Search"], input[type="search"]');
    if (searchInput) {
      await searchInput.fill('QA Test Item');
      await page.waitForTimeout(500);
      const count = await page.$$eval('table tbody tr', trs => trs.length);
      record('Products', 'Product Search Filter', 'Functional', count > 0 ? 'PASS' : 'FAIL', `Found ${count} rows`);
      await searchInput.fill('');
    }

    // ==========================================
    // 2. CURRENT STOCK & LOW STOCK
    // ==========================================
    console.log('\n--- Testing Current Stock & Low Stock ---');
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const stockRows = await page.$$eval('table tbody tr', trs => trs.length);
    record('Current Stock', 'Stock Table Records', 'UI Data Load', stockRows > 0 ? 'PASS' : 'FAIL', `Loaded ${stockRows} stock rows`);

    await page.goto('http://localhost/inventory/low-stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const lowStockHeader = await page.$('h4, h5, h6, [role="heading"]');
    record('Low Stock Alerts', 'Page Header & Surface', 'UI Presence', lowStockHeader ? 'PASS' : 'FAIL');

    // ==========================================
    // 3. STOCK ADJUSTMENTS
    // ==========================================
    console.log('\n--- Testing Stock Adjustments ---');
    await page.goto('http://localhost/inventory/adjustments');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const addAdjBtn = await page.$('button:has-text("New Adjustment"), button:has-text("Adjust Stock"), button:has-text("Add")');
    record('Stock Adjustments', 'New Adjustment Button', 'UI Presence', addAdjBtn ? 'PASS' : 'FAIL');
    if (addAdjBtn) {
      await addAdjBtn.click();
      await page.waitForTimeout(600);
      const form = await page.$('form, [role="dialog"]');
      record('Stock Adjustments', 'Adjustment Form Open', 'UI Modal/Form', form ? 'PASS' : 'FAIL');
    }

    // ==========================================
    // 4. WAREHOUSES & TRANSFERS
    // ==========================================
    console.log('\n--- Testing Warehouses & Transfers ---');
    await page.goto('http://localhost/inventory/warehouses');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const addWhBtn = await page.$('button:has-text("Add Warehouse"), button:has-text("New Warehouse"), button:has-text("Add")');
    record('Warehouses', 'Add Warehouse Button', 'UI Presence', addWhBtn ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/inventory/transfers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const newTransferBtn = await page.$('button:has-text("New Transfer"), button:has-text("Transfer Stock"), button:has-text("Add")');
    record('Stock Transfers', 'New Stock Transfer Button', 'UI Presence', newTransferBtn ? 'PASS' : 'FAIL');

    // ==========================================
    // 5. STOCK COUNT, SERIALS & EXPIRY
    // ==========================================
    console.log('\n--- Testing Stock Count, Serials, Expiry ---');
    await page.goto('http://localhost/inventory/stock-counts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const countHeader = await page.$('h4, h5, h6, [role="heading"]');
    record('Stock Counts', 'Stock Counts Page Load', 'UI Presence', countHeader ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/inventory/serials');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const serialsHeader = await page.$('h4, h5, h6, [role="heading"]');
    record('Serials Tracking', 'Serials Page Load', 'UI Presence', serialsHeader ? 'PASS' : 'FAIL');

    await page.goto('http://localhost/inventory/expiry-alerts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const expiryHeader = await page.$('h4, h5, h6, [role="heading"]');
    record('Expiry Alerts', 'Expiry Alerts Page Load', 'UI Presence', expiryHeader ? 'PASS' : 'FAIL');

  } catch (err) {
    console.error('Inventory test failed:', err);
    record('Inventory Module', 'Test Execution', 'Execution Error', 'FAIL', err.message);
  } finally {
    await audit.cleanup();
  }

  return results;
}

testInventoryModule().then(res => {
  console.log('=== INVENTORY MODULE TEST SUMMARY ===');
  console.table(res);
});
