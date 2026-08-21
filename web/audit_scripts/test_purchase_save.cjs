const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost/login');
  await page.fill('input[type=email]', 'demo@bizboard.local');
  await page.fill('input[type=password]', 'DemoPass123!');
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  console.log('Navigating to /purchases/new...');
  await page.goto('http://localhost/purchases/new');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Select Supplier
  console.log('Selecting supplier...');
  const suppInput = page.locator('input[placeholder*="Type 2+"]').first();
  await suppInput.click();
  await suppInput.fill('UXWAVE2');
  const suppOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Supplier-Alpha' });
  await suppOpt.waitFor({ state: 'visible', timeout: 5000 });
  await suppOpt.click();
  console.log('Supplier selected successfully!');

  // Select Product
  console.log('Selecting product...');
  const prodInput = page.locator('input[placeholder*="Search product"]').first();
  await prodInput.click();
  await prodInput.fill('UXWAVE2');
  const prodOpt = page.locator('li[role="option"]').filter({ hasText: 'UXWAVE2-Item-Widget' });
  await prodOpt.waitFor({ state: 'visible', timeout: 5000 });
  await prodOpt.click();
  console.log('Product selected successfully!');

  // Set quantity = 20
  const qtyField = page.locator('table tbody tr').first().locator('input').nth(1);
  await qtyField.fill('20');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(1000);

  const saveBtn = page.locator('button:has-text("Save & Complete")').first();
  console.log('Save & Complete disabled:', await saveBtn.isDisabled());

  if (!await saveBtn.isDisabled()) {
    console.log('Clicking Save & Complete...');
    await saveBtn.click();
    await page.waitForTimeout(2000);
    console.log('Purchase saved! Current URL:', page.url());
  }

  await browser.close();
})();
