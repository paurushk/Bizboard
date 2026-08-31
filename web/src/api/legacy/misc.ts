import { apiClient, idempotencyHeaders, newIdempotencyKey, unwrapData } from '../client';
import { mockSearchResults } from '@/mocks/data';
import type { ImportJob, ImportKind, PurchaseBillCommitResult, SearchResult, AssistantMessage, AssistantThread, AttentionRow, BusinessAlert, CashflowForecast, DailyBusinessSummary, GrowthHint } from '@/types/domain';
import { withMocks, fetchPage, fetchMoneyListFirstPage, fetchAllPagesMasters, type PageResult, type PageParams } from './common';

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
  extra?: { supplierId?: number; customerId?: number; idempotencyKey?: string },
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
    customerId?: number | null;
    supplierName?: string;
    customerName?: string;
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
      customerName: payload.customerName,
      billNumber: payload.billNumber,
      billDate: payload.billDate,
      lines: (payload.lines ?? []) as never,
    },
    supplier: payload.supplierId ?? null,
    customer: payload.customerId ?? null,
  });
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
  fetchAllPagesMasters<import('@/types/domain').BankAccount>('/payments/bank-accounts/');
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
export const updateAccountingSettings = (payload: Record<string, unknown>) => apiClient.post('/accounting/settings/', payload).then(({ data }) => unwrapData(data));
export const closeFinancialYear = (payload: { fyEnd: string; confirm: boolean }) =>
  apiClient.post('/accounting/fy-close/', payload).then(({ data }) => unwrapData(data));
export const listAccounts = () => fetchAllPagesMasters<import('@/types/domain').AccountingAccount>('/accounting/accounts/');
export const createAccount = (payload: Record<string, unknown>) => apiClient.post('/accounting/accounts/', payload).then(({ data }) => unwrapData(data));

export async function listJournals(params?: Record<string, string>): Promise<import('@/types/domain').JournalEntry[]> {
  return fetchMoneyListFirstPage<import('@/types/domain').JournalEntry>('/accounting/journals/', params);
}

export async function listJournalsPage(params?: PageParams): Promise<PageResult<import('@/types/domain').JournalEntry>> {
  return fetchPage<import('@/types/domain').JournalEntry>('/accounting/journals/', params);
}
export const createJournal = (payload: Record<string, unknown>) => apiClient.post('/accounting/journals/', payload).then(({ data }) => unwrapData(data));
export const postJournal = (id: number) => apiClient.post(`/accounting/journals/${id}/post/`).then(({ data }) => unwrapData(data));
export const reverseJournal = (id: number) => apiClient.post(`/accounting/journals/${id}/reverse/`).then(({ data }) => unwrapData(data));
export const listCostCenters = () => fetchAllPagesMasters<Record<string, unknown>>('/accounting/cost-centers/');
export const createCostCenter = (payload: Record<string, unknown>) => apiClient.post('/accounting/cost-centers/', payload).then(({ data }) => unwrapData(data));

export async function listFixedAssets(params?: Record<string, string>): Promise<Record<string, unknown>[]> {
  return fetchMoneyListFirstPage<Record<string, unknown>>('/accounting/fixed-assets/', params);
}

export async function listFixedAssetsPage(params?: PageParams): Promise<PageResult<Record<string, unknown>>> {
  return fetchPage<Record<string, unknown>>('/accounting/fixed-assets/', params);
}
export const createFixedAsset = (payload: Record<string, unknown>) => apiClient.post('/accounting/fixed-assets/', payload).then(({ data }) => unwrapData(data));
export const disposeFixedAsset = (id: number) => apiClient.post(`/accounting/fixed-assets/${id}/dispose/`).then(({ data }) => unwrapData(data));
export async function listAccountingPeriods(params?: Record<string, string>): Promise<Record<string, unknown>[]> {
  return fetchMoneyListFirstPage<Record<string, unknown>>('/accounting/periods/', params);
}

export async function listAccountingPeriodsPage(params?: PageParams): Promise<PageResult<Record<string, unknown>>> {
  return fetchPage<Record<string, unknown>>('/accounting/periods/', params);
}
export const createAccountingPeriod = (payload: Record<string, unknown>) => apiClient.post('/accounting/periods/', payload).then(({ data }) => unwrapData(data));
export const updateAccountingPeriod = (id: number, payload: Record<string, unknown>) => apiClient.patch(`/accounting/periods/${id}/`, payload).then(({ data }) => unwrapData(data));
export async function getDailySummary(params?: { date?: string }): Promise<DailyBusinessSummary> {
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
  const { data } = await apiClient.get('/insights/growth-hints/');
  const body = unwrapData<{ hints: GrowthHint[] }>(data);
  return body.hints ?? [];
}

export async function listAttentionRows(): Promise<AttentionRow[]> {
  const { data } = await apiClient.get('/insights/attention/');
  const body = unwrapData<{ rows: AttentionRow[]; count: number }>(data);
  return body.rows ?? [];
}

export async function snoozeAttentionRow(dedupeKey: string, reason: string, days = 7): Promise<void> {
  await apiClient.post('/insights/attention/snooze/', { dedupeKey, reason, days });
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

