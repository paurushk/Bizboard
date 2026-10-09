import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { InvoiceDetailPage } from '@/pages/sales/InvoiceDetailPage';

const downloadInvoicePdf = vi.hoisted(() => vi.fn(async () => new Blob(['%PDF'])));

const authState = vi.hoisted(() => ({
  user: {
    id: 2,
    role: 'STAFF' as string,
    companyId: 9,
    canViewFinancialReports: false,
    canCreateSales: true,
    canCreatePayments: true,
    canCancelDocuments: false,
    company: { einvoiceEnabled: false },
  },
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: authState.user }),
}));

vi.mock('@/api/resources', () => ({
  getSalesInvoice: async () => ({
    id: 8,
    number: 'INV-8',
    status: 'COMPLETED',
    invoiceType: 'GST',
    invoiceDate: '2026-10-08',
    customer: 10,
    customerName: 'Anil Store',
    grandTotal: '118.00',
    balance: '118.00',
    items: [],
  }),
  getCustomer: async () => ({ id: 10, name: 'Anil Store', state: 'Karnataka' }),
  getCompany: async () => ({ id: 9, name: 'Acme' }),
  getInvoiceAudit: async () => [],
  getInvoiceHsnSummary: async () => [],
  getInvoiceProfitReport: async () => ({ results: [] }),
  getInvoiceProfitDetails: async () => ({}),
  getSalesDocumentPdfStatus: async () => ({ status: 'READY' }),
  listPaymentLinksPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listAllocationsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPaymentPromises: async () => [],
  listSalesReturns: async () => [],
  downloadInvoicePdf: (...args: unknown[]) => downloadInvoicePdf(...args),
  downloadInvoiceThermalPdf: vi.fn(),
  downloadSalesDocumentPdf: vi.fn(),
  regenerateSalesDocumentPdf: vi.fn(),
  updateSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
  cancelSalesInvoice: vi.fn(),
  createPaymentLink: vi.fn(),
  cancelPaymentLink: vi.fn(),
  sharePaymentLink: vi.fn(),
  unallocatePayment: vi.fn(),
  createPaymentPromise: vi.fn(),
  resolvePaymentPromise: vi.fn(),
  getUpiQr: vi.fn(),
  amendInvoiceFilingIdentity: vi.fn(),
  createInvoicePublicLink: vi.fn(),
  revokeInvoicePublicLink: vi.fn(),
  prepareInvoiceEinvoice: vi.fn(),
  prepareInvoiceEway: vi.fn(),
  submitInvoiceEinvoice: vi.fn(),
  submitInvoiceEway: vi.fn(),
  cancelInvoiceEinvoice: vi.fn(),
  cancelInvoiceEway: vi.fn(),
  markInvoiceEinvoiceGenerated: vi.fn(),
  markInvoiceEwayGenerated: vi.fn(),
  postPlanEwayStub: vi.fn(),
  recordInvoicePayment: vi.fn(),
  shareInvoice: vi.fn(),
}));

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/sales/history/8']}>
        <Routes>
          <Route path="/sales/history/:id" element={<InvoiceDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('invoice detail profit and pdf', () => {
  it('INV-DET-07 profit details is absent when the user cannot view financial reports', async () => {
    renderDetail();
    expect(await screen.findByText('INV-8')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /profit details/i })).not.toBeInTheDocument();
  });

  it('INV-PREV-02 download and print ask for the stored invoice PDF', async () => {
    const user = userEvent.setup({ delay: null });
    URL.createObjectURL = vi.fn(() => 'blob:invoice');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(window, 'open').mockReturnValue(null);
    renderDetail();
    await screen.findByText('INV-8');
    await user.click(screen.getByRole('button', { name: /^more$/i }));
    await user.click(await screen.findByRole('menuitem', { name: /download original/i }));
    expect(downloadInvoicePdf).toHaveBeenCalledWith(8, { copy: 'ORIGINAL' });
    await user.click(screen.getByRole('button', { name: /^more$/i }));
    await user.click(await screen.findByRole('menuitem', { name: /^print$/i }));
    expect(downloadInvoicePdf).toHaveBeenCalledWith(8, { copy: 'ORIGINAL' });
  });
});
