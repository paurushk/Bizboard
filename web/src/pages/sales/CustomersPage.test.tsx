import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CustomersPage } from '@/pages/sales/CustomersPage';

const listCustomersPage = vi.fn();

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/resources', () => ({
  listCustomersPage: (...args: unknown[]) => listCustomersPage(...(args as [])),
  getCompany: async () => ({ id: 9, name: 'Shop' }),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  listCollectionRisk: async () => [],
  listPriceLists: async () => [],
  verifyCustomerGstin: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CustomersPage sort (#47)', () => {
  beforeEach(() => {
    listCustomersPage.mockReset();
    listCustomersPage.mockResolvedValue({
      results: [{ id: 1, name: 'Ravi Traders', status: 'ACTIVE', phone: '9999999999' }],
      count: 1,
      next: null,
      previous: null,
    });
  });

  it('sends sort=recent when Recently active is chosen', async () => {
    wrap(<CustomersPage />);
    expect(await screen.findByText('Ravi Traders')).toBeTruthy();
    await userEvent.click(screen.getByLabelText('Filter'));
    await userEvent.click(await screen.findByRole('option', { name: /recently active/i }));
    expect(listCustomersPage).toHaveBeenCalledWith(expect.objectContaining({ sort: 'recent' }));
  });
});
