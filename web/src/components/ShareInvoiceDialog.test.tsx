import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ShareInvoiceDialog } from '@/components/ShareInvoiceDialog';

const shareInvoice = vi.fn(async () => ({
  status: 'QUEUED',
  mode: 'cloud' as const,
  whatsappSendStatus: 'QUEUED',
}));

vi.mock('@/api/resources', () => ({
  shareInvoice: (...args: unknown[]) => shareInvoice(...(args as [number, { channel: string; recipient: string }])),
}));

vi.mock('@/config/featureFlags', () => ({
  isRuntimeFlagEnabled: () => false,
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ShareInvoiceDialog', () => {
  it('sends the invoice PDF via email using shareInvoice', async () => {
    const onSuccess = vi.fn();
    wrap(
      <ShareInvoiceDialog
        open
        invoiceId={42}
        defaultEmail="a@b.test"
        onClose={() => undefined}
        onSuccess={onSuccess}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }));
    expect(shareInvoice).toHaveBeenCalledWith(42, { channel: 'EMAIL', recipient: 'a@b.test' });
  });

  it('sends WhatsApp share with the default phone', async () => {
    wrap(
      <ShareInvoiceDialog
        open
        invoiceId={7}
        defaultPhone="919812345678"
        onClose={() => undefined}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /^whatsapp$/i }));
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }));
    expect(shareInvoice).toHaveBeenCalledWith(7, { channel: 'WHATSAPP', recipient: '919812345678' });
  });
});
