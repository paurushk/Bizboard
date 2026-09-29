import { apiClient, unwrapData } from '@/api/client';

export async function listJobCards() {
  const { data } = await apiClient.get('/workshop/job-cards/');
  return unwrapData<Record<string, unknown>[]>(data);
}

export async function createJobCard(payload: { customer: number; complaint?: string }) {
  const { data } = await apiClient.post('/workshop/job-cards/', payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function convertJobCard(id: number) {
  const { data } = await apiClient.post(`/workshop/job-cards/${id}/convert/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function listProjects() {
  const { data } = await apiClient.get('/projects/');
  return unwrapData<Record<string, unknown>[]>(data);
}

export async function createProject(payload: { customer: number; name: string }) {
  const { data } = await apiClient.post('/projects/', payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function invoiceMilestone(projectId: number, milestoneId: number) {
  const { data } = await apiClient.post(`/projects/${projectId}/milestones/${milestoneId}/invoice/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function markMilestoneReady(projectId: number, milestoneId: number) {
  const { data } = await apiClient.post(`/projects/${projectId}/milestones/${milestoneId}/ready/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function addMilestone(projectId: number, payload: { name: string; amount: string; serviceProduct: number }) {
  const { data } = await apiClient.post(`/projects/${projectId}/milestones/`, payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function closeProject(projectId: number) {
  const { data } = await apiClient.post(`/projects/${projectId}/close/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function listPolicyProducts() {
  const { data } = await apiClient.get('/insurance/products/');
  return unwrapData<Record<string, unknown>[]>(data);
}

export async function createPolicyProduct(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/insurance/products/', payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function advisorBook() {
  const { data } = await apiClient.get('/insurance/book/');
  return unwrapData<{ policies: unknown[]; leads: unknown[]; campaigns: unknown[] }>(data);
}

export async function createProspect(name: string) {
  const { data } = await apiClient.post('/insurance/prospects/', { name });
  return unwrapData<{ id: number; name: string }>(data);
}

export async function createOptionSet(lead: number, products: number[]) {
  const { data } = await apiClient.post('/insurance/option-sets/', { lead, products });
  return unwrapData<{ id: number; options: { id: number; product: number; chosen: boolean }[] }>(data);
}

export async function chooseOption(optionSetId: number, option: number) {
  const { data } = await apiClient.post(`/insurance/option-sets/${optionSetId}/choose/`, { option });
  return unwrapData<{ options?: { id: number; product: number; chosen: boolean }[] }>(data);
}

export async function issuePolicy(payload: { option: number; customer: number; nominee: string; startDate: string }) {
  const { data } = await apiClient.post('/insurance/policies/', payload);
  return unwrapData<Record<string, unknown>>(data);
}

export async function listSharedTickets() {
  const { data } = await apiClient.get('/support/shared/');
  return unwrapData<Record<string, unknown>[]>(data);
}

export async function shareTicket(id: number, includeDescription: boolean) {
  const { data } = await apiClient.post(`/support/tickets/${id}/share/`, { includeDescription });
  return unwrapData<Record<string, unknown>>(data);
}

export async function stopSharingTicket(id: number) {
  const { data } = await apiClient.post(`/support/tickets/${id}/stop-sharing/`);
  return unwrapData<Record<string, unknown>>(data);
}

export async function billingOps() {
  const { data } = await apiClient.get('/billing/subscription/');
  return unwrapData<Record<string, unknown>>(data);
}

export async function suspendSubscription(churnReason: string) {
  const { data } = await apiClient.post('/billing/subscription/', { action: 'suspend', churnReason });
  return unwrapData<Record<string, unknown>>(data);
}

export async function listVendorTenants() {
  const { data } = await apiClient.get('/billing/vendor/tenants/');
  return unwrapData<Record<string, unknown>[]>(data);
}
