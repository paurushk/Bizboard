import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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

const invoiceState = vi.hoisted(() => ({ value: { id: 1, number: 'INV-1' } as Record<string, unknown> }));

const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    email: 'owner@bizboard.test',
    fullName: 'Owner',
    role: 'OWNER' as string,
    companyId: 9,
    canImport: true,
    canViewFinancialReports: true,
    canCreateSales: true,
    canCreatePayments: true,
    company: { registrationType: 'REGULAR', state: 'Delhi' },
  },
}));

const companyState = vi.hoisted(() => ({
  negativeStockPolicy: 'WARN',
  invoiceCustomFieldDefs: [] as Array<{ key: string; label: string; type: string; active: boolean }>,
}));

const updateSalesInvoice = vi.hoisted(() => vi.fn(async () => ({ id: 5, status: 'COMPLETED', number: 'INV-5' })));
const createSalesInvoice = vi.hoisted(() => vi.fn(async () => ({ id: 77, status: 'DRAFT', number: '' })));
const completeSalesInvoice = vi.hoisted(() =>
  vi.fn(async () => ({ id: 88, status: 'COMPLETED', number: 'INV-88' })),
);
const createCustomer = vi.hoisted(() =>
  vi.fn(async (body: Record<string, unknown>) => ({
    id: 44,
    status: 'ACTIVE',
    state: 'Karnataka',
    ...body,
  })),
);

const createProduct = vi.hoisted(() =>
  vi.fn(async (body: Record<string, unknown>) => ({
    id: 301,
    status: 'ACTIVE',
    unitName: 'PCS',
    gstRate: 18,
    trackSerial: false,
    trackInventory: false,
    productType: 'GOODS',
    ...body,
  })),
);

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: authState.user }),
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
    negativeStockPolicy: companyState.negativeStockPolicy,
    invoiceCustomFieldDefs: companyState.invoiceCustomFieldDefs,
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
  getSalesInvoice: async () => invoiceState.value,
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
      {
        id: 202,
        name: 'Nirma Soap',
        sku: 'SOAP',
        sellingPrice: 20,
        trackSerial: false,
        trackInventory: false,
        productType: 'GOODS',
        unitName: 'PCS',
        status: 'ACTIVE',
        gstRate: 18,
        purchasePrice: 12,
      },
      {
        id: 203,
        name: 'Old Soap',
        sku: 'OLD',
        sellingPrice: 10,
        trackSerial: false,
        unitName: 'PCS',
        status: 'INACTIVE',
        gstRate: 18,
      },
      {
        id: 204,
        name: 'Rice',
        sku: 'RICE',
        sellingPrice: 30,
        trackSerial: false,
        trackInventory: true,
        productType: 'GOODS',
        unitName: 'KG',
        status: 'ACTIVE',
        gstRate: 5,
      },
      {
        id: 205,
        name: 'Delivery',
        sku: 'DEL',
        sellingPrice: 50,
        trackSerial: false,
        trackInventory: true,
        productType: 'SERVICE',
        unitName: 'NOS',
        status: 'ACTIVE',
        gstRate: 18,
      },
    ],
    count: 5,
    next: null,
    previous: null,
  }),
  searchProducts: async (q: string) => {
    const needle = String(q).toLowerCase();
    return [
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
      {
        id: 202,
        name: 'Nirma Soap',
        sku: 'SOAP',
        sellingPrice: 20,
        trackSerial: false,
        trackInventory: false,
        productType: 'GOODS',
        unitName: 'PCS',
        status: 'ACTIVE',
        gstRate: 18,
        purchasePrice: 12,
      },
      {
        id: 203,
        name: 'Old Soap',
        sku: 'OLD',
        sellingPrice: 10,
        trackSerial: false,
        unitName: 'PCS',
        status: 'INACTIVE',
        gstRate: 18,
      },
      {
        id: 204,
        name: 'Rice',
        sku: 'RICE',
        sellingPrice: 30,
        trackSerial: false,
        trackInventory: true,
        productType: 'GOODS',
        unitName: 'KG',
        status: 'ACTIVE',
        gstRate: 5,
      },
      {
        id: 205,
        name: 'Delivery',
        sku: 'DEL',
        sellingPrice: 50,
        trackSerial: false,
        trackInventory: true,
        productType: 'SERVICE',
        unitName: 'NOS',
        status: 'ACTIVE',
        gstRate: 18,
      },
    ].filter((row) => `${row.name} ${row.sku}`.toLowerCase().includes(needle));
  },
  listStock: async () => [],
  previewSalesTotals: async () => ({
    subtotal: 50000,
    grandTotal: 59000,
    cgstTotal: 4500,
    sgstTotal: 4500,
    taxTotal: 9000,
    estimatedCogs: 40000,
    estimatedMargin: 10000,
    estimatedMarginPercent: 20,
    marginLines: [
      { productId: 202, name: 'Nirma Soap', unitCost: 40, quantity: 1, lineCost: 40, missing: false },
    ],
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
  createSalesInvoice: (...args: unknown[]) => createSalesInvoice(...args),
  createCustomer: (...args: unknown[]) => createCustomer(...(args as [Record<string, unknown>])),
  updateSalesInvoice: (...args: unknown[]) => updateSalesInvoice(...args),
  completeSalesInvoice: (...args: unknown[]) => completeSalesInvoice(...args),
  downloadInvoicePdf: vi.fn(async () => new Blob(['%PDF'])),
  downloadInvoicePreviewPdf: vi.fn(async () => new Blob(['%PDF-preview'])),
  createProduct: (...args: unknown[]) => createProduct(...(args as [Record<string, unknown>])),
}));

function OpenedInvoice() {
  const { id } = useParams();
  return <h1>Opened invoice {id}</h1>;
}

function renderPage(initialEntries = ['/sales/new']) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/sales/new" element={<NewInvoicePage />} />
          <Route path="/sales/history/:id/edit" element={<NewInvoicePage />} />
          <Route path="/sales/history/:id" element={<OpenedInvoice />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NewInvoicePage CW-PR-5 Guidance and Focus', () => {
  it('INV-MAIN-14 a serial item with one number missing keeps complete disabled', async () => {
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
    expect(screen.getByRole('button', { name: /save & complete/i })).toBeDisabled();
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
    await user.click(await screen.findByRole('button', { name: 'Notes and terms' }));
    const terms = screen.getByLabelText('Add Terms and Conditions');
    expect(terms).toHaveValue('Pay within 7 days.');
    await user.clear(terms);
    expect(terms).toHaveValue('');
  });
});

describe('INV-MAIN default path', () => {
  beforeEach(() => {
    localStorage.removeItem('bizboard:draft:v1:9:1:sales-invoice');
  });

  afterEach(() => {
    authState.user.role = 'OWNER';
    authState.user.canImport = true;
    authState.user.canViewFinancialReports = true;
    authState.user.canCreateSales = true;
    authState.user.canCreatePayments = true;
    localStorage.removeItem('bizboard:draft:v1:9:1:sales-invoice');
    localStorage.removeItem('bizboard:show-purchase-price');
    localStorage.removeItem('bizboard.billing.batchCols');
    companyState.negativeStockPolicy = 'WARN';
    companyState.invoiceCustomFieldDefs = [];
    createSalesInvoice.mockClear();
    completeSalesInvoice.mockClear();
    createCustomer.mockClear();
    createProduct.mockReset();
    createProduct.mockImplementation(async (body: Record<string, unknown>) => ({
      id: 301,
      status: 'ACTIVE',
      unitName: 'PCS',
      gstRate: 18,
      trackSerial: false,
      trackInventory: false,
      productType: 'GOODS',
      ...body,
    }));
  });
  it('INV-MAIN-01 complete stays off and focus lands on the party', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    const complete = await screen.findByRole('button', { name: /save & complete/i });
    expect(complete).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /go to the missing field/i }));
    expect(document.getElementById('billing-party-input')).toHaveFocus();
  }, 60_000);

  it('INV-MAIN-02 party without a line keeps complete off and focuses the item', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    const complete = screen.getByRole('button', { name: /save & complete/i });
    expect(complete).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /go to the missing field/i }));
    expect(document.getElementById('billing-item-input')).toHaveFocus();
  }, 60_000);

  it('ACT-16 a default bill shows party, items, and total with tax, TCS, notes, and bank closed', async () => {
    renderPage();
    expect(await screen.findByPlaceholderText(/search by customer name/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/scan barcode or search sku/i)).toBeInTheDocument();
    expect(screen.getAllByText(/total amount/i).length).toBeGreaterThan(0);
    expect(await screen.findByRole('button', { name: /\+ TCS/i })).toBeInTheDocument();
    const notes = screen.getByRole('button', { name: 'Notes and terms' });
    expect(getComputedStyle(notes).minHeight).toBe('44px');
    expect(screen.queryByLabelText('Add Notes')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/tcs amount/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /advanced tax/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /less tax/i })).not.toBeInTheDocument();
  }, 60_000);

  it('INV-MAIN-22 an owner sees Upload Sales Bill', async () => {
    renderPage();
    const link = await screen.findByRole('link', { name: /upload sales bill/i });
    expect(link).toHaveAttribute('href', '/sales/bill-upload');
  }, 60_000);

  it('INV-PREV-01 preview of an unsaved line asks for the invoice PDF and edit mode keeps the draft', async () => {
    const user = userEvent.setup({ delay: null });
    URL.createObjectURL = vi.fn(() => 'blob:preview');
    URL.revokeObjectURL = vi.fn();
    const { downloadInvoicePreviewPdf } = await import('@/api/resources');
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Laptop');
    await user.click(await screen.findByRole('option', { name: /laptop pro/i }));
    await user.click(screen.getByRole('button', { name: /preview mode/i }));
    expect(await screen.findByTitle(/preview mode/i)).toBeInTheDocument();
    expect(downloadInvoicePreviewPdf).toHaveBeenCalled();
    const previewBody = (downloadInvoicePreviewPdf as unknown as { mock: { calls: unknown[][] } }).mock.calls.at(-1)?.[0] as {
      customer?: number;
      items?: Array<{ description?: string }>;
    };
    expect(previewBody.customer).toBe(10);
    expect(previewBody.items?.some((item) => /laptop pro/i.test(item.description ?? ''))).toBe(true);
    expect(await screen.findByText('Anil Store')).toBeInTheDocument();
    expect(screen.getByText(/59,000\.00/)).toBeInTheDocument();
    expect(screen.getByText('Fifty Nine Thousand Rupees Only')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /edit mode/i }));
    expect(screen.getAllByText(/laptop pro/i).length).toBeGreaterThan(0);
  }, 90_000);

  it('INV-ITEM-01 and INV-ITEM-03 and INV-ITEM-06 the create-item dialog refuses a blank name, a bad HSN, and cancel', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByRole('button', { name: /create item/i }));
    expect(screen.getByRole('button', { name: /^create$/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/^name/i), 'Soap');
    await user.type(screen.getByLabelText(/sku/i), 'SOAP-9');
    await user.type(screen.getByLabelText(/hsn/i), '12AB');
    expect(screen.getByText(/digits/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^create$/i })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByRole('heading', { name: /create item/i })).not.toBeVisible();
    expect(screen.queryByText(/^Soap$/)).not.toBeInTheDocument();
  }, 60_000);

  it('INV-MAIN-03 a party and one active item enable complete and show the line columns', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    await user.click(await screen.findByRole('option', { name: /nirma soap/i }));
    expect(screen.getByText('Nirma Soap')).toBeInTheDocument();
    expect(screen.getByText('QTY')).toBeInTheDocument();
    expect(screen.getByText('PRICE/ITEM (₹)')).toBeInTheDocument();
    expect(screen.getByText('DISCOUNT')).toBeInTheDocument();
    expect(screen.getByText('TAX')).toBeInTheDocument();
    expect(screen.getByText('AMOUNT (₹)')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: /save & complete/i })).toBeEnabled());
  }, 90_000);

  it('INV-MAIN-04 an inactive product is refused and is not added', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Old');
    await user.click(await screen.findByRole('option', { name: /old soap/i }));
    expect(await screen.findByText(/cannot sell inactive product/i)).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: /old soap/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save & complete/i })).toBeDisabled();
  }, 60_000);

  it('INV-MAIN-18 cash above the total shows change and other modes keep the bill amount', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    await user.click(await screen.findByRole('option', { name: /nirma soap/i }));
    await waitFor(() => expect(screen.getAllByText(/59,000\.00/).length).toBeGreaterThan(0));
    const received = screen.getByRole('textbox', { name: /amount received/i });
    await user.click(received);
    await user.paste('60000');
    await user.tab();
    expect(await screen.findByText('Cash tendered')).toBeInTheDocument();
    await user.click(screen.getByRole('combobox', { name: /payment mode/i }));
    await user.click(await screen.findByRole('option', { name: 'UPI' }));
    expect(screen.queryByText('Cash tendered')).not.toBeInTheDocument();
    expect(received).toHaveValue('59000');
    await user.click(screen.getByRole('combobox', { name: /payment mode/i }));
    await user.click(await screen.findByRole('option', { name: 'Card' }));
    expect(received).toHaveValue('59000');
    await user.click(screen.getByRole('combobox', { name: /payment mode/i }));
    await user.click(await screen.findByRole('option', { name: 'Bank' }));
    expect(received).toHaveValue('59000');
    await user.click(screen.getByRole('combobox', { name: /payment mode/i }));
    await user.click(await screen.findByRole('option', { name: 'Cheque' }));
    expect(received).toHaveValue('59000');
    expect(screen.queryByText('Cash tendered')).not.toBeInTheDocument();
  }, 90_000);

  it('INV-MAIN-19 mark fully paid sets the amount received to the total and the balance to zero', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    await user.click(await screen.findByRole('option', { name: /nirma soap/i }));
    await waitFor(() => expect(screen.getAllByText(/59,000\.00/).length).toBeGreaterThan(0));
    await user.click(screen.getByRole('checkbox', { name: /mark as fully paid/i }));
    expect(screen.getByRole('textbox', { name: /amount received/i })).toHaveValue('59000');
    expect(screen.getByText('Balance Amount').parentElement).toHaveTextContent('₹0.00');
  }, 90_000);

  it('INV-MAIN-21 the margin row shows the rupee, the percent, and the purchase cost', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    await user.click(await screen.findByRole('option', { name: /nirma soap/i }));
    const margin = await screen.findByText(/Est\. Margin/);
    expect(margin).toHaveTextContent('₹10,000.00');
    expect(margin).toHaveTextContent('20.0%');
    expect(margin).toHaveTextContent('₹40,000.00');
    expect(50000 - 40000).toBe(10000);
  }, 90_000);

  it('INV-MAIN-22 a user who cannot import does not see Upload Sales Bill', async () => {
    authState.user.role = 'STAFF';
    authState.user.canImport = false;
    authState.user.canCreateSales = true;
    renderPage();
    expect(await screen.findByPlaceholderText(/search by customer name/i)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /upload sales bill/i })).not.toBeInTheDocument();
  }, 60_000);

  it('INV-ITEM-02 creating an item adds it at the selling price', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByRole('button', { name: /create item/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^name/i), 'Soap');
    await user.type(within(dialog).getByLabelText(/sku/i), 'SOAP-NEW');
    await user.type(within(dialog).getByLabelText(/selling price/i), '40');
    await user.click(within(dialog).getByRole('button', { name: /^create$/i }));
    expect(await screen.findByText('Soap')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: /^create item$/i })).not.toBeInTheDocument();
    });
    expect(createProduct).toHaveBeenCalledWith(expect.objectContaining({ sellingPrice: 40, name: 'Soap' }));
    expect(screen.getAllByDisplayValue('40').length).toBeGreaterThan(0);
  }, 60_000);

  it('INV-ITEM-04 a duplicate SKU keeps the dialog open and adds no line', async () => {
    createProduct.mockRejectedValueOnce(new Error('SKU already exists'));
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByRole('button', { name: /create item/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^name/i), 'Soap');
    await user.type(within(dialog).getByLabelText(/sku/i), 'SOAP');
    await user.click(within(dialog).getByRole('button', { name: /^create$/i }));
    expect(await screen.findByText(/sku already exists/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /create item/i })).toBeVisible();
    expect(screen.queryByRole('cell', { name: /^soap$/i })).not.toBeInTheDocument();
  }, 60_000);

  it('INV-ITEM-05 the create payload sends the purchase price when that column is on', async () => {
    localStorage.setItem('bizboard:show-purchase-price', '1');
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByRole('button', { name: /create item/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^name/i), 'Soap');
    await user.type(within(dialog).getByLabelText(/sku/i), 'SOAP-PP');
    await user.type(within(dialog).getByLabelText(/selling price/i), '40');
    await user.type(within(dialog).getByLabelText(/item purchase price/i), '12');
    await user.click(within(dialog).getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(createProduct).toHaveBeenCalled());
    expect(createProduct).toHaveBeenCalledWith(expect.objectContaining({ purchasePrice: 12, sellingPrice: 40 }));
  }, 60_000);

  it('INV-MAIN-15 a service line does not block Complete when stock is short', async () => {
    companyState.negativeStockPolicy = 'BLOCK';
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Delivery');
    await user.click(await screen.findByRole('option', { name: /delivery/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /save & complete/i })).toBeEnabled());
    expect(screen.queryByText(/insufficient stock/i)).not.toBeInTheDocument();
  }, 60_000);

  it('INV-MAIN-15 a goods line that does not track stock does not block Complete', async () => {
    companyState.negativeStockPolicy = 'BLOCK';
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    await user.click(await screen.findByRole('option', { name: /nirma soap/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /save & complete/i })).toBeEnabled());
    expect(screen.queryByText(/insufficient stock/i)).not.toBeInTheDocument();
  }, 60_000);

  it('REVIEW-AMEND amending a completed invoice asks in a dialog, and Cancel saves nothing', async () => {
    const previous = invoiceState.value;
    invoiceState.value = {
      id: 5,
      number: 'INV-5',
      status: 'COMPLETED',
      invoiceType: 'GST',
      invoiceDate: '2026-10-08',
      customer: 1,
      amendRevision: 0,
      items: [{ id: 1, product: 202, productName: 'Nirma Soap', quantity: '1', unitPrice: '20.00', gstRate: '18', discountPercent: '0' }],
    };
    try {
      updateSalesInvoice.mockClear();
      const confirmSpy = vi.spyOn(window, 'confirm');
      const user = userEvent.setup({ delay: null });
      renderPage(['/sales/history/5/edit']);
      const save = await screen.findByRole('button', { name: /^save( changes)?$/i });
      await user.click(save);
      const dialog = await screen.findByRole('dialog', { name: /amend completed invoice/i });
      expect(confirmSpy).not.toHaveBeenCalled();
      await user.click(within(dialog).getByRole('button', { name: /cancel/i }));
      expect(updateSalesInvoice).not.toHaveBeenCalled();
    } finally {
      invoiceState.value = previous;
    }
  }, 60_000);

  it('REVIEW-AMEND confirming in the dialog saves the amend with confirmAmend', async () => {
    const previous = invoiceState.value;
    invoiceState.value = {
      id: 5,
      number: 'INV-5',
      status: 'COMPLETED',
      invoiceType: 'GST',
      invoiceDate: '2026-10-08',
      customer: 1,
      amendRevision: 3,
      items: [{ id: 1, product: 202, productName: 'Nirma Soap', quantity: '1', unitPrice: '20.00', gstRate: '18', discountPercent: '0' }],
    };
    try {
      updateSalesInvoice.mockClear();
      const user = userEvent.setup({ delay: null });
      renderPage(['/sales/history/5/edit']);
      await user.click(await screen.findByRole('button', { name: /^save( changes)?$/i }));
      const dialog = await screen.findByRole('dialog', { name: /amend completed invoice/i });
      await user.click(within(dialog).getByRole('button', { name: /^amend invoice$/i }));
      await waitFor(() => expect(updateSalesInvoice).toHaveBeenCalledTimes(1));
      expect(updateSalesInvoice.mock.calls[0]?.[1]).toEqual(
        expect.objectContaining({ confirmAmend: true, expectedAmendRevision: 3 }),
      );
    } finally {
      invoiceState.value = previous;
    }
  }, 60_000);

  describe('REVIEW complete failures and the idempotency key', () => {
    const draftInvoice = {
      id: 5,
      number: '',
      status: 'DRAFT',
      invoiceType: 'GST',
      invoiceDate: '2026-10-08',
      customer: 1,
      items: [{ id: 1, product: 202, productName: 'Nirma Soap', quantity: '1', unitPrice: '20.00', gstRate: '18', discountPercent: '0' }],
    };
    const completed = { ...draftInvoice, status: 'COMPLETED', number: 'INV-5' };
    const serverError = () =>
      new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, undefined, {
        status: 422,
        statusText: 'Unprocessable',
        headers: {},
        config: {} as never,
        data: { error: { message: 'Insufficient stock for Nirma Soap' } },
      });
    const networkError = () => new AxiosError('Network Error', 'ERR_NETWORK');
    let previous: Record<string, unknown>;

    beforeEach(() => {
      previous = invoiceState.value;
      invoiceState.value = draftInvoice;
      updateSalesInvoice.mockReset();
      updateSalesInvoice.mockImplementation(async () => draftInvoice as never);
      completeSalesInvoice.mockReset();
    });
    afterEach(() => {
      invoiceState.value = previous;
      completeSalesInvoice.mockImplementation(async () => ({ id: 88, status: 'COMPLETED', number: 'INV-88' }));
    });

    const keyOf = (call: number) =>
      (completeSalesInvoice.mock.calls[call]?.[1] as { idempotencyKey?: string } | undefined)?.idempotencyKey;

    async function openDraftAndComplete(user: ReturnType<typeof userEvent.setup>) {
      renderPage(['/sales/history/5/edit']);
      const complete = await screen.findByRole('button', { name: /save & complete/i });
      await waitFor(() => expect(complete).toBeEnabled());
      await user.click(complete);
    }

    it('a server answer is final for its key: the retry after a fix gets a new key', async () => {
      completeSalesInvoice.mockRejectedValueOnce(serverError());
      completeSalesInvoice.mockResolvedValueOnce(completed as never);
      const user = userEvent.setup({ delay: null });
      await openDraftAndComplete(user);
      expect(await screen.findByText(/insufficient stock for nirma soap/i)).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /save & complete/i }));
      await waitFor(() => expect(completeSalesInvoice).toHaveBeenCalledTimes(2));
      expect(keyOf(0)).toBeTruthy();
      expect(keyOf(1)).toBeTruthy();
      expect(keyOf(1)).not.toBe(keyOf(0));
    }, 60_000);

    it('a lost reply is checked on the server and, if it committed, opens the invoice', async () => {
      completeSalesInvoice.mockRejectedValueOnce(networkError());
      const user = userEvent.setup({ delay: null });
      renderPage(['/sales/history/5/edit']);
      const complete = await screen.findByRole('button', { name: /save & complete/i });
      await waitFor(() => expect(complete).toBeEnabled());
      invoiceState.value = completed;
      await user.click(complete);
      expect(await screen.findByText('Opened invoice 5')).toBeInTheDocument();
      expect(completeSalesInvoice).toHaveBeenCalledTimes(1);
    }, 60_000);

    it('a lost reply that did not commit says so, keeps the form, and retries with the same key', async () => {
      completeSalesInvoice.mockRejectedValueOnce(networkError());
      completeSalesInvoice.mockResolvedValueOnce(completed as never);
      const user = userEvent.setup({ delay: null });
      await openDraftAndComplete(user);
      expect(await screen.findByText(/did not get a reply/i)).toBeInTheDocument();
      expect(screen.queryByText('Opened invoice 5')).not.toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /save & complete/i }));
      await waitFor(() => expect(completeSalesInvoice).toHaveBeenCalledTimes(2));
      expect(keyOf(1)).toBe(keyOf(0));
    }, 60_000);

    it('a lost reply on a retry that did commit does not update the completed invoice again', async () => {
      completeSalesInvoice.mockRejectedValueOnce(networkError());
      const user = userEvent.setup({ delay: null });
      await openDraftAndComplete(user);
      expect(await screen.findByText(/did not get a reply/i)).toBeInTheDocument();
      const updatesBefore = updateSalesInvoice.mock.calls.length;
      invoiceState.value = completed;
      await user.click(screen.getByRole('button', { name: /save & complete/i }));
      expect(await screen.findByText('Opened invoice 5')).toBeInTheDocument();
      expect(updateSalesInvoice.mock.calls.length).toBe(updatesBefore);
    }, 60_000);
  });

  it('REVIEW-B2 two scans in a row both land, one line each', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    const box = screen.getByPlaceholderText(/scan barcode or search sku/i);
    await user.click(box);
    await user.keyboard('SOAP{Enter}RICE{Enter}');
    expect(await screen.findByText('Nirma Soap')).toBeInTheDocument();
    expect(await screen.findByText('Rice')).toBeInTheDocument();
    expect(box).toHaveValue('');
  }, 60_000);

  it('REVIEW-B2 a code that matches nothing says so and still clears the box for the next scan', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    const box = await screen.findByPlaceholderText(/scan barcode or search sku/i);
    await user.click(box);
    await user.keyboard('NO-SUCH-CODE{Enter}');
    expect(await screen.findByText(/no item matches that barcode or sku/i)).toBeInTheDocument();
    expect(box).toHaveValue('');
  }, 60_000);

  it('REVIEW-B2 the same item scanned twice becomes quantity 2, not two lines', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    const box = await screen.findByPlaceholderText(/scan barcode or search sku/i);
    await user.click(box);
    await user.keyboard('RICE{Enter}RICE{Enter}');
    expect(await screen.findByText('Rice')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('Rice')).toHaveLength(1));
    await waitFor(() => expect(screen.getByDisplayValue('2')).toBeInTheDocument());
  }, 60_000);

  it('REVIEW-B3 Tab leaves the item box and never adds a line', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    const box = await screen.findByPlaceholderText(/scan barcode or search sku/i);
    await user.click(box);
    await user.keyboard('SOAP');
    await user.tab();
    expect(box).not.toHaveFocus();
    expect(screen.queryByText('Nirma Soap')).not.toBeInTheDocument();
  }, 60_000);

  it('ACT-17 a 320px line shows the name, quantity, and amount, and the keyboard can finish the bill', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    const party = await screen.findByPlaceholderText(/search by customer name/i);
    party.focus();
    await user.keyboard('Anil');
    await screen.findByRole('option', { name: /anil store/i });
    await user.keyboard('{ArrowDown}{Enter}');
    const item = screen.getByPlaceholderText(/scan barcode or search sku/i);
    item.focus();
    await user.keyboard('Nirma');
    await screen.findByRole('option', { name: /nirma soap/i });
    await user.keyboard('{ArrowDown}{Enter}');
    const region = await screen.findByRole('region', { name: /scroll sideways/i });
    region.style.width = '320px';
    region.style.maxWidth = '320px';
    expect(getComputedStyle(region).overflow).toMatch(/auto|scroll/);
    expect(within(region).getByText('Nirma Soap')).toBeInTheDocument();
    expect(within(region).getByDisplayValue('1')).toBeInTheDocument();
    expect(within(region).getByLabelText(/total amount/i)).toBeInTheDocument();
    const complete = await screen.findByRole('button', { name: /save & complete/i });
    await waitFor(() => expect(complete).toBeEnabled());
    complete.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { name: /opened invoice 88/i })).toBeInTheDocument();
  }, 60_000);

  it('INV-MAIN-16 Complete stays off and names the short item', async () => {
    companyState.negativeStockPolicy = 'BLOCK';
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Rice');
    await user.click(await screen.findByRole('option', { name: /^rice/i }));
    expect(await screen.findByText(/rice: available 0/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save & complete/i })).toBeDisabled();
  }, 60_000);

  it('INV-SET-02 a PO Number field is sent on the invoice', async () => {
    companyState.invoiceCustomFieldDefs = [
      { key: 'po_number', label: 'PO Number', type: 'text', active: true },
    ];
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/search by customer name/i));
    await user.click(await screen.findByRole('option', { name: /anil store/i }));
    await user.click(screen.getByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    await user.click(await screen.findByRole('option', { name: /nirma soap/i }));
    await user.type(await screen.findByLabelText(/po number/i), 'PO-9');
    await user.click(screen.getByRole('button', { name: /save draft/i }));
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalled());
    const saved = createSalesInvoice.mock.calls.at(-1)?.[0] as { customFields?: { po_number?: string } };
    expect(saved.customFields?.po_number).toBe('PO-9');
  }, 60_000);

  it('INV-SET-09 purchase price stays off the item dialog, the search row, and the line', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByRole('button', { name: /create item/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByLabelText(/item purchase price/i)).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(await screen.findByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    const option = await screen.findByRole('option', { name: /nirma soap/i });
    expect(option).not.toHaveTextContent(/12\.00/);
    await user.click(option);
    expect(await screen.findByText('Nirma Soap')).toBeInTheDocument();
    expect(screen.queryByText(/12\.00/)).not.toBeInTheDocument();
  }, 60_000);

  it('INV-SET-10 purchase price shows on the search row and the line, and a new item can cost 40', async () => {
    localStorage.setItem('bizboard:show-purchase-price', '1');
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByPlaceholderText(/scan barcode or search sku/i));
    await user.paste('Nirma');
    expect(await screen.findByRole('option', { name: /nirma soap/i })).toHaveTextContent(/12\.00/);
    await user.click(screen.getByRole('option', { name: /nirma soap/i }));
    expect(await screen.findByText(/12\.00/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /create item/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^name/i), 'Rice Bag');
    await user.type(within(dialog).getByLabelText(/sku/i), 'RICE-40');
    await user.type(within(dialog).getByLabelText(/selling price/i), '80');
    await user.type(within(dialog).getByLabelText(/item purchase price/i), '40');
    await user.click(within(dialog).getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(createProduct).toHaveBeenCalledWith(
      expect.objectContaining({ purchasePrice: 40, name: 'Rice Bag' }),
    ));
    expect(await screen.findByText(/40\.00/)).toBeInTheDocument();
  }, 60_000);

  it('INV-SET-11 batch columns stay after the page is opened again', async () => {
    localStorage.setItem('bizboard.billing.batchCols', '1');
    const first = renderPage();
    expect(await screen.findByText(/batch no/i)).toBeInTheDocument();
    expect(screen.getByText(/exp\. date/i)).toBeInTheDocument();
    expect(screen.getByText(/mfg date/i)).toBeInTheDocument();
    first.unmount();
    renderPage();
    expect(await screen.findByText(/batch no/i)).toBeInTheDocument();
    expect(screen.getByText(/exp\. date/i)).toBeInTheDocument();
    expect(screen.getByText(/mfg date/i)).toBeInTheDocument();
  }, 60_000);

  it('INV-PARTY-02 a party created here is the selected customer', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    await user.click(await screen.findByRole('button', { name: /create party/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^name/i), 'Anil Store');
    await user.type(within(dialog).getByLabelText(/phone/i), '9876543210');
    await user.type(within(dialog).getByLabelText(/gstin/i), '29AABCU9603R1ZJ');
    await user.click(within(dialog).getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(createCustomer).toHaveBeenCalled());
    expect(await screen.findByText('Anil Store')).toBeInTheDocument();
  }, 60_000);

  it('ACT-10 the line table scrolls sideways and the bill can be reached from the party', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();
    const region = await screen.findByRole('region', { name: /scroll sideways/i });
    expect(getComputedStyle(region).overflow).toMatch(/auto|scroll/);
    const party = await screen.findByPlaceholderText(/search by customer name/i);
    const item = screen.getByPlaceholderText(/scan barcode or search sku/i);
    const complete = screen.getByRole('button', { name: /save & complete/i });
    const order = (node: HTMLElement) => Array.from(document.body.querySelectorAll('button, input, textarea, select, [tabindex]')).indexOf(node);
    expect(order(party)).toBeLessThan(order(item));
    expect(order(item)).toBeLessThan(order(complete));
    party.focus();
    expect(document.activeElement).toBe(party);
    await user.tab();
    expect(document.activeElement).not.toBe(party);
  }, 60_000);
});
