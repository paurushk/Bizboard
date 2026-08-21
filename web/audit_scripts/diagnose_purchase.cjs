const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost/login');
  await page.fill('input[type=email]', 'demo@bizboard.local');
  await page.fill('input[type=password]', 'DemoPass123!');
  await page.click('button[type=submit]');
  await page.waitForTimeout(2000);
  await page.goto('http://localhost/purchases/new');
  await page.waitForTimeout(2000);

  // Look at PartySelectPanel
  const partyPanelText = await page.locator('text=Bill from').first().locator('..').innerText();
  console.log('Party panel text:\n', partyPanelText);

  // Try selecting supplier
  const input = page.locator('input[placeholder*="Type 2+"]').first();
  console.log('Supplier search input visible:', await input.isVisible());
  await input.click();
  await input.fill('UXWAVE2');
  await page.waitForTimeout(1000);

  const options = await page.locator('li[role="option"]').allInnerTexts();
  console.log('Autocomplete options:', options);

  if (options.length > 0) {
    await page.locator('li[role="option"]').first().click();
  }

  await page.waitForTimeout(1000);
  console.log('Party panel after select:\n', await page.locator('text=Bill from').first().locator('..').innerText());

  // Search product
  const prodInput = page.locator('input[placeholder*="Search product"]').first();
  console.log('Product input visible:', await prodInput.isVisible());
  await prodInput.click();
  await prodInput.fill('UXWAVE2');
  await page.waitForTimeout(1000);
  const prodOptions = await page.locator('li[role="option"]').allInnerTexts();
  console.log('Product options:', prodOptions);
  if (prodOptions.length > 0) {
    await page.locator('li[role="option"]').first().click();
  }

  await page.waitForTimeout(1000);
  const saveBtn = page.locator('button:has-text("Save & Complete")').first();
  console.log('Save & Complete disabled:', await saveBtn.isDisabled());

  // Let's check tooltip if disabled
  const tooltipSpan = page.locator('button:has-text("Save & Complete")').locator('..');
  console.log('Tooltip parent title:', await tooltipSpan.getAttribute('aria-label') || await tooltipSpan.getAttribute('title'));

  await browser.close();
})();
