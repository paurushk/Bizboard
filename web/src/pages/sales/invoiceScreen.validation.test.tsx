import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DraftLineTable } from '@/components/billing/DraftLineTable';
import type { DraftLine } from '@/components/billing/types';
import { InvoicePostedActionBar } from '@/components/InvoicePostedActionBar';
import { InvoiceQuickSettingsDialog } from '@/components/InvoiceQuickSettingsDialog';
import { ProfitDetailsDialog } from '@/components/ProfitDetailsDialog';
import { RecordInvoicePaymentDialog } from '@/components/RecordInvoicePaymentDialog';
import { InvoicePartyPanel } from '@/pages/sales/invoice/InvoicePartyPanel';
import { applyDiscountAmountPatch, recomputeLine } from '@/components/billing/lineHelpers';
import { calculateLineTax } from '@/utils/tax';
import type { Customer, SalesInvoice } from '@/types/domain';

const companySettings = vi.hoisted(() => ({ showEmptySignatureBox: false }));
const updateCompany = vi.hoisted(() => vi.fn(async () => ({ id: 9 })));
const recordInvoicePayment = vi.hoisted(() => vi.fn(async () => ({ id: 1 })));
const createCustomer = vi.hoisted(() => vi.fn(async (body: Customer) => ({ id: 44, status: 'ACTIVE', ...body })));
const getInvoiceProfitDetails = vi.hoisted(() => vi.fn());
const createInvoicePublicLink = vi.hoisted(() => vi.fn(async () => ({ url: 'https://front.test/i/public-token' })));

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({
    id: 9,
    invoiceCustomFieldDefs: [],
    partyCustomFieldDefs: [],
    showEmptySignatureBox: companySettings.showEmptySignatureBox,
  }),
  getSalesInvoiceNumberSeries: async () => ({ preview: 'INV-1' }),
  updateCompany: (body: { showEmptySignatureBox?: boolean }) => {
    if (typeof body?.showEmptySignatureBox === 'boolean') {
      companySettings.showEmptySignatureBox = body.showEmptySignatureBox;
    }
    return updateCompany(body);
  },
  createCustomer: (...args: unknown[]) => createCustomer(...(args as [Customer])),
  updateCustomer: vi.fn(),
  listCustomersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  getInvoiceProfitDetails: (...args: unknown[]) => getInvoiceProfitDetails(...args),
  createInvoicePublicLink: (...args: unknown[]) => createInvoicePublicLink(...args),
  downloadInvoicePdf: vi.fn(async () => new Blob(['%PDF'])),
  getCompanyGstins: async () => [],
  prepareInvoiceEinvoice: vi.fn(),
  prepareInvoiceEway: vi.fn(),
  submitInvoiceEinvoice: vi.fn(),
  submitInvoiceEway: vi.fn(),
  revokeInvoicePublicLink: vi.fn(),
  updateSalesInvoice: vi.fn(),
  recordInvoicePayment: (...args: unknown[]) => recordInvoicePayment(...args),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      role: 'OWNER',
      companyId: 9,
      company: { einvoiceEnabled: true, ewayThresholdAmount: '50000' },
    },
  }),
}));

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const soap: DraftLine = {
  key: 'l1',
  product: 4,
  productName: 'Nirma Soap',
  description: '',
  sku: 'SOAP',
  hsnCode: '3401',
  unitName: 'PCS',
  batchNo: '',
  expDate: '',
  mfgDate: '',
  mrp: 0,
  quantity: 1,
  unitPrice: 187.5,
  discountPercent: 0,
  discountAmount: 0,
  gstRate: 18,
  cessRate: 0,
  taxableAmount: 187.5,
  cgst: 16.88,
  sgst: 16.88,
  igst: 0,
  cess: 0,
  lineTotal: 221.26,
  gross: 187.5,
};

function renderLine(
  line: DraftLine,
  intra: boolean | null,
  onUpdate = vi.fn(),
  extra: { priceInclusive?: boolean } = {},
) {
  const tax = calculateLineTax({
    quantity: line.quantity,
    unitPrice: line.unitPrice,
    discountPercent: line.discountPercent,
    gstRate: line.gstRate,
    intraState: intra,
  });
  wrap(
    <DraftLineTable
      lines={[line]}
      taxes={[tax]}
      showCess={false}
      intraState={intra}
      priceInclusive={extra.priceInclusive}
      onUpdate={onUpdate}
      onDelete={() => undefined}
    />,
  );
  return onUpdate;
}

describe('invoice line validation', () => {
  it('INV-MAIN-05 intra-state 18% on ₹187.50 is ₹221.26 split into CGST and SGST', () => {
    const tax = calculateLineTax({
      quantity: 1, unitPrice: 187.5, discountPercent: 0, gstRate: 18, intraState: true,
    });
    expect(tax.lineTotal).toBeCloseTo(221.26, 2);
    expect(tax.cgst + tax.sgst).toBeCloseTo(tax.taxTotal, 2);
    expect(tax.igst).toBe(0);
    renderLine(soap, true);
    expect(screen.getByLabelText(/total amount/i)).toHaveValue('221.26');
  });

  it('INV-MAIN-06 editing the amount back-calculates the price', async () => {
    const user = userEvent.setup({ delay: null });
    const onUpdate = renderLine(soap, true);
    const amount = screen.getByDisplayValue('221.26');
    await user.clear(amount);
    await user.type(amount, '221.26');
    await user.tab();
    const patch = onUpdate.mock.calls.at(-1)?.[1] as { unitPrice?: number };
    expect(patch.unitPrice).toBeCloseTo(187.5, 2);
    const price = screen.getByDisplayValue('187.5');
    await user.clear(price);
    await user.type(price, '200');
    await user.tab();
    const edited = onUpdate.mock.calls.at(-1)?.[1] as { unitPrice?: number };
    expect(edited.unitPrice).toBe(200);
    const forward = calculateLineTax({
      quantity: 1, unitPrice: 200, discountPercent: 0, gstRate: 18, intraState: true,
    });
    expect(forward.lineTotal).not.toBeCloseTo(221.26, 2);
  });

  it('INV-MAIN-06b tabbing through the amount box does not touch the price', async () => {
    const user = userEvent.setup({ delay: null });
    const onUpdate = renderLine(soap, true);
    const amount = screen.getByDisplayValue('221.26');
    await user.click(amount);
    await user.tab();
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it('REVIEW-B7 in tax-inclusive mode the typed amount becomes the rate with no tax taken out', async () => {
    const user = userEvent.setup({ delay: null });
    const onUpdate = renderLine({ ...soap, unitPrice: 118 }, true, vi.fn(), { priceInclusive: true });
    const amount = screen.getByLabelText(/total amount/i);
    await user.clear(amount);
    await user.type(amount, '236');
    await user.tab();
    const patch = onUpdate.mock.calls.at(-1)?.[1] as { unitPrice?: number; priceEdited?: boolean };
    expect(patch.unitPrice).toBe(236);
    expect(patch.priceEdited).toBe(true);
  });

  it('REVIEW-B6 typing an amount marks the price as typed, but tabbing past it twice does not', async () => {
    const user = userEvent.setup({ delay: null });
    const onUpdate = renderLine(soap, true);
    const amount = screen.getByLabelText(/total amount/i);
    await user.click(amount);
    await user.tab();
    await user.click(amount);
    await user.tab();
    expect(onUpdate).not.toHaveBeenCalled();
    await user.click(amount);
    await user.type(amount, '0');
    await user.tab();
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });

  it('INV-MAIN-07 a percent discount stays when the amount is edited', async () => {
    const user = userEvent.setup({ delay: null });
    const onUpdate = renderLine({ ...soap, discountPercent: 10 }, true);
    const amount = screen.getAllByRole('textbox').at(-1)!;
    await user.clear(amount);
    await user.type(amount, '200');
    await user.tab();
    const patch = onUpdate.mock.calls.at(-1)?.[1] as { unitPrice?: number; discountPercent?: number };
    expect(patch.discountPercent).toBeUndefined();
    expect(patch.unitPrice).toBeGreaterThan(0);
    const forward = calculateLineTax({
      quantity: 1,
      unitPrice: patch.unitPrice ?? 0,
      discountPercent: 10,
      gstRate: 18,
      intraState: true,
    });
    expect(Math.abs(forward.lineTotal - 200)).toBeLessThanOrEqual(0.01);
  });

  it('INV-MAIN-08 quantity 0 does not change the price when the amount is edited', () => {
    const onUpdate = renderLine({ ...soap, quantity: 0, lineTotal: 0 }, true);
    const amount = screen.getAllByRole('textbox').at(-1)!;
    expect(amount).toBeDisabled();
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it('INV-MAIN-09 a discount percent above 100 is stored as 100', async () => {
    const user = userEvent.setup({ delay: null });
    const onUpdate = renderLine(soap, true);
    const percent = screen.getByText('%').closest('.MuiInputBase-root')?.querySelector('input') as HTMLInputElement;
    await user.click(percent);
    await user.type(percent, '150');
    await user.tab();
    const percents = onUpdate.mock.calls
      .map((call) => (call[1] as { discountPercent?: number }).discountPercent)
      .filter((value) => value != null);
    expect(percents.at(-1)).toBe(100);
  });

  it('INV-MAIN-10 a rupee discount above the gross clamps to the gross', () => {
    const next = applyDiscountAmountPatch(soap, true, { discountAmount: 9999 });
    expect(next.discountAmount).toBe(187.5);
    expect(next.discountPercent).toBe(100);
  });

  it('INV-MAIN-11 an inter-state line is IGST', () => {
    const tax = calculateLineTax({
      quantity: 1, unitPrice: 187.5, discountPercent: 0, gstRate: 18, intraState: false,
    });
    expect(tax.igst).toBeGreaterThan(0);
    expect(tax.cgst).toBe(0);
    expect(tax.sgst).toBe(0);
    renderLine({ ...soap, lineTotal: tax.lineTotal, igst: tax.igst, cgst: 0, sgst: 0 }, false);
    expect(screen.getByLabelText(/total amount/i)).toHaveValue(String(tax.lineTotal));
  });

  it('INV-MAIN-13 an exempt supply drops the GST rate', () => {
    const next = recomputeLine(soap, true, { supplyNature: 'EXEMPT' });
    expect(next.gstRate).toBe(0);
    expect(next.lineTotal).toBeCloseTo(187.5, 2);
  });

  it('INV-MAIN-12 a non-GST line keeps the amount equal to the taxable value', () => {
    const line = { ...soap, gstRate: 0, lineTotal: 187.5, cgst: 0, sgst: 0 };
    renderLine(line, null);
    expect(screen.getByLabelText(/total amount/i)).toHaveValue('187.5');
  });

  it('INV-MAIN-20 money fields are read-only when the line cannot be amended', () => {
    wrap(
      <DraftLineTable
        lines={[soap]}
        taxes={[undefined]}
        showCess={false}
        moneyDisabled
        onUpdate={() => undefined}
        onDelete={() => undefined}
      />,
    );
    expect(screen.getByDisplayValue('187.5')).toBeDisabled();
  });
});

describe('invoice quick settings', () => {
  beforeEach(() => {
    updateCompany.mockClear();
    companySettings.showEmptySignatureBox = false;
  });

  function openSettings(extra?: { showPurchasePrice?: boolean; onPurchase?: (next: boolean) => void }) {
    wrap(
      <InvoiceQuickSettingsDialog
        open
        onClose={() => undefined}
        showBatchCols={false}
        onShowBatchColsChange={() => undefined}
        showPurchasePrice={extra?.showPurchasePrice ?? false}
        onShowPurchasePriceChange={extra?.onPurchase ?? (() => undefined)}
      />,
    );
  }

  it('INV-SET-03 a duplicate invoice label is refused', async () => {
    const user = userEvent.setup({ delay: null });
    openSettings();
    const first = await screen.findByLabelText(/^label$/i);
    await user.type(first, 'PO Number');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    const labels = screen.getAllByLabelText(/^label$/i);
    await user.type(labels[labels.length - 1], 'PO Number');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    expect(await screen.findByText(/already used/i)).toBeInTheDocument();
    expect(updateCompany).not.toHaveBeenCalled();
  });

  it('INV-SET-07 Address is refused as a party field', async () => {
    const user = userEvent.setup({ delay: null });
    openSettings();
    await user.click(await screen.findByRole('tab', { name: /party details/i }));
    const label = screen.getByLabelText(/label/i);
    await user.type(label, 'Address');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    expect(await screen.findByText(/built-in party field/i)).toBeInTheDocument();
    expect(updateCompany).not.toHaveBeenCalled();
  });

  it('INV-SET-08 Phone is refused as a party field', async () => {
    const user = userEvent.setup({ delay: null });
    openSettings();
    await user.click(await screen.findByRole('tab', { name: /party details/i }));
    await user.type(screen.getByLabelText(/label/i), 'Phone');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    expect(await screen.findByText(/built-in party field/i)).toBeInTheDocument();
  });

  it('INV-SET-09 purchase price stays off the item table until the setting is on', async () => {
    const user = userEvent.setup({ delay: null });
    openSettings();
    await user.click(await screen.findByRole('tab', { name: /item table/i }));
    const box = screen.getByRole('checkbox', { name: /show purchase price/i });
    expect(box).not.toBeChecked();
  });

  it('INV-SET-11 batch columns can be turned on', async () => {
    const user = userEvent.setup({ delay: null });
    const onBatch = vi.fn();
    wrap(
      <InvoiceQuickSettingsDialog
        open
        onClose={() => undefined}
        showBatchCols={false}
        onShowBatchColsChange={onBatch}
        showPurchasePrice={false}
        onShowPurchasePriceChange={() => undefined}
      />,
    );
    await user.click(await screen.findByRole('tab', { name: /item table/i }));
    await user.click(screen.getByRole('checkbox', { name: /batch/i }));
    expect(onBatch).toHaveBeenCalledWith(true);
  });

  it('INV-SET-02 saving a new invoice label sends it on the company patch', async () => {
    const user = userEvent.setup({ delay: null });
    openSettings();
    await user.type(await screen.findByLabelText(/^label$/i), 'PO Number');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    expect(updateCompany).toHaveBeenCalledWith(expect.objectContaining({
      invoiceCustomFieldDefs: expect.arrayContaining([
        expect.objectContaining({ label: 'PO Number', active: true }),
      ]),
    }));
  });

  it('INV-SET-04 the trading preset adds PO Number once', async () => {
    localStorage.setItem('bizboard:invoice-industry-preset', 'manufacturing');
    const user = userEvent.setup({ delay: null });
    openSettings();
    const industry = await screen.findByLabelText(/industry/i);
    await user.click(industry);
    await user.click(await screen.findByRole('option', { name: /^trading$/i }));
    expect(screen.getAllByDisplayValue('PO Number')).toHaveLength(1);
    expect(screen.getAllByDisplayValue('E-way Bill Number')).toHaveLength(1);
    expect(screen.getAllByDisplayValue('Vehicle Number')).toHaveLength(1);
    await user.click(industry);
    await user.click(await screen.findByRole('option', { name: /^trading$/i }));
    expect(screen.getAllByDisplayValue('PO Number')).toHaveLength(1);
    expect(screen.getAllByDisplayValue('E-way Bill Number')).toHaveLength(1);
    expect(screen.getAllByDisplayValue('Vehicle Number')).toHaveLength(1);
  });

  it('INV-SET-05 an empty signature box stays checked', async () => {
    const user = userEvent.setup({ delay: null });
    openSettings();
    await screen.findByText(/INV-1/);
    const box = screen.getByRole('checkbox', { name: /signature/i });
    await user.click(box);
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(updateCompany).toHaveBeenCalledWith(
      expect.objectContaining({ showEmptySignatureBox: true }),
    ));
    cleanup();
    openSettings();
    await screen.findByText(/INV-1/);
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: /signature/i })).toBeChecked();
    });
  });

  it('INV-SET-06 Route is saved as a party field', async () => {
    const user = userEvent.setup({ delay: null });
    openSettings();
    await user.click(await screen.findByRole('tab', { name: /party details/i }));
    await user.type(screen.getByLabelText(/^label$/i), 'Route');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    expect(updateCompany).toHaveBeenCalledWith(expect.objectContaining({
      partyCustomFieldDefs: expect.arrayContaining([
        expect.objectContaining({ key: 'route', label: 'Route', active: true }),
      ]),
    }));
  });

  it('INV-SET-01 closing without save does not patch the company', async () => {
    const user = userEvent.setup({ delay: null });
    const onClose = vi.fn();
    wrap(
      <InvoiceQuickSettingsDialog
        open
        onClose={onClose}
        showBatchCols={false}
        onShowBatchColsChange={() => undefined}
        showPurchasePrice={false}
        onShowPurchasePriceChange={() => undefined}
      />,
    );
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
    expect(updateCompany).not.toHaveBeenCalled();
  });
});

describe('create party', () => {
  beforeEach(() => {
    createCustomer.mockClear();
  });

  const customer: Customer = { id: 3, name: 'Bare Store', status: 'ACTIVE' };

  function panel(props?: Partial<Parameters<typeof InvoicePartyPanel>[0]>) {
    const onError = vi.fn();
    const onCreated = vi.fn();
    wrap(
      <InvoicePartyPanel
        selectedCustomer={props?.selectedCustomer}
        editingStatus={null}
        options={props?.options ?? []}
        query=""
        onQueryChange={() => undefined}
        onSelect={() => undefined}
        loading={false}
        requirePlaceOfSupply={props?.requirePlaceOfSupply}
        onCustomerCreated={onCreated}
        onError={onError}
        manualName=""
        onManualNameChange={() => undefined}
      />,
    );
    return { onError, onCreated };
  }

  it('INV-PARTY-01 create stays disabled until the party has a name', async () => {
    const user = userEvent.setup({ delay: null });
    panel();
    await user.click(screen.getByRole('button', { name: /create party/i }));
    expect(screen.getByRole('button', { name: /^create$/i })).toBeDisabled();
  });

  it('INV-PARTY-02 a named party with phone, GSTIN, and state is selected', async () => {
    const user = userEvent.setup({ delay: null });
    const { onCreated } = panel();
    await user.click(screen.getByRole('button', { name: /create party/i }));
    await user.type(screen.getByLabelText(/^name/i), 'Anil Store');
    await user.type(screen.getByLabelText(/^phone/i), '9876543210');
    await user.type(screen.getByLabelText(/gstin/i), '29AABCU9603R1ZJ');
    await user.click(screen.getByLabelText(/^state$/i));
    await user.click(await screen.findByRole('option', { name: 'Karnataka' }));
    await user.click(screen.getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({
      id: 44,
      name: 'Anil Store',
      phone: '9876543210',
      gstin: '29AABCU9603R1ZJ',
      state: 'Karnataka',
    }));
    expect(screen.getByRole('heading', { name: /create party/i })).not.toBeVisible();
  });

  it('INV-PARTY-03 a short GSTIN keeps the dialog open and names the error', async () => {
    const user = userEvent.setup({ delay: null });
    const { onError } = panel();
    await user.click(screen.getByRole('button', { name: /create party/i }));
    await user.type(screen.getByLabelText(/^name/i), 'Anil Store');
    await user.type(screen.getByLabelText(/gstin/i), '29SHORT');
    await user.click(screen.getByRole('button', { name: /^create$/i }));
    expect(await screen.findByRole('heading', { name: /create party/i })).toBeInTheDocument();
    expect(onError).toHaveBeenCalledWith(expect.stringMatching(/gstin/i));
    expect(createCustomer).not.toHaveBeenCalled();
  });

  it('INV-PARTY-04 a party without a state warns that place of supply is missing', () => {
    panel({ selectedCustomer: customer, requirePlaceOfSupply: true });
    expect(screen.getByText(/state or GSTIN/i)).toBeInTheDocument();
  });

  it('INV-PARTY-05 cancel closes the dialog and does not select a party', async () => {
    const user = userEvent.setup({ delay: null });
    const { onCreated } = panel();
    await user.click(screen.getByRole('button', { name: /create party/i }));
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /^cancel$/i }));
    expect(screen.getByRole('heading', { name: /create party/i })).not.toBeVisible();
    expect(onCreated).not.toHaveBeenCalled();
  });
});

describe('posted invoice actions', () => {
  const invoice = {
    id: 8,
    number: 'INV-8',
    status: 'COMPLETED',
    invoiceType: 'GST',
    grandTotal: '60000',
    balance: '60000',
    items: [{ hsnCode: '3401', quantity: 1 }],
  } as SalesInvoice;

  it('INV-DET-01 e-way, e-invoice, and record payment are on a bill with a balance', () => {
    wrap(
      <InvoicePostedActionBar
        invoice={invoice}
        customerGstin="29AABCU9603R1ZJ"
        onShareWhatsApp={() => undefined}
        onShareEmail={() => undefined}
        onRecordPayment={() => undefined}
        onMessage={() => undefined}
        onError={() => undefined}
      />,
    );
    expect(screen.getByRole('button', { name: /generate e-invoice/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /generate e-way bill/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /record payment/i })).toBeInTheDocument();
  });

  it('INV-DET-02 record payment is hidden when the balance is zero', () => {
    wrap(
      <InvoicePostedActionBar
        invoice={{ ...invoice, balance: '0' }}
        customerGstin="29AABCU9603R1ZJ"
        onShareWhatsApp={() => undefined}
        onShareEmail={() => undefined}
        onRecordPayment={() => undefined}
        onMessage={() => undefined}
        onError={() => undefined}
      />,
    );
    expect(screen.queryByRole('button', { name: /record payment/i })).not.toBeInTheDocument();
  });

  it('INV-DET-04 share offers WhatsApp and copy link', async () => {
    const user = userEvent.setup({ delay: null });
    wrap(
      <InvoicePostedActionBar
        invoice={invoice}
        customerGstin="29AABCU9603R1ZJ"
        onShareWhatsApp={() => undefined}
        onShareEmail={() => undefined}
        onRecordPayment={() => undefined}
        onMessage={() => undefined}
        onError={() => undefined}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^share$/i }));
    expect(screen.getByRole('menuitem', { name: /whatsapp/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /copy link/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /revoke link/i })).toBeInTheDocument();
    expect(screen.getByText(/anyone with this link can see the customer name/i)).toBeInTheDocument();
  });

  it('INV-DET-05 copy link writes the public invoice URL', async () => {
    const user = userEvent.setup({ delay: null });
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    const onMessage = vi.fn();
    wrap(
      <InvoicePostedActionBar
        invoice={invoice}
        customerGstin="29AABCU9603R1ZJ"
        onShareWhatsApp={() => undefined}
        onShareEmail={() => undefined}
        onRecordPayment={() => undefined}
        onMessage={onMessage}
        onError={() => undefined}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^share$/i }));
    await user.click(screen.getByRole('menuitem', { name: /copy link/i }));
    expect(writeText).toHaveBeenCalledWith('https://front.test/i/public-token');
  });

  it('INV-DET-08 a non-GST bill hides e-way and e-invoice', () => {
    wrap(
      <InvoicePostedActionBar
        invoice={{ ...invoice, invoiceType: 'NON_GST' }}
        onShareWhatsApp={() => undefined}
        onShareEmail={() => undefined}
        onRecordPayment={() => undefined}
        onMessage={() => undefined}
        onError={() => undefined}
      />,
    );
    expect(screen.queryByRole('button', { name: /generate e-invoice/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /generate e-way bill/i })).not.toBeInTheDocument();
  });

  it('INV-DET-09 a service-only bill hides e-way and keeps e-invoice', () => {
    wrap(
      <InvoicePostedActionBar
        invoice={{
          ...invoice,
          items: [{ hsnCode: '998313', quantity: 1, productType: 'SERVICE' }],
        }}
        customerGstin="29AABCU9603R1ZJ"
        onShareWhatsApp={() => undefined}
        onShareEmail={() => undefined}
        onRecordPayment={() => undefined}
        onMessage={() => undefined}
        onError={() => undefined}
      />,
    );
    expect(screen.getByRole('button', { name: /generate e-invoice/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /generate e-way bill/i })).not.toBeInTheDocument();
  });
});

describe('record payment and profit', () => {
  it('INV-DET-03 an amount above the balance is refused', async () => {
    const user = userEvent.setup({ delay: null });
    wrap(
      <RecordInvoicePaymentDialog
        open
        invoice={{ id: 8, number: 'INV-8', balance: '100', grandTotal: '100' } as SalesInvoice}
        onClose={() => undefined}
        onSuccess={() => undefined}
      />,
    );
    const amount = await screen.findByLabelText(/amount received/i);
    await user.clear(amount);
    await user.type(amount, '150');
    expect(screen.getByText(/cannot be more than the balance/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /record payment|save|receive/i })).toBeDisabled();
    expect(recordInvoicePayment).not.toHaveBeenCalled();
  });

  it('INV-DET-06 profit details lists the line cost and shows a loss in red', async () => {
    getInvoiceProfitDetails.mockResolvedValue({
      salesAmount: '100',
      totalCost: '140',
      taxPayable: '18',
      profit: '-58',
      lines: [{ name: 'Soap', quantity: '2', unitName: 'PCS', unitCost: '70', lineCost: '140' }],
    });
    wrap(<ProfitDetailsDialog invoiceId={8} open onClose={() => undefined} />);
    expect(await screen.findByText('Soap')).toBeInTheDocument();
    expect(screen.getByText(/2 PCS/)).toBeInTheDocument();
    expect(screen.getByText(/70\.00/)).toBeInTheDocument();
    expect(screen.getAllByText(/gst collected/i).length).toBeGreaterThan(0);
    const loss = screen.getByText(/^profit$/i).nextElementSibling as HTMLElement;
    expect(loss).toHaveTextContent(/58\.00/);
    expect(loss).toHaveStyle({ color: 'rgb(211, 47, 47)' });
  });
});

describe('line table purchase price and batch columns', () => {
  it('INV-SET-10 and INV-SET-12 the purchase price and batch columns follow the settings', () => {
    const { rerender } = wrap(
      <DraftLineTable
        lines={[{ ...soap, purchasePrice: 40 }]}
        taxes={[undefined]}
        showCess={false}
        showItemPurchasePrice
        showBatchSlot
        onUpdate={() => undefined}
        onDelete={() => undefined}
      />,
    );
    expect(screen.getByText(/item purchase price/i)).toBeInTheDocument();
    expect(screen.getByText(/batch no/i)).toBeInTheDocument();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DraftLineTable
            lines={[soap]}
            taxes={[undefined]}
            showCess={false}
            showItemPurchasePrice={false}
            showBatchSlot={false}
            onUpdate={() => undefined}
            onDelete={() => undefined}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.queryByText(/batch/i)).not.toBeInTheDocument();
  });
});
