import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RecurringInvoicesPage } from '@/pages/sales/RecurringInvoicesPage';

const listCustomersPage = vi.fn();

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));
vi.mock('@/hooks/useProductCfFilters', () => ({
  useProductCfFilters: () => ({ cfFilters: {}, defs: [], setFilter: () => undefined, clear: () => undefined }),
}));
vi.mock('@/api/resources', () => ({
  listRecurringSchedulesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listCustomersPage: (...args: unknown[]) => listCustomersPage(...args),
  searchProducts: async () => [],
  createRecurringSchedule: vi.fn(),
  runRecurringSchedule: vi.fn(),
  updateRecurringSchedule: vi.fn(),
  deleteRecurringSchedule: vi.fn(),
}));

describe('RecurringInvoicesPage customer picker', () => {
  beforeEach(() => {
    listCustomersPage.mockReset();
    listCustomersPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
  });

  it('offers active customers only, so a schedule is never set up for a blocked or archived one', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <RecurringInvoicesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(listCustomersPage).toHaveBeenCalledWith(expect.objectContaining({ status: 'ACTIVE', pageSize: 100 })),
    );
  });
});
