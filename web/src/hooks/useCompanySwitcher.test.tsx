import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ACTIVE_COMPANY_STORAGE_KEY } from '@/api/client';
import { useCompanySwitcher } from '@/hooks/useCompanySwitcher';

const env = vi.hoisted(() => ({
  mocks: false,
  get: vi.fn(),
  storedUser: null as { email: string } | null,
}));

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>();
  return {
    ...actual,
    shouldUseMocks: () => env.mocks,
    apiClient: { get: (...args: unknown[]) => env.get(...args), post: vi.fn() },
    unwrapData: (data: unknown) => data,
  };
});

vi.mock('@/api/auth', () => ({
  mockUserForEmail: (email: string) => ({
    email,
    role: 'OWNER',
    company: { id: 77, name: 'Mock Traders' },
  }),
}));

vi.mock('@/auth/session', () => ({
  getStoredUser: () => env.storedUser,
  setAccessToken: vi.fn(),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

describe('useCompanySwitcher', () => {
  beforeEach(() => {
    env.mocks = false;
    env.storedUser = null;
    env.get.mockReset();
    localStorage.clear();
  });

  it('loads the companies the user belongs to, in either key style', async () => {
    env.get.mockResolvedValue({
      data: [
        { companyId: 1, companyName: 'Acme', role: 'OWNER', isActiveSelection: true },
        { company_id: 2, company_name: 'Beta', role: 'STAFF', is_active_selection: false },
      ],
    });
    const { result } = renderHook(() => useCompanySwitcher(), { wrapper });
    await waitFor(() => expect(result.current.memberships).toHaveLength(2));
    expect(result.current.memberships[1]).toEqual({ companyId: 2, companyName: 'Beta', role: 'STAFF', isActiveSelection: false });
    expect(result.current.hasMultiple).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it('remembers the active company for later requests', async () => {
    env.get.mockResolvedValue({
      data: [{ companyId: 5, companyName: 'Acme', role: 'OWNER', isActiveSelection: true }],
    });
    renderHook(() => useCompanySwitcher(), { wrapper });
    await waitFor(() => expect(localStorage.getItem(ACTIVE_COMPANY_STORAGE_KEY)).toBe('5'));
  });

  it('reports a failure to load instead of leaving the list silently empty', async () => {
    env.get.mockRejectedValue(new Error('Server unreachable'));
    const { result } = renderHook(() => useCompanySwitcher(), { wrapper });
    await waitFor(() => expect(result.current.error).toBe('Server unreachable'));
    expect(result.current.memberships).toEqual([]);
    expect(result.current.hasMultiple).toBe(false);
  });

  it('starts empty and fills in after the first render, not during it', async () => {
    env.get.mockResolvedValue({ data: [{ companyId: 1, companyName: 'Acme', role: 'OWNER', isActiveSelection: true }] });
    const { result } = renderHook(() => useCompanySwitcher(), { wrapper });
    expect(result.current.memberships).toEqual([]);
    await waitFor(() => expect(result.current.memberships).toHaveLength(1));
  });

  it('in demo mode builds the one company from the stored user without calling the server', async () => {
    env.mocks = true;
    env.storedUser = { email: 'owner@bizboard.local' };
    const { result } = renderHook(() => useCompanySwitcher(), { wrapper });
    await waitFor(() => expect(result.current.memberships).toHaveLength(1));
    expect(result.current.memberships[0]).toEqual({
      companyId: 77,
      companyName: 'Mock Traders',
      role: 'OWNER',
      isActiveSelection: true,
    });
    expect(env.get).not.toHaveBeenCalled();
  });

  it('in demo mode with nobody stored shows no companies', async () => {
    env.mocks = true;
    const { result } = renderHook(() => useCompanySwitcher(), { wrapper });
    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.memberships).toEqual([]);
  });
});
