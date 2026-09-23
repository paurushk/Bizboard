import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { CustomerPortalRequestPage } from '@/pages/public/CustomerPortalRequestPage';

const requestCustomerPortalLink = vi.fn();

vi.mock('@/api/resources', () => ({
  requestCustomerPortalLink: (...args: unknown[]) => requestCustomerPortalLink(...args),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('CustomerPortalRequestPage', () => {
  it('keeps send disabled until an email is entered, then shows the generic confirmation', async () => {
    requestCustomerPortalLink.mockResolvedValue({ detail: 'sent' });
    wrap(<CustomerPortalRequestPage />);
    expect(screen.getByRole('heading', { name: 'Get a link to your invoices' })).toBeTruthy();
    const send = screen.getByRole('button', { name: 'Send link' });
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Email'), 'buyer@example.com');
    expect(send).toBeEnabled();
    await userEvent.click(send);
    expect(requestCustomerPortalLink).toHaveBeenCalledWith({ email: 'buyer@example.com', phone: undefined });
    expect(await screen.findByText(/if we found a matching customer, we sent a link/i)).toBeTruthy();
  });
});
