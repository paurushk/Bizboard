import { apiClient, unwrapData } from '@/api/client';
import { fetchPage } from '@/api/resources';
import { apiPath } from '@/api/typedClient';

export type ItcEligibility = 'UNREVIEWED' | 'CLAIMABLE' | 'INELIGIBLE' | 'REVERSED';
export type ImsAction = 'NO_ACTION' | 'ACCEPT' | 'REJECT' | 'PENDING';

export type Gstr2bRow = {
  id: number;
  period: string;
  supplierGstin: string;
  invoiceNumber: string;
  invoiceDate?: string | null;
  taxableValue: string | number;
  igst: string | number;
  cgst: string | number;
  sgst: string | number;
  cess?: string | number;
  matchStatus: string;
  matchClass?: string;
  itcEligibility: ItcEligibility;
  imsAction?: ImsAction;
  imsRemark?: string;
  actedAt?: string | null;
  section164Deadline?: string | null;
  section16_4Deadline?: string | null;
  purchaseInvoice?: number | null;
};

export type ImsSummary = {
  period: string;
  totalItc?: string;
  matchedItc?: string;
  unresolvedItc?: string;
  itcAtRisk?: string;
  itcAtRiskPaise?: number;
  expiringItc?: string;
  expiringCount?: number;
  ineligibleItc?: string;
  rowCount?: number;
  total_itc?: string;
  matched_itc?: string;
  unresolved_itc?: string;
  itc_at_risk?: string;
  expiring_itc?: string;
  expiring_count?: number;
};

export type SupplierScorecardRow = {
  supplierGstin?: string;
  supplierName?: string;
  supplierId?: number | null;
  purchaseValue?: string;
  mismatchCount?: number;
  rejections?: number;
  itcAffected?: string;
  averageCorrectionDays?: number;
  supplier_gstin?: string;
  supplier_name?: string;
  purchase_value?: string;
  mismatch_count?: number;
  itc_affected?: string;
};

export type SupplierDefectMessage = {
  text: string;
  supplierName?: string;
  supplierId?: number | null;
  phone?: string;
  defect?: string;
  ingestId?: number;
};

const BASE = apiPath('/reports/gstr2b/');

export function listGstr2bPage(params?: {
  period?: string;
  page?: number;
  pageSize?: number;
  imsAction?: string;
  matchClass?: string;
}) {
  return fetchPage<Gstr2bRow>(BASE, {
    period: params?.period,
    page: params?.page,
    pageSize: params?.pageSize,
    ims_action: params?.imsAction,
    match_class: params?.matchClass,
  });
}

export async function patchGstr2bEligibility(id: number, itcEligibility: ItcEligibility) {
  const { data } = await apiClient.patch(`/reports/gstr2b/${id}/`, { itcEligibility });
  return unwrapData<Gstr2bRow>(data);
}

export async function fetchMissingDocuments(period: string) {
  const { data } = await apiClient.get('/reports/gstr2b/missing-documents/', { params: { period } });
  return unwrapData<{ period: string; count: number; items: Record<string, unknown>[] }>(data);
}

export async function chaseMissingWhatsApp(period: string, phone = '') {
  const { data } = await apiClient.post('/reports/gstr2b/chase-whatsapp/', { period, phone });
  return unwrapData<{ count: number; shareLink?: string; share_link?: string; mode: string }>(data);
}

export async function chaseMissingPhoto(id: number, file: File) {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post(`/reports/gstr2b/${id}/chase-photo/`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return unwrapData<Record<string, unknown>>(data);
}

export async function matchGstr2b(period: string) {
  const { data } = await apiClient.post('/reports/gstr2b/match/', { period });
  return unwrapData(data);
}

export async function fetchImsSummary(period: string) {
  const { data } = await apiClient.get('/reports/gstr2b/ims-summary/', { params: { period } });
  return unwrapData<ImsSummary>(data);
}

export async function fetchImsScorecard(period: string) {
  const { data } = await apiClient.get('/reports/gstr2b/ims-scorecard/', { params: { period } });
  return unwrapData<{ period: string; suppliers: SupplierScorecardRow[] }>(data);
}

export async function actImsRow(id: number, action: ImsAction, remark = '') {
  const { data } = await apiClient.post(`/reports/gstr2b/${id}/ims-act/`, { action, remark });
  return unwrapData<Gstr2bRow>(data);
}

export async function bulkAcceptExact(period: string) {
  const { data } = await apiClient.post('/reports/gstr2b/ims-bulk-accept/', { period });
  return unwrapData<{ accepted: number; chunks: number; chunkSize?: number }>(data);
}

export async function fetchSupplierMessage(id: number) {
  const { data } = await apiClient.post(`/reports/gstr2b/${id}/supplier-message/`, {});
  return unwrapData<SupplierDefectMessage>(data);
}

export async function importImsOffline(payload: unknown, replace = false) {
  const { data } = await apiClient.post('/reports/gstr2b/ims-offline-import/', { payload, replace });
  return unwrapData<{ period: string; created: number }>(data);
}

export async function exportImsOffline(period: string) {
  const { data } = await apiClient.get('/reports/gstr2b/ims-offline-export/', { params: { period } });
  return unwrapData<Record<string, unknown>>(data);
}

export function money(summary: ImsSummary | undefined, camel: keyof ImsSummary, snake: keyof ImsSummary) {
  if (!summary) return '0';
  const v = summary[camel] ?? summary[snake];
  return v == null ? '0' : String(v);
}

export function rowDeadline(row: Gstr2bRow): string {
  return row.section164Deadline || row.section16_4Deadline || '—';
}
