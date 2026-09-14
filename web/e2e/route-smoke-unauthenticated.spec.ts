import { expect, test } from '@playwright/test';
import { PROTECTED_ROUTES } from './helpers/protectedRoutes';

/**
 * BB-000829 — a logged-out visitor hitting a protected, code-split route
 * directly (a bookmark, a shared link, a stale tab after the session cookie
 * expired) must bounce cleanly to /login. It must NOT render the generic
 * error boundary ("Something went wrong").
 *
 * This was the actual production bug: /sales/new crashed instead of
 * redirecting when hit cold and unauthenticated. route-smoke.spec.ts already
 * covered every route in PROTECTED_ROUTES for the *authenticated* case, but
 * every test in this suite logged in first (loginAsOwner in beforeEach), so
 * the logged-out deep-link path had zero coverage across the whole route
 * list — not just the one route that happened to fail. This file is the
 * missing logged-out pass over that same list.
 *
 * No login helper is called anywhere in this file — Playwright gives every
 * test a fresh, cookie-less browser context by default (no global
 * storageState is configured in playwright.config.ts), so these run genuinely
 * unauthenticated.
 */
test.describe('route smoke, logged out (top 20 deep links)', () => {
  for (const path of PROTECTED_ROUTES) {
    test(`${path} redirects to /login instead of crashing when logged out`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));

      await page.goto(path, { waitUntil: 'domcontentloaded' });
      // give the SPA a beat to boot auth, decide, and redirect
      await expect
        .poll(async () => (await page.locator('#root').innerHTML()).length, { timeout: 20_000 })
        .toBeGreaterThan(0);

      await expect(page, `logged-out deep link to ${path} should redirect to /login`).toHaveURL(/\/login/);
      await expect(
        page.getByRole('button', { name: /sign in/i }),
        `${path} should land on a working login form, not a stuck page`,
      ).toBeVisible();
      await expect(
        page.getByText(/something went wrong|unexpected error|error boundary/i),
        `${path} rendered the error boundary instead of redirecting while logged out`,
      ).toHaveCount(0);
      expect(errors, `${path} threw while logged out: ${errors.join(' | ')}`).toEqual([]);
    });
  }
});
