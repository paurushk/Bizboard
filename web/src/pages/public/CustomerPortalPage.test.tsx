import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { CustomerPortalPage } from '@/pages/public/CustomerPortalPage';

const getCustomerPortal = vi.fn();

vi.mock('@/api/resources', () => ({
  getCustomerPortal: (...args: unknown[]) => getCustomerPortal(...args),
  downloadCustomerPortalInvoice: vi.fn(),
  startCustomerPortalPayment: vi.fn(),
}));

function wrap(ui: ReactElement, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/portal/:token" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CustomerPortalPage', () => {
  it('lists the customer invoice and a pay action when money is outstanding', async () => {
    getCustomerPortal.mockResolvedValue({
      customerName: 'Ravi Traders',
      invoices: [{
        id: 9,
        number: 'INV-9',
        invoiceDate: '2026-09-01',
        amount: '118.00',
        outstanding: '118.00',
        payPath: '/pay/tok',
      }],
    });
    wrap(<CustomerPortalPage />, '/portal/tok');
    expect(await screen.findByText('Ravi Traders')).toBeTruthy();
    expect(screen.getByText(/INV-9/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Pay' })).toBeTruthy();
  });

  it('shows the expired-link message when the token is rejected', async () => {
    getCustomerPortal.mockRejectedValue(new Error('missing'));
    wrap(<CustomerPortalPage />, '/portal/expired');
    expect(await screen.findByRole('heading', { name: /unavailable or has expired/i })).toBeTruthy();
  });
});
