import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';

vi.mock('@/api/resources', () => ({
  getInvoicePdfStatus: vi.fn(async () => ({ pdfStatus: 'FAILED', pdfFile: null })),
  regenerateInvoicePdf: vi.fn(async () => ({ pdfStatus: 'QUEUED', pdfFile: null })),
  downloadInvoicePdf: vi.fn(async () => new Blob(['x'])),
}));

vi.mock('@/i18n', () => ({
  t: (key: string) => key,
}));

import { regenerateInvoicePdf } from '@/api/resources';

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('PdfStatusPoller', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls regenerateInvoicePdf on retry', async () => {
    wrap(<PdfStatusPoller invoiceId={42} />);
    const retry = await screen.findByText('common.retry');
    fireEvent.click(retry);
    await waitFor(() => {
      expect(regenerateInvoicePdf).toHaveBeenCalledWith(42);
    });
  });
});
