import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Customer360Page } from '@/pages/sales/Customer360Page';

vi.mock('@/api/osPlan', () => ({
  getCustomer360: vi.fn().mockResolvedValue({
    customerId: 4,
    name: 'Ravi Traders',
    sales: { invoices: 2, amount: '100' },
    products: ['Repeat Soap'],
    pattern: 'on_time',
    recommendedNextStep: '',
    outstanding: '40',
    aging: { current: '10', '130': '20', '3160': '0', '6190': '0', '90Plus': '5' },
    profit: { totals: { margin: '15', revenue: '100', cogs: '85' } },
  }),
}));

describe('Customer360Page', () => {
  it('shows aging buckets and profit from the margin total', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/sales/customers/4']}>
          <Routes>
            <Route path="/sales/customers/:id" element={<Customer360Page />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Ravi Traders')).toBeInTheDocument();
    expect(screen.getByText(/Profit:/)).toHaveTextContent('15.00');
    expect(screen.getByText(/Not yet due:/)).toHaveTextContent('10.00');
    expect(screen.getByText(/1–30 days:/)).toHaveTextContent('20.00');
    expect(screen.getByText(/Over 90 days:/)).toHaveTextContent('5.00');
    expect(screen.getByText('Repeat Soap')).toBeInTheDocument();
  });
});
