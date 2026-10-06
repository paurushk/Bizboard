import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ShareInvoiceDialog } from '@/components/ShareInvoiceDialog';

const { flagState, shareInvoice, openShare } = vi.hoisted(() => ({
  flagState: { cloud: false },
  shareInvoice: vi.fn(async () => ({
    status: 'QUEUED',
    mode: 'cloud' as const,
    shareLink: 'https://wa.me/919812345678',
    whatsappSendStatus: 'QUEUED',
  })),
  openShare: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  shareInvoice: (...args: unknown[]) => shareInvoice(...(args as [number, { channel: string; recipient: string }])),
}));

vi.mock('@/config/featureFlags', () => ({
  isRuntimeFlagEnabled: (key: string) => key === 'ENABLE_WHATSAPP_CLOUD' && flagState.cloud,
}));

vi.mock('@/utils/safeUrl', () => ({
  isAllowedShareUrl: () => true,
  openShareUrl: (...args: unknown[]) => openShare(...args),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ShareInvoiceDialog', () => {
  beforeEach(() => {
    flagState.cloud = false;
    shareInvoice.mockClear();
    openShare.mockClear();
  });

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
    const share = screen.getByRole('button', { name: /share on whatsapp/i });
    expect(share.textContent ?? '').not.toMatch(/send on whatsapp/i);
    await userEvent.click(share);
    expect(shareInvoice).toHaveBeenCalledWith(7, { channel: 'WHATSAPP', recipient: '919812345678' });
  });

  it('sends on WhatsApp through the share endpoint when cloud is on and does not open a share sheet', async () => {
    flagState.cloud = true;
    wrap(
      <ShareInvoiceDialog
        open
        invoiceId={9}
        defaultPhone="919812345678"
        onClose={() => undefined}
      />,
    );
    const send = screen.getByRole('button', { name: /send on whatsapp/i });
    await userEvent.click(send);
    expect(shareInvoice).toHaveBeenCalledWith(9, { channel: 'WHATSAPP', recipient: '919812345678' });
    expect(openShare).not.toHaveBeenCalled();
  });

  describe('starting values', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const dialog = (open: boolean, defaultEmail = 'a@b.test', defaultPhone = '') => (
      <QueryClientProvider client={qc}>
        <ShareInvoiceDialog
          open={open}
          invoiceId={1}
          defaultEmail={defaultEmail}
          defaultPhone={defaultPhone}
          onClose={() => undefined}
        />
      </QueryClientProvider>
    );
    const emailBox = () => screen.getByRole('textbox', { name: /email/i }) as HTMLInputElement;

    it('starts from the party email and lets the user edit it', async () => {
      render(dialog(true));
      expect(emailBox().value).toBe('a@b.test');
      await userEvent.clear(emailBox());
      await userEvent.type(emailBox(), 'typo');
      expect(emailBox().value).toBe('typo');
    });

    it('goes back to the party email each time the dialog is reopened', async () => {
      const { rerender } = render(dialog(true));
      await userEvent.clear(emailBox());
      await userEvent.type(emailBox(), 'typo');

      rerender(dialog(false));
      rerender(dialog(true));
      expect(emailBox().value).toBe('a@b.test');
    });

    it('picks up new party details while the dialog is open', () => {
      const { rerender } = render(dialog(true, 'a@b.test'));
      rerender(dialog(true, 'new@b.test'));
      expect(emailBox().value).toBe('new@b.test');
    });

    it('does not wipe what the user typed when the page re-renders with the same details', async () => {
      const { rerender } = render(dialog(true));
      await userEvent.clear(emailBox());
      await userEvent.type(emailBox(), 'typo');
      rerender(dialog(true));
      expect(emailBox().value).toBe('typo');
    });

    it('opens on WhatsApp when only a phone is known, and on email otherwise', () => {
      const { unmount } = render(dialog(true, '', '919812345678'));
      expect(screen.getByRole('textbox', { name: /whatsapp/i })).toBeTruthy();
      unmount();
      render(dialog(true, 'a@b.test', ''));
      expect(emailBox()).toBeTruthy();
    });
  });
});
