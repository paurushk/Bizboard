import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { InvoiceDetailPage } from '@/pages/sales/InvoiceDetailPage';
import type { SalesInvoice, SalesReturn } from '@/types/domain';

// G-17: the header status chip on this page is computed client-side the same
// way as SalesHistoryPage's list badge — this pins the same combinations at
// the detail level, plus the "related returns" panel that links a partial
// return back to its invoice for auditability.
function baseInvoice(overrides: Partial<SalesInvoice>): SalesInvoice {
  return {
    id: 1,
    number: 'INV-0001',
    status: 'COMPLETED',
    invoiceType: 'RETAIL',
    customer: 3,
    customerName: 'Cash',
    invoiceDate: '2026-09-12',
    grandTotal: '104.00',
    taxableTotal: '104.00',
    cgstTotal: '0',
    sgstTotal: '0',
    igstTotal: '0',
    balance: '0',
    received: '104.00',
    paymentState: 'PAID',
    returnState: 'NONE',
    items: [],
    ...overrides,
  } as SalesInvoice;
}

const RETURNED_INVOICE = baseInvoice({
  status: 'RETURNED',
  returnState: 'FULL',
  paymentState: 'PAID',
  balance: '0',
});

const PARTIAL_INVOICE = baseInvoice({
  id: 2,
  number: 'INV-0002',
  status: 'COMPLETED',
  returnState: 'PARTIAL',
  paymentState: 'UNPAID',
  balance: '200.00',
  grandTotal: '500.00',
});

const LINKED_RETURN: SalesReturn = {
  id: 9,
  number: 'SRN-0001',
  status: 'COMPLETED',
  customer: 3,
  salesInvoice: 2,
  returnDate: '2026-09-12',
  items: [],
  grandTotal: '150.00',
} as SalesReturn;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

const getSalesInvoice = vi.fn(async (id: number | string) =>
  String(id) === '2' ? PARTIAL_INVOICE : RETURNED_INVOICE,
);

vi.mock('@/api/resources', () => ({
  getSalesInvoice: (id: number | string) => getSalesInvoice(id),
  getCustomer: async () => ({ id: 3, name: 'Cash' }),
  getInvoiceAudit: async () => [],
  listAllocationsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPaymentLinksPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listSalesReturns: async () => [LINKED_RETURN],
  getSalesDocumentPdfStatus: async () => ({ pdfStatus: 'READY' }),
  downloadSalesDocumentPdf: vi.fn(),
  regenerateSalesDocumentPdf: vi.fn(),
  getUpiQr: vi.fn(),
  amendInvoiceFilingIdentity: vi.fn(),
  cancelSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
  createPaymentLink: vi.fn(),
  cancelPaymentLink: vi.fn(),
  downloadInvoicePdf: vi.fn(),
  downloadInvoiceThermalPdf: vi.fn(),
  shareInvoice: vi.fn(),
  sharePaymentLink: vi.fn(),
  unallocatePayment: vi.fn(),
  updateSalesInvoice: vi.fn(),
}));

function wrap(ui: ReactElement, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/sales/history/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InvoiceDetailPage status — G-17', () => {
  it('shows Returned, not Paid, for a fully-returned invoice', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/1');
    expect(await screen.findByText(/^returned$/i)).toBeTruthy();
    expect(screen.queryByText(/^paid$/i)).toBeNull();
  });

  it('flags a partial return and lists the linked SalesReturn for auditability', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');
    expect(screen.getAllByText(/^completed$/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/partially returned/i)).toBeTruthy();
    expect(await screen.findByText('SRN-0001')).toBeTruthy();
  });
});
