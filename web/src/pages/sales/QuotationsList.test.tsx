import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QuotationsPage } from '@/pages/sales/QuotationsPage';
import { t } from '@/i18n';

const auth = vi.hoisted(() => ({
  user: { role: 'OWNER' } as { role: string; canCreateSales?: boolean; canCancelDocuments?: boolean },
}));
const api = vi.hoisted(() => ({
  rows: [] as unknown[],
  lifecycleOn: false,
  listQuotationsPage: vi.fn(),
  cancelQuotation: vi.fn(),
  quotationLifecycle: vi.fn(),
  closeQuotationRemaining: vi.fn(),
  reopenClosedQuotation: vi.fn(),
  duplicateQuotation: vi.fn(),
  cancelExpiredQuotations: vi.fn(),
  shareQuotation: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', companyId: 9, ...auth.user },
  }),
}));

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) =>
      key === 'QUOTE_LIFECYCLE' ? api.lifecycleOn : actual.isRuntimeFlagEnabled(key),
  };
});

vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    listQuotationsPage: (...args: unknown[]) => api.listQuotationsPage(...args),
    listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    listCustomersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    getCompany: async () => ({ id: 9, name: 'Acme', registrationType: 'REGULAR', state: 'Delhi' }),
    cancelQuotation: (...args: unknown[]) => api.cancelQuotation(...args),
    quotationLifecycle: (...args: unknown[]) => api.quotationLifecycle(...args),
    closeQuotationRemaining: (...args: unknown[]) => api.closeQuotationRemaining(...args),
    reopenClosedQuotation: (...args: unknown[]) => api.reopenClosedQuotation(...args),
    duplicateQuotation: (...args: unknown[]) => api.duplicateQuotation(...args),
    cancelExpiredQuotations: (...args: unknown[]) => api.cancelExpiredQuotations(...args),
    shareQuotation: (...args: unknown[]) => api.shareQuotation(...args),
  };
});

function Where() {
  const location = useLocation();
  return <div data-testid="where">{location.pathname + location.search}</div>;
}

function mount(path = '/sales/quotations') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Where />
        <Routes>
          <Route path="/sales/quotations" element={<QuotationsPage />} />
          <Route path="/sales/quotations/new" element={<div>new editor</div>} />
          <Route path="/sales/quotations/:id" element={<div>view editor</div>} />
          <Route path="/sales/quotations/:id/edit" element={<div>edit editor</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const quote = (over: Record<string, unknown> = {}) => ({
  id: 5,
  number: 'QTN-0005',
  status: 'DRAFT',
  invoiceType: 'GST',
  customer: 3,
  customerName: 'Ravi',
  quotationDate: '2026-10-01',
  validUntil: '2099-01-01',
  grandTotal: '1180',
  items: [{ id: 11, product: 2, quantity: '10', convertedQuantity: '0' }],
  ...over,
});

const openMenu = async () => fireEvent.click(await screen.findByRole('button', { name: t('common.moreActions') }));
const menuItem = (name: string) => screen.findByRole('menuitem', { name });

beforeEach(() => {
  auth.user = { role: 'OWNER' };
  api.rows = [];
  api.lifecycleOn = false;
  api.listQuotationsPage.mockReset();
  api.listQuotationsPage.mockImplementation(async () => ({
    results: api.rows,
    count: api.rows.length,
    next: null,
    previous: null,
  }));
  for (const fn of [
    api.cancelQuotation, api.quotationLifecycle, api.closeQuotationRemaining, api.reopenClosedQuotation,
    api.duplicateQuotation, api.cancelExpiredQuotations, api.shareQuotation,
  ]) {
    fn.mockReset();
    fn.mockResolvedValue(quote());
  }
  api.duplicateQuotation.mockResolvedValue(quote({ id: 9 }));
  api.cancelExpiredQuotations.mockResolvedValue({ cancelled: 2, needsCloseRemaining: [{ id: 4, number: 'QTN-0004' }] });
});

describe('QuotationsPage', () => {
  it('shows an empty state with no rows', async () => {
    mount();
    expect(await screen.findByText(t('empty.quotations'))).toBeTruthy();
  });

  it('New quotation opens the editor page', async () => {
    mount();
    fireEvent.click(await screen.findByRole('button', { name: t('phase1.newQuotation') }));
    await screen.findByText('new editor');
    expect(screen.getByTestId('where').textContent).toBe('/sales/quotations/new');
  });

  it('redirects the old create link to the editor page', async () => {
    mount('/sales/quotations?create=1');
    await screen.findByText('new editor');
  });

  it('a viewer sees the list but no New button and is not redirected', async () => {
    auth.user = { role: 'VIEWER' };
    mount('/sales/quotations?create=1');
    await screen.findByText(t('nav.quotations'));
    expect(screen.queryByRole('button', { name: t('phase1.newQuotation') })).toBeNull();
  });

  it('renders the columns, the row and an Edit button that opens the edit page', async () => {
    api.rows = [quote()];
    mount();
    expect(await screen.findByText('QTN-0005')).toBeTruthy();
    for (const key of ['common.number', 'common.date', 'billing.validUntil', 'billing.customer', 'common.status', 'common.total']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(t(key)) })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole('button', { name: t('common.edit') }));
    await screen.findByText('edit editor');
  });

  it('asks the server for sorted, filtered pages', async () => {
    api.rows = [quote()];
    mount();
    await screen.findByText('QTN-0005');
    expect(api.listQuotationsPage.mock.calls[0][0]).toMatchObject({ ordering: '-quotation_date', page: 1 });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(t('common.total')) }));
    await waitFor(() =>
      expect(api.listQuotationsPage.mock.calls.some(([p]) => (p as { ordering: string }).ordering === '-grand_total')).toBe(true),
    );
    fireEvent.click(screen.getByRole('button', { name: t('status.cancelled') }));
    await waitFor(() =>
      expect(api.listQuotationsPage.mock.calls.some(([p]) => (p as { status?: string }).status === 'CANCELLED')).toBe(true),
    );
  });

  it('the Expired filter asks for expired quotes only, never a status', async () => {
    mount();
    await screen.findByText(t('empty.quotations'));
    fireEvent.click(screen.getByRole('button', { name: t('status.EXPIRED') }));
    await waitFor(() => {
      const last = api.listQuotationsPage.mock.calls.at(-1)?.[0] as { expired?: boolean; status?: string };
      expect(last.expired).toBe(true);
      expect(last.status).toBeUndefined();
    });
  });

  it('shows the Expired badge from the server flag, not the browser date', async () => {
    api.rows = [quote({ validUntil: '2099-01-01', isExpired: true })];
    mount();
    expect(await screen.findByText(`(${t('status.EXPIRED')})`)).toBeTruthy();
  });

  it('shows a clear-filters empty state when filters match nothing', async () => {
    mount();
    await screen.findByText(t('empty.quotations'));
    fireEvent.click(screen.getByRole('button', { name: t('status.cancelled') }));
    expect(await screen.findByText(t('phase1.quotationNoMatch'))).toBeTruthy();
    expect(screen.getByRole('button', { name: t('common.clearFilters') })).toBeTruthy();
  });

  it('shows what was passed from the editor once, and it can be dismissed', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[{ pathname: '/sales/quotations', state: { message: 'Saved. Total ₹1,180.00' } }]}>
          <Routes>
            <Route path="/sales/quotations" element={<QuotationsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Saved. Total ₹1,180.00')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    await waitFor(() => expect(screen.queryByText('Saved. Total ₹1,180.00')).toBeNull());
  });
});

describe('QuotationsPage actions', () => {
  it('cancels through a dialog and sends the reason; then the message shows', async () => {
    api.rows = [quote()];
    mount();
    await openMenu();
    fireEvent.click(await menuItem(t('common.cancel')));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(t('phase1.quotationCancelReason')), { target: { value: 'Customer left' } });
    fireEvent.click(within(dialog).getByRole('button', { name: t('common.cancel') }));
    await waitFor(() => expect(api.cancelQuotation).toHaveBeenCalledWith(5, 'Customer left'));
    expect(await screen.findByText(t('phase1.quotationCancelled'))).toBeTruthy();
  });

  it('hides Cancel from a user who can create sales but not cancel documents', async () => {
    auth.user = { role: 'SALES_STAFF', canCreateSales: true, canCancelDocuments: false };
    api.rows = [quote()];
    mount();
    await openMenu();
    await menuItem(t('phase1.quotationDuplicate'));
    expect(screen.queryByRole('menuitem', { name: t('common.cancel') })).toBeNull();
  });

  it('lets a user who can cancel but not create still download, view and cancel', async () => {
    auth.user = { role: 'ACCOUNTANT', canCreateSales: false, canCancelDocuments: true };
    api.rows = [quote()];
    mount();
    await screen.findByText('QTN-0005');
    expect(screen.getByRole('button', { name: t('common.download') })).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('common.edit') })).toBeNull();
    await openMenu();
    expect(await menuItem(t('common.cancel'))).toBeTruthy();
    expect(screen.queryByRole('menuitem', { name: t('phase1.quotationDuplicate') })).toBeNull();
  });

  it('duplicates a quote and opens the copy', async () => {
    api.rows = [quote()];
    mount();
    await openMenu();
    fireEvent.click(await menuItem(t('phase1.quotationDuplicate')));
    await waitFor(() => expect(api.duplicateQuotation).toHaveBeenCalledWith(5));
    await screen.findByText('view editor');
  });

  it('closing the remaining quantity needs a reason and calls the close endpoint', async () => {
    api.rows = [quote({ conversionState: 'PARTIAL', items: [{ id: 11, product: 2, quantity: '10', convertedQuantity: '4' }] })];
    mount();
    await openMenu();
    expect(screen.queryByRole('menuitem', { name: t('common.cancel') })).toBeNull();
    fireEvent.click(await menuItem(t('phase1.quotationCloseRemaining')));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: t('common.confirm') }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(new RegExp(t('phase1.quotationReasonLabel'))), { target: { value: 'Went elsewhere' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(api.closeQuotationRemaining).toHaveBeenCalledWith(5, 'Went elsewhere'));
  });

  it('a closed quote shows its chip and the owner can reopen it', async () => {
    api.rows = [quote({ shortClosedAt: '2026-10-02T00:00:00Z', shortCloseReason: 'Went elsewhere', status: 'CONVERTED' })];
    mount();
    expect(await screen.findByText(t('phase1.quotationClosedChip'))).toBeTruthy();
    await openMenu();
    fireEvent.click(await menuItem(t('phase1.quotationReopenClosed')));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(new RegExp(t('phase1.quotationReasonLabel'))), { target: { value: 'Back' } });
    fireEvent.click(within(dialog).getByRole('button', { name: t('common.confirm') }));
    await waitFor(() => expect(api.reopenClosedQuotation).toHaveBeenCalledWith(5, 'Back'));
  });

  it('cancels expired quotes after a confirmation and reports the ones that need Close remaining', async () => {
    api.rows = [quote({ isExpired: true })];
    mount();
    await screen.findByText('QTN-0005');
    fireEvent.click(screen.getByRole('button', { name: t('status.EXPIRED') }));
    fireEvent.click(await screen.findByRole('button', { name: t('phase1.quotationCancelExpired') }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: t('common.confirm') }));
    await waitFor(() => expect(api.cancelExpiredQuotations).toHaveBeenCalled());
    expect(await screen.findByText(/QTN-0004/)).toBeTruthy();
  });

  it('a failed action shows its error and the next action clears it', async () => {
    api.rows = [quote()];
    api.cancelQuotation.mockRejectedValueOnce(new Error('Boom'));
    mount();
    await openMenu();
    fireEvent.click(await menuItem(t('common.cancel')));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: t('common.cancel') }));
    expect(await screen.findByText(/Boom/)).toBeTruthy();
    await openMenu();
    fireEvent.click(await menuItem(t('phase1.quotationDuplicate')));
    await waitFor(() => expect(api.duplicateQuotation).toHaveBeenCalled());
  });
});

describe('QuotationsPage lifecycle (QUOTE_LIFECYCLE on)', () => {
  it('shows no lifecycle actions while the company flag is off', async () => {
    api.rows = [quote()];
    mount();
    await openMenu();
    await menuItem(t('phase1.quotationDuplicate'));
    expect(screen.queryByRole('menuitem', { name: t('phase1.quotationMarkSent') })).toBeNull();
  });

  it('marks a draft as sent', async () => {
    api.lifecycleOn = true;
    api.rows = [quote()];
    mount();
    await openMenu();
    fireEvent.click(await menuItem(t('phase1.quotationMarkSent')));
    await waitFor(() => expect(api.quotationLifecycle).toHaveBeenCalledWith(5, 'mark-sent', undefined));
  });

  it('offers accept, reject and reopen on a sent quote, and requires a reason to reopen', async () => {
    api.lifecycleOn = true;
    api.rows = [quote({ status: 'SENT' })];
    mount();
    await openMenu();
    await menuItem(t('phase1.quotationMarkAccepted'));
    fireEvent.click(await menuItem(t('phase1.quotationReopen')));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: t('common.confirm') }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(new RegExp(t('phase1.quotationReasonLabel'))), { target: { value: 'Price changed' } });
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);
    await waitFor(() => expect(api.quotationLifecycle).toHaveBeenCalledWith(5, 'reopen-for-changes', 'Price changed'));
  });

  it('a sent-quote filter appears only with the flag', async () => {
    api.lifecycleOn = true;
    mount();
    expect(await screen.findByRole('button', { name: t('status.SENT') })).toBeTruthy();
  });
});
