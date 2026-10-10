import axios from 'axios';
import { apiClient, idempotencyHeaders, shouldUseMocks, unwrapData } from '../client';
import { mockInvoices, mockQuotations } from '@/mocks/data';
import type { LineItem, Quotation, ReportResponse, SalesCreditNote, SalesDebitNote, SalesInvoice, SalesOrder, SalesReturn, DeliveryChallan, AdjustableInvoiceSummary, PdfStatus } from '@/types/domain';
import { withMocks, fetchPage, fetchAllPagesMasters, flattenQueryParams, type PageResult, type PageParams, type InvoiceNumberSeries } from './common';

export async function listSalesInvoices(params?: Record<string, string>): Promise<SalesInvoice[]> {
  return withMocks(async () => fetchAllPagesMasters<SalesInvoice>('/sales/invoices/', params), mockInvoices);
}

export async function listSalesInvoicesPage(
  params?: PageParams,
): Promise<PageResult<SalesInvoice>> {
  return withMocks(async () => fetchPage<SalesInvoice>('/sales/invoices/', params), {
    results: mockInvoices,
    count: mockInvoices.length,
    next: null,
    previous: null,
  });
}

/** Alias used by paginated invoice list UIs. */
export const listInvoicesPage = listSalesInvoicesPage;

export async function getSalesInvoice(id: number | string): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/invoices/${id}/`);
    return unwrapData<SalesInvoice>(data);
  }, mockInvoices.find((i) => String(i.id) === String(id)) ?? mockInvoices[0]);
}

export type InvoiceAuditEvent = {
  id: number;
  action: string;
  entityType?: string;
  description: string;
  metadata?: Record<string, unknown>;
  userName?: string;
  userEmail?: string;
  createdAt: string;
};

export async function getInvoiceAudit(id: number | string): Promise<InvoiceAuditEvent[]> {
  const { data } = await apiClient.get(`/sales/invoices/${id}/audit/`);
  const body = unwrapData<InvoiceAuditEvent[] | { results?: InvoiceAuditEvent[] }>(data);
  return Array.isArray(body) ? body : (body.results ?? []);
}

export async function createSalesInvoice(
  payload: {
    customer: number;
    invoiceType?: string;
    supplyType?: string;
    priceMode?: string;
    invoiceDate?: string;
    dueDate?: string | null;
    paymentTermsDays?: number;
    additionalCharges?: number | string;
    invoiceDiscount?: number | string;
    autoRoundOff?: boolean;
    notes?: string;
    termsText?: string;
    includeBankDetails?: boolean;
    includePaymentQr?: boolean;
    includeTerms?: boolean;
    signature?: number | null;
    isReverseCharge?: boolean;
    ecommerceOperatorGstin?: string;
    companyGstin?: number;
    tcsSection?: string;
    tcsRate?: number | string;
    tcsAmount?: number | string;
    warehouse?: number | null;
    items: Array<Partial<LineItem>>;
  },
  options?: { idempotencyKey?: string },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/invoices/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<SalesInvoice>(data);
  }, {
    ...mockInvoices[0],
    id: Date.now(),
    status: 'DRAFT',
    customer: payload.customer,
    items: payload.items as LineItem[],
  });
}

export interface PosCheckoutResult {
  invoice: SalesInvoice;
  receipt?: Record<string, unknown> | null;
}

export async function posCheckout(
  payload: {
    invoice: Record<string, unknown>;
    /** Cashier confirmed a walk-in sale with no place of supply (assume local). */
    confirm_blank_pos?: boolean;
    owner_pin?: string;
    expired_lot_reason?: string;
    terminal_id?: string;
    terminal_label?: string;
    apply_advance?: string;
    offline_credit?: boolean;
    pharmacy_patient?: string;
    pharmacy_prescriber?: string;
    pharmacy_registration?: string;
    pharmacy_prescription?: string;
    salesperson?: string | number;
    pharmacy_prescription_file?: number;
    offline?: boolean;
    shift_id?: number;
    outage_id?: string;
    credit_cached_at?: string;
    payment?: {
      mode?: string;
      amount?: number | string;
      tendered_amount?: number | string;
      notes?: string;
      reference?: string;
      bank_account?: number | null;
      expected_total?: number | string;
      confirm_totals_mismatch?: boolean;
      cheque_number?: string;
      cheque_bank_name?: string;
      cheque_date?: string;
      cheque_image?: number;
    };
  },
  options?: { idempotencyKey?: string },
): Promise<PosCheckoutResult> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/invoices/pos-checkout/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<PosCheckoutResult>(data);
  }, {
    invoice: {
      ...mockInvoices[0],
      id: Date.now(),
      status: 'COMPLETED',
    },
    receipt: null,
  });
}

export async function updateSalesInvoice(
  id: number,
  payload: {
    customer?: number;
    items?: Array<Partial<LineItem>>;
    notes?: string;
    invoiceType?: string;
    supplyType?: string;
    invoiceDate?: string;
    dueDate?: string | null;
    paymentTermsDays?: number;
    additionalCharges?: number | string;
    invoiceDiscount?: number | string;
    autoRoundOff?: boolean;
    termsText?: string;
    includeBankDetails?: boolean;
    includePaymentQr?: boolean;
    includeTerms?: boolean;
    signature?: number | null;
    /** H9-A: required for Owner amend of completed invoice money fields */
    confirmAmend?: boolean;
    /** CFT-120: OCC token from GET amendRevision */
    expectedAmendRevision?: number;
    priceMode?: string;
    vehicleNumber?: string;
    transporterName?: string;
    transporterId?: string;
    transportDistanceKm?: number | string | null;
    isReverseCharge?: boolean;
    ecommerceOperatorGstin?: string;
    companyGstin?: number;
    tcsSection?: string;
    tcsRate?: number | string;
    tcsAmount?: number | string;
  },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/sales/invoices/${id}/`, payload);
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, ...payload } as SalesInvoice);
}

export type PreviewTotals = {
  subtotal: number;
  discountTotal: number;
  taxableTotal: number;
  cgstTotal: number;
  sgstTotal: number;
  igstTotal: number;
  cessTotal: number;
  rcmTaxable?: number;
  rcmCgst?: number;
  rcmSgst?: number;
  rcmIgst?: number;
  rcmCess?: number;
  roundOff: number;
  grandTotal: number;
  taxTotal: number;
  tcsAmount?: number;
  tdsAmount?: number;
  amountDue?: number;
  intraState?: boolean | null;
  invoiceDiscountMode?: string;
  /** Sales-only, read-only estimate (current avg. cost, not FIFO) for the draft
   * editor's negotiation-room indicator. Undefined (not 0) when the backend
   * omitted it -- e.g. the viewer lacks financial-reports permission. */
  estimatedCogs?: number;
  estimatedMargin?: number;
  estimatedMarginPercent?: number;
  marginEstimatePartial?: boolean;
  marginLines?: Array<{
    productId: number;
    name: string;
    unitCost: number | null;
    quantity: number;
    lineCost: number | null;
    missing: boolean;
  }>;
  items?: Array<{
    taxableAmount: number;
    cgst: number;
    sgst: number;
    igst: number;
    cess: number;
    lineTotal: number;
    gstRate?: number;
    rateOverrideReason?: string;
  }>;
};

export function mapPreviewTotals(raw: Record<string, unknown>): PreviewTotals {
  const n = (...keys: string[]) => {
    for (const k of keys) {
      const v = raw[k];
      if (v != null && v !== '') return Number(v);
    }
    return 0;
  };
  const cgst = n('cgstTotal', 'cgst_total');
  const sgst = n('sgstTotal', 'sgst_total');
  const igst = n('igstTotal', 'igst_total');
  const cess = n('cessTotal', 'cess_total');
  const intra = raw.intraState ?? raw.intra_state;
  return {
    subtotal: n('subtotal'),
    discountTotal: n('discountTotal', 'discount_total'),
    taxableTotal: n('taxableTotal', 'taxable_total'),
    cgstTotal: cgst,
    sgstTotal: sgst,
    igstTotal: igst,
    cessTotal: cess,
    taxTotal: Math.round((cgst + sgst + igst + cess) * 100) / 100,
    rcmTaxable: n('rcmTaxable', 'rcm_taxable'),
    rcmCgst: n('rcmCgst', 'rcm_cgst'),
    rcmSgst: n('rcmSgst', 'rcm_sgst'),
    rcmIgst: n('rcmIgst', 'rcm_igst'),
    rcmCess: n('rcmCess', 'rcm_cess'),
    roundOff: n('roundOff', 'round_off'),
    grandTotal: n('grandTotal', 'grand_total'),
    tcsAmount: n('tcsAmount', 'tcs_amount'),
    tdsAmount: n('tdsAmount', 'tds_amount'),
    amountDue: n('amountDue', 'amount_due'),
    intraState: intra === true ? true : intra === false ? false : null,
    invoiceDiscountMode: String(raw.invoiceDiscountMode ?? raw.invoice_discount_mode ?? 'AFTER_TAX'),
    ...mapMarginEstimate(raw),
    items: mapPreviewItems(raw),
  };
}

function mapPreviewItems(raw: Record<string, unknown>): PreviewTotals['items'] {
  const rows = raw.items;
  if (!Array.isArray(rows)) return undefined;
  return rows.map((row) => {
    const r = (row ?? {}) as Record<string, unknown>;
    const n = (a: string, b: string) => Number(r[a] ?? r[b] ?? 0);
    return {
      taxableAmount: n('taxableAmount', 'taxable_amount'),
      cgst: n('cgst', 'cgst'),
      sgst: n('sgst', 'sgst'),
      igst: n('igst', 'igst'),
      cess: n('cess', 'cess'),
      lineTotal: n('lineTotal', 'line_total'),
      gstRate: n('gstRate', 'gst_rate'),
      rateOverrideReason: String(r.rateOverrideReason ?? r.rate_override_reason ?? ''),
    };
  });
}

/** Split out so a missing key stays `undefined` (no data) rather than the
 * `n()` helper's 0-default, which would look like "zero margin" in the UI. */
function mapMarginEstimate(raw: Record<string, unknown>): Pick<
  PreviewTotals,
  'estimatedCogs' | 'estimatedMargin' | 'estimatedMarginPercent' | 'marginEstimatePartial' | 'marginLines'
> {
  const cogs = raw.estimatedCogs ?? raw.estimated_cogs;
  const margin = raw.estimatedMargin ?? raw.estimated_margin;
  const marginPercent = raw.estimatedMarginPercent ?? raw.estimated_margin_percent;
  const rawLines = raw.marginLines ?? raw.margin_lines;
  const marginLines = Array.isArray(rawLines)
    ? rawLines.map((row) => {
        const line = row && typeof row === 'object' ? (row as Record<string, unknown>) : {};
        const unit = line.unitCost ?? line.unit_cost;
        const lineCost = line.lineCost ?? line.line_cost;
        return {
          productId: Number(line.productId ?? line.product_id ?? 0),
          name: String(line.name ?? ''),
          unitCost: unit == null || unit === '' ? null : Number(unit),
          quantity: Number(line.quantity ?? 0),
          lineCost: lineCost == null || lineCost === '' ? null : Number(lineCost),
          missing: Boolean(line.missing) || unit == null || unit === '',
        };
      })
    : undefined;
  if (margin == null && cogs == null && !marginLines?.length) return {};
  return {
    estimatedCogs: cogs != null ? Number(cogs) : undefined,
    estimatedMargin: margin != null ? Number(margin) : undefined,
    estimatedMarginPercent: marginPercent != null ? Number(marginPercent) : undefined,
    marginEstimatePartial: Boolean(raw.marginEstimatePartial ?? raw.margin_estimate_partial ?? false),
    marginLines,
  };
}

/** Client-side totals used when mocks are on (POS tender + editor preview). */
export function clientPreviewTotals(payload: Record<string, unknown>): PreviewTotals {
  const items = (Array.isArray(payload.items) ? payload.items : []) as Record<string, unknown>[];
  let subtotal = 0;
  let taxTotal = 0;
  for (const item of items) {
    const qty = Number(item.quantity ?? 0) || 0;
    const price = Number(item.unit_price ?? item.unitPrice ?? 0) || 0;
    const gst = Number(item.gst_rate ?? item.gstRate ?? 0) || 0;
    const line = qty * price;
    subtotal += line;
    taxTotal += (line * gst) / 100;
  }
  subtotal = Math.round(subtotal * 100) / 100;
  taxTotal = Math.round(taxTotal * 100) / 100;
  const half = Math.round((taxTotal / 2) * 100) / 100;
  return {
    subtotal,
    discountTotal: 0,
    taxableTotal: subtotal,
    cgstTotal: half,
    sgstTotal: half,
    igstTotal: 0,
    cessTotal: 0,
    taxTotal,
    roundOff: 0,
    grandTotal: Math.round((subtotal + taxTotal) * 100) / 100,
    invoiceDiscountMode: 'AFTER_TAX',
    intraState: true,
  };
}

export async function previewSalesTotals(payload: Record<string, unknown>): Promise<PreviewTotals> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/invoices/preview-totals/', payload);
    return mapPreviewTotals(unwrapData<Record<string, unknown>>(data));
  }, () => clientPreviewTotals(payload));
}

export async function completeSalesInvoice(
  id: number,
  options?: {
    confirmSalesRcm?: boolean;
    confirmBlankPos?: boolean;
    confirmGstinTotalChange?: boolean;
    gstGuardOverrideReason?: string;
    /** Owner only: why this bill is priced under purchase cost. */
    belowCostOverrideReason?: string;
    /** Collected on this save. The server posts the receipt in the same transaction. */
    amountReceived?: number;
    paymentMode?: string;
    chequeNumber?: string;
    chequeBankName?: string;
    chequeDate?: string;
    chequeImage?: number | null;
    idempotencyKey?: string;
  },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(
      `/sales/invoices/${id}/complete/`,
      {
        confirmSalesRcm: Boolean(options?.confirmSalesRcm),
        confirmBlankPos: Boolean(options?.confirmBlankPos),
        confirmGstinTotalChange: Boolean(options?.confirmGstinTotalChange),
        ...(options?.gstGuardOverrideReason
          ? { gstGuardOverrideReason: options.gstGuardOverrideReason }
          : {}),
        ...(options?.belowCostOverrideReason
          ? { belowCostOverrideReason: options.belowCostOverrideReason }
          : {}),
        ...(options?.amountReceived && options.amountReceived > 0
          ? {
              amountReceived: options.amountReceived,
              paymentMode: options.paymentMode || 'CASH',
              ...(options.chequeNumber ? { chequeNumber: options.chequeNumber } : {}),
              ...(options.chequeBankName ? { chequeBankName: options.chequeBankName } : {}),
              ...(options.chequeDate ? { chequeDate: options.chequeDate } : {}),
              ...(options.chequeImage ? { chequeImage: options.chequeImage } : {}),
            }
          : {}),
      },
      { headers: idempotencyHeaders(options?.idempotencyKey) },
    );
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, status: 'COMPLETED', number: `INV-${id}`, pdfStatus: 'QUEUED' });
}

export async function repeatLastInvoice(customerId: number): Promise<SalesInvoice> {
  const { data } = await apiClient.post('/sales/invoices/repeat-last/', { customer: customerId });
  return unwrapData<SalesInvoice>(data);
}

export type EinvoiceEwayPrepareResult = SalesInvoice & { payload?: Record<string, unknown> };

export async function prepareInvoiceEinvoice(id: number): Promise<EinvoiceEwayPrepareResult> {
  const { data } = await apiClient.post(`/sales/invoices/${id}/prepare-einvoice/`);
  return unwrapData<EinvoiceEwayPrepareResult>(data);
}

export async function markInvoiceEinvoiceGenerated(
  id: number,
  payload: { irn: string; ackNo: string; ackDate?: string; einvoiceQr?: string; reason: string },
): Promise<SalesInvoice> {
  const { data } = await apiClient.post(`/sales/invoices/${id}/mark-einvoice-generated/`, payload);
  return unwrapData<SalesInvoice>(data);
}

export async function prepareInvoiceEway(
  id: number,
  payload?: {
    challanId?: number;
    vehicleNumber?: string;
    transporterName?: string;
    transporterId?: string;
    transportDistanceKm?: string;
  },
): Promise<EinvoiceEwayPrepareResult> {
  const { data } = await apiClient.post(`/sales/invoices/${id}/prepare-eway/`, payload ?? {});
  return unwrapData<EinvoiceEwayPrepareResult>(data);
}

export async function markInvoiceEwayGenerated(
  id: number,
  payload: { ewayBillNo: string; ewayValidUpto?: string; reason: string },
): Promise<SalesInvoice> {
  const { data } = await apiClient.post(`/sales/invoices/${id}/mark-eway-generated/`, payload);
  return unwrapData<SalesInvoice>(data);
}

export async function cancelInvoiceEinvoice(
  id: number,
  payload?: { cnlRsn: string; cnlRem: string },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/cancel-einvoice/`, {
      cnlRsn: payload?.cnlRsn,
      cnlRem: payload?.cnlRem,
    });
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, einvoiceStatus: 'CANCELLED', irn: undefined, ackNo: undefined });
}

export async function cancelInvoiceEway(
  id: number,
  payload?: { cnlRsn: string; cnlRem: string },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/cancel-eway/`, {
      cnl_rsn: payload?.cnlRsn,
      cnl_rem: payload?.cnlRem,
    });
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, ewayStatus: 'CANCELLED', ewayBillNo: undefined });
}

export async function getSalesInvoiceNumberSeries(): Promise<InvoiceNumberSeries> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/sales/invoices/number-series/');
    return unwrapData<InvoiceNumberSeries>(data);
  }, {
    docType: 'SALES_INVOICE',
    prefix: 'INV',
    nextNumber: 1,
    padding: 5,
    preview: 'INV-00001',
  });
}

export async function updateSalesInvoiceNumberSeries(payload: {
  prefix?: string;
  nextNumber?: number;
  padding?: number;
}): Promise<InvoiceNumberSeries> {
  return withMocks(async () => {
    const { data } = await apiClient.patch('/sales/invoices/number-series/', payload);
    return unwrapData<InvoiceNumberSeries>(data);
  }, {
    docType: 'SALES_INVOICE',
    prefix: payload.prefix ?? 'INV',
    nextNumber: payload.nextNumber ?? 1,
    padding: payload.padding ?? 5,
    preview: `${payload.prefix ?? 'INV'}-${String(payload.nextNumber ?? 1).padStart(payload.padding ?? 5, '0')}`,
  });
}

export async function uploadFile(file: File, kind = 'ATTACHMENT'): Promise<{ id: number; url?: string }> {
  return withMocks(async () => {
    const form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    // Let the browser set multipart boundary — do not force Content-Type.
    const { data } = await apiClient.post('/files/', form, {
      headers: { 'Content-Type': undefined as unknown as string },
    });
    return unwrapData<{ id: number; url?: string }>(data);
  }, { id: Date.now(), url: URL.createObjectURL(file) });
}

export type CancelInvoiceResult =
  | { outcome: 'cancelled'; invoice: SalesInvoice }
  | { outcome: 'pending'; invoiceId: number; approvalId: number };

export async function cancelSalesInvoice(
  id: number,
  options?: { reason?: string },
): Promise<CancelInvoiceResult> {
  return withMocks(async () => {
    const response = await apiClient.post(`/sales/invoices/${id}/cancel/`, {
      cancelReason: options?.reason ?? '',
    });
    const body = unwrapData<Record<string, unknown>>(response.data);
    if (response.status === 202) {
      const approvalId = body.approvalId ?? body.approval_id;
      if (body.status !== 'PENDING' || approvalId == null) {
        throw new Error('Cancel returned 202 without a pending approval.');
      }
      return { outcome: 'pending', invoiceId: id, approvalId: Number(approvalId) };
    }
    if (response.status === 200) {
      const invoice = body as unknown as SalesInvoice;
      if (invoice?.id == null) throw new Error('Cancel returned 200 without an invoice.');
      return { outcome: 'cancelled', invoice };
    }
    throw new Error(`Unexpected cancel status ${response.status}`);
  }, { outcome: 'cancelled', invoice: { ...mockInvoices[0], id, status: 'CANCELLED' } });
}

export async function deleteSalesInvoice(id: number): Promise<void> {
  return withMocks(async () => {
    await apiClient.delete(`/sales/invoices/${id}/`);
  }, undefined);
}

export async function getInvoicePdfStatus(
  id: number | string,
): Promise<{ pdfStatus: SalesInvoice['pdfStatus']; pdfFile?: number | null; pdfUrl?: string }> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/invoices/${id}/pdf-status/`);
    const body = unwrapData<{ pdfStatus: SalesInvoice['pdfStatus']; pdfFile?: number | null }>(data);
    return {
      ...body,
      pdfUrl: body.pdfFile ? `/api/v1/sales/invoices/${id}/pdf/` : undefined,
    };
  }, { pdfStatus: 'READY', pdfFile: 1, pdfUrl: `#pdf-${id}` });
}

export async function regenerateInvoicePdf(
  id: number | string,
): Promise<{ pdfStatus: SalesInvoice['pdfStatus']; pdfFile?: number | null }> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/regenerate-pdf/`);
    return unwrapData(data);
  }, { pdfStatus: 'QUEUED', pdfFile: null });
}

export async function downloadInvoicePreviewPdf(payload: Record<string, unknown>): Promise<Blob> {
  const { data } = await apiClient.post('/sales/invoices/preview-pdf/', payload, {
    responseType: 'blob',
  });
  return data as Blob;
}

export async function downloadInvoicePdf(
  id: number | string,
  options?: { copy?: 'ORIGINAL' | 'DUPLICATE' | 'TRIPLICATE' },
): Promise<Blob> {
  if (shouldUseMocks()) {
    return new Blob(['mock-pdf'], { type: 'application/pdf' });
  }
  const copy = options?.copy ?? 'ORIGINAL';
  try {
    const { data } = await apiClient.get(`/sales/invoices/${id}/pdf/`, {
      responseType: 'blob',
      params: { copy },
    });
    return data as Blob;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.data instanceof Blob) {
      const text = await err.response.data.text();
      try {
        const json = JSON.parse(text) as { detail?: string; error?: { message?: string } };
        throw new Error(json.detail || json.error?.message || 'PDF is generating, retry shortly');
      } catch (e) {
        if (e instanceof Error && e.message !== 'Unexpected end of JSON input') throw e;
        throw new Error('PDF is generating, retry shortly');
      }
    }
    throw err;
  }
}

export type SalesPdfDocType = 'invoice' | 'credit-note' | 'debit-note' | 'delivery-challan' | 'quotation';

const SALES_PDF_BASE: Record<Exclude<SalesPdfDocType, 'invoice'>, string> = {
  'credit-note': '/sales/credit-notes',
  'debit-note': '/sales/debit-notes',
  'delivery-challan': '/sales/delivery-challans',
  quotation: '/sales/quotations',
};

async function downloadSalesDocPdfBlob(path: string): Promise<Blob> {
  if (shouldUseMocks()) {
    return new Blob(['mock-pdf'], { type: 'application/pdf' });
  }
  try {
    const { data } = await apiClient.get(path, { responseType: 'blob' });
    return data as Blob;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.data instanceof Blob) {
      const text = await err.response.data.text();
      try {
        const json = JSON.parse(text) as { detail?: string; error?: { message?: string } };
        throw new Error(json.detail || json.error?.message || 'PDF is generating, retry shortly');
      } catch (e) {
        if (e instanceof Error && e.message !== 'Unexpected end of JSON input') throw e;
        throw new Error('PDF is generating, retry shortly');
      }
    }
    throw err;
  }
}

export async function getSalesDocumentPdfStatus(
  docType: SalesPdfDocType,
  id: number | string,
): Promise<{ pdfStatus: PdfStatus; pdfFile?: number | null; pdfUrl?: string }> {
  if (docType === 'invoice') {
    const status = await getInvoicePdfStatus(id);
    return {
      ...status,
      pdfStatus: (status.pdfStatus ?? 'NONE') as PdfStatus,
    };
  }
  const base = SALES_PDF_BASE[docType];
  return withMocks(async () => {
    const { data } = await apiClient.get(`${base}/${id}/pdf-status/`);
    const body = unwrapData<{ pdfStatus?: PdfStatus; pdfFile?: number | null }>(data);
    return {
      ...body,
      pdfStatus: (body.pdfStatus ?? 'NONE') as PdfStatus,
      pdfUrl: body.pdfFile ? `/api/v1${base}/${id}/pdf/` : undefined,
    };
  }, { pdfStatus: 'READY' as PdfStatus, pdfFile: 1, pdfUrl: `#pdf-${docType}-${id}` });
}

export async function regenerateSalesDocumentPdf(
  docType: SalesPdfDocType,
  id: number | string,
): Promise<{ pdfStatus: PdfStatus; pdfFile?: number | null }> {
  if (docType === 'invoice') {
    const status = await regenerateInvoicePdf(id);
    return {
      ...status,
      pdfStatus: (status.pdfStatus ?? 'QUEUED') as PdfStatus,
    };
  }
  const base = SALES_PDF_BASE[docType];
  return withMocks(async () => {
    const { data } = await apiClient.post(`${base}/${id}/regenerate-pdf/`);
    const body = unwrapData<{ pdfStatus?: PdfStatus; pdfFile?: number | null }>(data);
    return {
      ...body,
      pdfStatus: (body.pdfStatus ?? 'QUEUED') as PdfStatus,
    };
  }, { pdfStatus: 'QUEUED' as PdfStatus, pdfFile: null });
}

export async function downloadSalesDocumentPdf(
  docType: SalesPdfDocType,
  id: number | string,
  options?: { copy?: 'ORIGINAL' | 'DUPLICATE' | 'TRIPLICATE' },
): Promise<Blob> {
  if (docType === 'invoice') return downloadInvoicePdf(id, options);
  const base = SALES_PDF_BASE[docType];
  return downloadSalesDocPdfBlob(`${base}/${id}/pdf/`);
}

export async function downloadInvoiceThermalPdf(
  id: number | string,
  width: 80 | 58 = 80,
): Promise<Blob> {
  if (shouldUseMocks()) {
    return new Blob(['mock-thermal-pdf'], { type: 'application/pdf' });
  }
  const { data } = await apiClient.get(`/sales/invoices/${id}/thermal-pdf/`, {
    responseType: 'blob',
    params: { width },
  });
  return data as Blob;
}

export type InvoiceShareResult = {
  status: string;
  shareLink?: string;
  mode?: 'cloud' | 'link' | 'device';
  error?: string;
  whatsappSendStatus?: string;
  text?: string;
  documentUrl?: string;
};

export async function shareInvoice(
  id: number,
  payload: {
    channel: 'EMAIL' | 'WHATSAPP';
    recipient: string;
    message?: string;
    /** Cloud send from the company number. The default device share omits this. */
    sendFromBusinessNumber?: boolean;
  },
): Promise<InvoiceShareResult> {
  const device =
    payload.channel === 'WHATSAPP' && !payload.recipient && !payload.sendFromBusinessNumber;
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/share/`, payload);
    return unwrapData<InvoiceShareResult>(data);
  }, device
    ? { status: 'OPENED', mode: 'device' as const, text: 'Invoice', documentUrl: '' }
    : {
        status: 'LINK_READY',
        shareLink: payload.recipient
          ? `https://wa.me/${payload.recipient}`
          : 'https://wa.me/?text=Invoice',
        mode: 'link' as const,
      });
}

export async function createInvoicePublicLink(id: number): Promise<{ url: string }> {
  const { data } = await apiClient.post(`/sales/invoices/${id}/public-link/`);
  const body = unwrapData<{ url?: string }>(data);
  return { url: String(body?.url ?? '') };
}

export async function revokeInvoicePublicLink(id: number): Promise<void> {
  await apiClient.post(`/sales/invoices/${id}/public-link/revoke/`);
}

const publicApiBase =
  (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || '/api/v1').replace(/\/$/, '');

/** Anonymous read. No Authorization header and no session cookie. */
export async function getPublicInvoice(token: string): Promise<Record<string, unknown>> {
  const { data } = await axios.get(
    `${publicApiBase}/public/invoices/${encodeURIComponent(token)}/`,
    { headers: { Accept: 'application/json' } },
  );
  return unwrapData<Record<string, unknown>>(data);
}

export async function payPublicInvoice(token: string): Promise<{ path: string }> {
  const { data } = await axios.post(
    `${publicApiBase}/public/invoices/${encodeURIComponent(token)}/pay/`,
    {},
    { headers: { Accept: 'application/json' } },
  );
  const body = unwrapData<{ path?: string }>(data);
  return { path: String(body?.path ?? '') };
}

export async function downloadPublicInvoicePdf(token: string): Promise<Blob> {
  const { data } = await axios.get(
    `${publicApiBase}/public/invoices/${encodeURIComponent(token)}/pdf/`,
    { responseType: 'blob', headers: { Accept: 'application/pdf' } },
  );
  return data as Blob;
}

export type ProfitDetailsLine = {
  name: string;
  quantity: string | number;
  unitName: string;
  unitCost: string | number | null;
  lineCost: string | number | null;
  fellBackToPurchasePrice: boolean;
  /** Draft estimate had no stock cost for this line. */
  costMissing: boolean;
};

export type ProfitDetails = {
  lines: ProfitDetailsLine[];
  salesAmount: string | number;
  totalCost: string | number;
  taxPayable: string | number;
  profit: string | number;
  estimated: boolean;
  /** At least one stocked line has no cost, so profit is overstated. */
  costIncomplete: boolean;
  formula: string;
};

function profitField(row: Record<string, unknown>, camel: string, snake: string): unknown {
  return row[camel] ?? row[snake];
}

export async function getInvoiceProfitDetails(id: number): Promise<ProfitDetails> {
  const { data } = await apiClient.get(`/sales/invoices/${id}/profit-details/`);
  const body = unwrapData<Record<string, unknown>>(data) ?? {};
  const rawLines = (body.lines ?? []) as Array<Record<string, unknown>>;
  return {
    lines: rawLines.map((row) => ({
      name: String(row.name ?? ''),
      quantity: (row.quantity ?? '') as string | number,
      unitName: String(profitField(row, 'unitName', 'unit_name') ?? ''),
      unitCost: (profitField(row, 'unitCost', 'unit_cost') ?? null) as string | number | null,
      lineCost: (profitField(row, 'lineCost', 'line_cost') ?? null) as string | number | null,
      fellBackToPurchasePrice: Boolean(
        profitField(row, 'fellBackToPurchasePrice', 'fell_back_to_purchase_price'),
      ),
      costMissing: Boolean(profitField(row, 'costMissing', 'cost_missing')),
    })),
    salesAmount: (profitField(body, 'salesAmount', 'sales_amount') ?? 0) as string | number,
    totalCost: (profitField(body, 'totalCost', 'total_cost') ?? 0) as string | number,
    taxPayable: (profitField(body, 'taxPayable', 'tax_payable') ?? 0) as string | number,
    profit: (body.profit ?? 0) as string | number,
    estimated: Boolean(body.estimated),
    costIncomplete: Boolean(profitField(body, 'costIncomplete', 'cost_incomplete')),
    formula: String(body.formula ?? ''),
  };
}

export async function listQuotations(params?: Record<string, string>): Promise<Quotation[]> {
  return withMocks(async () => fetchAllPagesMasters<Quotation>('/sales/quotations/', params), mockQuotations);
}

export async function listQuotationsPage(params?: PageParams): Promise<PageResult<Quotation>> {
  return withMocks(async () => fetchPage<Quotation>('/sales/quotations/', params), {
    results: mockQuotations,
    count: mockQuotations.length,
    next: null,
    previous: null,
  });
}

export async function getQuotation(id: number): Promise<Quotation> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/quotations/${id}/`);
    return unwrapData<Quotation>(data);
  }, mockQuotations.find((q) => q.id === id) ?? mockQuotations[0]);
}

export async function updateQuotation(id: number, payload: Record<string, unknown>): Promise<Quotation> {
  const { data } = await apiClient.patch(`/sales/quotations/${id}/`, payload);
  return unwrapData<Quotation>(data);
}

export async function cancelQuotation(id: number, reason?: string): Promise<Quotation> {
  const { data } = await apiClient.post(`/sales/quotations/${id}/cancel/`, reason ? { reason } : {});
  return unwrapData<Quotation>(data);
}

export type QuotationLifecycleAction = 'mark-sent' | 'mark-accepted' | 'mark-rejected' | 'reopen-for-changes';

export async function quotationLifecycle(
  id: number,
  action: QuotationLifecycleAction,
  reason?: string,
): Promise<Quotation> {
  const { data } = await apiClient.post(`/sales/quotations/${id}/${action}/`, reason ? { reason } : {});
  return unwrapData<Quotation>(data);
}

export async function closeQuotationRemaining(id: number, reason: string): Promise<Quotation> {
  const { data } = await apiClient.post(`/sales/quotations/${id}/close-remaining/`, { reason });
  return unwrapData<Quotation>(data);
}

export async function reopenClosedQuotation(id: number, reason: string): Promise<Quotation> {
  const { data } = await apiClient.post(`/sales/quotations/${id}/reopen-closed/`, { reason });
  return unwrapData<Quotation>(data);
}

export async function cancelExpiredQuotations(): Promise<{
  cancelled: number;
  needsCloseRemaining: Array<{ id: number; number: string }>;
}> {
  const { data } = await apiClient.post('/sales/quotations/cancel-expired/', {});
  return unwrapData(data);
}

export async function duplicateQuotation(id: number): Promise<Quotation> {
  const { data } = await apiClient.post(`/sales/quotations/${id}/duplicate/`, {}, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<Quotation>(data);
}

export async function shareQuotation(
  id: number,
  channel: 'link' | 'whatsapp' | 'download' = 'link',
): Promise<{ url: string; expiresAt?: string | null; status: string; sentAt?: string | null }> {
  const { data } = await apiClient.post(`/sales/quotations/${id}/share/`, { channel });
  return unwrapData(data);
}

export async function revokeQuotationLink(id: number): Promise<{ revoked: boolean }> {
  const { data } = await apiClient.post(`/sales/quotations/${id}/public-link/revoke/`, {});
  return unwrapData(data);
}

export type Salesperson = { id: number; name: string; code: string };

/** Active employees a sales user may pick. The payroll list is owner-only. */
export async function searchSalespeople(q = ''): Promise<Salesperson[]> {
  const { data } = await apiClient.get('/sales/salespeople/', { params: q ? { q } : {} });
  const body = unwrapData<{ results?: Salesperson[] } | Salesperson[]>(data);
  return Array.isArray(body) ? body : (body.results ?? []);
}

/** Anonymous read of a shared quotation. */
export async function getPublicQuotation(token: string): Promise<Record<string, unknown>> {
  const { data } = await axios.get(
    `${publicApiBase}/public/quotations/${encodeURIComponent(token)}/`,
    { headers: { Accept: 'application/json' } },
  );
  return unwrapData<Record<string, unknown>>(data);
}

export async function downloadPublicQuotationPdf(token: string): Promise<Blob> {
  const { data } = await axios.get(
    `${publicApiBase}/public/quotations/${encodeURIComponent(token)}/pdf/`,
    { responseType: 'blob', headers: { Accept: 'application/pdf' } },
  );
  return data as Blob;
}

export async function createQuotation(
  payload: Record<string, unknown> & { items?: Array<Partial<LineItem>> },
  idempotencyKey?: string,
): Promise<Quotation> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/quotations/', payload, {
      headers: idempotencyHeaders(idempotencyKey),
    });
    return unwrapData<Quotation>(data);
  }, { ...mockQuotations[0], id: Date.now(), status: 'DRAFT', items: (payload.items ?? []) as LineItem[] });
}

export async function convertQuotation(
  id: number,
  opts?: { confirmExpired?: boolean; items?: Array<{ id: number; quantity: string | number }>; idempotencyKey?: string },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/quotations/${id}/convert/`, {
      confirm_expired: opts?.confirmExpired ?? false,
      ...(opts?.items?.length ? { items: opts.items } : {}),
    }, { headers: idempotencyHeaders(opts?.idempotencyKey) });
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id: Date.now(), status: 'DRAFT' });
}

export async function convertQuotationToOrder(
  id: number,
  opts?: { confirmExpired?: boolean; items?: Array<{ id: number; quantity: string | number }>; idempotencyKey?: string },
): Promise<SalesOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/quotations/${id}/convert-to-order/`, {
      confirm_expired: opts?.confirmExpired ?? false,
      ...(opts?.items?.length ? { items: opts.items } : {}),
    }, { headers: idempotencyHeaders(opts?.idempotencyKey) });
    return unwrapData<SalesOrder>(data);
  }, { id: Date.now(), status: 'DRAFT' } as unknown as SalesOrder);
}

export async function listSalesReturns(params?: Record<string, string>): Promise<SalesReturn[]> {
  return withMocks(async () => fetchAllPagesMasters<SalesReturn>('/sales/returns/', params), []);
}

export async function listSalesReturnsPage(params?: PageParams): Promise<PageResult<SalesReturn>> {
  return withMocks(async () => fetchPage<SalesReturn>('/sales/returns/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function createSalesReturn(payload: {
  customer: number;
  salesInvoice: number;
  returnDate?: string;
  reason?: string;
  items: Array<Partial<LineItem>>;
}, options?: { idempotencyKey?: string }): Promise<SalesReturn> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/returns/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<SalesReturn>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    customer: payload.customer,
    salesInvoice: payload.salesInvoice,
    returnDate: payload.returnDate ?? new Date().toISOString().slice(0, 10),
    items: payload.items as LineItem[],
    subtotal: 0,
    discountTotal: 0,
    taxableTotal: 0,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    roundOff: 0,
    grandTotal: 0,
  });
}

export async function updateSalesReturn(
  id: number,
  payload: {
    reason?: string;
    items?: Array<Partial<LineItem>>;
  },
): Promise<SalesReturn> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/sales/returns/${id}/`, payload);
    return unwrapData<SalesReturn>(data);
  }, {
    id,
    status: 'DRAFT',
    customer: 0,
    salesInvoice: 0,
    returnDate: '',
    items: (payload.items ?? []) as LineItem[],
    subtotal: 0,
    discountTotal: 0,
    taxableTotal: 0,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    roundOff: 0,
    grandTotal: 0,
  });
}

export async function completeSalesReturn(id: number, options?: { idempotencyKey?: string }): Promise<SalesReturn> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/returns/${id}/complete/`, undefined, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<SalesReturn>(data);
  }, {
    id,
    status: 'COMPLETED',
    customer: 0,
    salesInvoice: 0,
    returnDate: '',
    items: [],
    subtotal: 0,
    discountTotal: 0,
    taxableTotal: 0,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    roundOff: 0,
    grandTotal: 0,
  });
}

export async function getSalesRegister(params?: {
  dateFrom?: string;
  dateTo?: string;
}): Promise<ReportResponse> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/sales-register/', {
      params: { date_from: params?.dateFrom, date_to: params?.dateTo },
    });
    return unwrapData<ReportResponse>(data);
  }, { rows: [], totals: {} });
}

export async function prepareCreditNoteEinvoice(id: number): Promise<EinvoiceEwayPrepareResult> {
  const { data } = await apiClient.post(`/sales/credit-notes/${id}/prepare-einvoice/`);
  return unwrapData<EinvoiceEwayPrepareResult>(data);
}

export async function submitCreditNoteEinvoice(id: number): Promise<SalesCreditNote> {
  const { data } = await apiClient.post(`/sales/credit-notes/${id}/submit-einvoice/`);
  return unwrapData<SalesCreditNote>(data);
}

export async function cancelCreditNoteEinvoice(id: number): Promise<SalesCreditNote> {
  const { data } = await apiClient.post(`/sales/credit-notes/${id}/cancel-einvoice/`);
  return unwrapData<SalesCreditNote>(data);
}

export async function prepareDebitNoteEinvoice(id: number): Promise<EinvoiceEwayPrepareResult> {
  const { data } = await apiClient.post(`/sales/debit-notes/${id}/prepare-einvoice/`);
  return unwrapData<EinvoiceEwayPrepareResult>(data);
}

export async function submitDebitNoteEinvoice(id: number): Promise<SalesDebitNote> {
  const { data } = await apiClient.post(`/sales/debit-notes/${id}/submit-einvoice/`);
  return unwrapData<SalesDebitNote>(data);
}

export async function cancelDebitNoteEinvoice(id: number): Promise<SalesDebitNote> {
  const { data } = await apiClient.post(`/sales/debit-notes/${id}/cancel-einvoice/`);
  return unwrapData<SalesDebitNote>(data);
}

export async function submitInvoiceEinvoice(id: number) {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/submit-einvoice/`);
    return unwrapData(data);
  }, { ...mockInvoices[0], id, einvoiceStatus: 'GENERATED', irn: 'MOCK-IRN-001', ackNo: 'MOCK-ACK-001' });
}

export async function postPlanEwayStub(body: {
  action: 'PART_B' | 'EXTEND' | 'SPLIT' | 'TRANSFER_PART_B';
  documentId: number | string;
  documentType?: string;
  billStatus?: string;
  payload?: Record<string, unknown>;
}) {
  const { data } = await apiClient.post('/plan/eway/', {
    action: body.action,
    document_id: String(body.documentId),
    document_type: body.documentType ?? 'invoice',
    bill_status: body.billStatus ?? 'ACTIVE',
    payload: body.payload ?? {},
  });
  return unwrapData<{ id: number }>(data);
}

export async function submitInvoiceEway(id: number, payload?: Record<string, unknown>) {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/submit-eway/`, payload ?? {});
    return unwrapData(data);
  }, { ...mockInvoices[0], id, ewayStatus: 'GENERATED', ewayBillNo: 'MOCK-EWB-001' });
}

export async function amendInvoiceFilingIdentity(
  id: number,
  payload: { filingPartyGstin?: string; filingPlaceOfSupply?: string; reason: string },
) {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/amend-filing-identity/`, {
      filing_party_gstin: payload.filingPartyGstin,
      filing_place_of_supply: payload.filingPlaceOfSupply,
      reason: payload.reason,
    });
    return unwrapData(data);
  }, {
    ...mockInvoices[0],
    id,
    filingPartyGstin: payload.filingPartyGstin ?? mockInvoices[0].filingPartyGstin,
    filingPlaceOfSupply: payload.filingPlaceOfSupply ?? mockInvoices[0].filingPlaceOfSupply,
  });
}

// ── Phase 1 sales documents ────────────────────────────────────────────────

function emptyNoteTotals() {
  return {
    subtotal: 0,
    discountTotal: 0,
    taxableTotal: 0,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    roundOff: 0,
    grandTotal: 0,
  };
}

export async function listSalesCreditNotes(params?: Record<string, string>): Promise<SalesCreditNote[]> {
  return withMocks(async () => fetchAllPagesMasters<SalesCreditNote>('/sales/credit-notes/', params), []);
}

export async function listSalesCreditNotesPage(params?: PageParams): Promise<PageResult<SalesCreditNote>> {
  return withMocks(async () => fetchPage<SalesCreditNote>('/sales/credit-notes/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function getSalesCreditNote(id: number | string): Promise<SalesCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/credit-notes/${id}/`);
    return unwrapData<SalesCreditNote>(data);
  }, {
    id: Number(id),
    status: 'DRAFT',
    customer: 0,
    salesInvoice: 0,
    noteDate: new Date().toISOString().slice(0, 10),
    reason: 'CORRECTION_OF_INVOICE',
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function createSalesCreditNote(payload: {
  customer: number;
  salesInvoice: number;
  noteDate?: string;
  reason?: string;
  reasonDetail?: string;
  notes?: string;
  items: Array<Partial<LineItem> & { sourceItem?: number | null }>;
}): Promise<SalesCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/credit-notes/', payload);
    return unwrapData<SalesCreditNote>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    customer: payload.customer,
    salesInvoice: payload.salesInvoice,
    noteDate: payload.noteDate ?? new Date().toISOString().slice(0, 10),
    reason: (payload.reason as SalesCreditNote['reason']) ?? 'CORRECTION_OF_INVOICE',
    items: payload.items as LineItem[],
    ...emptyNoteTotals(),
  });
}

export async function updateSalesCreditNote(
  id: number,
  payload: Record<string, unknown>,
): Promise<SalesCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/sales/credit-notes/${id}/`, payload);
    return unwrapData<SalesCreditNote>(data);
  }, { ...(await getSalesCreditNote(id)), ...payload } as SalesCreditNote);
}

export async function completeSalesCreditNote(
  id: number,
  options?: {
    confirmBlankPos?: boolean;
    confirmGstinTotalChange?: boolean;
    confirmPaidInvoice?: boolean;
    confirmPriceOverride?: boolean;
    gstGuardOverrideReason?: string;
  },
): Promise<SalesCreditNote> {
  return withMocks(async () => {
    // CamelCaseJSONParser maps these to confirm_paid_invoice / confirm_price_override.
    const { data } = await apiClient.post(`/sales/credit-notes/${id}/complete/`, {
      confirmBlankPos: Boolean(options?.confirmBlankPos),
      confirmGstinTotalChange: Boolean(options?.confirmGstinTotalChange),
      confirmPaidInvoice: Boolean(options?.confirmPaidInvoice),
      confirmPriceOverride: Boolean(options?.confirmPriceOverride),
      ...(options?.gstGuardOverrideReason
        ? { gstGuardOverrideReason: options.gstGuardOverrideReason }
        : {}),
    });
    return unwrapData<SalesCreditNote>(data);
  }, { ...(await getSalesCreditNote(id)), status: 'COMPLETED', number: `SCN-${id}` });
}

export async function cancelSalesCreditNote(id: number): Promise<SalesCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/credit-notes/${id}/cancel/`);
    return unwrapData<SalesCreditNote>(data);
  }, { ...(await getSalesCreditNote(id)), status: 'CANCELLED' });
}

export async function getSalesCreditNoteAdjustableSummary(
  invoiceId: number | string,
): Promise<AdjustableInvoiceSummary> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/sales/credit-notes/adjustable-summary/', {
      params: { invoice: invoiceId },
    });
    return unwrapData<AdjustableInvoiceSummary>(data);
  }, {
    invoiceId: Number(invoiceId),
    invoiceNumber: `INV-${invoiceId}`,
    grandTotal: 0,
    outstanding: 0,
  });
}

export async function listSalesDebitNotes(params?: Record<string, string>): Promise<SalesDebitNote[]> {
  return withMocks(async () => fetchAllPagesMasters<SalesDebitNote>('/sales/debit-notes/', params), []);
}

export async function listSalesDebitNotesPage(params?: PageParams): Promise<PageResult<SalesDebitNote>> {
  return withMocks(async () => fetchPage<SalesDebitNote>('/sales/debit-notes/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function getSalesDebitNote(id: number | string): Promise<SalesDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/debit-notes/${id}/`);
    return unwrapData<SalesDebitNote>(data);
  }, {
    id: Number(id),
    status: 'DRAFT',
    customer: 0,
    salesInvoice: 0,
    noteDate: new Date().toISOString().slice(0, 10),
    reason: 'CORRECTION_OF_INVOICE',
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function createSalesDebitNote(payload: {
  customer: number;
  salesInvoice: number;
  noteDate?: string;
  reason?: string;
  reasonDetail?: string;
  notes?: string;
  items: Array<Partial<LineItem> & { sourceItem?: number | null }>;
}): Promise<SalesDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/debit-notes/', payload);
    return unwrapData<SalesDebitNote>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    customer: payload.customer,
    salesInvoice: payload.salesInvoice,
    noteDate: payload.noteDate ?? new Date().toISOString().slice(0, 10),
    reason: (payload.reason as SalesDebitNote['reason']) ?? 'CORRECTION_OF_INVOICE',
    items: payload.items as LineItem[],
    ...emptyNoteTotals(),
  });
}

export async function updateSalesDebitNote(
  id: number,
  payload: Record<string, unknown>,
): Promise<SalesDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/sales/debit-notes/${id}/`, payload);
    return unwrapData<SalesDebitNote>(data);
  }, { ...(await getSalesDebitNote(id)), ...payload } as SalesDebitNote);
}

export async function completeSalesDebitNote(
  id: number,
  options?: { confirmAdditionalDebit?: boolean; gstGuardOverrideReason?: string },
): Promise<SalesDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/debit-notes/${id}/complete/`, {
      confirmAdditionalDebit: Boolean(options?.confirmAdditionalDebit),
      ...(options?.gstGuardOverrideReason
        ? { gstGuardOverrideReason: options.gstGuardOverrideReason }
        : {}),
    });
    return unwrapData<SalesDebitNote>(data);
  }, { ...(await getSalesDebitNote(id)), status: 'COMPLETED', number: `SDN-${id}` });
}

export async function cancelSalesDebitNote(id: number): Promise<SalesDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/debit-notes/${id}/cancel/`);
    return unwrapData<SalesDebitNote>(data);
  }, { ...(await getSalesDebitNote(id)), status: 'CANCELLED' });
}

export async function listSalesOrders(params?: Record<string, string>): Promise<SalesOrder[]> {
  return withMocks(async () => fetchAllPagesMasters<SalesOrder>('/sales/orders/', params), []);
}

export async function listSalesOrdersPage(params?: PageParams): Promise<PageResult<SalesOrder>> {
  return withMocks(async () => fetchPage<SalesOrder>('/sales/orders/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function getSalesOrder(id: number | string): Promise<SalesOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/orders/${id}/`);
    return unwrapData<SalesOrder>(data);
  }, {
    id: Number(id),
    status: 'DRAFT',
    customer: 0,
    invoiceType: 'GST',
    orderDate: new Date().toISOString().slice(0, 10),
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function createSalesOrder(payload: {
  customer: number;
  invoiceType?: string;
  orderDate?: string;
  expectedDelivery?: string | null;
  paymentTermsDays?: number;
  additionalCharges?: number | string;
  invoiceDiscount?: number | string;
  notes?: string;
  termsText?: string;
  salesman?: number | null;
  salesChannel?: string;
  deliveryAddress?: string;
  items: Array<Partial<LineItem>>;
}): Promise<SalesOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/orders/', payload);
    return unwrapData<SalesOrder>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    customer: payload.customer,
    invoiceType: (payload.invoiceType as SalesOrder['invoiceType']) ?? 'GST',
    orderDate: payload.orderDate ?? new Date().toISOString().slice(0, 10),
    items: payload.items as LineItem[],
    ...emptyNoteTotals(),
  });
}

export async function updateSalesOrder(id: number, payload: Record<string, unknown>): Promise<SalesOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/sales/orders/${id}/`, payload);
    return unwrapData<SalesOrder>(data);
  }, { ...(await getSalesOrder(id)), ...payload } as SalesOrder);
}

export async function convertSalesOrder(id: number): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/orders/${id}/convert/`);
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id: Date.now(), status: 'DRAFT' });
}

export async function convertSalesOrderToChallan(id: number): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/orders/${id}/convert-to-challan/`);
    return unwrapData<DeliveryChallan>(data);
  }, { id: Date.now(), status: 'DRAFT' } as unknown as DeliveryChallan);
}

export async function cancelSalesOrder(id: number): Promise<SalesOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/orders/${id}/cancel/`);
    return unwrapData<SalesOrder>(data);
  }, { ...(await getSalesOrder(id)), status: 'CANCELLED' });
}

export async function listDeliveryChallans(params?: Record<string, string>): Promise<DeliveryChallan[]> {
  return withMocks(async () => fetchAllPagesMasters<DeliveryChallan>('/sales/delivery-challans/', params), []);
}

export async function listDeliveryChallansPage(params?: PageParams): Promise<PageResult<DeliveryChallan>> {
  return withMocks(async () => fetchPage<DeliveryChallan>('/sales/delivery-challans/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function getDeliveryChallan(id: number | string): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/delivery-challans/${id}/`);
    return unwrapData<DeliveryChallan>(data);
  }, {
    id: Number(id),
    status: 'DRAFT',
    customer: 0,
    challanDate: new Date().toISOString().slice(0, 10),
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function createDeliveryChallan(payload: {
  customer: number;
  salesOrder?: number | null;
  challanDate?: string;
  vehicleNumber?: string;
  transporterName?: string;
  notes?: string;
  items: Array<Partial<LineItem>>;
}): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/delivery-challans/', payload);
    return unwrapData<DeliveryChallan>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    customer: payload.customer,
    challanDate: payload.challanDate ?? new Date().toISOString().slice(0, 10),
    items: payload.items as LineItem[],
    ...emptyNoteTotals(),
  });
}

export async function updateDeliveryChallan(
  id: number,
  payload: Record<string, unknown>,
): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/sales/delivery-challans/${id}/`, payload);
    return unwrapData<DeliveryChallan>(data);
  }, { ...(await getDeliveryChallan(id)), ...payload } as DeliveryChallan);
}

export async function completeDeliveryChallan(id: number): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/delivery-challans/${id}/complete/`);
    return unwrapData<DeliveryChallan>(data);
  }, { ...(await getDeliveryChallan(id)), status: 'COMPLETED', number: `DC-${id}` });
}

export async function convertDeliveryChallan(id: number): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/delivery-challans/${id}/convert/`);
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id: Date.now(), status: 'DRAFT' });
}

export async function cancelDeliveryChallan(id: number): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/delivery-challans/${id}/cancel/`);
    return unwrapData<DeliveryChallan>(data);
  }, { ...(await getDeliveryChallan(id)), status: 'CANCELLED' });
}

export type ChallanEwayPrepareResult = DeliveryChallan & { payload?: Record<string, unknown> };

export async function prepareChallanEway(id: number): Promise<ChallanEwayPrepareResult> {
  const { data } = await apiClient.post(`/sales/delivery-challans/${id}/prepare-eway/`);
  return unwrapData<ChallanEwayPrepareResult>(data);
}

export async function markChallanEwayGenerated(
  id: number,
  payload: { ewayBillNo: string; ewayValidUpto?: string },
): Promise<DeliveryChallan> {
  const { data } = await apiClient.post(`/sales/delivery-challans/${id}/mark-eway-generated/`, payload);
  return unwrapData<DeliveryChallan>(data);
}

export async function submitChallanEway(id: number): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/delivery-challans/${id}/submit-eway/`);
    return unwrapData<DeliveryChallan>(data);
  }, {
    id,
    status: 'COMPLETED',
    ewayStatus: 'GENERATED',
    ewayBillNo: 'MOCK-EWB-001',
    number: `DC-${id}`,
    customer: 0,
    challanDate: new Date().toISOString().slice(0, 10),
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function listRecurringSchedulesPage(params?: PageParams) {
  return fetchPage<Record<string, unknown>>('/sales/recurring-schedules/', params);
}

export async function createRecurringSchedule(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/sales/recurring-schedules/', payload);
  return unwrapData(data);
}

export async function updateRecurringSchedule(id: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/sales/recurring-schedules/${id}/`, payload);
  return unwrapData(data);
}

export async function runRecurringScheduleNow(id: number) {
  const { data } = await apiClient.post(`/sales/recurring-schedules/${id}/run-now/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function getInvoicePaymentStats(params?: PageParams) {
  const { data } = await apiClient.get('/sales/invoices/payment-stats/', { params: flattenQueryParams(params) });
  return unwrapData<{
    paid: { count: number; amount: string | number };
    partial: { count: number; amount: string | number };
    unpaid: { count: number; amount: string | number };
  }>(data);
}

export async function getInvoiceHsnSummary(id: number) {
  const { data } = await apiClient.get(`/sales/invoices/${id}/hsn-summary/`);
  return unwrapData<{ invoiceId: number; rows: Record<string, unknown>[] }>(data);
}

export async function recordInvoicePayment(
  id: number,
  payload: Record<string, unknown>,
  options?: { idempotencyKey?: string },
) {
  const { data } = await apiClient.post(`/sales/invoices/${id}/record-payment/`, payload, {
    headers: idempotencyHeaders(options?.idempotencyKey),
  });
  return unwrapData<SalesInvoice>(data);
}

export async function bulkInvoicePdfZip(ids: number[]) {
  const { data } = await apiClient.post('/sales/invoices/bulk-pdf-zip/', { ids });
  return unwrapData<{
    url: string;
    fileId?: number;
    included: { id: number; number: string }[];
    skipped: { id: number; number?: string; reason: string }[];
  }>(data);
}

export async function exportSalesRegisterCsv(params?: PageParams): Promise<Blob> {
  const { data } = await apiClient.get('/sales/invoices/export-csv/', {
    params: flattenQueryParams(params),
    responseType: 'blob',
  });
  return data as Blob;
}

export async function downloadBulkInvoicePdfZip(fileId: number): Promise<Blob> {
  const { data } = await apiClient.get(`/sales/invoices/bulk-pdf-zip/${fileId}/`, { responseType: 'blob' });
  return data as Blob;
}

export async function listDeliveryRoutesPage(params?: PageParams) {
  return fetchPage<Record<string, unknown>>('/sales/delivery-routes/', params);
}

export async function getDeliveryRoute(id: number) {
  const { data } = await apiClient.get(`/sales/delivery-routes/${id}/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function createDeliveryRoute(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/sales/delivery-routes/', payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function addOrdersToDeliveryRoute(id: number, orderIds: number[]) {
  const { data } = await apiClient.post(`/sales/delivery-routes/${id}/add-orders/`, { orderIds });
  return unwrapData<Record<string, unknown>>(data);
}

export async function removeDeliveryRouteStop(id: number, stopId: number) {
  const { data } = await apiClient.post(`/sales/delivery-routes/${id}/remove-stop/`, { stopId });
  return unwrapData<Record<string, unknown>>(data);
}

export async function setDeliveryRouteStopStatus(
  id: number,
  stopId: number,
  status: string,
  extra?: { completionSource?: string; otp?: string; podNote?: string; receivedByName?: string; podPhoto?: number; customerReceipt?: number },
) {
  const { data } = await apiClient.post(`/sales/delivery-routes/${id}/set-stop-status/`, {
    stopId,
    status,
    ...extra,
  });
  return unwrapData<Record<string, unknown>>(data);
}

export async function startDeliveryRoute(id: number) {
  const { data } = await apiClient.post(`/sales/delivery-routes/${id}/start/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function completeDeliveryRoute(id: number, payload?: { actualLogisticsCost?: number | string }) {
  const { data } = await apiClient.post(`/sales/delivery-routes/${id}/complete/`, payload ?? {});
  return unwrapData<Record<string, unknown>>(data);
}

export async function downloadDeliveryRouteManifest(id: number): Promise<Blob> {
  if (shouldUseMocks()) {
    return new Blob(['mock-route-manifest'], { type: 'application/pdf' });
  }
  const { data } = await apiClient.get(`/sales/delivery-routes/${id}/manifest/`, { responseType: 'blob' });
  return data as Blob;
}

export async function listDeliveryChallanReturnsPage(params?: PageParams) {
  return fetchPage<Record<string, unknown>>('/sales/challan-returns/', params);
}

export async function createDeliveryChallanReturn(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/sales/challan-returns/', payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function completeDeliveryChallanReturn(id: number) {
  const { data } = await apiClient.post(`/sales/challan-returns/${id}/complete/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function cancelChallanEway(id: number): Promise<DeliveryChallan> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/delivery-challans/${id}/cancel-eway/`);
    return unwrapData<DeliveryChallan>(data);
  }, {
    id,
    status: 'COMPLETED',
    ewayStatus: 'CANCELLED',
    ewayBillNo: undefined,
    number: `DC-${id}`,
    customer: 0,
    challanDate: new Date().toISOString().slice(0, 10),
    items: [],
    ...emptyNoteTotals(),
  });
}


/** Available quantity per product in the default godown (tracked products only). */
export async function getStockHints(productIds: number[]): Promise<Record<string, string>> {
  if (productIds.length === 0) return {};
  const { data } = await apiClient.get('/sales/stock-hints/', { params: { products: productIds.join(',') } });
  const body = unwrapData<{ available?: Record<string, string> }>(data);
  return body.available ?? {};
}
