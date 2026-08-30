import axios from 'axios';
import { apiClient, idempotencyHeaders, shouldUseMocks, unwrapData } from '../client';
import { mockInvoices, mockQuotations } from '@/mocks/data';
import type { LineItem, Quotation, ReportResponse, SalesCreditNote, SalesDebitNote, SalesInvoice, SalesOrder, SalesReturn, DeliveryChallan, AdjustableInvoiceSummary, PdfStatus } from '@/types/domain';
import { withMocks, fetchPage, fetchMoneyListFirstPage, type PageResult, type PageParams, type InvoiceNumberSeries } from './common';

export async function listSalesInvoices(params?: Record<string, string>): Promise<SalesInvoice[]> {
  return withMocks(async () => fetchMoneyListFirstPage<SalesInvoice>('/sales/invoices/', params), mockInvoices);
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

export async function completeSalesInvoice(
  id: number,
  options?: { confirmSalesRcm?: boolean },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/complete/`, {
      confirmSalesRcm: Boolean(options?.confirmSalesRcm),
    });
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, status: 'COMPLETED', number: `INV-${id}`, pdfStatus: 'QUEUED' });
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
      cnl_rsn: payload?.cnlRsn,
      cnl_rem: payload?.cnlRem,
    });
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, einvoiceStatus: 'CANCELLED', irn: undefined, ackNo: undefined });
}

export async function cancelInvoiceEway(id: number): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/cancel-eway/`);
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

export async function cancelSalesInvoice(id: number): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/cancel/`);
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, status: 'CANCELLED' });
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

export async function downloadInvoicePdf(
  id: number | string,
  options?: { copy?: 'ORIGINAL' | 'DUPLICATE' },
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

export type SalesPdfDocType = 'invoice' | 'credit-note' | 'debit-note' | 'delivery-challan';

const SALES_PDF_BASE: Record<Exclude<SalesPdfDocType, 'invoice'>, string> = {
  'credit-note': '/sales/credit-notes',
  'debit-note': '/sales/debit-notes',
  'delivery-challan': '/sales/delivery-challans',
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
  options?: { copy?: 'ORIGINAL' | 'DUPLICATE' },
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

export async function shareInvoice(
  id: number,
  payload: { channel: 'EMAIL' | 'WHATSAPP'; recipient: string; message?: string },
): Promise<{ status: string; shareLink?: string; mode?: 'cloud' | 'link'; error?: string }> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/share/`, payload);
    return unwrapData(data);
  }, {
    status: 'LINK_READY',
    shareLink: `https://wa.me/${payload.recipient}`,
    mode: 'link' as const,
  });
}

export async function listQuotations(params?: Record<string, string>): Promise<Quotation[]> {
  return withMocks(async () => fetchMoneyListFirstPage<Quotation>('/sales/quotations/', params), mockQuotations);
}

export async function listQuotationsPage(params?: PageParams): Promise<PageResult<Quotation>> {
  return withMocks(async () => fetchPage<Quotation>('/sales/quotations/', params), {
    results: mockQuotations,
    count: mockQuotations.length,
    next: null,
    previous: null,
  });
}

export async function createQuotation(payload: {
  customer?: number;
  invoiceType?: string;
  quotationDate?: string;
  items: Array<Partial<LineItem>>;
}): Promise<Quotation> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/quotations/', payload);
    return unwrapData<Quotation>(data);
  }, { ...mockQuotations[0], id: Date.now(), status: 'DRAFT', items: payload.items as LineItem[] });
}

export async function convertQuotation(id: number): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/quotations/${id}/convert/`);
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id: Date.now(), status: 'DRAFT' });
}

export async function convertQuotationToOrder(id: number, confirmExpired = false): Promise<SalesOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/quotations/${id}/convert-to-order/`, {
      confirm_expired: confirmExpired,
    });
    return unwrapData<SalesOrder>(data);
  }, { id: Date.now(), status: 'DRAFT' } as unknown as SalesOrder);
}

export async function listSalesReturns(params?: Record<string, string>): Promise<SalesReturn[]> {
  return withMocks(async () => fetchMoneyListFirstPage<SalesReturn>('/sales/returns/', params), []);
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
}): Promise<SalesReturn> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/returns/', payload);
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

export async function completeSalesReturn(id: number): Promise<SalesReturn> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/returns/${id}/complete/`);
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
  return withMocks(async () => fetchMoneyListFirstPage<SalesCreditNote>('/sales/credit-notes/', params), []);
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

export async function completeSalesCreditNote(id: number): Promise<SalesCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/credit-notes/${id}/complete/`);
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
  return withMocks(async () => fetchMoneyListFirstPage<SalesDebitNote>('/sales/debit-notes/', params), []);
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

export async function completeSalesDebitNote(id: number): Promise<SalesDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/debit-notes/${id}/complete/`);
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
  return withMocks(async () => fetchMoneyListFirstPage<SalesOrder>('/sales/orders/', params), []);
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
  return withMocks(async () => fetchMoneyListFirstPage<DeliveryChallan>('/sales/delivery-challans/', params), []);
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

