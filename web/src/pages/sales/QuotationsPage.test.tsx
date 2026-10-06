import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { QuotationsPage } from '@/pages/sales/QuotationsPage';
import { t } from '@/i18n';

const auth = vi.hoisted(() => ({ role: 'OWNER' as string }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: auth.role, companyId: 9 },
  }),
}));

vi.mock('@/api/payroll', () => ({
  listEmployeesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
}));

vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    listQuotationsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    listCustomersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    listProductsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    searchProducts: async () => [],
    listCustomFieldDefinitions: async () => [],
    getCompany: async () => ({ id: 9, name: 'Acme', registrationType: 'REGULAR', state: 'Delhi' }),
    getQuotation: vi.fn(),
  };
});

function SearchProbe() {
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
}

function mount(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <SearchProbe />
        <Routes>
          <Route path="/sales/quotations" element={<QuotationsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('QuotationsPage inbound ?create=1', () => {
  it('opens the new-quotation dialog and removes the parameter from the address', async () => {
    auth.role = 'OWNER';
    mount('/sales/quotations?create=1');
    expect(await screen.findByRole('dialog', { name: t('phase1.newQuotation') })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));
  });

  it('stays closed when the address has no create parameter', async () => {
    auth.role = 'OWNER';
    mount('/sales/quotations');
    await screen.findByText(t('nav.quotations'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps other parameters in the address when it strips create', async () => {
    auth.role = 'OWNER';
    mount('/sales/quotations?create=1&x=1');
    await screen.findByRole('dialog', { name: t('phase1.newQuotation') });
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe('?x=1'));
  });

  it('does not open for a user who cannot create quotations, and leaves the address alone', async () => {
    auth.role = 'VIEWER';
    mount('/sales/quotations?create=1');
    await screen.findByText(t('nav.quotations'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByTestId('search').textContent).toBe('?create=1');
  });
});
