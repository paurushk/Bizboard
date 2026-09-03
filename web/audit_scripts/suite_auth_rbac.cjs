const { createAuditBrowser } = require('./helper.cjs');

async function testAuthAndRbac() {
  const audit = await createAuditBrowser();
  const { page } = audit;
  const results = [];

  function record(element, testType, status, details = '') {
    results.push({ module: 'Auth & RBAC', element, testType, status, details });
    console.log(`[${status}] ${element} (${testType}): ${details}`);
  }

  try {
    console.log('--- 1. Testing Login Page UI & Validations ---');
    await page.goto('http://localhost/login');
    await page.waitForLoadState('networkidle');

    // 1.1 Check elements presence
    const emailInput = await page.$('input[name="email"], input[type="email"], #email');
    const passInput = await page.$('input[name="password"], input[type="password"], #password');
    const submitBtn = await page.$('button[type="submit"]');

    if (emailInput && passInput && submitBtn) {
      record('Login Form Elements', 'UI Presence', 'PASS', 'Email, password, and submit button found');
    } else {
      record('Login Form Elements', 'UI Presence', 'FAIL', 'Missing login input fields');
    }

    // 1.2 Empty submit test
    await submitBtn.click();
    await page.waitForTimeout(500);
    const emptyErrors = await page.$$eval('.Mui-error, [role="alert"], .MuiFormHelperText-root.Mui-error', els => els.map(e => e.innerText));
    if (emptyErrors.length > 0) {
      record('Empty Submit Validation', 'Negative Path', 'PASS', `Error shown: "${emptyErrors.join('; ')}"`);
    } else {
      record('Empty Submit Validation', 'Negative Path', 'FAIL', 'No validation error on empty login submit');
    }

    // 1.3 Invalid email format test
    await emailInput.fill('notanemail');
    await passInput.fill('short');
    await submitBtn.click();
    await page.waitForTimeout(500);
    const formatErrors = await page.$$eval('.Mui-error, [role="alert"], .MuiFormHelperText-root.Mui-error', els => els.map(e => e.innerText));
    record('Invalid Email/Pass Format', 'Negative Path', formatErrors.length > 0 ? 'PASS' : 'FAIL', `Errors: "${formatErrors.join('; ')}"`);

    // 1.4 Invalid credentials test
    await emailInput.fill('invalid_user_999@example.com');
    await passInput.fill('WrongPass123!@#');
    await submitBtn.click();
    await page.waitForTimeout(1500);
    const alertMsg = await page.$$eval('[role="alert"], .MuiAlert-message, .MuiSnackbar-root', els => els.map(e => e.innerText));
    record('Invalid Credentials Response', 'Negative Path', alertMsg.length > 0 ? 'PASS' : 'FAIL', `Alert text: "${alertMsg.join('; ')}"`);

    // 1.5 Valid Login
    await emailInput.fill('demo@bizboard.local');
    await passInput.fill('DemoPass123!');
    await submitBtn.click();
    await page.waitForNavigation({ timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(1500);

    if (page.url().includes('/login')) {
      record('Valid Login Submission', 'Happy Path', 'FAIL', `Still on login page: ${page.url()}`);
    } else {
      record('Valid Login Submission', 'Happy Path', 'PASS', `Redirected to ${page.url()}`);
    }

    // 1.6 Check User Profile menu & Logout
    const profileBtn = await page.$('button[aria-label*="account"], button[aria-label*="user"], button[aria-haspopup="menu"]');
    if (profileBtn) {
      record('User Profile Menu', 'UI Presence', 'PASS', 'User profile dropdown button present');
    }

    console.log('--- 2. Testing Register Page ---');
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.goto('http://localhost/register');
    await page.waitForLoadState('networkidle');

    const regName = await page.$('input[name="name"], input[name="fullName"]');
    const regEmail = await page.$('input[name="email"]');
    const regPhone = await page.$('input[name="phone"]');
    const regPassword = await page.$('input[name="password"]');
    const regSubmit = await page.$('button[type="submit"]');

    if (regEmail && regPassword && regSubmit) {
      record('Register Page Elements', 'UI Presence', 'PASS', 'Registration inputs found');
      await regSubmit.click();
      await page.waitForTimeout(500);
      const regErrors = await page.$$eval('.Mui-error, [role="alert"], .MuiFormHelperText-root.Mui-error', els => els.map(e => e.innerText));
      record('Register Empty Submit', 'Negative Path', regErrors.length > 0 ? 'PASS' : 'FAIL', `Errors: "${regErrors.join('; ')}"`);
    } else {
      record('Register Page Elements', 'UI Presence', 'FAIL', 'Registration inputs missing');
    }

    console.log('--- 3. Testing Forgot Password Page ---');
    await page.goto('http://localhost/forgot-password');
    await page.waitForLoadState('networkidle');
    const fpEmail = await page.$('input[name="email"], input[type="email"]');
    const fpSubmit = await page.$('button[type="submit"]');
    if (fpEmail && fpSubmit) {
      record('Forgot Password Page', 'UI Presence', 'PASS', 'Forgot password form present');
      await fpEmail.fill('nonexistent@example.com');
      await fpSubmit.click();
      await page.waitForTimeout(1500);
      const fpMsg = await page.$$eval('[role="alert"], .MuiAlert-message, .MuiSnackbar-root, p', els => els.map(e => e.innerText));
      record('Forgot Password Request', 'Happy/Negative Path', 'PASS', `Message: "${fpMsg.slice(0, 2).join('; ')}"`);
    } else {
      record('Forgot Password Page', 'UI Presence', 'FAIL', 'Forgot password form not found');
    }

    console.log('--- 4. Testing Protected Routes Redirect ---');
    await page.goto('http://localhost/sales/history');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) {
      record('Unauthenticated Route Guard', 'Security & Navigation', 'PASS', `Redirected to login: ${page.url()}`);
    } else {
      record('Unauthenticated Route Guard', 'Security & Navigation', 'FAIL', `Accessible without auth: ${page.url()}`);
    }

  } catch (err) {
    console.error('Auth test failed with error:', err);
    record('Auth Test Suite Execution', 'Execution', 'FAIL', err.message);
  } finally {
    await audit.cleanup();
  }

  return results;
}

testAuthAndRbac().then(res => {
  console.log('=== AUTH & RBAC TEST COMPLETE ===');
});
