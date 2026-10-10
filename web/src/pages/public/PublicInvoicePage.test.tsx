import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getPublicInvoice, payPublicInvoice } from '@/api/resources';
import { PublicInvoicePage } from '@/pages/public/PublicInvoicePage';

const completedBill = vi.hoisted(() => ({
  number: 'INV-9',
  status: 'COMPLETED',
  unpaid: '100.00',
  sellerName: 'Preview Stores',
  billTo: { name: 'Anil Store', address: 'MG Road' },
  lines: [{ name: 'Soap', quantity: '1', rate: '100', amount: '100' }],
  totals: { grandTotal: '100.00', paid: '0', unpaid: '100.00' },
}));

vi.mock('@/api/resources', () => ({
  getPublicInvoice: vi.fn(async () => completedBill),
  downloadPublicInvoicePdf: vi.fn(async () => new Blob(['%PDF'])),
  payPublicInvoice: vi.fn(),
}));

function openPublicInvoice() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/i/public-token']}>
        <Routes>
          <Route path="/i/:token" element={<PublicInvoicePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('INV-DET-05 public invoice', () => {
  beforeEach(() => {
    vi.mocked(getPublicInvoice).mockResolvedValue(completedBill);
    vi.mocked(payPublicInvoice).mockReset();
  });

  it('shows the bill and a download, and hides cost and profit', async () => {
    openPublicInvoice();
    expect(await screen.findByText('Anil Store')).toBeInTheDocument();
    expect(screen.getByText('Soap')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download pdf/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /pay now/i })).toBeInTheDocument();
    expect(screen.queryByText(/profit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/purchase price/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/margin/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unit cost/i)).not.toBeInTheDocument();
  });

  it('a cancelled bill stays on the page and hides Pay now', async () => {
    vi.mocked(getPublicInvoice).mockResolvedValue({ ...completedBill, status: 'CANCELLED' });
    openPublicInvoice();
    expect(await screen.findByText('Cancelled')).toBeInTheDocument();
    expect(screen.getByText('Anil Store')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pay now/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download pdf/i })).toBeInTheDocument();
  });

  it('Pay now shows the gateway message when no payment page can be opened', async () => {
    vi.mocked(payPublicInvoice).mockRejectedValue(new Error('Payment gateway credentials are required.'));
    const user = userEvent.setup();
    openPublicInvoice();
    await user.click(await screen.findByRole('button', { name: /pay now/i }));
    expect(await screen.findByText(/payment gateway credentials are required/i)).toBeInTheDocument();
  });
});
