import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SalesReturnsPage } from '@/pages/sales/SalesReturnsPage';
import type { SalesInvoice } from '@/types/domain';

const { INVOICE, getSalesInvoice } = vi.hoisted(() => {
  const invoice: SalesInvoice = {
    id: 7,
    number: 'INV-0007',
    status: 'COMPLETED',
    invoiceType: 'RETAIL',
    customer: 3,
    customerName: 'Ravi Traders',
    invoiceDate: '2026-09-12',
    grandTotal: '200.00',
    subtotal: '200.00',
    discountTotal: '0',
    taxableTotal: '200.00',
    cgstTotal: '0',
    sgstTotal: '0',
    igstTotal: '0',
    roundOff: '0',
    balance: '200.00',
    items: [
      {
        id: 11,
        product: 4,
        productName: 'Widget',
        quantity: '2',
        unitPrice: '100',
        gstRate: '0',
      },
    ],
  } as SalesInvoice;
  return {
    INVOICE: invoice,
    getSalesInvoice: vi.fn(async () => invoice),
  };
});

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  listSalesReturnsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listSalesInvoicesPage: async () => ({ results: [INVOICE], count: 1, next: null, previous: null }),
  getSalesInvoice: (...args: unknown[]) => getSalesInvoice(...(args as [number])),
  listProducts: async () => [{ id: 4, name: 'Widget', sku: 'WID-1' }],
  listSalesReturns: async () => [],
  createSalesReturn: vi.fn(),
  completeSalesReturn: vi.fn(),
  updateSalesReturn: vi.fn(),
}));

function wrap(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/sales/returns" element={<SalesReturnsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SalesReturnsPage inbound invoice query', () => {
  it('opens create and prefills the invoice from ?create=1&invoice=', async () => {
    wrap('/sales/returns?create=1&invoice=7');
    expect(await screen.findByRole('dialog', { name: /new sales return/i })).toBeTruthy();
    await waitFor(() => expect(getSalesInvoice).toHaveBeenCalledWith(7));
    expect(await screen.findByDisplayValue(/INV-0007/)).toBeTruthy();
  });
});
