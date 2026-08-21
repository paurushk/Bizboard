import { apiClient, idempotencyHeaders, unwrapData } from '../client';
import { mockPurchases } from '@/mocks/data';
import type { LineItem, PurchaseCreditNote, PurchaseDebitNote, PurchaseInvoice, PurchaseOrder, PurchaseReturn, ReportResponse } from '@/types/domain';
import { withMocks, fetchPage, fetchMoneyListFirstPage, type PageResult, type PageParams, type InvoiceNumberSeries } from './common';

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

export async function listPurchases(params?: Record<string, string>): Promise<PurchaseInvoice[]> {
  return withMocks(async () => fetchMoneyListFirstPage<PurchaseInvoice>('/purchases/invoices/', params), mockPurchases);
}

export async function listPurchasesPage(
  params?: PageParams,
): Promise<PageResult<PurchaseInvoice>> {
  return withMocks(async () => fetchPage<PurchaseInvoice>('/purchases/invoices/', params), {
    results: mockPurchases,
    count: mockPurchases.length,
    next: null,
    previous: null,
  });
}

export async function getPurchase(id: number | string): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/purchases/invoices/${id}/`);
    return unwrapData<PurchaseInvoice>(data);
  }, mockPurchases.find((p) => String(p.id) === String(id)) ?? mockPurchases[0]);
}

export async function createPurchase(
  payload: {
    supplier: number;
    purchaseType?: string;
    invoiceDate?: string;
    dueDate?: string | null;
    paymentTermsDays?: number;
    additionalCharges?: number | string;
    invoiceDiscount?: number | string;
    autoRoundOff?: boolean;
    supplierBillNumber?: string;
    notes?: string;
    termsText?: string;
    includeBankDetails?: boolean;
    includePaymentQr?: boolean;
    includeTerms?: boolean;
    signature?: number | null;
    tdsSection?: string;
    tdsRate?: number | string;
    tdsAmount?: number | string;
    items: Array<Partial<LineItem>>;
  },
  options?: { idempotencyKey?: string },
): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/purchases/invoices/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<PurchaseInvoice>(data);
  }, {
    ...mockPurchases[0],
    id: Date.now(),
    status: 'DRAFT',
    supplier: payload.supplier,
    items: payload.items as LineItem[],
  });
}

export async function updatePurchase(
  id: number,
  payload: {
    supplier?: number;
    items?: Array<Partial<LineItem>>;
    notes?: string;
    purchaseType?: string;
    invoiceDate?: string;
    dueDate?: string | null;
    paymentTermsDays?: number;
    additionalCharges?: number | string;
    invoiceDiscount?: number | string;
    autoRoundOff?: boolean;
    supplierBillNumber?: string;
    termsText?: string;
    includeBankDetails?: boolean;
    includePaymentQr?: boolean;
    includeTerms?: boolean;
    signature?: number | null;
    /** H9-A: required for Owner amend of completed purchase money fields */
    confirmAmend?: boolean;
    tdsSection?: string;
    tdsRate?: number | string;
    tdsAmount?: number | string;
  },
): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/purchases/invoices/${id}/`, payload);
    return unwrapData<PurchaseInvoice>(data);
  }, { ...mockPurchases[0], id, ...payload } as PurchaseInvoice);
}

export async function completePurchase(id: number): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/invoices/${id}/complete/`);
    return unwrapData<PurchaseInvoice>(data);
  }, { ...mockPurchases[0], id, status: 'COMPLETED', number: `PUR-${id}` });
}

export async function cancelPurchase(id: number): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/invoices/${id}/cancel/`);
    return unwrapData<PurchaseInvoice>(data);
  }, { ...mockPurchases[0], id, status: 'CANCELLED' });
}

export async function deletePurchase(id: number): Promise<void> {
  return withMocks(async () => {
    await apiClient.delete(`/purchases/invoices/${id}/`);
  }, undefined);
}

export async function getPurchaseNumberSeries(): Promise<InvoiceNumberSeries> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/purchases/invoices/number-series/');
    return unwrapData<InvoiceNumberSeries>(data);
  }, {
    docType: 'PURCHASE_INVOICE',
    prefix: 'PUR',
    nextNumber: 1,
    padding: 5,
    preview: 'PUR-00001',
  });
}

export async function updatePurchaseNumberSeries(payload: {
  prefix?: string;
  nextNumber?: number;
  padding?: number;
}): Promise<InvoiceNumberSeries> {
  return withMocks(async () => {
    const { data } = await apiClient.patch('/purchases/invoices/number-series/', payload);
    return unwrapData<InvoiceNumberSeries>(data);
  }, {
    docType: 'PURCHASE_INVOICE',
    prefix: payload.prefix ?? 'PUR',
    nextNumber: payload.nextNumber ?? 1,
    padding: payload.padding ?? 5,
    preview: `${payload.prefix ?? 'PUR'}-${String(payload.nextNumber ?? 1).padStart(payload.padding ?? 5, '0')}`,
  });
}

export async function listPurchaseReturns(params?: Record<string, string>): Promise<PurchaseReturn[]> {
  return withMocks(async () => fetchMoneyListFirstPage<PurchaseReturn>('/purchases/returns/', params), []);
}

export async function listPurchaseReturnsPage(params?: PageParams): Promise<PageResult<PurchaseReturn>> {
  return withMocks(async () => fetchPage<PurchaseReturn>('/purchases/returns/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function createPurchaseReturn(payload: {
  supplier: number;
  purchaseInvoice: number;
  returnDate?: string;
  reason?: string;
  items: Array<Partial<LineItem>>;
}): Promise<PurchaseReturn> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/purchases/returns/', payload);
    return unwrapData<PurchaseReturn>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    supplier: payload.supplier,
    purchaseInvoice: payload.purchaseInvoice,
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

export async function completePurchaseReturn(id: number): Promise<PurchaseReturn> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/returns/${id}/complete/`);
    return unwrapData<PurchaseReturn>(data);
  }, {
    id,
    status: 'COMPLETED',
    supplier: 0,
    purchaseInvoice: 0,
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

export async function getPurchaseRegister(params?: {
  dateFrom?: string;
  dateTo?: string;
}): Promise<ReportResponse> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/purchase-register/', {
      params: { date_from: params?.dateFrom, date_to: params?.dateTo },
    });
    return unwrapData<ReportResponse>(data);
  }, { rows: [], totals: {} });
}

// ── Phase 1 purchase documents ───────────────────────────────────────────

export async function listPurchaseCreditNotes(params?: Record<string, string>): Promise<PurchaseCreditNote[]> {
  return withMocks(async () => fetchMoneyListFirstPage<PurchaseCreditNote>('/purchases/credit-notes/', params), []);
}

export async function listPurchaseCreditNotesPage(
  params?: PageParams,
): Promise<PageResult<PurchaseCreditNote>> {
  return withMocks(async () => fetchPage<PurchaseCreditNote>('/purchases/credit-notes/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function getPurchaseCreditNote(id: number | string): Promise<PurchaseCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/purchases/credit-notes/${id}/`);
    return unwrapData<PurchaseCreditNote>(data);
  }, {
    id: Number(id),
    status: 'DRAFT',
    supplier: 0,
    noteDate: new Date().toISOString().slice(0, 10),
    reason: 'CORRECTION_OF_INVOICE',
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function createPurchaseCreditNote(payload: {
  supplier: number;
  purchaseInvoice?: number | null;
  supplierNoteNumber?: string;
  noteDate?: string;
  reason?: string;
  reasonDetail?: string;
  notes?: string;
  items: Array<Partial<LineItem>>;
}): Promise<PurchaseCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/purchases/credit-notes/', payload);
    return unwrapData<PurchaseCreditNote>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    supplier: payload.supplier,
    noteDate: payload.noteDate ?? new Date().toISOString().slice(0, 10),
    reason: (payload.reason as PurchaseCreditNote['reason']) ?? 'CORRECTION_OF_INVOICE',
    items: payload.items as LineItem[],
    ...emptyNoteTotals(),
  });
}

export async function updatePurchaseCreditNote(
  id: number,
  payload: Record<string, unknown>,
): Promise<PurchaseCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/purchases/credit-notes/${id}/`, payload);
    return unwrapData<PurchaseCreditNote>(data);
  }, { ...(await getPurchaseCreditNote(id)), ...payload } as PurchaseCreditNote);
}

export async function completePurchaseCreditNote(id: number): Promise<PurchaseCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/credit-notes/${id}/complete/`);
    return unwrapData<PurchaseCreditNote>(data);
  }, { ...(await getPurchaseCreditNote(id)), status: 'COMPLETED', number: `PCN-${id}` });
}

export async function cancelPurchaseCreditNote(id: number): Promise<PurchaseCreditNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/credit-notes/${id}/cancel/`);
    return unwrapData<PurchaseCreditNote>(data);
  }, { ...(await getPurchaseCreditNote(id)), status: 'CANCELLED' });
}

export async function listPurchaseDebitNotes(params?: Record<string, string>): Promise<PurchaseDebitNote[]> {
  return withMocks(async () => fetchMoneyListFirstPage<PurchaseDebitNote>('/purchases/debit-notes/', params), []);
}

export async function listPurchaseDebitNotesPage(
  params?: PageParams,
): Promise<PageResult<PurchaseDebitNote>> {
  return withMocks(async () => fetchPage<PurchaseDebitNote>('/purchases/debit-notes/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function getPurchaseDebitNote(id: number | string): Promise<PurchaseDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/purchases/debit-notes/${id}/`);
    return unwrapData<PurchaseDebitNote>(data);
  }, {
    id: Number(id),
    status: 'DRAFT',
    supplier: 0,
    noteDate: new Date().toISOString().slice(0, 10),
    reason: 'CORRECTION_OF_INVOICE',
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function createPurchaseDebitNote(payload: {
  supplier: number;
  purchaseInvoice?: number | null;
  supplierNoteNumber?: string;
  noteDate?: string;
  reason?: string;
  reasonDetail?: string;
  notes?: string;
  items: Array<Partial<LineItem>>;
}): Promise<PurchaseDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/purchases/debit-notes/', payload);
    return unwrapData<PurchaseDebitNote>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    supplier: payload.supplier,
    noteDate: payload.noteDate ?? new Date().toISOString().slice(0, 10),
    reason: (payload.reason as PurchaseDebitNote['reason']) ?? 'CORRECTION_OF_INVOICE',
    items: payload.items as LineItem[],
    ...emptyNoteTotals(),
  });
}

export async function updatePurchaseDebitNote(
  id: number,
  payload: Record<string, unknown>,
): Promise<PurchaseDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/purchases/debit-notes/${id}/`, payload);
    return unwrapData<PurchaseDebitNote>(data);
  }, { ...(await getPurchaseDebitNote(id)), ...payload } as PurchaseDebitNote);
}

export async function completePurchaseDebitNote(id: number): Promise<PurchaseDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/debit-notes/${id}/complete/`);
    return unwrapData<PurchaseDebitNote>(data);
  }, { ...(await getPurchaseDebitNote(id)), status: 'COMPLETED', number: `PDN-${id}` });
}

export async function cancelPurchaseDebitNote(id: number): Promise<PurchaseDebitNote> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/debit-notes/${id}/cancel/`);
    return unwrapData<PurchaseDebitNote>(data);
  }, { ...(await getPurchaseDebitNote(id)), status: 'CANCELLED' });
}

export async function listPurchaseOrders(params?: Record<string, string>): Promise<PurchaseOrder[]> {
  return withMocks(async () => fetchMoneyListFirstPage<PurchaseOrder>('/purchases/orders/', params), []);
}

export async function listPurchaseOrdersPage(params?: PageParams): Promise<PageResult<PurchaseOrder>> {
  return withMocks(async () => fetchPage<PurchaseOrder>('/purchases/orders/', params), {
    results: [],
    count: 0,
    next: null,
    previous: null,
  });
}

export async function getPurchaseOrder(id: number | string): Promise<PurchaseOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/purchases/orders/${id}/`);
    return unwrapData<PurchaseOrder>(data);
  }, {
    id: Number(id),
    status: 'DRAFT',
    supplier: 0,
    purchaseType: 'GST',
    orderDate: new Date().toISOString().slice(0, 10),
    items: [],
    ...emptyNoteTotals(),
  });
}

export async function createPurchaseOrder(payload: {
  supplier: number;
  purchaseType?: string;
  orderDate?: string;
  expectedDelivery?: string | null;
  paymentTermsDays?: number;
  additionalCharges?: number | string;
  invoiceDiscount?: number | string;
  notes?: string;
  termsText?: string;
  items: Array<Partial<LineItem>>;
}): Promise<PurchaseOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/purchases/orders/', payload);
    return unwrapData<PurchaseOrder>(data);
  }, {
    id: Date.now(),
    status: 'DRAFT',
    supplier: payload.supplier,
    purchaseType: (payload.purchaseType as PurchaseOrder['purchaseType']) ?? 'GST',
    orderDate: payload.orderDate ?? new Date().toISOString().slice(0, 10),
    items: payload.items as LineItem[],
    ...emptyNoteTotals(),
  });
}

export async function updatePurchaseOrder(id: number, payload: Record<string, unknown>): Promise<PurchaseOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/purchases/orders/${id}/`, payload);
    return unwrapData<PurchaseOrder>(data);
  }, { ...(await getPurchaseOrder(id)), ...payload } as PurchaseOrder);
}

export async function convertPurchaseOrder(id: number): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/orders/${id}/convert/`);
    return unwrapData<PurchaseInvoice>(data);
  }, { ...mockPurchases[0], id: Date.now(), status: 'DRAFT' });
}

export async function cancelPurchaseOrder(id: number): Promise<PurchaseOrder> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/purchases/orders/${id}/cancel/`);
    return unwrapData<PurchaseOrder>(data);
  }, { ...(await getPurchaseOrder(id)), status: 'CANCELLED' });
}

// ---- Phases 3–5: payments, inventory, accounting ----
// The API returns snake_case but the client interceptor normalizes response keys.
