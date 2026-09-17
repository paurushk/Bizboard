/**
 * Shared route list for smoke coverage of protected screens — every route here
 * sits behind <ProtectedRoute> in src/App.tsx and must be reachable by an
 * authenticated OWNER without crashing, AND must bounce a logged-out visitor
 * straight to /login without crashing. See:
 *   - e2e/route-smoke.spec.ts (authenticated pass)
 *   - e2e/route-smoke-unauthenticated.spec.ts (logged-out deep-link pass)
 *
 * Keep this list in sync across both specs by importing it rather than
 * duplicating — that was the gap that let BB-000829 (a logged-out deep link
 * to /sales/new crashing into the error boundary) go untested for every other
 * protected route.
 */
export const PROTECTED_ROUTES = [
  '/',
  '/pos',
  '/sales/new',
  '/sales/history',
  '/sales/customers',
  '/sales/quotations',
  '/sales/orders',
  '/sales/delivery-challans',
  '/sales/credit-notes',
  '/purchases/history',
  '/purchases/new',
  '/purchases/orders',
  '/inventory/products',
  '/inventory/stock',
  '/accounting/journals',
  '/accounting/chart-of-accounts',
  '/reports/sales',
  '/insights',
  '/offline-outbox',
  '/settings/company',
];
