import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';

vi.mock('@/api/resources', () => ({
  getSalesDocumentPdfStatus: vi.fn(async () => ({ pdfStatus: 'FAILED', pdfFile: null })),
  regenerateSalesDocumentPdf: vi.fn(async () => ({ pdfStatus: 'QUEUED', pdfFile: null })),
  downloadSalesDocumentPdf: vi.fn(async () => new Blob(['x'])),
}));

vi.mock('@/i18n', () => ({
  t: (key: string) => key,
}));

import { getSalesDocumentPdfStatus, regenerateSalesDocumentPdf } from '@/api/resources';

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('PdfStatusPoller', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls regenerateSalesDocumentPdf on retry for invoice', async () => {
    wrap(<PdfStatusPoller invoiceId={42} />);
    const retry = await screen.findByText('common.retry');
    fireEvent.click(retry);
    await waitFor(() => {
      expect(regenerateSalesDocumentPdf).toHaveBeenCalledWith('invoice', 42);
    });
  });

  it('uses docType for credit notes', async () => {
    wrap(<PdfStatusPoller documentId={7} docType="credit-note" />);
    const retry = await screen.findByText('common.retry');
    fireEvent.click(retry);
    await waitFor(() => {
      expect(regenerateSalesDocumentPdf).toHaveBeenCalledWith('credit-note', 7);
    });
  });
});

describe('PdfStatusPoller polling', () => {
  const status = vi.mocked(getSalesDocumentPdfStatus);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the download button, tells the page once, and stops polling when the PDF is ready', async () => {
    status.mockResolvedValue({ pdfStatus: 'READY', pdfUrl: 'https://files.test/inv-1.pdf' } as never);
    const onReady = vi.fn();
    wrap(<PdfStatusPoller invoiceId={1} onReady={onReady} />);

    expect(await screen.findByText('common.download')).toBeTruthy();
    expect(onReady).toHaveBeenCalledWith('https://files.test/inv-1.pdf');
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(status).toHaveBeenCalledTimes(1);
    expect(onReady).toHaveBeenCalledTimes(1);
  });

  it('keeps asking while the PDF is still being made', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'setInterval', 'clearTimeout', 'clearInterval'], shouldAdvanceTime: true });
    status.mockResolvedValue({ pdfStatus: 'QUEUED' } as never);
    wrap(<PdfStatusPoller invoiceId={2} />);

    expect(await screen.findByText('billing.pdfWaiting')).toBeTruthy();
    const first = status.mock.calls.length;
    await vi.advanceTimersByTimeAsync(4000);
    await waitFor(() => expect(status.mock.calls.length).toBeGreaterThan(first));
    expect(screen.queryByText('common.retry')).toBeNull();
  });

  it('asks the server again after Retry, rather than showing the old failure', async () => {
    status.mockResolvedValueOnce({ pdfStatus: 'FAILED' } as never);
    status.mockResolvedValue({ pdfStatus: 'READY', pdfUrl: 'https://files.test/ok.pdf' } as never);
    wrap(<PdfStatusPoller invoiceId={3} />);

    fireEvent.click(await screen.findByText('common.retry'));
    await waitFor(() => expect(regenerateSalesDocumentPdf).toHaveBeenCalledWith('invoice', 3));
    expect(await screen.findByText('common.download')).toBeTruthy();
    expect(status.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('renders nothing when disabled or when there is no document', () => {
    const { container, rerender } = wrap(<PdfStatusPoller invoiceId={4} enabled={false} />);
    expect(container.textContent).toBe('');
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <PdfStatusPoller />
      </QueryClientProvider>,
    );
    expect(container.textContent).toBe('');
    expect(status).not.toHaveBeenCalled();
  });
});
