import { defineConfig, devices } from '@playwright/test';

/**
 * BUG-725 — a real end-to-end run against the live backend (no mocks),
 * covering the golden path: register -> create product/customer -> invoice
 * -> complete -> stock decrement -> receipt -> allocate -> PDF download.
 *
 * The API webServer pins DJANGO_SETTINGS_MODULE=config.settings so a parent
 * shell that exported config.settings_test (in-memory SQLite) cannot make
 * register hit "no such table: accounts_user".
 * Prerequisite: `cd backend && python manage.py migrate` against that settings module.
 *
 * Run with: npm run test:e2e:golden
 * Override ports (e.g. if 8000/5173 are already in use locally) with
 * E2E_GOLDEN_API_PORT / E2E_GOLDEN_WEB_PORT.
 */
const apiPort = process.env.E2E_GOLDEN_API_PORT || '8000';
const webPort = process.env.E2E_GOLDEN_WEB_PORT || '5173';
const backendBase = process.env.E2E_GOLDEN_API_URL || `http://127.0.0.1:${apiPort}`;
const webBase = process.env.E2E_GOLDEN_BASE_URL || `http://127.0.0.1:${webPort}`;
const spaOrigins = [`http://127.0.0.1:${webPort}`, `http://localhost:${webPort}`].join(',');
const goldenApiEnv = {
  PYTHONUNBUFFERED: '1',
  CELERY_TASK_ALWAYS_EAGER: '1',
  // F1-014: the recent mandatory sign-up email OTP requirement means
  // registerTenant() (used by every golden spec, not just the
  // competitive-roadmap ones) now needs to read the "Dev OTP:" hint this
  // config never enabled — without it, EVERY golden spec's registration
  // step hangs until its own timeout. Same opt-in-debug-echo posture as
  // PORTAL_DEBUG_ECHO below, hard-rejected outside dev/test.
  OTP_DEBUG_ECHO: '1',
  DJANGO_DEBUG: '1',
  DJANGO_ENV: 'development',
  DJANGO_SETTINGS_MODULE: 'config.settings',
  REDIS_URL: '',
  ENABLE_SETUP_WIZARD: '0',
  ENABLE_POS: '1',
  ENABLE_ACCOUNTING: '1',
  UNSUBSCRIBED_SEAT_LIMIT: '0',
  FRONTEND_URL: webBase,
  CORS_ALLOWED_ORIGINS: spaOrigins,
  CSRF_TRUSTED_ORIGINS: spaOrigins,
  // F1-012: the six competitive-roadmap tickets (COMP-002/003/005/006/007),
  // all ROLLOUT_GRANTABLE_KEYS with no plan-entitlement narrowing for a
  // fresh e2e tenant, so setting the env default is enough — no per-company
  // UI toggle exists (there is no settings page for these yet; see
  // docs/roadmap/COMPETITIVE_ROADMAP_PHASED_PLAN.md). Runtime-checked on the
  // frontend (isRuntimeFlagEnabled), so no matching VITE_ENABLE_* is needed.
  ENABLE_REPLENISHMENT: '1',
  ENABLE_GST_GUARD: '1',
  ENABLE_ROUTE_PROFIT: '1',
  ENABLE_SUPPLIER_PRICE_HISTORY: '1',
  ENABLE_CUSTOMER_PORTAL: '1',
  // F1-011: lets the customer-portal e2e spec read the magic-link token
  // straight from the request-link response instead of an inbox — same
  // opt-in-debug-echo posture as OTP_DEBUG_ECHO, hard-rejected outside dev.
  PORTAL_DEBUG_ECHO: '1',
};

export default defineConfig({
  testDir: './e2e-golden',
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: webBase,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.E2E_GOLDEN_SKIP_WEBSERVER
    ? undefined
    : [
        {
          command: `python manage.py runserver 127.0.0.1:${apiPort} --noreload`,
          cwd: '../backend',
          url: `${backendBase}/api/v1/health/`,
          // Must not reuse a leftover runserver: parent shells often export
          // settings_test / Redis / localhost-only CORS, which 403 cookie refresh
          // after page.goto and the suite looks "logged out" on Products.
          reuseExistingServer: false,
          timeout: 60_000,
          env: goldenApiEnv,
        },
        {
          command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
          cwd: '.',
          url: webBase,
          reuseExistingServer: false,
          timeout: 60_000,
          env: {
            VITE_API_PROXY_TARGET: backendBase,
            VITE_ENABLE_POS: 'true',
            VITE_ENABLE_ACCOUNTING: 'true',
            VITE_ENABLE_ATOMIC_POS_CHECKOUT: 'true',
          },
        },
      ],
});
