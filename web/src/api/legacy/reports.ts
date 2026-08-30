import { apiClient, unwrapData } from '../client';
import { mockCompany } from '@/mocks/data';
import type { Company, LedgerStatement, ReportResponse, BusinessHealth, BusinessHealthSnapshot } from '@/types/domain';
import { withMocks } from './common';

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
  params?: { dateFrom?: string; dateTo?: string },
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
  apiClient.get('/payments/health/').then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const getCashBook = (params?: Record<string, string>) => apiClient.get('/reports/cash-book/', { params }).then(({ data }) => unwrapData<Record<string, unknown>>(data));
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
  const { data } = await apiClient.get('/insights/health/');
  return unwrapData<BusinessHealth>(data);
}

export async function getBusinessHealthHistory(): Promise<BusinessHealthSnapshot[]> {
  const { data } = await apiClient.get('/insights/health/history/');
  return unwrapData<BusinessHealthSnapshot[]>(data);
}

