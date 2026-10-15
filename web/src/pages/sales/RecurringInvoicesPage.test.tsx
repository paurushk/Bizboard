import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RecurringSchedule } from '@/api/legacy/sales';
import { RecurringInvoicesPage } from '@/pages/sales/RecurringInvoicesPage';

const listCustomersPage = vi.fn();
const listRecurringSchedulesPage = vi.fn();
const listRecurringRunsPage = vi.fn();
const updateRecurringSchedule = vi.fn();
const runRecurringScheduleNow = vi.fn();
const deleteRecurringSchedule = vi.fn();
const createRecurringSchedule = vi.fn();
const previewSalesTotals = vi.fn();
let role = 'OWNER';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role, companyId: 9, canCreateSales: true } }),
}));
vi.mock('@/hooks/useProductCfFilters', () => ({
  useProductCfFilters: () => ({ cfFilters: undefined, filterBar: null, enabled: false, defs: [] }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));
vi.mock('@/api/resources', () => ({
  listRecurringSchedulesPage: (...a: unknown[]) => listRecurringSchedulesPage(...a),
  listRecurringRunsPage: (...a: unknown[]) => listRecurringRunsPage(...a),
  listCustomersPage: (...a: unknown[]) => listCustomersPage(...a),
  listProductsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  getProduct: async (id: number) => ({ id, name: 'Widget', sku: 'W-1', sellingPrice: '100' }),
  createRecurringSchedule: (...a: unknown[]) => createRecurringSchedule(...a),
  updateRecurringSchedule: (...a: unknown[]) => updateRecurringSchedule(...a),
  runRecurringScheduleNow: (...a: unknown[]) => runRecurringScheduleNow(...a),
  deleteRecurringSchedule: (...a: unknown[]) => deleteRecurringSchedule(...a),
  previewSalesTotals: (...a: unknown[]) => previewSalesTotals(...a),
}));

function row(over: Partial<RecurringSchedule> = {}): RecurringSchedule {
  return {
    id: 1,
    customer: 7,
    customerName: 'Ravi Kumar',
    customerStatus: 'ACTIVE',
    companyGstin: null,
    cadence: 'QUARTERLY',
    nextRunAt: '2099-01-01T04:30:00Z',
    isActive: true,
    lineTemplate: { items: [{ product: 3, quantity: 2, unitPrice: 100 }] },
    notes: '',
    stopStage: 'INVOICE',
    autoComplete: false,
    additionalCharges: '0.00',
    invoiceDiscount: '0.00',
    invoiceDiscountMode: 'AFTER_TAX',
    priceMode: 'EXCLUSIVE',
    endDate: null,
    maxOccurrences: null,
    totalRunsCount: 0,
    lastError: '',
    anchorDay: 1,
    pausedReason: '',
    managedByContract: null,
    hasRuns: false,
    nextFutureRunAt: '2099-01-01T04:30:00Z',
    ...over,
  };
}

function setRows(rows: RecurringSchedule[]) {
  listRecurringSchedulesPage.mockResolvedValue({ results: rows, count: rows.length, next: null, previous: null });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <RecurringInvoicesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RecurringInvoicesPage', () => {
  beforeEach(() => {
    role = 'OWNER';
    for (const fn of [
      listCustomersPage, listRecurringSchedulesPage, listRecurringRunsPage, updateRecurringSchedule,
      runRecurringScheduleNow, deleteRecurringSchedule, createRecurringSchedule, previewSalesTotals,
    ]) fn.mockReset();
    listCustomersPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    listRecurringRunsPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    previewSalesTotals.mockResolvedValue({ taxableTotal: 200, taxTotal: 36, grandTotal: 236 });
    updateRecurringSchedule.mockResolvedValue({});
    setRows([]);
  });

  it('offers active customers only, searched on the server, so a schedule is never set up for a blocked or archived one', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'New recurring schedule' }));
    await waitFor(() =>
      expect(listCustomersPage).toHaveBeenCalledWith(expect.objectContaining({ status: 'ACTIVE' })),
    );
  });

  it('shows cadence, run count, status and the last problem for each schedule', async () => {
    setRows([
      row({ id: 1, totalRunsCount: 2, maxOccurrences: 4, lastError: 'period closed' }),
      row({ id: 2, customerName: 'Paused Co', isActive: false, cadence: 'ANNUALLY' }),
    ]);
    renderPage();
    expect(await screen.findByText('Ravi Kumar')).toBeInTheDocument();
    expect(screen.getByText('Quarterly')).toBeInTheDocument();
    expect(screen.getByText('Annually')).toBeInTheDocument();
    expect(screen.getByText('2 of 4 runs')).toBeInTheDocument();
    expect(screen.getByLabelText('Last problem: period closed')).toBeInTheDocument();
    expect(screen.getAllByText('Paused').length).toBeGreaterThan(0);
  });

  it('filters by status on the server and starts again from the first page', async () => {
    setRows([row({ id: 1 })]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    expect(listRecurringSchedulesPage).toHaveBeenLastCalledWith({ page: 1, pageSize: 50 });
    setRows([row({ id: 2, customerName: 'Paused Co', isActive: false })]);
    fireEvent.click(screen.getByRole('button', { name: 'Paused' }));
    expect(await screen.findByText('Paused Co')).toBeInTheDocument();
    expect(listRecurringSchedulesPage).toHaveBeenLastCalledWith({ page: 1, pageSize: 50, is_active: 'false' });
    expect(screen.queryByText('Ravi Kumar')).not.toBeInTheDocument();
  });

  it('pages through a long list', async () => {
    listRecurringSchedulesPage.mockResolvedValue({ results: [row({ id: 1 })], count: 120, next: 'x', previous: null });
    renderPage();
    await screen.findByText('Ravi Kumar');
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    listRecurringSchedulesPage.mockResolvedValue({
      results: [row({ id: 2, customerName: 'Second Page Co' })], count: 120, next: 'x', previous: 'y',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('Second Page Co')).toBeInTheDocument();
    expect(listRecurringSchedulesPage).toHaveBeenLastCalledWith({ page: 2, pageSize: 50 });
  });

  it('says when a contract ending paused the schedule', async () => {
    setRows([row({ isActive: false, pausedReason: 'CONTRACT_ENDED' })]);
    renderPage();
    expect(await screen.findByText('Paused: contract ended')).toBeInTheDocument();
  });

  it('pauses a schedule', async () => {
    setRows([row()]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(updateRecurringSchedule).toHaveBeenCalledWith(1, { isActive: false }));
  });

  it('resumes a schedule whose saved date has passed only after a new date is chosen', async () => {
    setRows([row({ isActive: false, nextRunAt: '2020-01-01T04:30:00Z', nextFutureRunAt: '2099-02-02T04:30:00Z' })]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/not created back-dated/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(updateRecurringSchedule).toHaveBeenCalled());
    const [id, body] = updateRecurringSchedule.mock.calls[0] as [number, Record<string, unknown>];
    expect(id).toBe(1);
    expect(body.isActive).toBe(true);
    expect(typeof body.nextRunAt).toBe('string');
  });

  it('resumes straight away when the saved date is still ahead', async () => {
    setRows([row({ isActive: false })]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(updateRecurringSchedule).toHaveBeenCalledWith(1, { isActive: true }));
  });

  it('runs now after confirming, and links the generated invoice', async () => {
    setRows([row()]);
    runRecurringScheduleNow.mockResolvedValue({
      ok: true, runId: 1, invoiceId: 42, salesOrderId: null, deliveryChallanId: null, stopStage: 'INVOICE',
      periodKey: '2026-10', status: 'DRAFT', documentNumber: null, alreadyExisted: false, completionError: '',
    });
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/left as a draft/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Run now' }));
    await waitFor(() => expect(runRecurringScheduleNow).toHaveBeenCalledWith(1));
    const link = await screen.findByRole('link', { name: 'View' });
    expect(link).toHaveAttribute('href', '/sales/history/42');
  });

  it('links a sales order run to the order itself', async () => {
    setRows([row({ stopStage: 'SALES_ORDER' })]);
    runRecurringScheduleNow.mockResolvedValue({
      ok: true, runId: 1, invoiceId: null, salesOrderId: 9, deliveryChallanId: null, stopStage: 'SALES_ORDER',
      periodKey: '2026-10', status: 'DRAFT', documentNumber: null, alreadyExisted: false, completionError: '',
    });
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Run now' }));
    expect(await screen.findByRole('link', { name: 'View' })).toHaveAttribute('href', '/sales/orders/9');
  });

  it('tells the owner when auto-complete will finalize the invoice', async () => {
    setRows([row({ autoComplete: true })]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/completes it/)).toBeInTheDocument();
  });

  it('only offers delete for a schedule with no runs that no contract owns', async () => {
    setRows([
      row({ id: 1 }),
      row({ id: 2, customerName: 'Has Runs', hasRuns: true }),
      row({ id: 3, customerName: 'Contract Co', managedByContract: { id: 9, number: 'CON-9' } }),
    ]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(1);
    expect(screen.getByText('Contract CON-9')).toBeInTheDocument();
  });

  it('deletes after confirming', async () => {
    setRows([row()]);
    deleteRecurringSchedule.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteRecurringSchedule).toHaveBeenCalledWith(1));
  });

  it('shows run history with the reason a run was not completed', async () => {
    setRows([row({ hasRuns: true })]);
    listRecurringRunsPage.mockResolvedValue({
      count: 1, next: null, previous: null,
      results: [{
        id: 1, periodKey: '2026-Q4', createdAt: '2026-10-01T04:00:00Z', isManual: false,
        completionError: 'credit limit', documentType: 'invoice', documentId: 8, documentNumber: 'INV-8', status: 'COMPLETED',
        einvoiceStatus: 'FAILED',
      }],
    });
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'History' }));
    expect(await screen.findByText('2026-Q4')).toBeInTheDocument();
    expect(screen.getByText('Not completed: credit limit')).toBeInTheDocument();
    expect(screen.getByText('e-invoice: Failed')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'INV-8' })).toHaveAttribute('href', '/sales/history/8');
  });

  it('edits a schedule: shows the estimated amount from the server and saves a PATCH without the unchanged date', async () => {
    setRows([row()]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(await screen.findByText('Edit recurring schedule')).toBeInTheDocument();
    expect(await screen.findByText('236.00', {}, { timeout: 8000 })).toBeInTheDocument();
    expect(previewSalesTotals).toHaveBeenCalledWith(
      expect.objectContaining({ customer: 7, items: [{ product: 3, quantity: 2, unitPrice: 100 }] }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save template' }));
    await waitFor(() => expect(updateRecurringSchedule).toHaveBeenCalled(), { timeout: 8000 });
    const [id, body] = updateRecurringSchedule.mock.calls[0] as [number, Record<string, unknown>];
    expect(id).toBe(1);
    expect('nextRunAt' in body).toBe(false);
    expect(body.cadence).toBe('QUARTERLY');
  }, 20_000);

  it('on a phone keeps customer and status in the table and moves the actions into a menu', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes('max-width'),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      onchange: null,
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    try {
      setRows([row()]);
      renderPage();
      await screen.findByText('Ravi Kumar');
      expect(screen.queryByRole('columnheader', { name: 'Cadence' })).not.toBeInTheDocument();
      expect(screen.getByText(/Quarterly ·/)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Run now' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: /Actions: Ravi Kumar/ }));
      fireEvent.click(await screen.findByRole('menuitem', { name: 'Pause' }));
      await waitFor(() => expect(updateRecurringSchedule).toHaveBeenCalledWith(1, { isActive: false }));
    } finally {
      window.matchMedia = original;
    }
  });

  it('hides write actions from a user who cannot create sales', async () => {
    role = 'VIEWER';
    setRows([row()]);
    renderPage();
    await screen.findByText('Ravi Kumar');
    expect(screen.queryByRole('button', { name: 'New recurring schedule' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  });
});
