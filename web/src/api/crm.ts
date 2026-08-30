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
>;

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

export function listLeadsPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<Lead>(`${BASE}/leads/`, params);
}

export async function createLead(payload: Partial<Lead>): Promise<Lead> {
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
