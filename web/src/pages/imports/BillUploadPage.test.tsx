import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BillUploadPage } from '@/pages/imports/BillUploadPage';
import type { ImportJob } from '@/types/domain';

const api = vi.hoisted(() => ({
  getImportJob: vi.fn(),
  uploadImport: vi.fn(),
  updateImportPreview: vi.fn(),
  commitImport: vi.fn(),
  validateImportBill: vi.fn(),
  cancelImport: vi.fn(),
  retryImportExtract: vi.fn(),
  answerImportClarifications: vi.fn(),
  switchImportKind: vi.fn(),
  voidImport: vi.fn(),
  getCustomer: vi.fn(),
  getSupplier: vi.fn(),
  listBillImportJobs: vi.fn(),
  fetchImportSourceFile: vi.fn(),
  listProductsPage: vi.fn(),
}));

vi.mock('@/api/resources', () => api);
// jsdom has no layout, so the real windowing renders nothing: draw a fixed window and
// expose the props the table passes, so the test can check what is (not) in the DOM.
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({
    children,
    rowCount,
    scrollToIndex,
  }: {
    children: (a: unknown) => unknown;
    rowCount: number;
    scrollToIndex?: number | null;
  }) => (
    <div data-testid="windowed" data-count={rowCount} data-scroll-to={scrollToIndex ?? ''}>
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
const auth = vi.hoisted(() => ({
  user: {
    id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9,
    canImport: true, canCreateSales: true, canCreatePurchases: true,
  } as Record<string, unknown>,
}));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: auth.user }) }));
vi.mock('@/hooks/usePartySearch', () => {
  const search = { options: [], setQuery: vi.fn(), isFetching: false, enabled: true };
  return { useCustomerSearch: () => search, useSupplierSearch: () => search };
});

const NAV = vi.fn();
vi.mock('react-router-dom', async (orig) => {
  const actual = await orig<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => NAV };
});

function line(id: number, over: Record<string, unknown> = {}) {
  return {
    lineId: id,
    si: String(id),
    name: `Item ${id}`,
    sku: `SKU-${id}`,
    hsnCode: '3402',
    quantity: '2',
    unitPrice: '100',
    gstRate: '18',
    mrp: '150',
    include: true,
    flags: [],
    errors: [],
    pcs: '',
    productMatch: { status: 'none', productId: null, candidates: [] },
    ...over,
  };
}

function previewedJob(over: Record<string, unknown> = {}, previewOver: Record<string, unknown> = {}): ImportJob {
  return {
    id: 5,
    kind: 'SALES_BILL',
    status: 'PREVIEWED',
    totalRows: 2,
    validRows: 2,
    errorRows: 0,
    customer: null,
    supplier: null,
    fileName: 'bill.png',
    clarifications: [],
    preview: {
      previewVersion: 3,
      billNumber: 'SB-1',
      billDate: '2026-07-05',
      buyerName: 'Retail Buyer LLP',
      buyerGstin: '',
      extractionConfidence: 0.9,
      priceMode: 'EXCLUSIVE',
      newProductCount: 2,
      totals: {
        taxable: '400.00', gst: '72.00', cess: '0.00', charges: '0.00', invoiceDiscount: '0.00',
        grandTotal: '472.00', roundedTotal: '472', includedLines: 2,
      },
      partyMatch: {
        status: 'none', id: null, candidates: [], extracted: { name: 'Retail Buyer LLP', gstin: '' },
        willCreate: true, notes: [],
      },
      companyGstinStatus: { status: 'defaulted_single', options: [], resolvedId: null },
      lines: [line(1), line(2)],
      ...previewOver,
    },
    ...over,
  } as unknown as ImportJob;
}

function renderPage(entry = '/sales/bill-upload?job=5', kind: 'SALES_BILL' | 'PURCHASE_BILL' = 'SALES_BILL') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <BillUploadPage kind={kind} canAccess />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function axiosFailure(status: number, data: unknown) {
  return new AxiosError('failed', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    data,
    statusText: '',
    headers: {},
    config: {} as never,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listBillImportJobs.mockResolvedValue([]);
  api.getCustomer.mockResolvedValue({ id: 1, name: 'X' });
  api.fetchImportSourceFile.mockResolvedValue({ url: 'blob:bill', contentType: 'image/png' });
  api.updateImportPreview.mockImplementation(async () => previewedJob({}, { previewVersion: 4 }));
  api.commitImport.mockResolvedValue({ created: 2, productsCreated: 2, salesInvoiceId: 77, status: 'COMMITTED', errorRows: 0 });
  api.validateImportBill.mockResolvedValue({
    ok: true, headerErrors: [], lineErrors: [], summary: { included: 2, excluded: 0, newProducts: 2, newParty: true },
    totals: previewedJob().preview,
  });
  window.localStorage.setItem('billUpload.showSource', '0');
  URL.revokeObjectURL = vi.fn();
  auth.user = {
    id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9,
    canImport: true, canCreateSales: true, canCreatePurchases: true,
  };
});

describe('BillUploadPage (sales)', () => {
  it('uses billing-system copy for the structured mode, not "supplier\'s system"', () => {
    renderPage('/sales/bill-upload');
    expect(screen.getByText('I have a CSV or Excel bill export')).toBeInTheDocument();
    expect(screen.queryByText(/supplier's system/i)).not.toBeInTheDocument();
  });

  it('does not ask for AI consent for a CSV/Excel upload', async () => {
    renderPage('/sales/bill-upload');
    const user = userEvent.setup();
    expect(screen.getByRole('checkbox', { name: /sent to an AI service/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'I have a CSV or Excel bill export' }));
    expect(screen.queryByRole('checkbox', { name: /sent to an AI service/i })).not.toBeInTheDocument();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['a,b'], 'export.csv', { type: 'text/csv' }));
    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled();
  });

  it('rejects a file of the wrong type before uploading', async () => {
    renderPage('/sales/bill-upload');
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'notes.txt', { type: 'text/plain' })] } });
    expect(await screen.findByText(/not allowed here/i)).toBeInTheDocument();
    expect(api.uploadImport).not.toHaveBeenCalled();
  });

  it('restores the review from ?job= after a refresh', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    expect(await screen.findByDisplayValue('SB-1')).toBeInTheDocument();
    expect(screen.getByText('Item 1')).toBeInTheDocument();
    expect(screen.getByText('Item 2')).toBeInTheDocument();
    expect(api.getImportJob).toHaveBeenCalledWith(5);
  });

  it('shows who the draft is for and what will happen to them', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    expect(await screen.findByDisplayValue('Retail Buyer LLP')).toBeInTheDocument();
    expect(screen.getByText(/A new party will be created: Retail Buyer LLP/)).toBeInTheDocument();
  });

  it('shows the server totals and the difference from the printed total', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({}, {
        printedTotal: '500',
        totals: {
          taxable: '400.00', gst: '72.00', cess: '0.00', charges: '0.00', invoiceDiscount: '0.00',
          grandTotal: '472.00', roundedTotal: '472', includedLines: 2,
          printedTotal: '500.00', printedDifference: '28.00', printedMatches: false,
        },
      }),
    );
    renderPage();
    expect(await screen.findByText('472.00')).toBeInTheDocument();
    expect(screen.getByText(/Difference from printed total: 28.00/)).toBeInTheDocument();
  });

  it('blocks the commit and points at rows with a blank GST rate or a bad HSN', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({}, { lines: [line(1, { gstRate: '' }), line(2, { hsnCode: '123' })] }),
    );
    renderPage();
    const commit = await screen.findByRole('button', { name: 'Review on sales invoice' });
    expect(commit).toBeDisabled();
    expect(screen.getByText(/2 row\(s\) need fixing/)).toBeInTheDocument();
    expect(screen.getByText('GST rate is required')).toBeInTheDocument();
    expect(screen.getByText('invalid HSN code')).toBeInTheDocument();
  });

  it('"Include all non-flagged rows" does not tick a row with a blank quantity or GST', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({}, {
        lines: [
          line(1),
          line(2, { include: false, quantity: '', gstRate: '' }),
          line(3, { include: false }),
        ],
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await screen.findByText('Item 1');
    await user.click(screen.getByRole('button', { name: 'Include all non-flagged rows' }));
    const boxes = screen.getAllByRole('checkbox', { name: /Include, row/ });
    expect(boxes.map((b) => (b as HTMLInputElement).checked)).toEqual([true, false, true]);
  });

  it('commits with ONE request that carries the edit, and never calls the preview endpoint', async () => {
    api.getImportJob.mockResolvedValue(previewedJob({ customer: 1 }));
    renderPage();
    const user = userEvent.setup();
    const commit = await screen.findByRole('button', { name: 'Review on sales invoice' });
    await user.click(commit);
    await waitFor(() => expect(api.commitImport).toHaveBeenCalledTimes(1));
    expect(api.updateImportPreview).not.toHaveBeenCalled();
    const [jobId, payload, options] = api.commitImport.mock.calls[0];
    expect(jobId).toBe(5);
    expect(payload).toMatchObject({ previewVersion: 3, billNumber: 'SB-1', customerId: 1, buyerName: 'Retail Buyer LLP' });
    expect(options.idempotencyKey).toMatch(/^import-commit-5-/);
    await waitFor(() =>
      expect(NAV).toHaveBeenCalledWith('/sales/history/77/edit', {
        state: { fromBillUpload: true, importJobId: 5, productsCreated: 2 },
      }),
    );
  });

  it('autosaves only the line that changed, with the version it was loaded at', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    const user = userEvent.setup();
    const row = await screen.findByText('Item 2');
    await user.click(row);
    const nameField = await screen.findByRole('textbox', { name: /Name, row 2/i });
    await user.clear(nameField);
    await user.type(nameField, 'Renamed');
    await waitFor(() => expect(api.updateImportPreview).toHaveBeenCalled(), { timeout: 5000 });
    const [, payload] = api.updateImportPreview.mock.calls[0];
    expect(payload.previewVersion).toBe(3);
    expect(payload.lines).toHaveLength(1);
    expect(payload.lines[0]).toMatchObject({ lineId: 2, name: 'Renamed' });
  }, 15_000);

  it('turns server row errors into per-row messages after a rejected commit', async () => {
    api.getImportJob.mockResolvedValue(previewedJob({ customer: 1 }));
    api.commitImport.mockRejectedValueOnce(
      axiosFailure(400, {
        error: {
          message: 'Fix the highlighted rows before creating the draft: 1 line(s) need fixing',
          details: {
            lineErrors: [
              { row: 2, lineId: 2, name: 'Item 2', errors: [{ field: 'hsn_code', code: 'HSN_FORMAT', message: 'invalid HSN code' }] },
            ],
            headerErrors: [],
          },
        },
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Review on sales invoice' }));
    expect(await screen.findByText('invalid HSN code')).toBeInTheDocument();
    expect(screen.getByText(/1 row\(s\) need fixing/)).toBeInTheDocument();
  });

  it('adds a row and removes one with an undo', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    const user = userEvent.setup();
    await screen.findByText('Item 1');
    await user.click(screen.getAllByRole('button', { name: 'Add a row' })[0]);
    expect(await screen.findByRole('textbox', { name: /Name, row 3/i })).toBeInTheDocument();
    // delete the new row
    await user.click(screen.getByRole('button', { name: 'Delete row 3' }));
    expect(screen.queryByRole('textbox', { name: /Name, row 3/i })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Undo' }));
    expect(await screen.findByRole('textbox', { name: /Name, row 3/i })).toBeInTheDocument();
  });

  it('hides the pack columns when the bill has no Cs / UPC data', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    await screen.findByText('Item 1');
    expect(screen.queryByRole('columnheader', { name: 'Cs' })).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'UPC' })).not.toBeInTheDocument();
  });

  it('shows the pack columns when a row has Cs / UPC', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({}, { lines: [line(1, { cs: '2', upc: '12' }), line(2)] }),
    );
    renderPage();
    expect(await screen.findByRole('columnheader', { name: 'Cs' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'UPC' })).toBeInTheDocument();
  });

  it('wraps the table so it scrolls on a narrow screen', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    const table = await screen.findByRole('table');
    expect(getComputedStyle(table.parentElement as HTMLElement).overflowX).toBe('auto');
  });

  it('shows the original bill beside the rows when asked', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Show the original bill' }));
    expect(await screen.findByRole('img', { name: 'Original bill' })).toHaveAttribute('src', 'blob:bill');
    expect(api.fetchImportSourceFile).toHaveBeenCalledWith(5);
  });

  it('offers to switch a bill that looks like it is on the wrong screen', async () => {
    api.getImportJob.mockResolvedValue(previewedJob({}, { directionWarning: 'looks like a purchase bill' }));
    api.switchImportKind.mockResolvedValue(previewedJob({ kind: 'PURCHASE_BILL' }));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Switch to a purchase bill' }));
    await waitFor(() => expect(api.switchImportKind).toHaveBeenCalledWith(5, 'PURCHASE_BILL'));
    await waitFor(() => expect(NAV).toHaveBeenCalledWith('/purchases/bill-upload?job=5'));
  });

  it('lists unfinished uploads so one can be resumed', async () => {
    api.listBillImportJobs.mockResolvedValue([
      { id: 9, kind: 'SALES_BILL', status: 'PREVIEWED', fileName: 'lost-tab.png', createdAt: '2026-07-05T10:00:00Z' },
    ]);
    renderPage('/sales/bill-upload');
    const panel = (await screen.findByText('Recent uploads')).closest('div') as HTMLElement;
    expect(within(panel.parentElement as HTMLElement).getByText(/lost-tab.png/)).toBeInTheDocument();
  });

  it('shows a committed upload with a way to open or undo the draft', async () => {
    api.getImportJob.mockResolvedValue(previewedJob({ status: 'COMMITTED', salesInvoice: 77 }));
    renderPage();
    expect(await screen.findByText('This bill is now a draft.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the draft' })).toHaveAttribute('href', '/sales/history/77/edit');
    expect(screen.getByRole('button', { name: 'Undo this import' })).toBeInTheDocument();
  });

  it('requires choosing which GSTIN issued the bill when the company has several', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({ customer: 1 }, {
        companyGstinStatus: {
          status: 'unresolved',
          resolvedId: null,
          options: [
            { id: 1, gstin: '29AAAAA0000A1ZY', state: 'Karnataka', isPrimary: true },
            { id: 2, gstin: '27AAAAA0000A1ZV', state: 'Maharashtra', isPrimary: false },
          ],
        },
      }),
    );
    renderPage();
    expect(await screen.findByLabelText('Which of your GSTINs issued this bill?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review on sales invoice' })).toBeDisabled();
  });

  it('labels every field in an expanded row for screen readers', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText('Item 1'));
    expect(await screen.findByRole('spinbutton', { name: /Qty, row 1/i })).toBeInTheDocument();
    // qty, price, GST %, MRP: every numeric input names its column and its row
    expect(screen.getAllByRole('spinbutton', { name: /, row 1$/i }).length).toBeGreaterThanOrEqual(4);
    expect(screen.getByRole('spinbutton', { name: /GST %, row 1/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse row 1' })).toBeInTheDocument();
  });
});

describe('BillUploadPage (purchase)', () => {
  it('keeps the supplier wording on the purchase screen', () => {
    renderPage('/purchases/bill-upload', 'PURCHASE_BILL');
    expect(screen.getByText("I have an export from my supplier's system")).toBeInTheDocument();
  });
});

describe('BillUploadPage (round 2)', () => {
  it('tells the server the uploader agreed to AI processing, only for a photo/PDF', async () => {
    api.uploadImport.mockResolvedValue(previewedJob({ status: 'EXTRACTING' }));
    api.getImportJob.mockResolvedValue(previewedJob({ status: 'EXTRACTING' }));
    renderPage('/sales/bill-upload');
    const user = userEvent.setup();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['x'], 'bill.png', { type: 'image/png' }));
    await user.click(screen.getByRole('checkbox', { name: /sent to an AI service/i }));
    await user.click(screen.getByRole('button', { name: 'Upload' }));
    await waitFor(() => expect(api.uploadImport).toHaveBeenCalled());
    expect(api.uploadImport.mock.calls[0][2]).toMatchObject({ aiConsent: true });
  });

  it('does not claim AI consent for a CSV/Excel upload', async () => {
    api.uploadImport.mockResolvedValue(previewedJob({ status: 'EXTRACTING' }));
    api.getImportJob.mockResolvedValue(previewedJob({ status: 'EXTRACTING' }));
    renderPage('/sales/bill-upload');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'I have a CSV or Excel bill export' }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['a'], 'x.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: 'Upload' }));
    await waitFor(() => expect(api.uploadImport).toHaveBeenCalled());
    expect(api.uploadImport.mock.calls[0][2]).toMatchObject({ aiConsent: false });
  });

  it('draws the row you point at on the original bill', async () => {
    window.localStorage.setItem('billUpload.showSource', '1');
    api.getImportJob.mockResolvedValue(
      previewedJob({}, { lines: [line(1, { bbox: [0.1, 0.2, 0.8, 0.05] }), line(2)] }),
    );
    renderPage();
    await screen.findByRole('img', { name: 'Original bill' });
    expect(screen.queryByTestId('bill-row-highlight')).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.hover(screen.getByText('Item 1'));
    const box = await screen.findByTestId('bill-row-highlight');
    expect(box).toHaveStyle({ left: '10%', top: '20%', width: '80%', height: '5%' });
    await user.unhover(screen.getByText('Item 1'));
    await waitFor(() => expect(screen.queryByTestId('bill-row-highlight')).not.toBeInTheDocument());
  });

  it('suggests your own GSTIN when the printed one is a character off, and applies it on request', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({ customer: 1 }, {
        companyGstinStatus: {
          status: 'unresolved',
          resolvedId: null,
          suggestion: { id: 2, gstin: '27AAAAA0000A1ZV' },
          options: [
            { id: 1, gstin: '29AAAAA0000A1ZY', state: 'Karnataka', isPrimary: true },
            { id: 2, gstin: '27AAAAA0000A1ZV', state: 'Maharashtra', isPrimary: false },
          ],
        },
      }),
    );
    renderPage();
    const user = userEvent.setup();
    expect(await screen.findByText(/looks like your 27AAAAA0000A1ZV/)).toBeInTheDocument();
    const commit = screen.getByRole('button', { name: 'Review on sales invoice' });
    expect(commit).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Use it' }));
    await waitFor(() => expect(commit).toBeEnabled());
    expect(screen.queryByText(/looks like your/)).not.toBeInTheDocument();
  });

  it('windows a large bill: only the rows on screen are in the page', async () => {
    const many = Array.from({ length: 230 }, (_, i) => line(i + 1));
    api.getImportJob.mockResolvedValue(previewedJob({}, { lines: many }));
    renderPage();
    await screen.findByText('Item 1');
    const windowed = screen.getByTestId('windowed');
    expect(windowed).toHaveAttribute('data-count', '230');
    expect(screen.getByText('Item 20')).toBeInTheDocument();
    expect(screen.queryByText('Item 21')).not.toBeInTheDocument();
  });

  it('keeps a small bill whole (no windowing)', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    await screen.findByText('Item 1');
    expect(screen.queryByTestId('windowed')).not.toBeInTheDocument();
  });

  it('narrows a big bill to its problem rows and opens the first one', async () => {
    const many = Array.from({ length: 150 }, (_, i) => line(i + 1, i === 120 ? { gstRate: '' } : {}));
    api.getImportJob.mockResolvedValue(previewedJob({ customer: 1 }, { lines: many }));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText('Item 1');
    expect(screen.getByTestId('windowed')).toHaveAttribute('data-count', '150');
    await user.click(screen.getByRole('button', { name: 'Go to the first one' }));
    // One problem row left: the table is small again and the row is open for editing.
    expect(await screen.findByRole('textbox', { name: /Name, row 121/i })).toBeInTheDocument();
    expect(screen.queryByTestId('windowed')).not.toBeInTheDocument();
  });

  it('splits GST into CGST and SGST, or IGST, from the states', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({}, {
        totals: {
          taxable: '400.00', gst: '72.00', cess: '0.00', charges: '0.00', invoiceDiscount: '0.00',
          grandTotal: '472.00', roundedTotal: '472', includedLines: 2,
          cgst: '36.00', sgst: '36.00', igst: '0.00', taxType: 'INTRA',
        },
      }),
    );
    renderPage();
    expect(await screen.findByText('CGST')).toBeInTheDocument();
    expect(screen.getByText('SGST')).toBeInTheDocument();
    expect(screen.queryByText('IGST')).not.toBeInTheDocument();
  });

  it('shows IGST for an inter-state bill and says when the split is only assumed', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({}, {
        totals: {
          taxable: '400.00', gst: '72.00', cess: '0.00', charges: '0.00', invoiceDiscount: '0.00',
          grandTotal: '472.00', roundedTotal: '472', includedLines: 2,
          cgst: '0.00', sgst: '0.00', igst: '72.00', taxType: 'INTER',
        },
      }),
    );
    renderPage();
    expect(await screen.findByText('IGST')).toBeInTheDocument();
    expect(screen.queryByText('CGST')).not.toBeInTheDocument();
  });

  it('notes that the CGST/SGST split is assumed until the customer is known', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({}, {
        totals: {
          taxable: '400.00', gst: '72.00', cess: '0.00', charges: '0.00', invoiceDiscount: '0.00',
          grandTotal: '472.00', roundedTotal: '472', includedLines: 2,
          cgst: '36.00', sgst: '36.00', igst: '0.00', taxType: 'ASSUMED_INTRA',
        },
      }),
    );
    renderPage();
    expect(await screen.findByText(/split is assumed/i)).toBeInTheDocument();
  });

  it('opens the read-only invoice when the person can no longer edit the draft', async () => {
    auth.user = { ...auth.user, role: 'SALES_STAFF', canCreateSales: false, canViewFinancialReports: true };
    api.getImportJob.mockResolvedValue(previewedJob({ customer: 1 }));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Review on sales invoice' }));
    await waitFor(() =>
      expect(NAV).toHaveBeenCalledWith('/sales/history/77', {
        state: { fromBillUpload: true, importJobId: 5, productsCreated: 2 },
      }),
    );
  });

  it('stays on the upload screen when the person can neither edit nor view the draft', async () => {
    auth.user = { ...auth.user, role: 'SALES_STAFF', canCreateSales: false, canViewFinancialReports: false };
    api.getImportJob.mockResolvedValue(previewedJob({ customer: 1 }));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Review on sales invoice' }));
    await waitFor(() => expect(api.commitImport).toHaveBeenCalled());
    expect(NAV).not.toHaveBeenCalled();
  });

  it('warns before leaving with edits that are not saved yet', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    api.updateImportPreview.mockImplementation(() => new Promise(() => undefined)); // never finishes
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText('Item 1'));
    await user.type(await screen.findByRole('textbox', { name: /Name, row 1/i }), 'x');
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('shows the original bill in a drawer instead of a column on a narrow screen', async () => {
    window.localStorage.setItem('billUpload.showSource', '1');
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
      api.getImportJob.mockResolvedValue(previewedJob());
      renderPage();
      await screen.findByText('Item 1');
      const drawer = await screen.findByRole('presentation');
      expect(within(drawer).getByRole('img', { name: 'Original bill' })).toBeInTheDocument();
    } finally {
      window.matchMedia = original;
    }
  });
});

describe('BillUploadPage (deep review fixes)', () => {
  it('does not edit a sales bill with the purchase screen: it points to the right one', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage('/purchases/bill-upload?job=5', 'PURCHASE_BILL');
    expect(await screen.findByText(/cannot be edited on this screen/i)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Open in Sales' });
    expect(link.getAttribute('href')).toBe('/sales/bill-upload?job=5');
    expect(screen.queryByText('Item 1')).not.toBeInTheDocument();
  });

  it('asks before discarding an unfinished upload', async () => {
    api.listBillImportJobs.mockResolvedValue([
      { id: 9, kind: 'SALES_BILL', status: 'PREVIEWED', fileName: 'lost-tab.png', createdAt: '2026-07-05T10:00:00Z' },
    ]);
    api.cancelImport.mockResolvedValue({});
    renderPage('/sales/bill-upload');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Discard' }));
    expect(api.cancelImport).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Discard' }));
    await waitFor(() => expect(api.cancelImport).toHaveBeenCalledWith(9));
  });

  it('labels the save retry as a save, not an extraction, and retries it', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    api.updateImportPreview.mockRejectedValueOnce(new Error('Network Error'));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText('Item 1'));
    await user.type(await screen.findByRole('textbox', { name: /Name, row 1/i }), 'x');
    const retry = await screen.findByRole('button', { name: 'Try saving again' }, { timeout: 5000 });
    expect(screen.queryByRole('button', { name: 'Retry extraction' })).not.toBeInTheDocument();
    await user.click(retry);
    await waitFor(() => expect(api.updateImportPreview).toHaveBeenCalledTimes(2));
  }, 15_000);

  it('sends an edited row again when its deletion is undone', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText('Item 2'));
    const name = await screen.findByRole('textbox', { name: /Name, row 2/i });
    await user.clear(name);
    await user.type(name, 'Renamed');
    await user.click(screen.getByRole('button', { name: 'Delete row 2' }));
    await user.click(await screen.findByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(api.updateImportPreview).toHaveBeenCalled(), { timeout: 5000 });
    const lines = api.updateImportPreview.mock.calls.at(-1)![1].lines as Array<Record<string, unknown>>;
    expect(lines.some((l) => l.lineId === 2 && l.name === 'Renamed')).toBe(true);
    expect(lines.some((l) => l.deleted)).toBe(false);
  }, 15_000);
});

describe('BillUploadPage (purchase review 2)', () => {
  it('shows an error when "Retry extraction" itself fails (B-03)', async () => {
    api.getImportJob.mockResolvedValue(
      previewedJob({ status: 'FAILED', failureReason: 'Reader crashed' }, {}),
    );
    api.retryImportExtract.mockRejectedValue(new Error('Network Error'));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Retry extraction' }));
    expect(await screen.findByText(/Could not restart reading the bill/i)).toBeInTheDocument();
  });

  it('names the reason Create draft is off (C-01)', async () => {
    api.getImportJob.mockResolvedValue(previewedJob({}, { billDate: '' }));
    renderPage();
    expect(await screen.findByText(/You cannot create the draft yet: enter the bill date/i)).toBeInTheDocument();
  });

  it('asks before discarding the review and keeps the job when declined (G-01)', async () => {
    api.getImportJob.mockResolvedValue(previewedJob());
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Discard this upload' }));
    expect(confirm).toHaveBeenCalled();
    expect(api.cancelImport).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Discard this upload' }));
    await waitFor(() => expect(api.cancelImport).toHaveBeenCalledWith(5));
    confirm.mockRestore();
  });

  it('remembers the AI agreement instead of asking on every upload (C-03)', async () => {
    window.localStorage.setItem('bizboard:billUpload:aiConsent', '1');
    renderPage('/purchases/bill-upload', 'PURCHASE_BILL');
    expect(await screen.findByText(/You agreed earlier/i)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    window.localStorage.removeItem('bizboard:billUpload:aiConsent');
  });

  it('offers a sample file for the CSV / Excel route (H-06)', async () => {
    renderPage('/purchases/bill-upload', 'PURCHASE_BILL');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /export from my supplier/i }));
    expect(await screen.findByRole('button', { name: 'Download a sample CSV' })).toBeInTheDocument();
  });
});
