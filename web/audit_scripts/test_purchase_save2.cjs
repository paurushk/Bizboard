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

  // Focus and type supplier
  console.log('Typing supplier...');
  const suppInput = page.locator('input[placeholder*="Type 2+"]').first();
  await suppInput.focus();
  await suppInput.pressSequentially('UXWAVE2', { delay: 100 });
  await page.waitForTimeout(1000);

  const opts = await page.locator('li[role="option"]').allInnerTexts();
  console.log('Options found:', opts);

  if (opts.length > 0) {
    await page.locator('li[role="option"]').first().click();
    console.log('Clicked option 1');
  }
  await page.waitForTimeout(1000);

  // Focus and type product
  console.log('Typing product...');
  const prodInput = page.locator('input[placeholder*="Search product"]').first();
  await prodInput.focus();
  await prodInput.pressSequentially('UXWAVE2', { delay: 100 });
  await page.waitForTimeout(1000);

  const prodOpts = await page.locator('li[role="option"]').allInnerTexts();
  console.log('Product options found:', prodOpts);

  if (prodOpts.length > 0) {
    await page.locator('li[role="option"]').first().click();
    console.log('Clicked product option 1');
  }
  await page.waitForTimeout(1000);

  // Update quantity to 20
  const qtyField = page.locator('table tbody tr td').locator('input').nth(1);
  if (await qtyField.isVisible()) {
    await qtyField.fill('20');
    await page.keyboard.press('Tab');
  }
  await page.waitForTimeout(1000);

  const saveBtn = page.locator('button:has-text("Save & Complete")').first();
  console.log('Save & Complete disabled:', await saveBtn.isDisabled());

  if (!await saveBtn.isDisabled()) {
    await saveBtn.click();
    await page.waitForTimeout(2000);
    console.log('Purchase saved! URL is now:', page.url());
  }

  await browser.close();
})();
