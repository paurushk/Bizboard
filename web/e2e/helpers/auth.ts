import { expect, type APIRequestContext, type Page } from '@playwright/test';

const DEFAULT_OWNER = {
  email: 'owner@bizboard.local',
  password: 'demo-password',
};

const DEFAULT_VIEWER = {
  email: 'viewer@bizboard.local',
  password: 'demo-password',
};

const DEFAULT_SALES = {
  email: 'sales@bizboard.local',
  password: 'demo-password',
};

const DEFAULT_ACCOUNTANT = {
  email: 'accountant@bizboard.local',
  password: 'demo-password',
};

// "books-on" opts into the accountingEnabled:true mock company (mocks/data.ts)
// instead of the shared books-off default every other persona uses — see
// web/src/api/auth.ts's mockUserForEmail.
const DEFAULT_OWNER_BOOKS_ON = {
  email: 'owner-books-on@bizboard.local',
  password: 'demo-password',
};

const DEFAULT_ACCOUNTANT_BOOKS_ON = {
  email: 'accountant-books-on@bizboard.local',
  password: 'demo-password',
};

/** POST /api/v1/auth/login/ and rely on Set-Cookie (real backend). */
export async function loginViaApi(
  request: APIRequestContext,
  baseURL: string,
  credentials: { email: string; password: string } = DEFAULT_OWNER,
) {
  const apiRoot = baseURL.replace(/\/$/, '') + '/api/v1';
  const response = await request.post(`${apiRoot}/auth/login/`, {
    data: { email: credentials.email, password: credentials.password },
  });
  expect(response.ok(), `login failed: ${response.status()} ${await response.text()}`).toBeTruthy();
  return response;
}

/** Sign in through the login form (mock e2e or real UI flow). */
export async function loginViaUi(
  page: Page,
  credentials: { email: string; password: string } = DEFAULT_OWNER,
) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /email/i }).fill(credentials.email);
  await page.locator('input[name="password"]').fill(credentials.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 });
}

export async function loginAsOwner(page: Page) {
  await loginViaUi(page, DEFAULT_OWNER);
}

export async function loginAsViewer(page: Page) {
  await loginViaUi(page, DEFAULT_VIEWER);
}

export async function loginAsSales(page: Page) {
  await loginViaUi(page, DEFAULT_SALES);
}

export async function loginAsAccountant(page: Page) {
  await loginViaUi(page, DEFAULT_ACCOUNTANT);
}

export async function loginAsOwnerBooksOn(page: Page) {
  await loginViaUi(page, DEFAULT_OWNER_BOOKS_ON);
}

export async function loginAsAccountantBooksOn(page: Page) {
  await loginViaUi(page, DEFAULT_ACCOUNTANT_BOOKS_ON);
}

const DEFAULT_OWNER_EMPTY_GSTIN = {
  email: 'owner-empty-gstin@bizboard.local',
  password: 'demo-password',
};

const DEFAULT_OWNER_STOCK_BLOCK = {
  email: 'owner-stock-block@bizboard.local',
  password: 'demo-password',
};

export async function loginAsOwnerEmptyGstin(page: Page) {
  await loginViaUi(page, DEFAULT_OWNER_EMPTY_GSTIN);
}

export async function loginAsOwnerStockBlock(page: Page) {
  await loginViaUi(page, DEFAULT_OWNER_STOCK_BLOCK);
}

const DEFAULT_OWNER_WRITES_BLOCKED = {
  email: 'owner-writes-blocked@bizboard.local',
  password: 'demo-password',
};

export async function loginAsOwnerWritesBlocked(page: Page) {
  await loginViaUi(page, DEFAULT_OWNER_WRITES_BLOCKED);
}
