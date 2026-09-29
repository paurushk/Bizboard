import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CustomersPage } from '@/pages/sales/CustomersPage';

const listCustomersPage = vi.fn();
const createCustomer = vi.fn();

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/resources', () => ({
  listCustomersPage: (...args: unknown[]) => listCustomersPage(...(args as [])),
  getCompany: async () => ({ id: 9, name: 'Shop' }),
  createCustomer: (...args: unknown[]) => createCustomer(...(args as [])),
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

  it('asks for both coordinates and sends them together', async () => {
    createCustomer.mockReset();
    createCustomer.mockImplementation(async (payload: unknown) => ({ id: 2, ...(payload as object) }));
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByRole('textbox', { name: /^Name/ }), 'Placed Shop');
    await user.type(within(dialog).getByRole('textbox', { name: 'Latitude' }), '12.97');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Enter both latitude and longitude, or leave both blank.')).toBeTruthy();
    expect(createCustomer).not.toHaveBeenCalled();
    await user.type(within(dialog).getByRole('textbox', { name: 'Longitude' }), '77.59');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createCustomer).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Placed Shop',
      latitude: '12.97',
      longitude: '77.59',
    })));
  });
});
