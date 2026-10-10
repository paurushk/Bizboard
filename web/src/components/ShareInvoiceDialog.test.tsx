import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ShareInvoiceDialog } from '@/components/ShareInvoiceDialog';

const { shareInvoice } = vi.hoisted(() => ({
  shareInvoice: vi.fn(async (_id: number, payload: { channel: string; recipient: string; sendFromBusinessNumber?: boolean }) => {
    if (payload.channel === 'WHATSAPP' && !payload.recipient && !payload.sendFromBusinessNumber) {
      return { status: 'OPENED', mode: 'device' as const, text: 'Hello' };
    }
    return {
      status: 'SENT',
      mode: 'cloud' as const,
      shareLink: 'https://wa.me/919812345678',
      whatsappSendStatus: 'SENT',
    };
  }),
}));

const createInvoicePublicLink = vi.hoisted(() => vi.fn(async () => ({ url: '' })));
const downloadInvoicePdf = vi.hoisted(() => vi.fn(async () => new Blob(['pdf'])));

vi.mock('@/api/resources', () => ({
  shareInvoice: (...args: unknown[]) => shareInvoice(...(args as [number, { channel: string; recipient: string }])),
  createInvoicePublicLink: (...args: unknown[]) => createInvoicePublicLink(...(args as [])),
  downloadInvoicePdf: (...args: unknown[]) => downloadInvoicePdf(...(args as [])),
}));

let openWindow: ReturnType<typeof vi.spyOn>;

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ShareInvoiceDialog', () => {
  beforeEach(() => {
    shareInvoice.mockClear();
    openWindow = vi.spyOn(window, 'open').mockImplementation(() => null);
  });

  afterEach(() => {
    openWindow.mockRestore();
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

  it('INV-DET-04 WhatsApp opens this device with no phone number in the link', async () => {
    wrap(
      <ShareInvoiceDialog
        open
        invoiceId={7}
        defaultPhone="919812345678"
        onClose={() => undefined}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /^whatsapp$/i }));
    const share = screen.getByRole('button', { name: /you choose the chat/i });
    await userEvent.click(share);
    expect(shareInvoice).toHaveBeenCalledWith(7, { channel: 'WHATSAPP', recipient: '' });
    expect(openWindow).toHaveBeenCalled();
    const url = String(openWindow.mock.calls[0]?.[0] ?? '');
    expect(url.startsWith('https://wa.me/?text=')).toBe(true);
    expect(url).not.toMatch(/wa\.me\/\d/);
  });

  it('REVIEW device share is one server request and never mints a link on its own', async () => {
    createInvoicePublicLink.mockClear();
    wrap(<ShareInvoiceDialog open invoiceId={7} defaultPhone="919812345678" onClose={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: /^whatsapp$/i }));
    await userEvent.click(screen.getByRole('button', { name: /you choose the chat/i }));
    expect(shareInvoice).toHaveBeenCalledTimes(1);
    expect(createInvoicePublicLink).not.toHaveBeenCalled();
    const url = String(openWindow.mock.calls[0]?.[0] ?? '');
    expect(decodeURIComponent(url)).toContain('Hello');
  });

  it('REVIEW on a phone the PDF is fetched when WhatsApp is chosen and shared as a file', async () => {
    downloadInvoicePdf.mockClear();
    const share = vi.fn(async () => undefined);
    const ua = vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (Linux; Android 14) Mobile Safari');
    Object.defineProperty(navigator, 'canShare', { value: () => true, configurable: true });
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    try {
      wrap(<ShareInvoiceDialog open invoiceId={7} defaultPhone="919812345678" onClose={() => undefined} />);
      await userEvent.click(screen.getByRole('button', { name: /^whatsapp$/i }));
      await waitFor(() => expect(downloadInvoicePdf).toHaveBeenCalledWith(7));
      await userEvent.click(screen.getByRole('button', { name: /you choose the chat/i }));
      await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
      const data = share.mock.calls[0]?.[0] as unknown as { files?: File[]; text?: string };
      expect(data.files?.[0]?.type).toBe('application/pdf');
      expect(openWindow).not.toHaveBeenCalled();
    } finally {
      ua.mockRestore();
      delete (navigator as unknown as Record<string, unknown>).canShare;
      delete (navigator as unknown as Record<string, unknown>).share;
    }
  });

  it('REVIEW closing the phone share sheet is not an error', async () => {
    const onError = vi.fn();
    const dismissed = Object.assign(new Error('closed'), { name: 'AbortError' });
    const ua = vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile');
    Object.defineProperty(navigator, 'share', { value: vi.fn(async () => { throw dismissed; }), configurable: true });
    try {
      wrap(<ShareInvoiceDialog open invoiceId={7} defaultPhone="919812345678" onClose={() => undefined} onError={onError} />);
      await userEvent.click(screen.getByRole('button', { name: /^whatsapp$/i }));
      await userEvent.click(screen.getByRole('button', { name: /you choose the chat/i }));
      await waitFor(() => expect(shareInvoice).toHaveBeenCalled());
      expect(onError).not.toHaveBeenCalled();
    } finally {
      ua.mockRestore();
      delete (navigator as unknown as Record<string, unknown>).share;
    }
  });

  it('posts the phone only for send from business number and does not open a share sheet', async () => {
    wrap(
      <ShareInvoiceDialog
        open
        invoiceId={9}
        defaultPhone="919812345678"
        allowBusinessWhatsApp
        onClose={() => undefined}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /send from business number/i }));
    expect(shareInvoice).toHaveBeenCalledWith(9, {
      channel: 'WHATSAPP',
      recipient: '919812345678',
      sendFromBusinessNumber: true,
    });
    expect(openWindow).not.toHaveBeenCalled();
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
      expect(screen.getByRole('button', { name: /^whatsapp$/i, pressed: true })).toBeTruthy();
      expect(screen.queryByRole('textbox', { name: /whatsapp/i })).toBeNull();
      unmount();
      render(dialog(true, 'a@b.test', ''));
      expect(emailBox()).toBeTruthy();
    });
  });
});
