import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const authApi = vi.hoisted(() => ({
  login: vi.fn(),
  verifyOtp: vi.fn(),
  verifyMfaLogin: vi.fn(),
  fetchCurrentUser: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
}));
vi.mock('@/api/auth', () => authApi);

vi.mock('@/api/client', () => ({
  ACTIVE_COMPANY_STORAGE_KEY: 'bb-active-company',
  shouldUseMocks: () => false,
  silentRefreshAccessToken: vi.fn().mockResolvedValue(null),
}));

const fetchFeatureFlags = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock('@/config/featureFlags', () => ({
  clearFeatureFlagsCache: vi.fn(),
  fetchFeatureFlags: (...a: unknown[]) => fetchFeatureFlags(...a),
}));

const session = vi.hoisted(() => ({
  clearSession: vi.fn(),
  getAccessToken: vi.fn(() => null),
  getStoredUser: vi.fn(() => null),
  setAccessToken: vi.fn(),
  setStoredUser: vi.fn(),
}));
vi.mock('@/auth/session', () => session);

vi.mock('@/lib/native', () => ({
  deepLinkToPath: vi.fn(),
  isNative: () => false,
  onDeepLink: () => () => undefined,
  registerForPushNotifications: vi.fn(),
}));
vi.mock('@/offline/invoiceDraftCache', () => ({ clearAllDrafts: vi.fn() }));
vi.mock('@/lib/deviceDraft', () => ({ clearForUser: vi.fn() }));
vi.mock('@/pages/pos/posStatus', () => ({ clearPosPendingStorageForUser: vi.fn() }));
vi.mock('@/pwaCaches', () => ({ clearBizboardPwaCaches: vi.fn() }));

import { AuthProvider, useAuth } from '@/auth/AuthContext';

function Probe() {
  const { user, isAuthenticated, completeMfaLogin } = useAuth();
  return (
    <div>
      <span data-testid="state">{isAuthenticated ? `in:${user?.email}` : 'out'}</span>
      <button onClick={() => void completeMfaLogin('tok-1', { code: '123456' }).catch(() => undefined)}>finish</button>
    </div>
  );
}

function renderProvider() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('AuthContext.completeMfaLogin (F-SEC-02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    session.getStoredUser.mockReturnValue(null);
    session.getAccessToken.mockReturnValue(null);
  });

  it('starts signed out, then a verified second factor establishes the session and loads feature flags', async () => {
    authApi.verifyMfaLogin.mockResolvedValue({
      user: { id: 7, email: 'owner@example.test', role: 'OWNER', companyId: 1 },
      tokens: { access: 'cookie' },
    });
    renderProvider();
    expect(await screen.findByTestId('state')).toHaveTextContent('out');

    await userEvent.click(screen.getByRole('button', { name: 'finish' }));

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('in:owner@example.test'));
    expect(authApi.verifyMfaLogin).toHaveBeenCalledWith('tok-1', { code: '123456' });
    expect(fetchFeatureFlags).toHaveBeenCalledWith(true);
  });

  it('a rejected code leaves the user signed out and does not fetch flags', async () => {
    authApi.verifyMfaLogin.mockRejectedValue(Object.assign(new Error('401'), { response: { status: 401 } }));
    renderProvider();
    await userEvent.click(await screen.findByRole('button', { name: 'finish' }));
    await waitFor(() => expect(authApi.verifyMfaLogin).toHaveBeenCalled());
    expect(screen.getByTestId('state')).toHaveTextContent('out');
    expect(fetchFeatureFlags).not.toHaveBeenCalledWith(true);
  });
});
