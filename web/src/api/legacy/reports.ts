import { apiClient, shouldUseMocks, unwrapData } from '../client';
import { mockCompany, mockPaymentHealth } from '@/mocks/data';
import type { Company, LedgerStatement, ReportResponse, ReportRow, BusinessHealth, BusinessHealthSnapshot, DiscountReportResponse } from '@/types/domain';
import { getBlob, withMocks } from './common';

export async function getCustomerLedger(
  customerId: number | string,
  params?: { date_from?: string; date_to?: string },
): Promise<LedgerStatement> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/ledgers/customers/${customerId}/`, { params });
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

export async function getSupplierLedgerPdf(
  supplierId: number,
  params: { date_from?: string; date_to?: string } = {},
): Promise<Blob> {
  return getBlob(`/ledgers/suppliers/${supplierId}/pdf/`, params);
}

export async function getSupplierLedger(
  supplierId: number | string,
  params?: { date_from?: string; date_to?: string },
): Promise<LedgerStatement> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/ledgers/suppliers/${supplierId}/`, { params });
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

export async function exportReport(
  type: string,
  // BUG-616/323: the export previously ignored whatever date range was
  // applied on-screen, silently exporting the full unfiltered register.
  params?: { dateFrom?: string; dateTo?: string; warehouse?: number | string; q?: string },
): Promise<{ url: string }> {
  return withMocks(async () => {
    const reportMap: Record<string, string> = {
      sales: 'sales-register',
      purchases: 'purchase-register',
      inventory: 'inventory-summary',
      customers: 'customers',
      suppliers: 'suppliers',
    };
    const report = reportMap[type] ?? type;
    const response = await apiClient.get(`/exports/${report}/`, {
      responseType: 'blob',
      // CSV bypasses the JSON envelope renderer
      transformResponse: [(d) => d],
      params: {
        date_from: params?.dateFrom || undefined,
        date_to: params?.dateTo || undefined,
        warehouse: params?.warehouse || undefined,
        q: params?.q || undefined,
      },
    });
    const blob =
      response.data instanceof Blob
        ? response.data
        : new Blob([response.data as BlobPart], { type: 'text/csv' });
    return { url: URL.createObjectURL(blob) };
  }, { url: '#' });
}

export async function getInventorySummary(): Promise<ReportResponse> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/inventory-summary/');
    return unwrapData<ReportResponse>(data);
  }, { rows: [] });
}

export async function getCmp08(params: { period: string }): Promise<Record<string, unknown>> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/cmp08/', { params: { period: params.period } });
    return unwrapData<Record<string, unknown>>(data);
  }, {
    period: params.period,
    aid_kind: 'composition_cmp08',
    table_1_outward_taxable: '0',
    table_2_inward_rcm_taxable: '0',
    table_2_inward_rcm_tax: '0',
    table_3_tax_payable: '0',
    composition_rate: '0.01',
    disclaimer: 'CMP-08 aid (mock).',
  });
}

export async function getGstr4(params: { fy: string }): Promise<Record<string, unknown>> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/gstr4/', { params: { fy: params.fy } });
    return unwrapData<Record<string, unknown>>(data);
  }, {
    fy: params.fy,
    aid_kind: 'composition_gstr4',
    supported: false,
    disclaimer: 'GSTR-4 worksheet aid — not a portal-complete annual return.',
    tables: {
      note: 'GSTR-4 tables are not implemented — this is a composition worksheet stub, not a portal file.',
    },
  });
}

export async function getGstReturn(
  kind: 'gstr1' | 'gstr3b' | 'gstr6' | 'gstr7' | 'gstr8',
  params: { period: string; persist?: boolean; companyGstin?: string | number },
): Promise<Record<string, unknown>> {
  return withMocks(async () => {
    const queryParams: Record<string, string> = {
      period: params.period,
      format: 'json',
    };
    if (params.persist) queryParams.persist = '1';
    if (params.companyGstin != null && params.companyGstin !== '') {
      queryParams.company_gstin = String(params.companyGstin);
    }
    const { data } = await apiClient.get(`/reports/${kind}/`, { params: queryParams });
    return unwrapData<Record<string, unknown>>(data);
  }, {
    period: params.period,
    b2b: [],
    b2cl: [],
    b2cs: [],
    cdnr: [],
    docs: {},
    totals: {},
    outwardSupplies: {},
    issues: [],
  });
}

export async function downloadGstReturn(
  kind: 'gstr1' | 'gstr3b',
  params: { period: string; format: 'json' | 'xlsx'; companyGstin?: string | number },
): Promise<{ url: string }> {
  return withMocks(async () => {
    if (params.format === 'json') {
      const payload = await getGstReturn(kind, {
        period: params.period,
        persist: true,
        companyGstin: params.companyGstin,
      });
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      return { url: URL.createObjectURL(blob) };
    }
    const queryParams: Record<string, string> = {
      period: params.period,
      format: 'xlsx',
      persist: '1',
    };
    if (params.companyGstin != null && params.companyGstin !== '') {
      queryParams.company_gstin = String(params.companyGstin);
    }
    const response = await apiClient.get(`/reports/${kind}/`, {
      params: queryParams,
      responseType: 'blob',
      transformResponse: [(d) => d],
    });
    const blob =
      response.data instanceof Blob
        ? response.data
        : new Blob([response.data as BlobPart], {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          });
    return { url: URL.createObjectURL(blob) };
  }, { url: '#' });
}

export async function getGstHealth(params: { period: string }): Promise<{
  period: string;
  summary: { critical?: number; warning?: number; info?: number };
  alerts: Array<{
    code: string;
    severity: string;
    message: string;
    documentType?: string;
    documentId?: number;
    number?: string;
  }>;
}> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/gst-health/', { params });
    return unwrapData(data);
  }, {
    period: params.period,
    summary: { critical: 0, warning: 1, info: 2 },
    alerts: [
      {
        code: 'MOCK_GST_HEALTH',
        severity: 'info',
        message: 'Mock GST health check — no issues in demo mode.',
      },
    ],
  });
}

export async function downloadGstCaPack(params: {
  period: string;
  companyGstin?: string | number;
}): Promise<{ url: string }> {
  const queryParams: Record<string, string> = { period: params.period };
  if (params.companyGstin != null && params.companyGstin !== '') {
    queryParams.company_gstin = String(params.companyGstin);
  }
  const response = await apiClient.get('/reports/gst-ca-pack/', {
    params: queryParams,
    responseType: 'blob',
    transformResponse: [(d) => d],
  });
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], { type: 'application/zip' });
  return { url: URL.createObjectURL(blob) };
}

export async function getGstr9(params: { fy: string }): Promise<Record<string, unknown>> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/reports/gstr9/', {
      params: { fy: params.fy, format: 'json' },
    });
    return unwrapData(data);
  }, {
    fy: params.fy,
    annual: {
      outwardTaxable: '0',
      outwardTax: '0',
    },
  });
}

export async function downloadGstr9(params: {
  fy: string;
  format: 'json' | 'xlsx';
}): Promise<{ url: string }> {
  if (params.format === 'json') {
    const payload = await getGstr9({ fy: params.fy });
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    return { url: URL.createObjectURL(blob) };
  }
  const response = await apiClient.get('/reports/gstr9/', {
    params: { fy: params.fy, format: 'xlsx' },
    responseType: 'blob',
    transformResponse: [(d) => d],
  });
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        });
  return { url: URL.createObjectURL(blob) };
}

export interface CompanyGstinVerification {
  valid: boolean;
  status: string;
  tradeName?: string;
}

export async function verifyCompanyGstin() {
  return withMocks<CompanyGstinVerification>(async () => {
    const { data } = await apiClient.post('/company/verify-gstin/');
    return unwrapData<CompanyGstinVerification>(data);
  }, { valid: true, status: 'ACTIVE', tradeName: mockCompany.name });
}

export async function verifyCompanyPan() {
  const { data } = await apiClient.post('/company/verify-pan/');
  return unwrapData<Company>(data);
}

export async function verifyCompanyUdyam() {
  const { data } = await apiClient.post('/company/verify-udyam/');
  return unwrapData<Company>(data);
}

export const getPaymentHealth = () =>
  withMocks(
    () => apiClient.get('/payments/health/').then(({ data }) => unwrapData<Record<string, unknown>>(data)),
    mockPaymentHealth,
  );
export const getCashBook = (params?: Record<string, string>) => apiClient.get('/reports/cash-book/', { params }).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const getSalesDiscountReport = (params?: Record<string, string>) =>
  apiClient.get('/reports/sales-discounts/', { params }).then(({ data }) => unwrapData<DiscountReportResponse>(data));
export type TdsReceivableRow = {
  receiptId: number;
  receiptNumber: string;
  receiptDate: string;
  customerId: number;
  customer: string;
  pan: string;
  section: string;
  amountReceived: string;
  tdsDeducted: string;
  tdsApplied: string;
  tdsUnapplied: string;
  /** Set when the customer's TDS certificate (Form 16A) arrived; bookkeeping only. */
  certificateReceivedOn: string | null;
  certificateRef: string;
};
export const getTdsReceivableReport = (params?: Record<string, string>) =>
  apiClient
    .get('/reports/tds-receivable/', { params })
    .then(({ data }) => unwrapData<{ rows: TdsReceivableRow[]; totalTds: string; count: number }>(data));
export async function exportTdsReceivableCsv(params?: Record<string, string>): Promise<Blob> {
  const { data } = await apiClient.get('/reports/tds-receivable/export/', { params, responseType: 'blob' });
  return data as Blob;
}
export const getPurchaseDiscountReport = (params?: Record<string, string>) =>
  apiClient.get('/reports/purchase-discounts/', { params }).then(({ data }) => unwrapData<DiscountReportResponse>(data));
export const getInvoiceProfitReport = (params?: Record<string, string>) =>
  apiClient.get('/reports/invoice-profit/', { params }).then(({ data }) => unwrapData<ReportResponse>(data));
export const getInvoiceProfitRollup = (groupBy: string, params?: Record<string, string>) =>
  apiClient
    .get('/reports/invoice-profit/rollup/', { params: { ...params, group_by: groupBy } })
    .then(({ data }) => unwrapData<{ rows: ReportRow[] }>(data));
export const getAccountingReport = (report: 'trial-balance' | 'profit-and-loss' | 'balance-sheet' | 'books-health', params?: Record<string, string>) =>
  apiClient.get(`/accounting/${report}/`, { params }).then(({ data }) => unwrapData<Record<string, unknown>>(data));

export async function downloadAccountingReport(
  report: 'trial-balance' | 'profit-and-loss' | 'balance-sheet',
  params?: Record<string, string>,
): Promise<{ url: string }> {
  const response = await apiClient.get(`/accounting/${report}/`, {
    params: { ...params, format: 'xlsx' },
    responseType: 'blob',
    transformResponse: [(d) => d],
  });
  if (response.data instanceof Blob && response.data.type?.includes('application/json')) {
    const text = await response.data.text();
    try {
      const parsed = JSON.parse(text);
      throw new Error(parsed.detail || parsed.message || 'Report download failed');
    } catch (e) {
      if (e instanceof Error && e.message !== 'Report download failed') throw e;
    }
  }
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        });
  return { url: URL.createObjectURL(blob) };
}

// ---- Phase 6 Insights ----

export async function downloadTdsWorksheet(period: string): Promise<Blob> {
  const { data } = await apiClient.get('/reports/tds-worksheet/', { params: { period }, responseType: 'blob' });
  return data instanceof Blob ? data : new Blob([data as BlobPart], { type: 'text/csv' });
}

export async function downloadTcsWorksheet(period: string): Promise<Blob> {
  const { data } = await apiClient.get('/reports/tcs-worksheet/', { params: { period }, responseType: 'blob' });
  return data instanceof Blob ? data : new Blob([data as BlobPart], { type: 'text/csv' });
}

export async function getBusinessHealth(): Promise<BusinessHealth> {
  if (shouldUseMocks()) {
    return { score: 0, grade: '', factors: [], limitedData: true, asOf: '' };
  }
  const { data } = await apiClient.get('/insights/health/');
  return unwrapData<BusinessHealth>(data);
}

export async function getBusinessHealthHistory(): Promise<BusinessHealthSnapshot[]> {
  const { data } = await apiClient.get('/insights/health/history/');
  return unwrapData<BusinessHealthSnapshot[]>(data);
}

export async function getDayBook(params?: { date?: string }) {
  const { data } = await apiClient.get('/reports/day-book/', { params });
  return unwrapData<Record<string, unknown>>(data);
}

export type LedgerDayBookRow = {
  id: number;
  date: string;
  voucher: string;
  entryId: number;
  voucherType: string;
  voucherTypeLabel: string;
  accountCode: string;
  accountName: string;
  party: string;
  costCenter: string;
  debit: string;
  credit: string;
  narration: string;
  status: string;
  sourceLabel: string;
  sourcePath: string | null;
};
export type LedgerDayBook = {
  dateFrom: string;
  dateTo: string;
  count: number;
  results: LedgerDayBookRow[];
  totals: { debit: string; credit: string; balanced: boolean };
  dayTotals: Array<{ date: string; debit: string; credit: string; balanced: boolean }>;
  voucherTypes: Array<{ key: string; label: string }>;
  tieOut: { trialBalanceDebit: string; trialBalanceCredit: string; ties: boolean };
  previous: string;
  next: string;
};
export async function getLedgerDayBook(params: Record<string, string | number | undefined>) {
  const { data } = await apiClient.get('/reports/day-book/ledger/', { params });
  return unwrapData<LedgerDayBook>(data);
}
export const exportLedgerDayBook = (params: Record<string, string | undefined>, file: 'csv' | 'xlsx') =>
  getBlob('/reports/day-book/ledger/', { ...params, file });

export async function getSalesSummary(params?: { date_from?: string; date_to?: string }) {
  const { data } = await apiClient.get('/reports/sales-summary/', { params });
  return unwrapData<Record<string, unknown>>(data);
}

export async function getCustomerLedgerTabs(
  customerId: number | string,
  params?: { date_from?: string; date_to?: string; txn_type?: string; status?: string },
) {
  const { data } = await apiClient.get(`/reports/customer-ledger/${customerId}/`, { params });
  return unwrapData<Record<string, unknown>>(data);
}

export async function downloadCustomerLedgerXlsx(
  customerId: number | string,
  params?: { date_from?: string; date_to?: string; txn_type?: string; status?: string },
): Promise<Blob> {
  const { data } = await apiClient.get(`/reports/customer-ledger/${customerId}/`, {
    params: { ...params, export: 'xlsx' },
    responseType: 'blob',
  });
  return data as Blob;
}


export interface Gstr9FilingDate {
  fy: string;
  filedOn: string | null;
  noteDeadline: string;
}

function toFilingDate(raw: Record<string, unknown>): Gstr9FilingDate {
  return {
    fy: String(raw.fy ?? ''),
    filedOn: (raw.filed_on ?? raw.filedOn ?? null) as string | null,
    noteDeadline: String(raw.note_deadline ?? raw.noteDeadline ?? ''),
  };
}

/** Sec 34(2): when the annual return for a financial year was filed (null until recorded). */
export async function getGstr9FilingDate(fy: string): Promise<Gstr9FilingDate> {
  const { data } = await apiClient.get('/reports/gstr9/filing-date/', { params: { fy } });
  return toFilingDate(unwrapData<Record<string, unknown>>(data));
}

export async function setGstr9FilingDate(fy: string, filedOn: string | null): Promise<Gstr9FilingDate> {
  const { data } = await apiClient.put('/reports/gstr9/filing-date/', { fy, filed_on: filedOn });
  return toFilingDate(unwrapData<Record<string, unknown>>(data));
}
