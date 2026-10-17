import { t } from '@/i18n';
import { apiClient, idempotencyHeaders, newIdempotencyKey, shouldUseMocks, unwrapData } from '../client';
import {
  mockAccountingAccounts,
  mockAccountingPeriods,
  mockBankAccounts,
  mockCostCenters,
  mockFixedAssets,
  mockJournalEntries,
  mockSearchResults,
} from '@/mocks/data';
import type { BillValidationReport, ImportJob, ImportKind, PurchaseBillCommitResult, SearchResult, AssistantMessage, AssistantThread, AttentionRow, BusinessAlert, CashflowForecast, DailyBusinessSummary, GrowthHint } from '@/types/domain';
import { mockBillImageUrl, mockBillJob } from '@/mocks/billImport';
import { withMocks, fetchPage, fetchAllPagesMasters, flattenQueryParams, getBlob, type PageResult, type PageParams } from './common';

/** Master import validate/commit can run long for multi-thousand-row CSVs. */
const IMPORT_TIMEOUT_MS = 120_000;

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
          quotations?: Array<{ id: number; number?: string | null; status?: string; customer_name?: string; customerName?: string }>;
          sales_orders?: Array<{ id: number; number?: string | null; status?: string; customer_name?: string; customerName?: string }>;
          delivery_challans?: Array<{ id: number; number?: string | null; status?: string; customer_name?: string; customerName?: string }>;
          delivery_routes?: Array<{ id: number; number?: string | null; status?: string; vehicle_number?: string; vehicleNumber?: string; driver_name?: string; driverName?: string }>;
          credit_notes?: Array<{ id: number; number?: string | null; party?: string; invoice_number?: string }>;
          debit_notes?: Array<{ id: number; number?: string | null; party?: string; invoice_number?: string }>;
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
        path: inv.kind === 'purchase' ? `/purchases/history/${inv.id}` : `/sales/history/${inv.id}`,
      });
    }
    for (const quote of body.quotations ?? []) {
      results.push({
        id: quote.id,
        type: 'quotation',
        title: quote.number || String(quote.id),
        subtitle: [t('nav.quotations'), quote.customer_name ?? quote.customerName].filter(Boolean).join(' · '),
        path: `/sales/quotations/${quote.id}`,
      });
    }
    for (const order of body.sales_orders ?? []) {
      results.push({
        id: order.id,
        type: 'sales_order',
        title: order.number || t('status.DRAFT'),
        subtitle: [order.customer_name ?? order.customerName, order.status ? t(`status.${order.status}`) : '']
          .filter(Boolean)
          .join(' · '),
        path: `/sales/orders/${order.id}`,
      });
    }
    for (const challan of body.delivery_challans ?? []) {
      results.push({
        id: challan.id,
        type: 'delivery_challan',
        title: challan.number || t('status.DRAFT'),
        subtitle: [challan.customer_name ?? challan.customerName, challan.status ? t(`status.${challan.status}`) : '']
          .filter(Boolean)
          .join(' · '),
        path: `/sales/delivery-challans/${challan.id}`,
      });
    }
    for (const route of body.delivery_routes ?? []) {
      results.push({
        id: route.id,
        type: 'delivery_route',
        title: route.number || String(route.id),
        subtitle: [
          route.vehicle_number ?? route.vehicleNumber,
          route.driver_name ?? route.driverName,
          route.status ? t(`status.${route.status}`) : '',
        ]
          .filter(Boolean)
          .join(' · '),
        path: `/sales/delivery-routes/${route.id}`,
      });
    }
    for (const note of body.credit_notes ?? []) {
      results.push({
        id: note.id,
        type: 'credit_note',
        title: note.number || t('status.DRAFT'),
        subtitle: [note.party, note.invoice_number].filter(Boolean).join(' · '),
        path: `/sales/credit-notes/${note.id}`,
      });
    }
    for (const note of body.debit_notes ?? []) {
      results.push({
        id: note.id,
        type: 'debit_note',
        title: note.number || t('status.DRAFT'),
        subtitle: [note.party, note.invoice_number].filter(Boolean).join(' · '),
        path: `/sales/debit-notes/${note.id}`,
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
  extra?: { supplierId?: number; customerId?: number; idempotencyKey?: string; aiConsent?: boolean },
): Promise<ImportJob> {
  return withMocks(async () => {
    const form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    if (extra?.supplierId != null) {
      form.append('supplier_id', String(extra.supplierId));
    }
    if (extra?.customerId != null) {
      form.append('customer_id', String(extra.customerId));
    }
    if (extra?.aiConsent) {
      form.append('ai_consent', 'true');
    }
    const key = extra?.idempotencyKey ?? newIdempotencyKey();
    // Let the browser set multipart boundary — do not force Content-Type.
    const { data } = await apiClient.post('/imports/', form, {
      headers: {
        'Content-Type': undefined as unknown as string,
        ...idempotencyHeaders(key),
      },
      timeout: IMPORT_TIMEOUT_MS,
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
  }, mockBillJob(Number(id), 'SALES_BILL') ?? {
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
    customerId?: number | null;
    supplierName?: string;
    customerName?: string;
    billNumber?: string;
    billDate?: string;
    lines?: Array<Record<string, unknown>>;
    buyerName?: string;
    buyerGstin?: string;
    previewVersion?: number;
    priceMode?: 'EXCLUSIVE' | 'INCLUSIVE';
    additionalCharges?: string;
    invoiceDiscount?: string;
    printedTotal?: string;
    companyGstinId?: number | null;
    confirmDuplicate?: boolean;
    confirmNewProducts?: boolean;
    confirmNonGst?: boolean;
    confirm_non_gst?: boolean;
    lowConfidenceAccepted?: boolean;
    low_confidence_accepted?: boolean;
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
      customerName: payload.customerName,
      billNumber: payload.billNumber,
      billDate: payload.billDate,
      lines: (payload.lines ?? []) as never,
    },
    supplier: payload.supplierId ?? null,
    customer: payload.customerId ?? null,
  });
}

export async function validateImportBill(
  id: number | string,
  payload?: Record<string, unknown>,
): Promise<BillValidationReport> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/imports/${id}/validate/`, payload ?? {});
    return unwrapData<BillValidationReport>(data);
  }, {
    ok: true,
    headerErrors: [],
    lineErrors: [],
    summary: { included: 0, excluded: 0, newProducts: 0, newParty: false },
    totals: {
      taxable: '0.00', gst: '0.00', cess: '0.00', charges: '0.00', invoiceDiscount: '0.00',
      grandTotal: '0.00', roundedTotal: '0', includedLines: 0,
    },
  });
}

export async function cancelImport(id: number | string): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/imports/${id}/cancel/`);
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id), kind: 'PURCHASE_BILL', status: 'CANCELLED',
    totalRows: 0, validRows: 0, errorRows: 0, preview: { lines: [] },
  });
}

export async function switchImportKind(
  id: number | string,
  kind: 'PURCHASE_BILL' | 'SALES_BILL',
): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/imports/${id}/switch-kind/`, { kind });
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id), kind, status: 'PREVIEWED',
    totalRows: 0, validRows: 0, errorRows: 0, preview: { lines: [] },
  });
}

export async function listBillImportJobs(
  kind: 'PURCHASE_BILL' | 'SALES_BILL',
  statuses = 'UPLOADED,EXTRACTING,NEEDS_CLARIFICATION,PREVIEWED,FAILED',
): Promise<ImportJob[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/imports/', { params: { kind, status: statuses, mine: 1 } });
    const body = unwrapData<ImportJob[] | { results: ImportJob[] }>(data);
    return Array.isArray(body) ? body : body.results ?? [];
  }, [] as ImportJob[]);
}

/** The uploaded bill as an object URL (auth header required, so not a plain <img src>). */
export async function fetchImportSourceFile(
  id: number | string,
): Promise<{ url: string; contentType: string }> {
  if (shouldUseMocks()) {
    await new Promise((r) => setTimeout(r, 100));
    return { url: mockBillImageUrl(), contentType: 'image/png' };
  }
  const response = await apiClient.get(`/imports/${id}/file/`, {
    responseType: 'blob',
    timeout: IMPORT_TIMEOUT_MS,
  });
  const blob = response.data as Blob;
  return { url: URL.createObjectURL(blob), contentType: blob.type || '' };
}

/** Open an API file (needs the auth header, so it is fetched, not linked) in a new tab. */
export async function openAuthenticatedFile(apiPath: string): Promise<void> {
  const response = await apiClient.get(apiPath, {
    responseType: 'blob',
    timeout: IMPORT_TIMEOUT_MS,
  });
  const url = URL.createObjectURL(response.data as Blob);
  window.open(url, '_blank', 'noopener');
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function markProductsReviewed(ids: number[]): Promise<{ updated: number }> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/products/mark-reviewed/', { ids });
    return unwrapData<{ updated: number }>(data);
  }, { updated: ids.length });
}

export async function answerImportClarifications(
  id: number | string,
  answers: Record<string, string>,
): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/imports/${id}/clarify/`, { answers });
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id),
    kind: 'PURCHASE_BILL',
    status: 'PREVIEWED',
    totalRows: 0,
    validRows: 0,
    errorRows: 0,
    preview: { lines: [] },
  });
}

export async function commitImport(
  id: number | string,
  payload?: Record<string, unknown>,
  options?: { idempotencyKey?: string },
): Promise<ImportJob | PurchaseBillCommitResult> {
  return withMocks(async () => {
    const key = options?.idempotencyKey ?? `import-commit-${id}-${newIdempotencyKey()}`;
    const { data } = await apiClient.post(`/imports/${id}/commit/`, payload ?? {}, {
      headers: idempotencyHeaders(key),
      timeout: IMPORT_TIMEOUT_MS,
    });
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

export async function voidImport(id: number | string): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.post(
      `/imports/${id}/void/`,
      {},
      {
        headers: idempotencyHeaders(),
        timeout: IMPORT_TIMEOUT_MS,
      },
    );
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id),
    kind: 'PRODUCTS',
    status: 'VOIDED',
    totalRows: 0,
    validRows: 0,
    errorRows: 0,
    preview: [],
  });
}

export async function voidImportRows(
  id: number | string,
  skus: string[],
): Promise<ImportJob> {
  return withMocks(async () => {
    const { data } = await apiClient.post(
      `/imports/${id}/void-rows/`,
      { skus },
      {
        headers: idempotencyHeaders(),
        timeout: IMPORT_TIMEOUT_MS,
      },
    );
    return unwrapData<ImportJob>(data);
  }, {
    id: Number(id),
    kind: 'PRODUCTS',
    status: 'COMMITTED',
    totalRows: 0,
    validRows: 0,
    errorRows: 0,
    preview: [],
    voidedRows: skus.map((sku) => ({ sku })),
  });
}

export async function downloadImportErrorsCsv(id: number | string, kind: string): Promise<void> {
  const response = await apiClient.get(`/imports/${id}/errors/`, {
    params: { as: 'csv' },
    responseType: 'blob',
    timeout: IMPORT_TIMEOUT_MS,
    transformResponse: [(d) => d],
  });
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${kind.toLowerCase()}_import_errors.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadImportTemplate(kind = 'PRODUCTS', format: 'xlsx' | 'csv' = 'xlsx'): Promise<void> {
  const response = await apiClient.get('/imports/template/', {
    params: { kind, as: format === 'csv' ? 'csv' : undefined },
    responseType: 'blob',
    timeout: IMPORT_TIMEOUT_MS,
    transformResponse: [(d) => d],
  });
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], {
          type:
            format === 'csv'
              ? 'text/csv;charset=utf-8'
              : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download =
    format === 'csv' ? `${kind.toLowerCase()}_template.csv` : `${kind.toLowerCase()}_import_template.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

export const listBankAccounts = () =>
  withMocks(
    () => fetchAllPagesMasters<import('@/types/domain').BankAccount>('/payments/bank-accounts/'),
    mockBankAccounts,
  );
export const createBankAccount = (payload: Record<string, unknown>) =>
  apiClient.post('/payments/bank-accounts/', payload).then(({ data }) => unwrapData<import('@/types/domain').BankAccount>(data));
export const updateBankAccount = (id: number, payload: Record<string, unknown>) =>
  apiClient.patch(`/payments/bank-accounts/${id}/`, payload).then(({ data }) => unwrapData<import('@/types/domain').BankAccount>(data));

export const getUpiQr = (payload: Record<string, unknown>) => apiClient.post('/payments/upi-qr/', payload).then(({ data }) => unwrapData<Record<string, string>>(data));
export async function downloadCashBookXlsx(params?: Record<string, string>): Promise<{ url: string }> {
  const response = await apiClient.get('/reports/cash-book/', {
    responseType: 'blob',
    transformResponse: [(d) => d],
    params: { ...params, export: 'xlsx' },
  });
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        });
  return { url: URL.createObjectURL(blob) };
}

export const getAccountingSettings = () => apiClient.get('/accounting/settings/').then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const postAccountingBackfill = (payload: { dry_run?: boolean; confirm?: boolean }) =>
  apiClient.post('/accounting/backfill/', payload).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const getAccountingBackfillStatus = () =>
  apiClient.get('/accounting/backfill/').then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const updateAccountingSettings = (payload: Record<string, unknown>) => apiClient.post('/accounting/settings/', payload).then(({ data }) => unwrapData(data));
export const closeFinancialYear = (payload: { fyEnd: string; confirm: boolean }) =>
  apiClient.post('/accounting/fy-close/', payload).then(({ data }) => unwrapData(data));
export const previewFinancialYearClose = (fyEnd: string) =>
  apiClient.get('/accounting/fy-close/', { params: { fy_end: fyEnd } }).then(({ data }) => unwrapData<FyClosePreview>(data));
export const reverseFinancialYearClose = (payload: { fyEnd: string; reason: string }) =>
  apiClient.post('/accounting/fy-close/', { ...payload, reverse: true }).then(({ data }) => unwrapData(data));
export type FyClosePreview = {
  fyStart: string;
  fyEnd: string;
  income: string;
  expense: string;
  netProfit: string;
  movesToAccount: string;
  draftInvoices: number;
  periods: Array<{ id: number; name: string; status: string }>;
  blockers: string[];
  canClose: boolean;
  alreadyClosed: boolean;
  journalId: number | null;
};
export type CloseBlocker = { code: string; severity: string; message: string; title: string; fixPath: string; count?: number };
export type CloseReadiness = {
  period: number;
  name: string;
  status: string;
  gstStatus: string;
  earlierOpenPeriod: { id: number; name: string } | null;
  blockers: CloseBlocker[];
  advisory: CloseBlocker[];
  canSoftClose: boolean;
  canClose: boolean;
  canReopen: boolean;
};
export type CloseSummaryRow = {
  id: number;
  name: string;
  startDate: string;
  endDate: string;
  status: string;
  gstStatus: string;
  blockerCount: number | null;
  blockedByEarlier: boolean;
};
export const listAccounts = () =>
  withMocks(
    () => fetchAllPagesMasters<import('@/types/domain').AccountingAccount>('/accounting/accounts/'),
    mockAccountingAccounts,
  );
export type ChartAccount = {
  id: number;
  code: string;
  name: string;
  type: string;
  parent: number | null;
  parentName: string;
  isSystem: boolean;
  isControl: boolean;
  bankAccount: number | null;
  isActive: boolean;
  hasPostings: boolean;
  balance: string | null;
};
export const listChartAccounts = (params?: Record<string, string>) =>
  fetchAllPagesMasters<ChartAccount>('/accounting/accounts/', { with_balance: '1', ...params });
export const updateAccount = (id: number, payload: Record<string, unknown>) =>
  apiClient.patch(`/accounting/accounts/${id}/`, payload).then(({ data }) => unwrapData(data));
export const transferAccountBalance = (id: number, payload: { toAccount: number; entryDate?: string }) =>
  apiClient.post(`/accounting/accounts/${id}/transfer-balance/`, payload).then(({ data }) => unwrapData<{ journalId: number; number: string; amount: string }>(data));
export const exportChartAccounts = (params: Record<string, string>, file: 'csv' | 'xlsx') =>
  getBlob('/accounting/accounts/export/', { ...params, file });
export const createAccount = (payload: Record<string, unknown>) => apiClient.post('/accounting/accounts/', payload).then(({ data }) => unwrapData(data));

export async function listJournals(params?: Record<string, string>): Promise<import('@/types/domain').JournalEntry[]> {
  return withMocks(
    () => fetchAllPagesMasters<import('@/types/domain').JournalEntry>('/accounting/journals/', params),
    mockJournalEntries,
  );
}

export async function listJournalsPage(params?: PageParams): Promise<PageResult<import('@/types/domain').JournalEntry>> {
  return withMocks(
    () => fetchPage<import('@/types/domain').JournalEntry>('/accounting/journals/', params),
    () => ({ results: mockJournalEntries, count: mockJournalEntries.length, next: null, previous: null }),
  );
}
export type UnreconciledGlLine = {
  id: number;
  entryId: number;
  entryNumber: string;
  entryDate: string;
  narration: string;
  debit: string;
  credit: string;
  signedAmount?: string;
};

// F2-028: still-unreconciled GL lines for one account, resolved server-side so
// the bank-recon picker isn't limited to the most recent journals page.
export async function listUnreconciledGlLines(accountId: number | string): Promise<UnreconciledGlLine[]> {
  return fetchAllPagesMasters<UnreconciledGlLine>('/accounting/journals/unreconciled-lines/', {
    account: String(accountId),
  });
}

export const createJournal = (payload: Record<string, unknown>) => apiClient.post('/accounting/journals/', payload).then(({ data }) => unwrapData(data));
export const getJournal = (id: number) => apiClient.get(`/accounting/journals/${id}/`).then(({ data }) => unwrapData<import('@/types/domain').JournalEntry>(data));
export const updateJournal = (id: number, payload: Record<string, unknown>) => apiClient.put(`/accounting/journals/${id}/`, payload).then(({ data }) => unwrapData(data));
export const discardJournal = (id: number) => apiClient.delete(`/accounting/journals/${id}/`).then(() => undefined);
/** ACS-23: the filtered register as a CSV/XLSX blob. */
export const exportJournals = (params: Record<string, string>, file: 'csv' | 'xlsx' = 'csv') =>
  getBlob('/accounting/journals/export/', { ...params, file });
export const postJournal = (id: number) => apiClient.post(`/accounting/journals/${id}/post/`).then(({ data }) => unwrapData(data));
export const reverseJournal = (id: number) => apiClient.post(`/accounting/journals/${id}/reverse/`).then(({ data }) => unwrapData(data));
export const listCostCenters = () =>
  withMocks(() => fetchAllPagesMasters<Record<string, unknown>>('/accounting/cost-centers/'), mockCostCenters);
export type CostCenterRow = {
  id: number;
  code: string;
  name: string;
  parent: number | null;
  parentName: string;
  isActive: boolean;
  usage: { journalLines: number; invoices: number; expenses: number };
};
export const listCostCentersFull = () => fetchAllPagesMasters<CostCenterRow>('/accounting/cost-centers/');
export const updateCostCenter = (id: number, payload: Record<string, unknown>) =>
  apiClient.patch(`/accounting/cost-centers/${id}/`, payload).then(({ data }) => unwrapData(data));
export const deleteCostCenter = (id: number) => apiClient.delete(`/accounting/cost-centers/${id}/`).then(() => undefined);
export type CostCenterReport = {
  results: Array<{ costCenter: number | null; code: string; name: string; income: string; expense: string; net: string }>;
  totals: { income: string; expense: string; net: string };
};
export const getCostCenterReport = (params: { dateFrom?: string; dateTo?: string }) =>
  apiClient
    .get('/accounting/cost-centers/report/', { params: { date_from: params.dateFrom || undefined, date_to: params.dateTo || undefined } })
    .then(({ data }) => unwrapData<CostCenterReport>(data));
export const createCostCenter = (payload: Record<string, unknown>) => apiClient.post('/accounting/cost-centers/', payload).then(({ data }) => unwrapData(data));

export async function listExpensesPage(params?: PageParams) {
  return fetchPage<Record<string, unknown>>('/accounting/expenses/', params);
}

/** The register page: rows plus the total of everything the filters match (not just this page). */
export async function listExpensesRegister(params?: PageParams) {
  const { data } = await apiClient.get('/accounting/expenses/', { params: flattenQueryParams(params) });
  const body = unwrapData<{ results: Record<string, unknown>[]; count: number; filteredTotal?: string }>(data);
  return { results: body.results ?? [], count: body.count ?? 0, filteredTotal: body.filteredTotal ?? '0' };
}
export const exportExpenses = (params: Record<string, string | undefined>, file: 'csv' | 'xlsx') =>
  getBlob('/accounting/expenses/export/', { ...params, file });
export type RecurringExpense = {
  id: number;
  category: number;
  categoryName: string;
  partyName: string;
  amount: string;
  notes: string;
  paymentMode: 'CASH' | 'BANK';
  bankAccount: number | null;
  expenseAccount: number | null;
  costCenter: number | null;
  frequency: 'MONTHLY' | 'QUARTERLY' | 'YEARLY';
  nextDate: string;
  endDate: string | null;
  isActive: boolean;
  lastCreatedDate: string | null;
};
export const listRecurringExpenses = () => fetchAllPagesMasters<RecurringExpense>('/accounting/recurring-expenses/');
export const createRecurringExpense = (payload: Record<string, unknown>) =>
  apiClient.post('/accounting/recurring-expenses/', payload).then(({ data }) => unwrapData<RecurringExpense>(data));
export const updateRecurringExpense = (id: number, payload: Record<string, unknown>) =>
  apiClient.patch(`/accounting/recurring-expenses/${id}/`, payload).then(({ data }) => unwrapData<RecurringExpense>(data));
export const deleteRecurringExpense = (id: number) =>
  apiClient.delete(`/accounting/recurring-expenses/${id}/`).then(() => undefined);
export const createDueRecurringExpenses = (ids?: number[]) =>
  apiClient.post('/accounting/recurring-expenses/create-due/', { ids }).then(({ data }) =>
    unwrapData<{ created: Array<{ template: number; expense: number; date: string }>; skipped: Array<{ template: number; date: string; reason: string }> }>(data));
/** An attachment is fetched with the user's session, then handed to the browser. */
export const downloadFileAsset = (id: number) => getBlob(`/files/${id}/download/`);
export const deleteFileAsset = (id: number) => apiClient.delete(`/files/${id}/`).then(() => undefined);

export async function createExpense(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/accounting/expenses/', payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function updateExpense(id: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/accounting/expenses/${id}/`, payload);
  return unwrapData<Record<string, unknown>>(data);
}

/** ACS-16: other active expenses with the same date, amount and party. */
export async function findExpenseDuplicates(params: {
  date: string;
  amount: string;
  party?: string;
  exclude?: number;
}): Promise<{ count: number; results: Array<{ id: number; number: string; partyName: string }> }> {
  const { data } = await apiClient.get('/accounting/expenses/duplicates/', {
    params: { date: params.date, amount: params.amount, party: params.party || undefined, exclude: params.exclude },
  });
  return unwrapData(data);
}

export type ExpenseCategoryAccount = { id: number; category: number; account: number; accountName: string };

/** ACS-15: which expense ledger each category posts to. */
export async function listExpenseCategoryAccounts(): Promise<ExpenseCategoryAccount[]> {
  return fetchAllPagesMasters<ExpenseCategoryAccount>('/accounting/expense-category-accounts/');
}

export async function setExpenseCategoryAccount(payload: { category: number; account: number }) {
  const { data } = await apiClient.post('/accounting/expense-category-accounts/', payload);
  return unwrapData<ExpenseCategoryAccount>(data);
}

export type ExpensePostingPreview = {
  posted: number;
  total: string | number;
  skipped: Array<{ id: number; number: string; reason: string }>;
  dryRun: boolean;
};

/** ACS-15: post (or, with dryRun, count) the expenses that should be in the books. */
export async function postPendingExpenses(dryRun: boolean): Promise<ExpensePostingPreview> {
  const { data } = await apiClient.post('/accounting/expenses/post-pending/', { dry_run: dryRun });
  return unwrapData(data);
}

/** ACS-14: an expense is voided with a reason, never deleted. */
export async function voidExpense(id: number, reason: string) {
  const { data } = await apiClient.post(`/accounting/expenses/${id}/void/`, { reason });
  return unwrapData<Record<string, unknown>>(data);
}

export async function listFixedAssets(params?: Record<string, string>): Promise<Record<string, unknown>[]> {
  return withMocks(
    () => fetchAllPagesMasters<Record<string, unknown>>('/accounting/fixed-assets/', params),
    mockFixedAssets,
  );
}

export async function listFixedAssetsPage(params?: PageParams): Promise<PageResult<Record<string, unknown>>> {
  return withMocks(
    () => fetchPage<Record<string, unknown>>('/accounting/fixed-assets/', { pageSize: 200, ...params }),
    { results: mockFixedAssets, count: mockFixedAssets.length, next: null, previous: null },
  );
}
export type AssetSummary = {
  count: number;
  totalCost: string;
  accumulated: string;
  netBookValue: string;
  thisMonthCharge: string;
  errors: number;
  lastCompletedMonth: string;
  registerVsGl: {
    registerCost: string;
    glCost: string;
    costDifference: string;
    registerAccumulated: string;
    glAccumulated: string;
    accumulatedDifference: string;
  };
};
export type AssetPreset = { key: string; name: string; usefulLifeMonths: number; method: string; wdvAnnualRate: string };
export type ScheduleRow = { month: string; amount: string; status: 'posted' | 'missing' | 'projected'; journalId: number | null; number: string; accumulated: string };
export type DepreciationRun = {
  through: string;
  dryRun: boolean;
  posted: number;
  total: string;
  assets: Array<{ asset: number; name: string; errors: string[]; months: Array<{ month: string; amount: string; status: string }> }>;
};
export const getFixedAssetSummary = () =>
  apiClient.get('/accounting/fixed-assets/summary/').then(({ data }) => unwrapData<AssetSummary>(data));
export const getFixedAssetSchedule = (id: number) =>
  apiClient.get(`/accounting/fixed-assets/${id}/schedule/`).then(({ data }) =>
    unwrapData<{ asset: number; rows: ScheduleRow[]; disposal: { journalId: number; number: string; date: string } | null }>(data));
export const listFixedAssetPresets = () =>
  apiClient.get('/accounting/fixed-assets/presets/').then(({ data }) => unwrapData<{ results: AssetPreset[]; note: string }>(data));
export const runFixedAssetDepreciation = (payload: { month?: string; dryRun?: boolean }) =>
  apiClient.post('/accounting/fixed-assets/run-depreciation/', payload).then(({ data }) => unwrapData<DepreciationRun>(data));
export const draftAssetRegisterFix = () =>
  apiClient.post('/accounting/fixed-assets/register-check/draft/', {}).then(({ data }) => unwrapData<{ journalId: number; number: string }>(data));
export const createFixedAsset = (payload: Record<string, unknown>) => apiClient.post('/accounting/fixed-assets/', payload).then(({ data }) => unwrapData(data));
// F3-024: correct a wrong useful-life/acquisition-date entered at create time.
export const updateFixedAsset = (id: number, payload: Record<string, unknown>) => apiClient.patch(`/accounting/fixed-assets/${id}/`, payload).then(({ data }) => unwrapData(data));
export const disposeFixedAsset = (id: number, payload?: Record<string, unknown>) =>
  apiClient.post(`/accounting/fixed-assets/${id}/dispose/`, payload).then(({ data }) => unwrapData(data));
export async function listAccountingPeriods(params?: Record<string, string>): Promise<Record<string, unknown>[]> {
  return withMocks(
    () => fetchAllPagesMasters<Record<string, unknown>>('/accounting/periods/', params),
    mockAccountingPeriods,
  );
}

export async function listAccountingPeriodsPage(params?: PageParams): Promise<PageResult<Record<string, unknown>>> {
  return withMocks(
    () => fetchPage<Record<string, unknown>>('/accounting/periods/', { pageSize: 200, ...params }),
    { results: mockAccountingPeriods, count: mockAccountingPeriods.length, next: null, previous: null },
  );
}
export const getCloseSummary = () =>
  apiClient.get('/accounting/periods/close-summary/').then(({ data }) => unwrapData<{ results: CloseSummaryRow[] }>(data).results);
export const getCloseReadiness = (id: number) =>
  apiClient.get(`/accounting/periods/${id}/close-readiness/`).then(({ data }) => unwrapData<CloseReadiness>(data));
export const reopenAccountingPeriod = (id: number, reason: string) =>
  apiClient.post(`/accounting/periods/${id}/reopen/`, { reason }).then(({ data }) => unwrapData(data));
export const generateAccountingYear = (fyStartYear: number) =>
  apiClient.post('/accounting/periods/generate/', { fyStartYear }).then(({ data }) => unwrapData<{ created: string[]; skipped: string[] }>(data));
export const createAccountingPeriod = (payload: Record<string, unknown>) => apiClient.post('/accounting/periods/', payload).then(({ data }) => unwrapData(data));
export const updateAccountingPeriod = (id: number, payload: Record<string, unknown>) => apiClient.patch(`/accounting/periods/${id}/`, payload).then(({ data }) => unwrapData(data));
export const softCloseAccountingPeriod = (id: number) => apiClient.post(`/accounting/periods/${id}/soft-close/`).then(({ data }) => unwrapData(data));
export const closeAccountingPeriod = (id: number) => apiClient.post(`/accounting/periods/${id}/close/`).then(({ data }) => unwrapData(data));
export const closeAccountingAndGstPeriod = (id: number) =>
  apiClient.post(`/accounting/periods/${id}/close-period/`).then(({ data }) => unwrapData(data));
export const softCloseGstPeriod = (period: string) =>
  apiClient.post('/reports/gst-period/', { period, action: 'soft_close' }).then(({ data }) => unwrapData(data));
export async function getDailySummary(params?: { date?: string }): Promise<DailyBusinessSummary> {
  if (shouldUseMocks()) {
    return { id: 0, summaryDate: '', kpis: {}, alertCodes: [], narrative: '' };
  }
  const { data } = await apiClient.get('/insights/daily-summary/', { params });
  return unwrapData<DailyBusinessSummary>(data);
}

export async function generateDailySummary(params?: { date?: string }): Promise<DailyBusinessSummary> {
  const { data } = await apiClient.post('/insights/daily-summary/', params ?? {});
  return unwrapData<DailyBusinessSummary>(data);
}

export async function listBusinessAlerts(params?: {
  status?: string;
  severity?: string;
}): Promise<BusinessAlert[]> {
  if (shouldUseMocks()) return [];
  const { data } = await apiClient.get('/insights/alerts/', { params });
  const body = unwrapData<BusinessAlert[] | { results: BusinessAlert[] }>(data);
  return Array.isArray(body) ? body : (body.results ?? []);
}

export async function snoozeBusinessAlert(id: number, days = 7): Promise<BusinessAlert> {
  const { data } = await apiClient.post(`/insights/alerts/${id}/snooze/`, { days });
  return unwrapData<BusinessAlert>(data);
}

export async function getCashflowForecast(horizon = 14): Promise<CashflowForecast> {
  const { data } = await apiClient.get('/insights/cashflow-forecast/', { params: { horizon } });
  return unwrapData<CashflowForecast>(data);
}

export async function listGrowthHints(): Promise<GrowthHint[]> {
  if (shouldUseMocks()) return [];
  const { data } = await apiClient.get('/insights/growth-hints/');
  const body = unwrapData<{ hints: GrowthHint[] }>(data);
  return body.hints ?? [];
}

export async function listAttentionRows(options?: { mine?: boolean }): Promise<AttentionRow[]> {
  if (shouldUseMocks()) return [];
  const { data } = await apiClient.get('/insights/attention/', {
    params: options?.mine ? { mine: 1 } : undefined,
  });
  const body = unwrapData<{ rows: AttentionRow[]; count: number }>(data);
  return body.rows ?? [];
}

export async function assignAttentionRow(
  dedupeKey: string,
  assignedTo: number | null,
  dueDate: string | null,
): Promise<void> {
  await apiClient.post('/insights/attention/assign/', { dedupeKey, assignedTo, dueDate });
}

export async function snoozeAttentionRow(dedupeKey: string, reason: string, days = 7): Promise<void> {
  await apiClient.post('/insights/attention/snooze/', { dedupeKey, reason, days });
}

export async function dismissAttentionRow(dedupeKey: string, reason?: string): Promise<void> {
  await apiClient.post('/insights/attention/dismiss/', reason ? { dedupeKey, reason } : { dedupeKey });
}

export async function getLearningReport(): Promise<{
  windowDays: number;
  acted: number;
  resolvedInWindow: number;
  dismissedInWindow: number;
  metricImproved: number;
  thresholdsChanged: boolean;
}> {
  const { data } = await apiClient.get('/insights/learning-report/');
  return unwrapData(data);
}

export async function listAssistantThreads(): Promise<AssistantThread[]> {
  const { data } = await apiClient.get('/insights/assistant/threads/');
  const body = unwrapData<AssistantThread[] | { results: AssistantThread[] }>(data);
  return Array.isArray(body) ? body : (body.results ?? []);
}

export async function createAssistantThread(title = 'Chat'): Promise<AssistantThread> {
  const { data } = await apiClient.post('/insights/assistant/threads/', { title });
  return unwrapData<AssistantThread>(data);
}

export async function getAssistantThread(id: number): Promise<AssistantThread> {
  const { data } = await apiClient.get(`/insights/assistant/threads/${id}/`);
  return unwrapData<AssistantThread>(data);
}

export async function postAssistantMessage(threadId: number, content: string): Promise<AssistantMessage> {
  const { data } = await apiClient.post(`/insights/assistant/threads/${threadId}/messages/`, { content });
  return unwrapData<AssistantMessage>(data);
}

export async function confirmAssistantAction(
  messageId: number,
): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post('/insights/assistant/actions/confirm/', { messageId });
  return unwrapData(data);
}

export async function dismissAssistantAction(
  messageId: number,
): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post('/insights/assistant/actions/dismiss/', { messageId });
  return unwrapData(data);
}

export async function uploadTallyMasters(file: File): Promise<{
  syncRunId: number;
  preview: Record<string, unknown>;
}> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post('/integrations/tally/upload/', form);
  const body = unwrapData<{
    syncRunId?: number;
    sync_run_id?: number;
    preview: Record<string, unknown>;
  }>(data);
  return {
    syncRunId: body.syncRunId ?? body.sync_run_id!,
    preview: body.preview,
  };
}

export async function previewTallyImport(
  syncRunId: number,
  preview?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post('/integrations/tally/preview/', {
    syncRunId,
    ...(preview ? { preview } : {}),
  });
  return unwrapData(data);
}

export async function commitTallyImport(syncRunId: number): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post('/integrations/tally/commit/', { syncRunId });
  return unwrapData(data);
}

export async function exportTallyAid(params?: {
  dateFrom?: string;
  dateTo?: string;
}): Promise<Blob> {
  const { data } = await apiClient.get('/integrations/tally/export/', {
    params,
    responseType: 'blob',
  });
  return data as Blob;
}

