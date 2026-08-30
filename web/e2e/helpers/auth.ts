import { expect, type APIRequestContext, type Page } from '@playwright/test';

const DEFAULT_OWNER = {
  email: 'owner@bizboard.local',
  password: 'demo-password',
};

const DEFAULT_VIEWER = {
  email: 'viewer@bizboard.local',
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
