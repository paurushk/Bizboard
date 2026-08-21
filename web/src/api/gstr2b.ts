import { apiClient, unwrapData } from '@/api/client';
import { fetchPage } from '@/api/resources';
import { apiPath, type SchemaOr } from '@/api/typedClient';

export type ItcEligibility = 'UNREVIEWED' | 'CLAIMABLE' | 'INELIGIBLE' | 'REVERSED';

export type Gstr2bRow = SchemaOr<
  'Gstr2bIngest',
  {
    id: number;
    period: string;
    supplierGstin: string;
    invoiceNumber: string;
    invoiceDate?: string | null;
    taxableValue: string | number;
    igst: string | number;
    cgst: string | number;
    sgst: string | number;
    matchStatus: string;
    itcEligibility: ItcEligibility;
    purchaseInvoice?: number | null;
  }
>;

const BASE = apiPath('/reports/gstr2b/');

export function listGstr2bPage(params?: { period?: string; page?: number; pageSize?: number }) {
  return fetchPage<Gstr2bRow>(BASE, params);
}

export async function patchGstr2bEligibility(id: number, itcEligibility: ItcEligibility) {
  const { data } = await apiClient.patch(`/reports/gstr2b/${id}/`, { itcEligibility });
  return unwrapData<Gstr2bRow>(data);
}

export async function matchGstr2b(period: string) {
  const { data } = await apiClient.post('/reports/gstr2b/match/', { period });
  return data;
}
