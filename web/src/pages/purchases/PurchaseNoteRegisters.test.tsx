import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PurchaseCreditNotesPage } from '@/pages/purchases/PurchaseCreditNotesPage';
import { PurchaseDebitNotesPage } from '@/pages/purchases/PurchaseDebitNotesPage';

// DEP-12: the purchase-side registers get the same filters, source-invoice link and export.
const OWNER = { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 1 };
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: OWNER }) }));

const row = (id: number, number: string) => ({
  id, number, status: 'DRAFT', supplierName: 'Mega Suppliers', purchaseInvoice: 14, invoiceNumber: 'PB-14',
  noteDate: '2026-09-01', grandTotal: '100.00',
});
const page = (rows: unknown[]) => ({ results: rows, count: rows.length, next: null, previous: null });

const listCredit = vi.fn(async (_p?: Record<string, unknown>) => page([row(1, 'PCN-1')]));
const listDebit = vi.fn(async (_p?: Record<string, unknown>) => page([row(2, 'PDN-1')]));
const exportCredit = vi.fn(async (_p?: Record<string, unknown>) => new Blob(['x']));
const exportDebit = vi.fn(async (_p?: Record<string, unknown>) => new Blob(['x']));
const download = vi.fn();

vi.mock('@/api/resources', () => ({
  listPurchaseCreditNotesPage: (p?: Record<string, unknown>) => listCredit(p),
  listPurchaseDebitNotesPage: (p?: Record<string, unknown>) => listDebit(p),
  exportPurchaseCreditNotesCsv: (p?: Record<string, unknown>) => exportCredit(p),
  exportPurchaseDebitNotesCsv: (p?: Record<string, unknown>) => exportDebit(p),
  completePurchaseCreditNote: vi.fn(),
  completePurchaseDebitNote: vi.fn(),
  cancelPurchaseCreditNote: vi.fn(),
  cancelPurchaseDebitNote: vi.fn(),
}));
vi.mock('@/utils/blob', () => ({
  printBlob: vi.fn(),
  triggerBlobDownload: (...args: unknown[]) => download(...args),
}));

function wrap(ui: ReactElement, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe.each([
  ['credit', PurchaseCreditNotesPage, listCredit, exportCredit, 'PCN-1'],
  ['debit', PurchaseDebitNotesPage, listDebit, exportDebit, 'PDN-1'],
] as const)('purchase %s notes register', (_kind, Page, list, exporter, number) => {
  it('links the source purchase bill', async () => {
    wrap(<Page />);
    await screen.findByText(number);
    expect(screen.getByRole('link', { name: 'PB-14' }).getAttribute('href')).toBe('/purchases/history/14');
  });

  it('sends the search text to the API', async () => {
    wrap(<Page />);
    await screen.findByText(number);
    await userEvent.type(screen.getByLabelText(/^search$/i), 'Mega');
    await waitFor(() => expect(list.mock.calls.at(-1)?.[0]).toMatchObject({ search: 'Mega', page: 1 }));
  });

  it('exports with the current filters', async () => {
    wrap(<Page />, '/?status=DRAFT');
    await screen.findByText(number);
    await userEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(exporter).toHaveBeenCalled());
    expect(exporter.mock.calls[0][0]).toMatchObject({ status: 'DRAFT' });
    await waitFor(() => expect(download).toHaveBeenCalled());
  });
});
