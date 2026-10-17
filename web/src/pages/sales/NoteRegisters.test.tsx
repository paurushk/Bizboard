import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CreditNotesPage } from '@/pages/sales/CreditNotesPage';
import { DebitNotesPage } from '@/pages/sales/DebitNotesPage';

// CN-02 / DN-02 (search, filters, source invoice), CN-06 (auto return note), CN-11 / DN-10 (export),
// CN-03 / DN-03 (who can complete).
const OWNER = { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 1 };
const ACCOUNTANT = { id: 2, email: 'a@x.test', fullName: 'Acct', role: 'ACCOUNTANT', companyId: 1, canExport: true };
const VIEWER = { id: 3, email: 'v@x.test', fullName: 'View', role: 'VIEWER', companyId: 1 };
let currentUser: Record<string, unknown> = OWNER;
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: currentUser }) }));

const rows = {
  credit: [
    {
      id: 1, number: 'SCN-1', status: 'DRAFT', customerName: 'Asha', salesInvoice: 7, invoiceNumber: 'INV-7',
      noteDate: '2026-09-01', grandTotal: '100.00', salesReturn: null,
    },
    {
      id: 2, number: 'SCN-2', status: 'COMPLETED', customerName: 'Bala', salesInvoice: 8, invoiceNumber: 'INV-8',
      noteDate: '2026-09-02', grandTotal: '50.00', salesReturn: 33,
    },
  ] as Array<Record<string, unknown>>,
  debit: [
    {
      id: 5, number: 'SDN-1', status: 'DRAFT', customerName: 'Asha', salesInvoice: 7, invoiceNumber: 'INV-7',
      noteDate: '2026-09-03', grandTotal: '20.00',
    },
  ] as Array<Record<string, unknown>>,
};

const listCredit = vi.fn(async (_params?: Record<string, unknown>) => ({
  results: rows.credit, count: rows.credit.length, next: null, previous: null,
}));
const listDebit = vi.fn(async (_params?: Record<string, unknown>) => ({
  results: rows.debit, count: rows.debit.length, next: null, previous: null,
}));
const exportCredit = vi.fn(async (_params?: Record<string, unknown>) => new Blob(['x']));
const exportDebit = vi.fn(async (_params?: Record<string, unknown>) => new Blob(['x']));
const triggerDownload = vi.fn();

vi.mock('@/api/resources', () => ({
  listSalesCreditNotesPage: (p?: Record<string, unknown>) => listCredit(p),
  listSalesDebitNotesPage: (p?: Record<string, unknown>) => listDebit(p),
  exportSalesCreditNotesCsv: (p?: Record<string, unknown>) => exportCredit(p),
  exportSalesDebitNotesCsv: (p?: Record<string, unknown>) => exportDebit(p),
  completeSalesCreditNote: vi.fn(),
  completeSalesDebitNote: vi.fn(),
  cancelSalesCreditNote: vi.fn(),
  cancelSalesDebitNote: vi.fn(),
  downloadSalesDocumentPdf: vi.fn(),
}));
vi.mock('@/utils/blob', () => ({
  printBlob: vi.fn(),
  triggerBlobDownload: (...args: unknown[]) => triggerDownload(...args),
}));

function wrap(ui: ReactElement, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  currentUser = OWNER;
});
afterEach(() => {
  vi.clearAllMocks();
});

describe.each([
  ['credit', CreditNotesPage, listCredit, exportCredit, 'SCN-1'],
  ['debit', DebitNotesPage, listDebit, exportDebit, 'SDN-1'],
] as const)('%s notes register', (_kind, Page, list, exporter, firstNumber) => {
  it('shows the source invoice as a link to the invoice (CN-02 / DN-02)', async () => {
    wrap(<Page />);
    await screen.findByText(firstNumber);
    const link = screen.getByRole('link', { name: 'INV-7' });
    expect(link.getAttribute('href')).toBe('/sales/history/7');
    expect(screen.getByRole('columnheader', { name: /source invoice/i })).toBeTruthy();
  });

  it('sends the search text to the API after the debounce and resets paging', async () => {
    wrap(<Page />);
    await screen.findByText(firstNumber);
    await userEvent.type(screen.getByLabelText(/^search$/i), 'Asha');
    await waitFor(() => {
      const last = list.mock.calls.at(-1)?.[0];
      expect(last).toMatchObject({ search: 'Asha', page: 1 });
    });
  });

  it('sends status and date filters, and does not send an inverted date range', async () => {
    wrap(<Page />);
    await screen.findByText(firstNumber);
    fireEvent.change(screen.getByLabelText(/^from$/i), { target: { value: '2026-09-10' } });
    fireEvent.change(screen.getByLabelText(/^to$/i), { target: { value: '2026-09-01' } });
    expect(await screen.findByText(/cannot be after/i)).toBeTruthy();
    await waitFor(() => {
      const last = list.mock.calls.at(-1)?.[0] as Record<string, unknown>;
      expect(last.date_from).toBeUndefined();
      expect(last.date_to).toBeUndefined();
    });
    expect(screen.getByRole('button', { name: /export csv/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/^to$/i), { target: { value: '2026-09-30' } });
    await waitFor(() => {
      const last = list.mock.calls.at(-1)?.[0] as Record<string, unknown>;
      expect(last).toMatchObject({ date_from: '2026-09-10', date_to: '2026-09-30' });
    });
  });

  it('exports with the current filters and downloads the file (CN-11 / DN-10)', async () => {
    wrap(<Page />, '/?q=Asha&status=DRAFT');
    await screen.findByText(firstNumber);
    await userEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(exporter).toHaveBeenCalled());
    expect(exporter.mock.calls[0][0]).toMatchObject({ search: 'Asha', status: 'DRAFT' });
    await waitFor(() => expect(triggerDownload).toHaveBeenCalled());
  });

  it('hides Export from a user without export permission', async () => {
    currentUser = { ...ACCOUNTANT, canExport: false };
    wrap(<Page />);
    await screen.findByText(firstNumber);
    expect(screen.queryByRole('button', { name: /export csv/i })).toBeNull();
  });

  it('lets an Accountant complete a draft note (CN-03 / DN-03)', async () => {
    currentUser = ACCOUNTANT;
    wrap(<Page />);
    const row = (await screen.findByText(firstNumber)).closest('tr') as HTMLElement;
    expect(within(row).getByRole('button', { name: /^complete$/i })).toBeTruthy();
  });

  it('gives a Viewer neither Complete nor Create', async () => {
    currentUser = VIEWER;
    wrap(<Page />);
    const row = (await screen.findByText(firstNumber)).closest('tr') as HTMLElement;
    expect(within(row).queryByRole('button', { name: /^complete$/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /new (credit|debit) note/i })).toBeNull();
  });
});

describe('credit notes register — notes a sales return issued (CN-06)', () => {
  it('replaces Cancel with a link to Sales Returns', async () => {
    wrap(<CreditNotesPage />);
    const auto = (await screen.findByText('SCN-2')).closest('tr') as HTMLElement;
    expect(within(auto).queryByRole('button', { name: /^cancel$/i })).toBeNull();
    expect(within(auto).getByRole('link', { name: /cancel via sales return/i }).getAttribute('href')).toBe(
      '/sales/returns',
    );
  });
});
