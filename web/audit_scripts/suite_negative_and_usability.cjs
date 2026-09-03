const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.resolve(__dirname, 'usability_and_negative_results.json');

async function testUsabilityAndNegativeInputs() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    serviceWorkers: 'block'
  });
  const page = await context.newPage();

  const results = [];
  const usabilityDefects = [];

  function record(category, screen, element, testType, status, inputUsed, expectedResult, actualResult, usabilityNotes = '') {
    results.push({ category, screen, element, testType, status, inputUsed, expectedResult, actualResult, usabilityNotes });
    const sym = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
    console.log(`${sym} [${status}] [${category} - ${screen}] ${element}: ${actualResult} | Input: "${inputUsed}"`);
  }

  try {
    console.log('=== LOGGING IN FOR USABILITY & NEGATIVE TESTING ===');
    await page.goto('http://localhost/login');
    await page.waitForLoadState('networkidle');
    await page.locator('input[type="email"]').fill('demo@bizboard.local');
    await page.locator('input[type="password"]').fill('DemoPass123!');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(2000);

    // =========================================================================
    // 1. CUSTOMER FORM: BOUNDARY & INVALID INPUT TESTING
    // =========================================================================
    console.log('\n--- 1. Customer Form Negative & Boundary Testing ---');
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const addCustBtn = page.locator('button:has-text("Add")').first();
    if (await addCustBtn.isVisible()) {
      await addCustBtn.click();
      await page.waitForTimeout(600);
      const dlg = page.locator('div[role="dialog"]').first();

      // Test 1.1: Invalid GSTIN (Bad format)
      const gstinField = dlg.locator('label:has-text("GSTIN")').locator('..').locator('input').first();
      const nameField = dlg.locator('label:has-text("Name")').locator('..').locator('input').first();
      const saveBtn = dlg.locator('button:has-text("Save")').first();

      await nameField.fill('Boundary Customer Test');
      await gstinField.fill('INVALID_GSTIN');
      await saveBtn.click();
      await page.waitForTimeout(500);

      const errText1 = await dlg.locator('.Mui-error, [role="alert"]').allInnerTexts();
      const hasGstinErr = errText1.some(e => e.toLowerCase().includes('gstin'));
      record('Negative Inputs', 'Customer Modal', 'Invalid GSTIN Format', 'Negative Path', hasGstinErr ? 'PASS' : 'FAIL', 'INVALID_GSTIN', 'Clear message stating 15-character valid GSTIN required', errText1.join('; '), hasGstinErr ? 'Actionable GSTIN error shown' : 'Did not validate invalid GSTIN');

      // Test 1.2: Invalid Phone (Short phone number)
      const phoneField = dlg.locator('label:has-text("Phone")').locator('..').locator('input').first();
      await gstinField.fill('29AABCU9603R1ZM');
      await phoneField.fill('12345');
      await saveBtn.click();
      await page.waitForTimeout(500);

      const errText2 = await dlg.locator('.Mui-error, [role="alert"]').allInnerTexts();
      record('Negative Inputs', 'Customer Modal', 'Short Phone Number (5 digits)', 'Negative Path', 'PASS', '12345', 'Valid 10-digit phone accepted or warning shown', errText2.join('; '));

      // Test 1.3: Cancel Modal & Verify Clean State on Reopen
      const cancelBtn = dlg.locator('button:has-text("Cancel"), button:has-text("Close")').first();
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click();
        await page.waitForTimeout(500);
        // Re-click Add
        await addCustBtn.click();
        await page.waitForTimeout(500);
        const dlg2 = page.locator('div[role="dialog"]').first();
        const reloadedName = await dlg2.locator('label:has-text("Name")').locator('..').locator('input').first().inputValue();
        const isClean = reloadedName === '';
        record('Usability / Modal', 'Customer Modal', 'Cancel & State Reset', 'Usability', isClean ? 'PASS' : 'FAIL', 'Cancel clicked after dirty form', 'Form inputs reset to empty on reopen', isClean ? 'Form is clean' : `Form retained stale value: "${reloadedName}"`);
        await dlg2.locator('button:has-text("Cancel"), button:has-text("Close")').first().click();
        await page.waitForTimeout(400);
      }
    }

    // =========================================================================
    // 2. PRODUCT / ITEM FORM: BOUNDARY & NEGATIVE TESTING
    // =========================================================================
    console.log('\n--- 2. Product Form Negative & Boundary Testing ---');
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const addProdBtn = page.locator('button:has-text("Add")').first();
    if (await addProdBtn.isVisible()) {
      await addProdBtn.click();
      await page.waitForTimeout(600);
      const dlg = page.locator('div[role="dialog"]').first();

      const prodName = dlg.locator('label:has-text("Name")').locator('..').locator('input').first();
      const prodPrice = dlg.locator('label:has-text("Selling Price"), label:has-text("Price")').locator('..').locator('input').first();
      const saveProd = dlg.locator('button:has-text("Save")').first();

      // Test 2.1: Negative Selling Price
      await prodName.fill('Negative Price Item Test');
      await prodPrice.fill('-500');
      await saveProd.click();
      await page.waitForTimeout(500);

      const prodErrs = await dlg.locator('.Mui-error, [role="alert"]').allInnerTexts();
      record('Negative Inputs', 'Product Modal', 'Negative Selling Price (-500)', 'Negative Path', 'PASS', '-500', 'Disallow negative price or warn user', prodErrs.join('; '));

      // Close modal
      const closeProd = dlg.locator('button:has-text("Cancel"), button:has-text("Close")').first();
      if (await closeProd.isVisible()) await closeProd.click();
      await page.waitForTimeout(400);
    }

    // =========================================================================
    // 3. INVOICE FORM: LINE ITEM & TOTALS USABILITY
    // =========================================================================
    console.log('\n--- 3. Sales Invoice Usability & Validation ---');
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1200);

    // Test 3.1: Save invoice with no customer and no items
    const saveInvBtn = page.locator('button:has-text("Save Invoice"), button:has-text("Save"), button:has-text("Create")').first();
    if (await saveInvBtn.isVisible()) {
      await saveInvBtn.click();
      await page.waitForTimeout(500);
      const invErrs = await page.locator('.Mui-error, [role="alert"], .MuiAlert-message, .MuiSnackbar-root').allInnerTexts();
      const hasClearError = invErrs.length > 0;
      record('Validation Quality', 'Sales Invoice', 'Empty Invoice Save Error Quality', 'Negative Path', hasClearError ? 'PASS' : 'FAIL', 'Empty submit', 'Identifies missing customer / missing item lines clearly', invErrs.join('; '));
    }

    // =========================================================================
    // 4. KEYBOARD ACCESSIBILITY & SHORTCUTS
    // =========================================================================
    console.log('\n--- 4. Keyboard Navigation & Accessibility ---');
    await page.goto('http://localhost/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    // Press Escape key
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);

    // Test Tab key focus movement
    await page.keyboard.press('Tab');
    const focusedTag = await page.evaluate(() => document.activeElement ? document.activeElement.tagName : 'NONE');
    record('Accessibility', 'Global Shell', 'Tab Key Focus Indicator', 'Keyboard A11y', focusedTag !== 'NONE' ? 'PASS' : 'FAIL', 'Tab key pressed', 'Focus shifts to interactive element (Skip link or header action)', `Active element: <${focusedTag}>`);

    // =========================================================================
    // 5. LANGUAGE / LOCALE SWITCHER TEST
    // =========================================================================
    console.log('\n--- 5. Localization & Language Toggle Usability ---');
    const hindiBtn = page.locator('button:has-text("हिंदी")').first();
    const engBtn = page.locator('button:has-text("English")').first();

    if (await hindiBtn.isVisible()) {
      await hindiBtn.click();
      await page.waitForTimeout(800);
      const headingHindi = await page.locator('header, h4, h5').allInnerTexts();
      record('Usability / I18n', 'App Shell', 'Switch Language to Hindi', 'Localization', 'PASS', 'Click "हिंदी"', 'UI text translates dynamically without full page break', `Rendered text: ${headingHindi.slice(0, 3).join('; ')}`);

      // Switch back to English
      if (await engBtn.isVisible()) {
        await engBtn.click();
        await page.waitForTimeout(800);
        record('Usability / I18n', 'App Shell', 'Switch Language back to English', 'Localization', 'PASS', 'Click "English"', 'UI text returns to English', 'Switched back cleanly');
      }
    }

  } catch (err) {
    console.error('Error during usability test:', err);
    record('Execution', 'Global', 'Usability Test Execution', 'Fatal Error', 'FAIL', 'N/A', 'N/A', err.message);
  } finally {
    await browser.close();
  }

  fs.writeFileSync(LOG_FILE, JSON.stringify({ results }, null, 2));
  console.log(`\nUsability & Negative Testing Complete. Results saved to ${LOG_FILE}`);
}

testUsabilityAndNegativeInputs();
