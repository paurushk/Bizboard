import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CustomerPortalPage } from '@/pages/public/CustomerPortalPage';

const getCustomerPortal = vi.fn();
const submitPortalComplaint = vi.fn();

vi.mock('@/api/resources', () => ({
  getCustomerPortal: (...args: unknown[]) => getCustomerPortal(...args),
  downloadCustomerPortalInvoice: vi.fn(),
  startCustomerPortalPayment: vi.fn(),
  submitPortalComplaint: (...args: unknown[]) => submitPortalComplaint(...args),
}));

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/portal/tok']}>
        <Routes>
          <Route path="/portal/:token" element={<CustomerPortalPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CustomerPortalPage complaints', () => {
  it('hides the complaint form when complaints are off', async () => {
    getCustomerPortal.mockResolvedValue({
      customerName: 'Ravi',
      expiresAt: '2026-09-29T00:00:00Z',
      complaintsEnabled: false,
      invoices: [],
    });
    wrap();
    expect(await screen.findByText('Ravi')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /submit complaint/i })).toBeNull();
  });

  it('shows the complaint form when complaints are on', async () => {
    getCustomerPortal.mockResolvedValue({
      customerName: 'Ravi',
      expiresAt: '2026-09-29T00:00:00Z',
      complaintsEnabled: true,
      invoices: [],
    });
    wrap();
    expect(await screen.findByRole('button', { name: /submit complaint/i })).toBeTruthy();
  });

  it('uses a fresh idempotency key after a complaint is sent', async () => {
    submitPortalComplaint.mockResolvedValue({ id: 1, number: 'RMA-1' });
    getCustomerPortal.mockResolvedValue({
      customerName: 'Ravi',
      expiresAt: '2026-09-29T00:00:00Z',
      complaintsEnabled: true,
      invoices: [],
    });
    const user = userEvent.setup();
    wrap();
    const description = await screen.findByLabelText('What went wrong');
    await user.type(description, 'The box was crushed');
    await user.click(screen.getByRole('button', { name: 'Submit complaint' }));
    expect(await screen.findByText('Complaint received')).toBeTruthy();
    const firstKey = submitPortalComplaint.mock.calls[0][2];
    await user.click(screen.getByRole('button', { name: 'Submit complaint' }));
    expect(submitPortalComplaint.mock.calls[1][2]).not.toBe(firstKey);
  });
});
