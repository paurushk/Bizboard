import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Gstr2bPage } from '@/pages/reports/Gstr2bPage';
import { PurchaseReportPage } from '@/pages/reports/PurchaseReportPage';
import { ledgerEntryPath } from '@/pages/reports/ledgerLinks';
import { SupplierLedgerPage } from '@/pages/reports/SupplierLedgerPage';

const api = vi.hoisted(() => ({
  getSupplierLedger: vi.fn(),
  getPurchaseRegister: vi.fn(),
  exportReport: vi.fn(),
}));
const ims = vi.hoisted(() => ({ actImsRow: vi.fn(async () => ({})) }));

vi.mock('@/api/resources', async (orig) => ({
  ...(await orig<typeof import('@/api/resources')>()),
  getSupplierLedger: api.getSupplierLedger,
  getPurchaseRegister: api.getPurchaseRegister,
  exportReport: api.exportReport,
}));
vi.mock('@/hooks/usePartySearch', () => ({
  useSupplierSearch: () => ({
    options: [{ id: 7, name: 'Acme Traders', phone: '9876543210' }],
    setQuery: vi.fn(),
    isFetching: false,
    enabled: true,
  }),
  useCustomerSearch: () => ({ options: [], setQuery: vi.fn(), isFetching: false, enabled: true }),
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', canExport: true } }),
}));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) => (
    <div>
      {children({
        rows: Array.from({ length: Math.min(rowCount, 20) }, (_, i) => ({
          index: i, start: i * 64, end: (i + 1) * 64, size: 64, key: i,
        })),
        totalSize: rowCount * 64,
        measureElement: () => undefined,
      }) as never}
    </div>
  ),
}));
vi.mock('@/api/gstr2b', async () => {
  const actual = await vi.importActual<typeof import('@/api/gstr2b')>('@/api/gstr2b');
  return {
    ...actual,
    actImsRow: ims.actImsRow,
    listGstr2bPage: vi.fn(async () => ({
      results: [
        {
          id: 11, supplierGstin: '29ABCDE1234F1Z5', invoiceNumber: 'INV-9', invoiceDate: '2026-09-02',
          igst: '10', cgst: '0', sgst: '0', cess: '0', matchStatus: 'UNMATCHED', matchClass: 'value_mismatch',
          imsAction: 'NO_ACTION', itcEligibility: 'UNREVIEWED',
        },
      ],
      count: 1, next: null, previous: null,
    })),
    fetchImsSummary: vi.fn(async () => ({ period: '2026-09', totalItc: '0', matchedItc: '0' })),
    fetchImsScorecard: vi.fn(async () => ({ period: '2026-09', suppliers: [] })),
  };
});

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('supplier ledger (H-01/H-02/H-03/G-03)', () => {
  const entry = (over = {}) => ({
    date: '2026-09-02', type: 'PURCHASE_INVOICE', number: 'PUR-3', sourceId: 3, referenceId: 99,
    debit: '0', credit: '500', balance: '1500', ...over,
  });

  it('maps a row to the page of the document behind it, using the source id', () => {
    expect(ledgerEntryPath(entry() as never)).toBe('/purchases/history/3');
    expect(ledgerEntryPath(entry({ type: 'PURCHASE_DEBIT_NOTE', sourceId: 4 }) as never)).toBe('/purchases/debit-notes/4');
    expect(ledgerEntryPath(entry({ type: 'JOURNAL', sourceId: 4 }) as never)).toBeNull();
    expect(ledgerEntryPath(entry({ type: 'SUPPLIER_PAYMENT', sourceId: 5 }) as never, 7)).toBe('/purchases/payments?supplier=7');
  });

  it('links rows, names types in words, explains the columns and shows the carried-in balance', async () => {
    api.getSupplierLedger.mockResolvedValue({
      supplierId: 7, supplierName: 'Acme Traders', outstanding: '1500', openingBalance: '1000',
      entries: [entry(), entry({ type: 'SUPPLIER_PAYMENT', number: 'PAY-1', sourceId: 5, debit: '200', credit: '0', balance: '1300' })],
    });
    const user = userEvent.setup();
    wrap(<SupplierLedgerPage />);
    await user.click(await screen.findByRole('combobox'));
    await user.click(await screen.findByText(/Acme Traders/));
    await user.type(screen.getByLabelText(/from/i), '2026-09-01');
    expect(await screen.findByText('Purchase bill')).toBeInTheDocument();
    expect(screen.getAllByText('Payment').length).toBeGreaterThan(0);
    expect(screen.queryByText('PURCHASE_INVOICE')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open PUR-3' }).getAttribute('href')).toBe('/purchases/history/3');
    expect(screen.getByText(/Bills and debit notes add to what you owe/)).toBeInTheDocument();
    expect(screen.getByText('Balance brought forward')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export CSV/ })).toBeInTheDocument();
  });
});

describe('GSTR-2B (C-05/C-06/C-07/G-04)', () => {
  it('shows plain words, an order of work, and asks before accepting a row', async () => {
    const user = userEvent.setup();
    wrap(<Gstr2bPage />);
    expect(await screen.findByText('INV-9')).toBeInTheDocument();
    expect(screen.getByText('Amount differs')).toBeInTheDocument();
    expect(screen.getByText('No action yet')).toBeInTheDocument();
    expect(screen.queryByText('NO_ACTION')).not.toBeInTheDocument();
    expect(screen.getByText(/Order of work/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Accept' }));
    expect(ims.actImsRow).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Accept this invoice')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(ims.actImsRow).toHaveBeenCalledWith(11, 'ACCEPT', expect.any(String)));
  });

  it('keeps Reject, Pending and the supplier message under one menu', async () => {
    const user = userEvent.setup();
    wrap(<Gstr2bPage />);
    await user.click(await screen.findByRole('button', { name: 'More actions' }));
    expect(await screen.findByRole('menuitem', { name: 'Reject' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Supplier message' })).toBeInTheDocument();
  });
});

describe('purchase register (H-04/H-05/C-11/G-07)', () => {
  it('opens on a bounded range, shows totals and a curated column set', async () => {
    api.getPurchaseRegister.mockResolvedValue({
      rows: [
        { id: 1, number: 'PUR-1', date: '2026-09-01', supplier: 'Acme', status: 'COMPLETED', taxable: '100', cgst: '9', sgst: '9', igst: '0', grand_total: '118' },
        { id: 2, number: 'PUR-2', date: '2026-09-02', supplier: 'Beta', status: 'COMPLETED', taxable: '200', cgst: '0', sgst: '0', igst: '36', grand_total: '236' },
      ],
      totals: {},
    });
    wrap(<PurchaseReportPage />);
    expect(await screen.findByText('PUR-1')).toBeInTheDocument();
    const first = api.getPurchaseRegister.mock.calls[0][0];
    expect(first.dateFrom).toBeTruthy();
    expect(first.dateTo).toBeTruthy();
    expect(screen.getByText(/GST:/).textContent).toMatch(/54\.00/);
    expect(screen.getByText(/Taxable value:/).textContent).toMatch(/300\.00/);
    expect(screen.getByRole('columnheader', { name: 'Bill no.' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Cgst' })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('checkbox', { name: 'Show all columns' }));
    expect(await screen.findByRole('columnheader', { name: /CGST/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last Month' })).toBeInTheDocument();
  });

  it('confirms the export started', async () => {
    api.getPurchaseRegister.mockResolvedValue({ rows: [], totals: {} });
    api.exportReport.mockResolvedValue({ url: 'blob:x' });
    const user = userEvent.setup();
    wrap(<PurchaseReportPage />);
    await user.click(await screen.findByRole('button', { name: 'Export' }));
    expect(await screen.findByText(/Export started/)).toBeInTheDocument();
  });
});
