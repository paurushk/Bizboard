import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { RecordInvoicePaymentDialog } from '@/components/RecordInvoicePaymentDialog';
import type { SalesInvoice } from '@/types/domain';

const recordInvoicePayment = vi.fn(async () => ({ id: 7, status: 'COMPLETED', balance: '0' }));

vi.mock('@/api/resources', () => ({
  recordInvoicePayment: (...args: unknown[]) =>
    recordInvoicePayment(...(args as [number, Record<string, unknown>])),
  uploadFile: vi.fn(),
}));

const invoice = {
  id: 7,
  number: 'INV-7',
  status: 'COMPLETED',
  grandTotal: '1180',
  balance: '1180',
} as SalesInvoice;

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('RecordInvoicePaymentDialog', () => {
  it('posts amount, settlement discount, and payment date', async () => {
    const onSuccess = vi.fn();
    wrap(
      <RecordInvoicePaymentDialog invoice={invoice} open onClose={() => undefined} onSuccess={onSuccess} />,
    );
    const amount = await screen.findByLabelText(/amount received/i);
    await userEvent.clear(amount);
    await userEvent.type(amount, '1000');
    await userEvent.type(screen.getByLabelText(/settlement discount/i), '180');
    await userEvent.click(screen.getByRole('button', { name: /record payment/i }));
    expect(recordInvoicePayment).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ amount: 1000, discount: 180, mode: 'CASH' }),
    );
  });
});
