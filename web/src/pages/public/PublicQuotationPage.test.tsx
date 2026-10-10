import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { AxiosError } from 'axios';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PublicQuotationPage } from '@/pages/public/PublicQuotationPage';
import { t } from '@/i18n';

const api = vi.hoisted(() => ({ getPublicQuotation: vi.fn(), downloadPublicQuotationPdf: vi.fn() }));

vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    getPublicQuotation: (...a: unknown[]) => api.getPublicQuotation(...a),
    downloadPublicQuotationPdf: (...a: unknown[]) => api.downloadPublicQuotationPdf(...a),
  };
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/q/tok']}>
        <Routes>
          <Route path="/q/:token" element={<PublicQuotationPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function httpError(status: number) {
  const err = new AxiosError('x');
  err.response = { status, data: {}, statusText: '', headers: {}, config: {} as never };
  return err;
}

describe('PublicQuotationPage', () => {
  beforeEach(() => {
    api.getPublicQuotation.mockReset();
  });

  it('shows the quotation without signing in', async () => {
    api.getPublicQuotation.mockResolvedValue({
      sellerName: 'Acme Traders',
      number: 'QTN-0001',
      quotationDate: '2026-10-01',
      validUntil: '2026-11-01',
      billTo: { name: 'Ravi', address: '7 Market Rd' },
      lines: [{ name: 'Widget', qty: '2', rate: '100', amount: '236' }],
      totals: { grandTotal: '236' },
      notes: 'Thanks',
      terms: 'Pay in 15 days',
    });
    mount();
    expect(await screen.findByText('Acme Traders')).toBeTruthy();
    expect(screen.getByText('QTN-0001')).toBeTruthy();
    expect(screen.getByText(t('phase1.publicQuotationValidUntil', { date: '2026-11-01' }))).toBeTruthy();
    expect(screen.getByText('Pay in 15 days')).toBeTruthy();
    expect(screen.getByRole('button', { name: t('phase1.publicQuotationDownload') })).toBeTruthy();
  });

  it('says the quotation has expired on a 410 and not-available on a 404', async () => {
    api.getPublicQuotation.mockRejectedValue(httpError(410));
    const first = mount();
    expect(await screen.findByText(t('phase1.publicQuotationExpired'))).toBeTruthy();
    first.unmount();
    api.getPublicQuotation.mockRejectedValue(httpError(404));
    mount();
    expect(await screen.findByText(t('phase1.publicQuotationUnavailable'))).toBeTruthy();
  });
});
