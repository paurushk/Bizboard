import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PublicInvoicePage } from '@/pages/public/PublicInvoicePage';

vi.mock('@/api/resources', () => ({
  getPublicInvoice: vi.fn(async () => ({
    number: 'INV-9',
    status: 'COMPLETED',
    unpaid: '100.00',
    sellerName: 'Preview Stores',
    billTo: { name: 'Anil Store', address: 'MG Road' },
    lines: [{ name: 'Soap', quantity: '1', rate: '100', amount: '100' }],
    totals: { grandTotal: '100.00', paid: '0', unpaid: '100.00' },
  })),
  downloadPublicInvoicePdf: vi.fn(async () => new Blob(['%PDF'])),
  payPublicInvoice: vi.fn(),
}));

describe('INV-DET-05 public invoice', () => {
  it('shows the bill and a download, and hides cost and profit', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/i/public-token']}>
          <Routes>
            <Route path="/i/:token" element={<PublicInvoicePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Anil Store')).toBeInTheDocument();
    expect(screen.getByText('Soap')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download pdf/i })).toBeInTheDocument();
    expect(screen.queryByText(/profit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/purchase price/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/margin/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unit cost/i)).not.toBeInTheDocument();
  });
});
