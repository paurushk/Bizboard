import axios from 'axios';
import { apiClient, shouldUseMocks, unwrapData } from './client';
import {
  mockCompany,
  mockCustomers,
  mockDashboard,
  mockInvoices,
  mockProducts,
  mockPurchases,
  mockQuotations,
  mockReceipts,
  mockSearchResults,
  mockStock,
  mockSupplierPayments,
  mockSuppliers,
  mockUsers,
} from '@/mocks/data';
import type {
  Company,
  CompanyUser,
  Customer,
  CustomerReceipt,
  DashboardKpis,
  ImportJob,
  ImportKind,
  LedgerStatement,
  LineItem,
  Paginated,
  PaymentAllocation,
  Product,
  PurchaseBillCommitResult,
  PurchaseInvoice,
  PurchaseReturn,
  Quotation,
  ReportResponse,
  SalesInvoice,
  SalesReturn,
  SearchResult,
  StockAdjustment,
  StockBalance,
  Supplier,
  SupplierPayment,
} from '@/types/domain';

async function withMocks<T>(fn: () => Promise<T>, fallback: T | (() => T)): Promise<T> {
  if (shouldUseMocks()) {
    await sleep(150);
    return typeof fallback === 'function' ? (fallback as () => T)() : fallback;
  }
  return fn();
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function asList<T>(data: Paginated<T> | T[] | null | undefined): T[] {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

function getNextUrl(data: Paginated<unknown> | unknown[] | null | undefined): string | null {
  if (!data || Array.isArray(data)) return null;
  return data.next ?? null;
}

/** Fetch first page + optional cursor for load-more UIs. */
export async function listPage<T>(
  path: string,
  params?: Record<string, string>,
): Promise<{ results: T[]; next: string | null }> {
  const { data } = await apiClient.get(path, { params });
  const body = unwrapData<Paginated<T> | T[]>(data);
  return { results: asList(body), next: getNextUrl(body) };
}

export async function fetchNextPage<T>(nextUrl: string): Promise<{ results: T[]; next: string | null }> {
  // DRF may return an absolute URL; strip origin + /api/v1 prefix for apiClient.
  let path = nextUrl;
  try {
    const u = new URL(nextUrl, window.location.origin);
    path = u.pathname.replace(/^\/api\/v1/, '') + u.search;
  } catch {
    path = nextUrl.replace(/^\/api\/v1/, '');
  }
  const { data } = await apiClient.get(path);
  const body = unwrapData<Paginated<T> | T[]>(data);
  return { results: asList(body), next: getNextUrl(body) };
}

/**
 * BUG-521/606-609: several call sites (customer/supplier/product/stock
 * pickers and tables) expect a full T[] and silently only ever got page 1
 * of a paginated response, making any record past the first page (~50
 * rows) invisible/unreachable through the UI with no error shown. This
 * transparently walks every page so callers keep their existing `T[]`
 * signature instead of needing a "load more" UI at every use site.
 */
async function fetchAllPages<T>(
  path: string,
  params?: Record<string, string>,
): Promise<T[]> {
  const first = await listPage<T>(path, params);
  let results = first.results;
  let next = first.next;
  // Safety cap — a runaway `next` cursor should never spin forever.
  let guard = 0;
  while (next && guard < 200) {
    const page = await fetchNextPage<T>(next);
    results = results.concat(page.results);
    next = page.next;
    guard += 1;
  }
  return results;
}

export async function getDashboard(): Promise<DashboardKpis> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/dashboard/');
    return unwrapData<DashboardKpis>(data);
  }, mockDashboard);
}

export async function getCompany(): Promise<Company> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/company/');
    return unwrapData<Company>(data);
  }, mockCompany);
}

export async function updateCompany(payload: Partial<Company>): Promise<Company> {
  return withMocks(async () => {
    const { data } = await apiClient.patch('/company/', payload);
    return unwrapData<Company>(data);
  }, { ...mockCompany, ...payload } as Company);
}

export async function listCustomers(params?: { q?: string }): Promise<Customer[]> {
  return withMocks(async () => fetchAllPages<Customer>('/customers/', params), mockCustomers);
}

export async function createCustomer(payload: Partial<Customer>): Promise<Customer> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/customers/', payload);
    return unwrapData<Customer>(data);
  }, { id: Date.now(), name: payload.name ?? '', status: 'ACTIVE', ...payload } as Customer);
}

export async function updateCustomer(id: number, payload: Partial<Customer>): Promise<Customer> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/customers/${id}/`, payload);
    return unwrapData<Customer>(data);
  }, { ...(mockCustomers[0] ?? { id, name: '', status: 'ACTIVE' }), ...payload, id } as Customer);
}

export async function listSuppliers(): Promise<Supplier[]> {
  return withMocks(async () => fetchAllPages<Supplier>('/suppliers/'), mockSuppliers);
}

export async function createSupplier(payload: Partial<Supplier>): Promise<Supplier> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/suppliers/', payload);
    return unwrapData<Supplier>(data);
  }, { id: Date.now(), name: payload.name ?? '', isActive: true, ...payload } as Supplier);
}

export async function updateSupplier(id: number, payload: Partial<Supplier>): Promise<Supplier> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/suppliers/${id}/`, payload);
    return unwrapData<Supplier>(data);
  }, { ...(mockSuppliers[0] ?? { id, name: '', isActive: true }), ...payload, id } as Supplier);
}

export async function listProducts(params?: { q?: string }): Promise<Product[]> {
  return withMocks(async () => fetchAllPages<Product>('/products/', params), () => filterProducts(params?.q));
}

function filterProducts(q?: string): Product[] {
  if (!q) return mockProducts;
  const term = q.toLowerCase();
  return mockProducts.filter(
    (p) =>
      p.name.toLowerCase().includes(term) ||
      p.sku.toLowerCase().includes(term) ||
      (p.barcode && p.barcode.includes(term)),
  );
}

export async function searchProducts(q: string): Promise<Product[]> {
  return listProducts({ q });
}

export async function createProduct(payload: Partial<Product>): Promise<Product> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/products/', payload);
    return unwrapData<Product>(data);
  }, {
    id: Date.now(),
    name: payload.name ?? '',
    sku: payload.sku ?? '',
    gstRate: payload.gstRate ?? 18,
    purchasePrice: payload.purchasePrice ?? 0,
    sellingPrice: payload.sellingPrice ?? 0,
    reorderLevel: payload.reorderLevel ?? 0,
    status: 'ACTIVE',
    ...payload,
  } as Product);
}

export async function updateProduct(id: number, payload: Partial<Product>): Promise<Product> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/products/${id}/`, payload);
    return unwrapData<Product>(data);
  }, { ...mockProducts[0], ...payload, id } as Product);
}

export async function listSalesInvoices(params?: Record<string, string>): Promise<SalesInvoice[]> {
  return withMocks(async () => {
    const page = await listPage<SalesInvoice>('/sales/invoices/', params);
    return page.results;
  }, mockInvoices);
}

export async function listSalesInvoicesPage(
  params?: Record<string, string>,
): Promise<{ results: SalesInvoice[]; next: string | null }> {
  return withMocks(async () => listPage<SalesInvoice>('/sales/invoices/', params), {
    results: mockInvoices,
    next: null,
  });
}

export async function getSalesInvoice(id: number | string): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/sales/invoices/${id}/`);
    return unwrapData<SalesInvoice>(data);
  }, mockInvoices.find((i) => String(i.id) === String(id)) ?? mockInvoices[0]);
}

export async function createSalesInvoice(payload: {
  customer: number;
  invoiceType?: string;
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
  items: Array<Partial<LineItem>>;
}): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/sales/invoices/', payload);
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
  },
): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/sales/invoices/${id}/`, payload);
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, ...payload } as SalesInvoice);
}

export async function completeSalesInvoice(id: number): Promise<SalesInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/complete/`);
    return unwrapData<SalesInvoice>(data);
  }, { ...mockInvoices[0], id, status: 'COMPLETED', number: `INV-${id}`, pdfStatus: 'QUEUED' });
}

export interface InvoiceNumberSeries {
  docType: string;
  prefix: string;
  nextNumber: number;
  padding: number;
  preview: string;
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

export async function shareInvoice(
  id: number,
  payload: { channel: 'EMAIL' | 'WHATSAPP'; recipient: string; message?: string },
): Promise<{ status: string; shareLink?: string }> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/sales/invoices/${id}/share/`, payload);
    return unwrapData(data);
  }, { status: 'SENT', shareLink: `https://wa.me/${payload.recipient}` });
}

export async function listQuotations(): Promise<Quotation[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/sales/quotations/');
    return asList(unwrapData<Paginated<Quotation> | Quotation[]>(data));
  }, mockQuotations);
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

export async function listSalesReturns(): Promise<SalesReturn[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/sales/returns/');
    return asList(unwrapData<Paginated<SalesReturn> | SalesReturn[]>(data));
  }, []);
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

export async function listReceipts(): Promise<CustomerReceipt[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/payments/receipts/');
    return asList(unwrapData<Paginated<CustomerReceipt> | CustomerReceipt[]>(data));
  }, mockReceipts);
}

export async function createReceipt(payload: {
  customer: number;
  amount: number | string;
  mode: string;
  receiptDate?: string;
  reference?: string;
  notes?: string;
}): Promise<CustomerReceipt> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/receipts/', payload);
    return unwrapData<CustomerReceipt>(data);
  }, {
    id: Date.now(),
    customer: payload.customer,
    amount: payload.amount,
    mode: payload.mode as CustomerReceipt['mode'],
    receiptDate: payload.receiptDate ?? new Date().toISOString().slice(0, 10),
    allocated: 0,
    unallocated: payload.amount,
  });
}

export async function listPurchases(params?: Record<string, string>): Promise<PurchaseInvoice[]> {
  return withMocks(async () => {
    const page = await listPage<PurchaseInvoice>('/purchases/invoices/', params);
    return page.results;
  }, mockPurchases);
}

export async function listPurchasesPage(
  params?: Record<string, string>,
): Promise<{ results: PurchaseInvoice[]; next: string | null }> {
  return withMocks(async () => listPage<PurchaseInvoice>('/purchases/invoices/', params), {
    results: mockPurchases,
    next: null,
  });
}

export async function getPurchase(id: number | string): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/purchases/invoices/${id}/`);
    return unwrapData<PurchaseInvoice>(data);
  }, mockPurchases.find((p) => String(p.id) === String(id)) ?? mockPurchases[0]);
}

export async function createPurchase(payload: {
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
  items: Array<Partial<LineItem>>;
}): Promise<PurchaseInvoice> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/purchases/invoices/', payload);
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

export async function listPurchaseReturns(): Promise<PurchaseReturn[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/purchases/returns/');
    return asList(unwrapData<Paginated<PurchaseReturn> | PurchaseReturn[]>(data));
  }, []);
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

export async function listSupplierPayments(): Promise<SupplierPayment[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/payments/supplier-payments/');
    return asList(unwrapData<Paginated<SupplierPayment> | SupplierPayment[]>(data));
  }, mockSupplierPayments);
}

export async function createSupplierPayment(payload: {
  supplier: number;
  amount: number | string;
  mode: string;
  paymentDate?: string;
  reference?: string;
  notes?: string;
}): Promise<SupplierPayment> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/supplier-payments/', payload);
    return unwrapData<SupplierPayment>(data);
  }, {
    id: Date.now(),
    supplier: payload.supplier,
    amount: payload.amount,
    mode: payload.mode as SupplierPayment['mode'],
    paymentDate: payload.paymentDate ?? new Date().toISOString().slice(0, 10),
    allocated: 0,
    unallocated: payload.amount,
  });
}

export async function createAllocation(payload: {
  receipt?: number;
  supplierPayment?: number;
  salesInvoice?: number;
  purchaseInvoice?: number;
  amount: number | string;
}): Promise<PaymentAllocation> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/allocations/', payload);
    return unwrapData<PaymentAllocation>(data);
  }, { id: Date.now(), ...payload, amount: payload.amount });
}

export async function listStock(): Promise<StockBalance[]> {
  return withMocks(async () => fetchAllPages<StockBalance>('/inventory/balances/'), mockStock);
}

export async function listLowStock(): Promise<StockBalance[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/inventory/alerts/');
    const body = unwrapData<{ count: number; items: StockBalance[] }>(data);
    return body.items ?? [];
  }, mockStock.filter((s) => Number(s.available) <= Number(s.reorderLevel)));
}

export async function createStockAdjustment(payload: StockAdjustment): Promise<void> {
  return withMocks(async () => {
    await apiClient.post('/inventory/adjustments/', payload);
  }, undefined);
}

export async function getCustomerLedger(customerId: number | string): Promise<LedgerStatement> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/ledgers/customers/${customerId}/`);
    return unwrapData<LedgerStatement>(data);
  }, {
    customerId: Number(customerId),
    customerName: 'Demo',
    outstanding: 3250,
    entries: [
      {
        date: '2026-07-18',
        type: 'SALES_INVOICE',
        number: 'INV-1',
        debit: 5250,
        credit: 0,
        balance: 5250,
      },
      {
        date: '2026-07-18',
        type: 'RECEIPT',
        number: 'RCT-1',
        debit: 0,
        credit: 2000,
        balance: 3250,
      },
    ],
  });
}

export async function getSupplierLedger(supplierId: number | string): Promise<LedgerStatement> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/ledgers/suppliers/${supplierId}/`);
    return unwrapData<LedgerStatement>(data);
  }, {
    supplierId: Number(supplierId),
    supplierName: 'Demo',
    outstanding: 12000,
    entries: [
      {
        date: '2026-07-15',
        type: 'PURCHASE_INVOICE',
        number: 'PUR-1',
        debit: 0,
        credit: 15000,
        balance: 15000,
      },
    ],
  });
}

export async function universalSearch(q: string): Promise<SearchResult[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/search/', { params: { q } });
    const body = unwrapData<
      | SearchResult[]
      | {
          customers?: Array<{ id: number; name: string }>;
          products?: Array<{ id: number; name: string; sku?: string }>;
          suppliers?: Array<{ id: number; name: string }>;
          invoices?: Array<{ id: number; number?: string; kind?: string }>;
        }
    >(data);

    if (Array.isArray(body)) return body;

    const results: SearchResult[] = [];
    for (const c of body.customers ?? []) {
      results.push({
        id: c.id,
        type: 'customer',
        title: c.name,
        path: '/sales/customers',
      });
    }
    for (const p of body.products ?? []) {
      results.push({
        id: p.id,
        type: 'product',
        title: p.name,
        subtitle: p.sku,
        path: '/inventory/products',
      });
    }
    for (const s of body.suppliers ?? []) {
      results.push({
        id: s.id,
        type: 'supplier',
        title: s.name,
        path: '/purchases/suppliers',
      });
    }
    for (const inv of body.invoices ?? []) {
      results.push({
        id: inv.id,
        type: 'invoice',
        title: inv.number ?? String(inv.id),
        subtitle: inv.kind,
        path: `/sales/history/${inv.id}`,
      });
    }
    return results;
  }, mockSearchResults.filter(
    (r) =>
      r.title.toLowerCase().includes(q.toLowerCase()) ||
      r.subtitle?.toLowerCase().includes(q.toLowerCase()),
  ));
}

export async function uploadImport(
  file: File,
  kind: ImportKind,
  extra?: { supplierId?: number },
): Promise<ImportJob> {
  return withMocks(async () => {
    const form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    if (extra?.supplierId != null) {
      form.append('supplier_id', String(extra.supplierId));
    }
    // Let the browser set multipart boundary — do not force Content-Type.
    const { data } = await apiClient.post('/imports/', form, {
      headers: { 'Content-Type': undefined as unknown as string },
    });
    return unwrapData<ImportJob>(data);
  }, {
    id: Date.now(),
    kind,
    status: 'PREVIEWED',
    totalRows: 3,
    validRows: 2,
    errorRows: 1,
    preview: [
      { rowNumber: 1, data: { name: 'Sample A' }, errors: [], warnings: [] },
      { rowNumber: 3, data: { name: '' }, errors: ['Name is required'], warnings: [] },
    ],
  });
}

export async function getImportJob(id: number | string): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/imports/${id}/`);
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id),
    kind: 'PURCHASE_BILL',
    status: 'PREVIEWED',
    totalRows: 1,
    validRows: 1,
    errorRows: 0,
    preview: {
      supplierName: 'Demo Supplier',
      billNumber: 'PB-1',
      billDate: '2026-07-01',
      lines: [
        {
          name: 'Sample Item',
          sku: 'SKU-1',
          quantity: '1',
          unitPrice: '100',
          gstRate: '18',
          include: true,
        },
      ],
    },
  });
}

export async function retryImportExtract(id: number | string): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/imports/${id}/retry-extract/`);
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id),
    kind: 'PURCHASE_BILL',
    status: 'EXTRACTING',
    totalRows: 0,
    validRows: 0,
    errorRows: 0,
    preview: { lines: [] },
  });
}

export async function updateImportPreview(
  id: number | string,
  payload: {
    supplierId?: number | null;
    supplierName?: string;
    billNumber?: string;
    billDate?: string;
    lines?: Array<Record<string, unknown>>;
  },
): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/imports/${id}/preview/`, payload);
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id),
    kind: 'PURCHASE_BILL',
    status: 'PREVIEWED',
    totalRows: payload.lines?.length ?? 0,
    validRows: payload.lines?.filter((l) => l.include !== false).length ?? 0,
    errorRows: 0,
    preview: {
      supplierName: payload.supplierName,
      billNumber: payload.billNumber,
      billDate: payload.billDate,
      lines: (payload.lines ?? []) as never,
    },
    supplier: payload.supplierId ?? null,
  });
}

export async function commitImport(
  id: number | string,
  payload?: Record<string, unknown>,
): Promise<ImportJob | PurchaseBillCommitResult> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/imports/${id}/commit/`, payload ?? {});
    return unwrapData<ImportJob | PurchaseBillCommitResult>(data);
  }, {
    id: Number(id),
    kind: 'PRODUCTS',
    status: 'COMMITTED',
    totalRows: 3,
    validRows: 2,
    errorRows: 1,
    preview: [],
  });
}

export async function exportReport(
  type: string,
  // BUG-616/323: the export previously ignored whatever date range was
  // applied on-screen, silently exporting the full unfiltered register.
  params?: { dateFrom?: string; dateTo?: string },
): Promise<{ url: string }> {
  return withMocks(async () => {
    const reportMap: Record<string, string> = {
      sales: 'sales-register',
      purchases: 'purchase-register',
      inventory: 'inventory-summary',
      customers: 'sales-register',
    };
    const report = reportMap[type] ?? type;
    const response = await apiClient.get(`/exports/${report}/`, {
      responseType: 'blob',
      // CSV bypasses the JSON envelope renderer
      transformResponse: [(d) => d],
      params: {
        date_from: params?.dateFrom || undefined,
        date_to: params?.dateTo || undefined,
      },
    });
    const blob =
      response.data instanceof Blob
        ? response.data
        : new Blob([response.data as BlobPart], { type: 'text/csv' });
    return { url: URL.createObjectURL(blob) };
  }, { url: '#' });
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

export async function getInventorySummary(): Promise<ReportResponse> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/inventory-summary/');
    return unwrapData<ReportResponse>(data);
  }, { rows: [] });
}

export async function listCompanyUsers(): Promise<CompanyUser[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/company/users/');
    return asList(unwrapData<Paginated<CompanyUser> | CompanyUser[]>(data));
  }, mockUsers);
}

export async function inviteCompanyUser(payload: {
  email: string;
  password: string;
  fullName?: string;
  phone?: string;
  role?: string;
  canManageInventory?: boolean;
  canImport?: boolean;
}): Promise<CompanyUser> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/company/users/', payload);
    return unwrapData<CompanyUser>(data);
  }, {
    id: Date.now(),
    user: Date.now(),
    email: payload.email,
    fullName: payload.fullName ?? '',
    role: (payload.role as CompanyUser['role']) ?? 'SALES_STAFF',
    canManageInventory: payload.canManageInventory ?? false,
    canImport: payload.canImport ?? false,
    isActive: true,
  });
}

export async function updateCompanyUser(
  id: number,
  payload: Partial<CompanyUser>,
): Promise<CompanyUser> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/company/users/${id}/`, payload);
    return unwrapData<CompanyUser>(data);
  }, { ...mockUsers[0], ...payload, id });
}
