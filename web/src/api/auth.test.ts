import { beforeEach, describe, expect, it, vi } from 'vitest';

// G-4 (docs/TESTING_STRATEGY.md §7): fetchCurrentUser() in mock mode used to
// always return mockUser (OWNER), silently resetting a SALES/ACCT mock
// session back to OWNER on every AuthContext boot/navigation re-fetch — this
// made PJ-SALES/PJ-ACCT e2e assertions in role-boundaries.spec.ts pass for
// the wrong reason (testing OWNER's permissions, not SALES/ACCT's).
vi.mock('./client', () => ({
  shouldUseMocks: () => true,
  apiClient: { get: vi.fn(), post: vi.fn() },
  unwrapData: (x: unknown) => x,
}));

const getStoredUser = vi.fn();
vi.mock('@/auth/session', () => ({
  getStoredUser: (...args: unknown[]) => getStoredUser(...args),
  setAccessToken: vi.fn(),
}));

describe('mock-mode auth — fetchCurrentUser resolves the actual logged-in persona', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('login() picks the mock user matching the email', async () => {
    const { login } = await import('./auth');
    expect((await login({ email: 'sales@bizboard.local', password: 'x' })).user.role).toBe(
      'SALES_STAFF',
    );
    expect(
      (await login({ email: 'accountant@bizboard.local', password: 'x' })).user.role,
    ).toBe('ACCOUNTANT');
    expect((await login({ email: 'viewer@bizboard.local', password: 'x' })).user.role).toBe(
      'VIEWER',
    );
    expect((await login({ email: 'owner@bizboard.local', password: 'x' })).user.role).toBe(
      'OWNER',
    );
  });

  it('fetchCurrentUser() resolves from the stored session, not a hardcoded OWNER', async () => {
    const { fetchCurrentUser } = await import('./auth');

    getStoredUser.mockReturnValue({ id: 2, email: 'sales@bizboard.local', fullName: 'Demo Sales' });
    expect((await fetchCurrentUser()).role).toBe('SALES_STAFF');

    getStoredUser.mockReturnValue({
      id: 3,
      email: 'accountant@bizboard.local',
      fullName: 'Demo Accountant',
    });
    expect((await fetchCurrentUser()).role).toBe('ACCOUNTANT');
  });

  it('fetchCurrentUser() falls back to OWNER only when there is no stored session', async () => {
    const { fetchCurrentUser } = await import('./auth');
    getStoredUser.mockReturnValue(null);
    expect((await fetchCurrentUser()).role).toBe('OWNER');
  });
});
