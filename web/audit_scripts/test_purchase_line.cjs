const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost/login');
  await page.fill('input[type=email]', 'demo@bizboard.local');
  await page.fill('input[type=password]', 'DemoPass123!');
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');

  await page.goto('http://localhost/purchases/new');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Select Supplier
  const changeParty = page.locator('button:has-text("Change")').first();
  if (await changeParty.isVisible()) {
    await changeParty.click();
    await page.waitForTimeout(300);
  }

  const suppInput = page.locator('input[placeholder*="Type 2+"]').first();
  await suppInput.click();
  await suppInput.fill('Alpha');
  const suppOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Supplier-Alpha' }).first();
  await suppOpt.waitFor({ state: 'visible', timeout: 5000 });
  await suppOpt.click();
  console.log('Supplier selected successfully!');

  // Select Product
  const prodInput = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
  await prodInput.click();
  await prodInput.fill('UXWAVE2');
  const prodOpt = page.locator('li[role="option"]').first();
  await prodOpt.waitFor({ state: 'visible', timeout: 5000 });
  console.log('Product option label:', await prodOpt.innerText());
  await prodOpt.click();

  // Wait for line item row in table
  const lineRow = page.locator('table tbody tr').first();
  await lineRow.waitFor({ state: 'visible', timeout: 5000 });
  console.log('Line added to table!');

  // Quantity input
  const qtyInput = lineRow.locator('input').nth(1);
  await qtyInput.fill('20');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(1000);

  const saveBtn = page.locator('button:has-text("Save & Complete")').first();
  console.log('Save & Complete disabled:', await saveBtn.isDisabled());

  if (!await saveBtn.isDisabled()) {
    await saveBtn.click();
    await page.waitForTimeout(2500);
    console.log('Purchase saved! Redirected to:', page.url());
  }

  await browser.close();
})();
