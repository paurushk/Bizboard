import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { ImportHistory, TallyRunsHistory } from '@/components/settings/ImportHistory';

const api = vi.hoisted(() => ({
  listImportHistory: vi.fn(),
  listTallyRuns: vi.fn(),
  voidImport: vi.fn(),
  downloadImportErrorsCsv: vi.fn(),
  downloadTallyErrorsCsv: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const JOBS = [
  { id: 1, kind: 'PRODUCTS', status: 'COMMITTED', totalRows: 100, validRows: 97, errorRows: 3, fileName: 'items.csv', createdByName: 'Asha', committedAt: '2026-10-18T10:00:00Z', canUndo: true },
  { id: 2, kind: 'CUSTOMERS', status: 'COMMITTED', totalRows: 40, validRows: 40, errorRows: 0, fileName: 'cust.csv', createdByName: 'Ravi', committedAt: '2026-10-17T10:00:00Z', canUndo: false },
  { id: 3, kind: 'OPENING_STOCK', status: 'VOIDED', totalRows: 5, validRows: 5, errorRows: 0, fileName: 'stock.csv', createdByName: 'Asha', createdAt: '2026-10-16T10:00:00Z', canUndo: false },
];

const PAGE_OF = (rows: unknown[], extra: Record<string, unknown> = {}) => ({ rows, count: rows.length, hasNext: false, hasPrevious: false, ...extra });

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
const rowOf = async (text: string) => (await screen.findByText(text)).closest('tr') as HTMLElement;

describe('ImportHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listImportHistory.mockResolvedValue(PAGE_OF(JOBS));
    api.voidImport.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('lists each import with who ran it, its file, its rows and its result', async () => {
    wrap(<ImportHistory canUndo />);
    const row = await rowOf('items.csv');
    expect(within(row).getByText('Asha')).toBeTruthy();
    expect(within(row).getByText(t('importHistory.kind.PRODUCTS'))).toBeTruthy();
    expect(within(row).getByText(t('importHistory.rows', { total: '100', valid: '97', errors: '3' }))).toBeTruthy();
    expect(within(row).getByText(t('importHistory.status.COMMITTED'))).toBeTruthy();
    expect(within(await rowOf('stock.csv')).getByText(t('importHistory.status.VOIDED'))).toBeTruthy();
  });

  it('offers the problems file only where there were problems', async () => {
    wrap(<ImportHistory canUndo />);
    await userEvent.click(within(await rowOf('items.csv')).getByRole('button', { name: t('importHistory.errors') }));
    expect(api.downloadImportErrorsCsv).toHaveBeenCalledWith(1, 'PRODUCTS');
    expect(within(await rowOf('cust.csv')).queryByRole('button', { name: t('importHistory.errors') })).toBeNull();
  });

  it('offers Undo only where the server says it can be undone, and says so where it cannot', async () => {
    wrap(<ImportHistory canUndo />);
    expect(within(await rowOf('items.csv')).getByRole('button', { name: t('importHistory.undo') })).toBeTruthy();
    const customers = await rowOf('cust.csv');
    expect(within(customers).queryByRole('button', { name: t('importHistory.undo') })).toBeNull();
    expect(within(customers).getByText(t('importHistory.cannotUndo'))).toBeTruthy();
  });

  it('offers no Undo to someone who is not the owner', async () => {
    wrap(<ImportHistory canUndo={false} />);
    expect(within(await rowOf('items.csv')).queryByRole('button', { name: t('importHistory.undo') })).toBeNull();
  });

  it('undoes only after confirmation, and shows the server reason when it is refused', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true);
    api.voidImport.mockRejectedValueOnce(new Error('Some imported stock has already been used.'));
    wrap(<ImportHistory canUndo />);
    const row = await rowOf('items.csv');
    await userEvent.click(within(row).getByRole('button', { name: t('importHistory.undo') }));
    expect(api.voidImport).not.toHaveBeenCalled();
    await userEvent.click(within(row).getByRole('button', { name: t('importHistory.undo') }));
    await waitFor(() => expect(api.voidImport).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/already been used/)).toBeTruthy();
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it('says there are none yet, and shows an error with Retry rather than an empty list when it cannot load', async () => {
    api.listImportHistory.mockResolvedValueOnce(PAGE_OF([]));
    const first = wrap(<ImportHistory canUndo />);
    expect(await screen.findByText(t('importHistory.empty'))).toBeTruthy();
    first.unmount();
    api.listImportHistory.mockRejectedValue(new Error('down'));
    wrap(<ImportHistory canUndo />);
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
  });
});

describe('ImportHistory filters and paging (SET-09)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listImportHistory.mockResolvedValue(PAGE_OF(JOBS));
  });

  it('asks the server for the chosen type, and says so when nothing matches', async () => {
    wrap(<ImportHistory canUndo />);
    await rowOf('items.csv');
    api.listImportHistory.mockResolvedValue(PAGE_OF([]));
    await userEvent.click(screen.getByLabelText(t('importHistory.filterKind')));
    await userEvent.click(await screen.findByRole('option', { name: t('importHistory.kind.SALES_BILL') }));
    await waitFor(() =>
      expect(api.listImportHistory).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'SALES_BILL', page: 1 })),
    );
    expect(await screen.findByText(t('importHistory.emptyFiltered'))).toBeTruthy();
  });

  it('can show only the signed-in person imports', async () => {
    wrap(<ImportHistory canUndo />);
    await rowOf('items.csv');
    await userEvent.click(screen.getByRole('checkbox', { name: t('importHistory.filterMine') }));
    await waitFor(() => expect(api.listImportHistory).toHaveBeenLastCalledWith(expect.objectContaining({ mine: true })));
  });

  it('pages through older imports and back, and goes back to page 1 when a filter changes', async () => {
    api.listImportHistory.mockResolvedValue(PAGE_OF(JOBS, { count: 45, hasNext: true }));
    wrap(<ImportHistory canUndo />);
    await rowOf('items.csv');
    expect(screen.getByText(t('importHistory.pageOf', { page: '1', pages: '3' }))).toBeTruthy();
    expect((screen.getByRole('button', { name: t('importHistory.newer') }) as HTMLButtonElement).disabled).toBe(true);
    api.listImportHistory.mockResolvedValue(PAGE_OF(JOBS, { count: 45, hasNext: true, hasPrevious: true }));
    await userEvent.click(screen.getByRole('button', { name: t('importHistory.older') }));
    await waitFor(() => expect(api.listImportHistory).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
    await userEvent.click(screen.getByLabelText(t('importHistory.filterStatus')));
    await userEvent.click(await screen.findByRole('option', { name: t('importHistory.status.FAILED') }));
    await waitFor(() =>
      expect(api.listImportHistory).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'FAILED', page: 1 })),
    );
  });
});

describe('TallyRunsHistory', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists recent Tally imports with counts and downloads their problems', async () => {
    api.listTallyRuns.mockResolvedValue([
      { id: 9, status: 'PREVIEWED', createdAt: '2026-10-18T10:00:00Z', by: 'Asha', fileName: 'tally.csv', customers: 3, suppliers: 1, products: 2, errorCount: 4, failureReason: '' },
    ]);
    wrap(<TallyRunsHistory />);
    const row = await rowOf('tally.csv');
    expect(within(row).getByText(t('importHistory.tallyRows', { customers: '3', suppliers: '1', products: '2' }))).toBeTruthy();
    await userEvent.click(within(row).getByRole('button', { name: t('importHistory.tallyErrors', { count: '4' }) }));
    expect(api.downloadTallyErrorsCsv).toHaveBeenCalledWith(9);
  });

  it('explains that Tally is not switched on when the server answers not found', async () => {
    api.listTallyRuns.mockRejectedValue({ response: { status: 404 } });
    wrap(<TallyRunsHistory />);
    expect(await screen.findByText(t('importHistory.tallyOff'))).toBeTruthy();
  });
});
