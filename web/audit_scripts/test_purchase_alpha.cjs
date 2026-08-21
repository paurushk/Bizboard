const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost/login');
  await page.fill('input[type=email]', 'demo@bizboard.local');
  await page.fill('input[type=password]', 'DemoPass123!');
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');

  // Let's create UXWAVE2-Supplier-Alpha with proper state and GSTIN if needed
  await page.goto('http://localhost/purchases/suppliers');
  await page.waitForLoadState('networkidle');
  
  // Check if UXWAVE2-Supplier-Alpha is in list
  const alphaRow = page.locator('table tbody tr').filter({ hasText: 'UXWAVE2-Supplier-Alpha' });
  if (await alphaRow.count() === 0) {
    console.log('Creating UXWAVE2-Supplier-Alpha...');
    await page.locator('button:has-text("Add")').first().click();
    await page.waitForTimeout(500);
    await page.locator('div[role="dialog"] label:has-text("Name")').locator('..').locator('input').first().fill('UXWAVE2-Supplier-Alpha');
    await page.locator('div[role="dialog"] label:has-text("GSTIN")').locator('..').locator('input').first().fill('27AABCU9603R1ZM');
    await page.locator('div[role="dialog"] label:has-text("Phone")').locator('..').locator('input').first().fill('9876543210');
    await page.locator('div[role="dialog"] label:has-text("Address")').locator('..').locator('input, textarea').first().fill('Plot 10, MIDC, Mumbai, Maharashtra 400093');
    await page.locator('div[role="dialog"] button:has-text("Save")').first().click();
    await page.waitForTimeout(1000);
  }

  // Go to /purchases/new
  await page.goto('http://localhost/purchases/new');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  console.log('Selecting UXWAVE2-Supplier-Alpha...');
  const suppInput = page.locator('input[placeholder*="Type 2+"]').first();
  await suppInput.focus();
  await suppInput.pressSequentially('Alpha', { delay: 100 });
  await page.waitForTimeout(1000);

  const suppOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Supplier-Alpha' }).first();
  await suppOpt.click();
  await page.waitForTimeout(1000);

  console.log('Party Box text:\n', await page.locator('text=Bill from').first().locator('..').innerText());

  // Add Product: UXWAVE2-Item-Widget
  const prodInput = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
  await prodInput.focus();
  await prodInput.pressSequentially('Widget', { delay: 100 });
  await page.waitForTimeout(1000);

  const prodOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Item-Widget' }).first();
  if (await prodOpt.count() > 0) {
    await prodOpt.click();
  } else {
    // try option 1
    await page.locator('li[role="option"]').first().click();
  }
  await page.waitForTimeout(1000);

  // Set quantity = 20
  const qtyField = page.locator('table tbody tr td').locator('input').nth(1);
  if (await qtyField.isVisible()) {
    await qtyField.fill('20');
    await page.keyboard.press('Tab');
  }
  await page.waitForTimeout(1000);

  const saveBtn = page.locator('button:has-text("Save & Complete")').first();
  console.log('Save & Complete disabled:', await saveBtn.isDisabled());

  if (!await saveBtn.isDisabled()) {
    console.log('Clicking Save & Complete...');
    await saveBtn.click();
    await page.waitForTimeout(2500);
    console.log('Purchase saved! Current URL:', page.url());
  }

  await browser.close();
})();
