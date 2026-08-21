import { beforeEach, describe, expect, it, vi } from 'vitest';
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

import { regenerateSalesDocumentPdf } from '@/api/resources';

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
