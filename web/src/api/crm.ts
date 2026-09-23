import { apiClient, idempotencyHeaders, unwrapData } from '@/api/client';
import { fetchPage } from '@/api/resources';
import { apiPath, type SchemaOr } from '@/api/typedClient';

export type Lead = SchemaOr<
  'Lead',
  {
    id: number;
    name: string;
    phone: string;
    email: string;
    status: string;
    customer: number | null;
    createdAt: string;
    updatedAt: string;
  }
> & {
  source?: string | null;
  message?: string;
  assignedTo?: number | null;
  dedupeReview?: string;
  dedupeCandidates?: { customers?: number[]; leads?: number[] };
};

export type LeadActivity = {
  id: number;
  kind: 'NOTE' | 'CALL' | 'EMAIL' | string;
  body: string;
  createdAt: string;
  createdBy: number | null;
};

export type LeadConvertResult = {
  lead: Lead;
  opportunity: Opportunity;
};

export type Opportunity = SchemaOr<
  'Opportunity',
  {
    id: number;
    lead: number | null;
    customer: number | null;
    title: string;
    amount: string;
    stage: string;
    createdAt: string;
    updatedAt: string;
  }
>;

const BASE = apiPath('/crm');

export function listLeadsPage(params?: {
  page?: number;
  pageSize?: number;
  source?: string;
  dedupe_review?: string;
  mine?: boolean;
}) {
  return fetchPage<Lead>(`${BASE}/leads/`, params);
}

export async function createLead(payload: Partial<Lead> & { dedupeDecision?: string }): Promise<Lead> {
  const { data } = await apiClient.post(`${BASE}/leads/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<Lead>(data);
}

export async function updateLead(id: number, payload: Partial<Lead>): Promise<Lead> {
  const { data } = await apiClient.patch(`${BASE}/leads/${id}/`, payload);
  return unwrapData<Lead>(data);
}

export async function convertLead(
  id: number,
  opts: { won?: boolean; amount?: number | string } = {},
): Promise<LeadConvertResult> {
  const { data } = await apiClient.post(
    `${BASE}/leads/${id}/convert/`,
    { won: opts.won ? 1 : 0, amount: opts.amount ?? 0 },
    { headers: idempotencyHeaders() },
  );
  return unwrapData<LeadConvertResult>(data);
}

export async function listLeadActivities(leadId: number): Promise<LeadActivity[]> {
  const { data } = await apiClient.get(`${BASE}/leads/${leadId}/activities/`);
  const body = unwrapData<LeadActivity[] | { results: LeadActivity[] }>(data);
  return Array.isArray(body) ? body : body.results ?? [];
}

export async function createLeadActivity(
  leadId: number,
  payload: { kind: string; body: string },
): Promise<LeadActivity> {
  const { data } = await apiClient.post(`${BASE}/leads/${leadId}/activities/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<LeadActivity>(data);
}

export function listOpportunitiesPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<Opportunity>(`${BASE}/opportunities/`, params);
}

export async function createOpportunity(payload: Partial<Opportunity>): Promise<Opportunity> {
  const { data } = await apiClient.post(`${BASE}/opportunities/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<Opportunity>(data);
}

export async function updateOpportunity(
  id: number,
  payload: Partial<Opportunity>,
): Promise<Opportunity> {
  const { data } = await apiClient.patch(`${BASE}/opportunities/${id}/`, payload);
  return unwrapData<Opportunity>(data);
}

export async function assignLead(id: number, assignedTo: number | null): Promise<Lead> {
  const { data } = await apiClient.post(`${BASE}/leads/${id}/assign/`, { assignedTo });
  return unwrapData<Lead>(data);
}

export async function importLeadsCsv(file: File): Promise<{ created: number; pendingReview: number; errors: Array<{ row: number; detail: string }>; accepted?: boolean }> {
  const body = new FormData();
  body.append('file', file);
  const { data } = await apiClient.post(`${BASE}/leads/import-csv/`, body);
  let job = unwrapData<{ id: number; status: string; result: { created: number; pendingReview: number; errors: Array<{ row: number; detail: string }> }; error: string }>(data);
  for (let attempt = 0; attempt < 60 && (job.status === 'PENDING' || job.status === 'RUNNING'); attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const next = await apiClient.get(`${BASE}/leads/ingest-jobs/${job.id}/`);
    job = unwrapData(next.data);
  }
  if (job.status === 'FAILED') {
    throw new Error(job.error || 'Import failed');
  }
  if (job.status !== 'DONE') {
    return { created: 0, pendingReview: 0, errors: [], accepted: true };
  }
  return job.result;
}

export async function issueLeadFormToken(): Promise<{ token: string }> {
  const { data } = await apiClient.post(`${BASE}/leads/form-token/`, {});
  return unwrapData(data);
}

export async function createQuotationFromOpportunity(id: number): Promise<{ id: number; customer: number; opportunity: number }> {
  const { data } = await apiClient.post(`${BASE}/opportunities/${id}/quotation/`, {}, {
    headers: idempotencyHeaders(),
  });
  return unwrapData(data);
}
