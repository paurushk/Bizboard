import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { writeDraft, removeDraft } from '@/lib/deviceDraft';
import { NewInvoicePage } from '@/pages/sales/NewInvoicePage';

const track = vi.hoisted(() => vi.fn());

vi.mock('@/lib/telemetry', () => ({
  trackShopFloor: (...args: unknown[]) => track(...args),
  runInvoiceCompleteJourney: async (run: () => Promise<unknown>) => run(),
  classifyCompleteFailure: () => 'unknown',
}));

// This test mounts the whole editor and types with userEvent. Under a full parallel run the default
// 1s async wait is not enough, so give the lookups the same headroom as the test itself.
configure({ asyncUtilTimeout: 30_000 });

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'owner@bizboard.test',
      fullName: 'Owner',
      role: 'OWNER',
      companyId: 9,
      company: { registrationType: 'REGULAR', state: 'Delhi' },
    },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({
    id: 9,
    name: 'Acme',
    registrationType: 'REGULAR',
    state: 'Delhi',
    gstin: '07AAAAA0000A1Z5',
    negativeStockPolicy: 'WARN',
    invoiceTerms: 'Pay within 7 days.',
  }),
  listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listCustomersPage: async () => ({
    results: [
      { id: 10, name: 'Anil Store', phone: '9876543210', status: 'ACTIVE', state: 'Delhi' },
    ],
    count: 1,
    next: null,
    previous: null,
  }),
  getCustomer: async (id: number) => ({
    id,
    name: 'Anil Store',
    phone: '9876543210',
    status: 'ACTIVE',
    state: 'Delhi',
  }),
  listCollectionRisk: async () => [],
  listWarehouses: async () => [{ id: 1, name: 'Main Godown' }],
  listCompanyGstins: async () => [],
  listCostCenters: async () => [],
  listPriceLists: async () => [],
  listBatches: async () => [],
  getSalesInvoiceNumberSeries: async () => ({ prefix: 'INV', nextNumber: 1 }),
  getSalesInvoice: async () => ({ id: 1, number: 'INV-1' }),
  listProductsPage: async () => ({
    results: [
      {
        id: 201,
        name: 'Laptop Pro',
        sku: 'LAP-001',
        sellingPrice: 50000,
        trackSerial: true,
        unitName: 'PCS',
        status: 'ACTIVE',
        gstRate: 18,
      },
    ],
    count: 1,
    next: null,
    previous: null,
  }),
  searchProducts: async () => [
    {
      id: 201,
      name: 'Laptop Pro',
      sku: 'LAP-001',
      sellingPrice: 50000,
      trackSerial: true,
      unitName: 'PCS',
      status: 'ACTIVE',
      gstRate: 18,
    },
  ],
  listStock: async () => [],
  previewSalesTotals: async () => ({
    subtotal: 50000,
    grandTotal: 59000,
    cgstTotal: 4500,
    sgstTotal: 4500,
    taxTotal: 9000,
    items: [
      {
        gstRate: 18,
        taxableAmount: 50000,
        cgst: 4500,
        sgst: 4500,
        igst: 0,
        cess: 0,
        lineTotal: 59000,
      },
    ],
  }),
  previewSalesInvoiceTotals: async () => ({
    subtotal: 50000,
    grandTotal: 59000,
    cgstTotal: 4500,
    sgstTotal: 4500,
    taxTotal: 9000,
  }),
  createSalesInvoice: vi.fn(),
  updateSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
}));

function renderPage(initialEntries = ['/sales/new']) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/sales/new" element={<NewInvoicePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NewInvoicePage CW-PR-5 Guidance and Focus', () => {
  it('renders interactive Next Step Card with Enter Serial Numbers button when item requires serials', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();

    // Select customer Anil Store
    const partyInput = screen.getByPlaceholderText(/search by customer name/i);
    await user.click(partyInput);
    const customerOption = await screen.findByRole('option', { name: /anil store/i });
    await user.click(customerOption);

    // Search and add Laptop Pro (which has trackSerial: true)
    const productInput = screen.getByPlaceholderText(/scan barcode or search sku \/ name/i);
    await user.click(productInput);
    await user.paste('Laptop');
    const productOption = await screen.findByRole('option', { name: /laptop pro/i });
    await user.click(productOption);

    // Next step action card should appear with "Enter Serial Numbers" button
    const serialButton = await screen.findByRole('button', { name: /enter serial numbers/i }, { timeout: 20000 });
    expect(serialButton).toBeInTheDocument();

    // Click focus button
    await user.click(serialButton);

    // Assert that the serial input field receives focus
    const serialInput = screen.getByPlaceholderText(/sn-001, sn-002/i);
    expect(serialInput).toHaveFocus();
  }, 90_000); // mounts the whole editor; the serial card appears only after the picker resolves
});

describe('NewInvoicePage draft restore and terms', () => {
  afterEach(() => {
    removeDraft(9, 1, 'sales-invoice');
    track.mockClear();
  });

  it('offers the saved draft and records one restore', async () => {
    writeDraft(9, 1, 'sales-invoice', {
      lines: [{ product: 201, productName: 'Laptop Pro', quantity: 1, unitPrice: 10 }],
      customerId: 10,
    });
    renderPage();
    expect(await screen.findByRole('button', { name: 'Restore' })).toBeTruthy();
    await waitFor(() => {
      expect(track).toHaveBeenCalledTimes(1);
    });
    expect(track).toHaveBeenCalledWith('draft_restored', { feature: 'form' });
  });

  it('does not put company terms back after they are cleared', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '+ Add Terms and Conditions' }));
    const terms = screen.getByLabelText('Add Terms and Conditions');
    expect(terms).toHaveValue('Pay within 7 days.');
    await user.clear(terms);
    expect(terms).toHaveValue('');
  });
});
