import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * AI Insights — /insights (hub) already has route-smoke coverage; these 4
 * sub-pages had none. ENABLE_AI defaults false (src/config/featureFlags.ts),
 * so allowAiInsights()/allowAiAssistant() fail and every route here lands on
 * LimitedAccessLanding's "Open Insights settings" CTA, not the page itself
 * — the same not-a-pilot-differentiator posture FREEZE_SCOPE.md records for
 * ENABLE_AI. Asserts that real, current, flag-off behavior.
 */
const ROUTES = [
  '/insights/alerts',
  '/insights/health',
  '/insights/cashflow',
  '/insights/assistant',
];

test.describe('insights domain (AI off — the default)', () => {
  for (const path of ROUTES) {
    test(`${path} offers to enable AI Insights rather than erroring`, async ({ page }) => {
      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page).not.toHaveURL(/\/login/);
      const enableLink = page.getByRole('link', { name: 'Open Insights settings' });
      await expect(enableLink).toBeVisible({ timeout: 15_000 });
      await expect(enableLink).toHaveAttribute('href', '/settings/ai');
    });
  }
});
