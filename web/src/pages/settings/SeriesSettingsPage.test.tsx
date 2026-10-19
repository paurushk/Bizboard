import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { SeriesSettingsPage } from '@/pages/settings/SeriesSettingsPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));

const api = vi.hoisted(() => ({ getNumberSeries: vi.fn(), saveNumberSeries: vi.fn(), previewSettingsChange: vi.fn() }));
vi.mock('@/api/resources', () => api);

const TYPES = [
  'SALES_INVOICE', 'QUOTATION', 'SALES_ORDER', 'DELIVERY_CHALLAN', 'SALES_CREDIT_NOTE', 'SALES_DEBIT_NOTE',
  'PURCHASE_INVOICE', 'PURCHASE_ORDER', 'GOODS_RECEIPT', 'PURCHASE_CREDIT_NOTE', 'PURCHASE_DEBIT_NOTE',
];
const LIST = {
  gstin: '',
  fyLabel: '2026-27',
  gstins: [],
  fyOptions: ['2026-27', '2025-26'],
  hasSeries: true,
  items: TYPES.map((docType, i) => ({
    docType,
    prefix: docType === 'SALES_INVOICE' ? 'INV' : `P${i}`,
    nextNumber: 12,
    padding: 4,
    preview: 'x',
    length: 5,
    lengthWarning: null,
    updatedAt: `2026-10-19T10:00:0${i % 10}Z`,
  })),
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SeriesSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const invoicePrefix = () => screen.getByLabelText(`${t('cog.seriesSales')} ${t('sweep.prefix')}`) as HTMLInputElement;

describe('SeriesSettingsPage (SET-02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getNumberSeries.mockResolvedValue(LIST);
    api.saveNumberSeries.mockResolvedValue(LIST);
    api.previewSettingsChange.mockResolvedValue([{ key: 'series_next', params: { doc_type: 'SALES_INVOICE', numbers: 'TAX-0012, TAX-0013' } }]);
    window.confirm = vi.fn(() => true);
  });
  afterEach(() => setLocale('en'));

  it('shows every series in one table, in Hindi when the language is Hindi', async () => {
    setLocale('hi');
    renderPage();
    expect(await screen.findByText(t('cog.seriesSales'))).toBeTruthy();
    expect(screen.getByText(t('cog.seriesGrn'))).toBeTruthy();
    expect(screen.queryByText('Sales Invoices')).toBeNull();
    expect(api.getNumberSeries).toHaveBeenCalledTimes(1);
  });

  it('sends only the changed rows, each with the time it was loaded', async () => {
    renderPage();
    const field = await waitFor(() => invoicePrefix());
    await userEvent.clear(field);
    await userEvent.type(field, 'TAX');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(api.saveNumberSeries).toHaveBeenCalledTimes(1));
    const [body] = api.saveNumberSeries.mock.calls[0];
    expect(body.items).toHaveLength(1);
    expect(body.items[0]).toMatchObject({ doc_type: 'SALES_INVOICE', prefix: 'TAX', expected_updated_at: LIST.items[0].updatedAt });
  });

  it('shows the next numbers in a dry run first, and saves nothing when declined', async () => {
    window.confirm = vi.fn(() => false);
    renderPage();
    const field = await waitFor(() => invoicePrefix());
    await userEvent.clear(field);
    await userEvent.type(field, 'TAX');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    expect(String((window.confirm as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain('TAX-0012, TAX-0013');
    expect(api.previewSettingsChange).toHaveBeenCalledWith(
      'series',
      expect.objectContaining({ items: [expect.objectContaining({ doc_type: 'SALES_INVOICE', prefix: 'TAX' })] }),
    );
    expect(api.saveNumberSeries).not.toHaveBeenCalled();
  });

  it('still asks, and says the preview was not available, when it cannot be fetched', async () => {
    api.previewSettingsChange.mockRejectedValue(new Error('down'));
    renderPage();
    const field = await waitFor(() => invoicePrefix());
    await userEvent.type(field, 'X');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    expect(String((window.confirm as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain(t('settingsPreview.unavailable'));
    await waitFor(() => expect(api.saveNumberSeries).toHaveBeenCalled());
  });

  it('warns, without blocking, when an invoice number is longer than 16 characters', async () => {
    renderPage();
    const field = await waitFor(() => invoicePrefix());
    await userEvent.clear(field);
    await userEvent.type(field, 'ABCDEFGHIJKLMNOP');
    expect(await screen.findByText(t('seriesPage.tooLong', { count: 'ABCDEFGHIJKLMNOP-0012'.length }))).toBeTruthy();
    expect((screen.getByRole('button', { name: t('common.save') }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows the server reason and keeps the edits when a save is refused', async () => {
    api.saveNumberSeries.mockRejectedValueOnce(new Error('Nothing was saved. QUOTATION: bad prefix'));
    renderPage();
    const field = await waitFor(() => invoicePrefix());
    await userEvent.clear(field);
    await userEvent.type(field, 'TAX');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    expect(await screen.findByText(/Nothing was saved/)).toBeTruthy();
    expect(invoicePrefix().value).toBe('TAX');
  });

  it('offers a GSTIN choice only when the company has more than one', async () => {
    renderPage();
    await waitFor(() => invoicePrefix());
    expect(screen.queryByLabelText(t('seriesPage.gstin'))).toBeNull();
    expect(screen.getByLabelText(t('seriesPage.financialYear'))).toBeTruthy();
  });

  it('loads another financial year after asking when there are unsaved changes', async () => {
    window.confirm = vi.fn(() => true);
    renderPage();
    const field = await waitFor(() => invoicePrefix());
    await userEvent.type(field, 'X');
    await userEvent.click(screen.getByLabelText(t('seriesPage.financialYear')));
    await userEvent.click(await screen.findByRole('option', { name: '2025-26' }));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(api.getNumberSeries).toHaveBeenLastCalledWith('', '2025-26'));
  });

  it('shows an error with Retry, and no editable rows, when the series cannot be loaded', async () => {
    api.getNumberSeries.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.queryByLabelText(`${t('cog.seriesSales')} ${t('sweep.prefix')}`)).toBeNull();
  });
});
