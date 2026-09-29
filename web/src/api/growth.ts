import { apiClient, idempotencyHeaders, unwrapData } from '@/api/client';
import { fetchPage, type PageParams } from '@/api/resources';

export type Campaign = {
  id: number;
  name: string;
  campaignType: string;
  status: string;
  parent: number | null;
  budget: string;
  targetRevenue: string | null;
  expectedOutcome: string;
  startDate: string | null;
  endDate: string | null;
};

export type FunnelRow = { opportunity: number; revenueSource: string; revenue: string };

export type Funnel = {
  leads: number;
  opportunities: number;
  wonOpportunities: number;
  budget: string;
  revenue: string;
  targetRevenue: string | null;
  roiRatio: string | null;
  variance: string;
  rows: FunnelRow[];
  rollup?: Funnel;
};

export type OpportunityRow = {
  id: number;
  title: string;
  stage: string;
  amount: string;
  probability: number;
  expectedCloseDate: string | null;
  customer: number | null;
  competitor?: string;
};

export type OpportunityLine = {
  id: number;
  product: number;
  description: string;
  quantity: string;
  unitPrice: string;
};

export type SupplierComplaintRow = {
  id: number;
  number: string;
  supplier: number;
  sourceInvoice: number | null;
  category: string;
  description: string;
  status: string;
  inspectionNotes: string;
  purchaseDebitNote: number | null;
  assignedTo: number | null;
};

export type ComplaintRow = {
  id: number;
  number: string;
  customer: number;
  sourceInvoice: number | null;
  category: string;
  description: string;
  status: string;
  inspectionNotes: string;
  salesReturn: number | null;
  salesCreditNote: number | null;
  replacementOrder: number | null;
  assignedTo: number | null;
};

export type TicketRow = {
  id: number;
  number: string;
  customer: number;
  subject: string;
  description: string;
  status: string;
  priority: string;
  assignedTo: number | null;
  assigneeName?: string;
  slaDueAt: string | null;
};

export type TicketComment = {
  id: number;
  body: string;
  isInternal: boolean;
  createdAt: string;
};

export type ContractRow = {
  id: number;
  number: string;
  customer: number;
  product: number | null;
  products?: number[];
  contractType: string;
  status: string;
  startDate: string;
  endDate: string;
  renewalReminderDays: number;
  value: string | null;
  notes: string;
};

export type ServiceEvent = {
  id: number;
  ticket: number | null;
  notes: string;
  occurredAt: string;
};

export type AttachmentRow = { id: number; file: number; createdAt?: string };

export type ReferralReward = {
  id: number;
  referralCode: number;
  opportunity: number;
  rewardAmount: string;
  rewardStatus: string;
  rejectionReason?: string;
  paidAt?: string | null;
};

export function listCampaignsPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<Campaign>('/crm/campaigns/', params);
}

export async function createCampaign(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/crm/campaigns/', payload);
  return unwrapData<Campaign>(data);
}

export async function updateCampaign(id: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/crm/campaigns/${id}/`, payload);
  return unwrapData<Campaign>(data);
}

export async function deleteCampaign(id: number) {
  await apiClient.delete(`/crm/campaigns/${id}/`);
}

export async function getCampaignFunnel(id: number) {
  const { data } = await apiClient.get(`/crm/campaigns/${id}/funnel/`);
  return unwrapData<Funnel>(data);
}

export function listOpportunitiesPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<OpportunityRow>('/crm/opportunities/', params);
}

export async function patchOpportunity(id: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/crm/opportunities/${id}/`, payload);
  return unwrapData<OpportunityRow>(data);
}

export function listOpportunityLines(opportunityId: number) {
  return fetchPage<OpportunityLine>(`/crm/opportunities/${opportunityId}/lines/`, { pageSize: 100 });
}

export async function createOpportunityLine(opportunityId: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.post(`/crm/opportunities/${opportunityId}/lines/`, payload);
  return unwrapData<OpportunityLine>(data);
}

export async function deleteOpportunityLine(opportunityId: number, lineId: number) {
  await apiClient.delete(`/crm/opportunities/${opportunityId}/lines/${lineId}/`);
}

export async function getForecast() {
  const { data } = await apiClient.get('/crm/opportunities/forecast/');
  return unwrapData<{ months: { month: string; amount: string }[]; unscheduled: string }>(data);
}

export async function getWonVersusInvoices(month: string) {
  const { data } = await apiClient.get('/crm/opportunities/won-versus-invoices/', { params: { month } });
  return unwrapData<{ month: string; wonAmount: string; invoicedAmount: string }>(data);
}

export async function createContractSchedule(id: number) {
  const { data } = await apiClient.post(
    `/contracts/${id}/create-schedule/`,
    {},
    { headers: idempotencyHeaders(`contract-schedule-${id}`) },
  );
  return unwrapData<{ id: number; contract: number }>(data);
}

export function listComplaintsPage(params?: PageParams) {
  return fetchPage<ComplaintRow>('/complaints/', params);
}

export async function getComplaint(id: number) {
  const { data } = await apiClient.get(`/complaints/${id}/`);
  return unwrapData<ComplaintRow>(data);
}

export async function createComplaint(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/complaints/', payload);
  return unwrapData<ComplaintRow>(data);
}

export async function updateComplaint(id: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/complaints/${id}/`, payload);
  return unwrapData<ComplaintRow>(data);
}

export async function transitionComplaint(id: number, payload: { status: string; inspection_notes?: string }) {
  const { data } = await apiClient.post(`/complaints/${id}/transition/`, payload);
  return unwrapData<ComplaintRow>(data);
}

export async function complaintDocument(id: number, kind: 'create-return' | 'create-credit-note' | 'create-replacement-order', items: Record<string, unknown>[]) {
  const { data } = await apiClient.post(`/complaints/${id}/${kind}/`, { items });
  return unwrapData<{ id: number; existing: boolean; warning?: string }>(data);
}

export function listSupplierComplaintsPage(params?: PageParams) {
  return fetchPage<SupplierComplaintRow>('/complaints/supplier/', params);
}

export async function getSupplierComplaint(id: number) {
  const { data } = await apiClient.get(`/complaints/supplier/${id}/`);
  return unwrapData<SupplierComplaintRow>(data);
}

export async function createSupplierComplaint(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/complaints/supplier/', payload);
  return unwrapData<SupplierComplaintRow>(data);
}

export async function updateSupplierComplaint(id: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/complaints/supplier/${id}/`, payload);
  return unwrapData<SupplierComplaintRow>(data);
}

export async function transitionSupplierComplaint(id: number, payload: { status: string; inspection_notes?: string }) {
  const { data } = await apiClient.post(`/complaints/supplier/${id}/transition/`, payload);
  return unwrapData<SupplierComplaintRow>(data);
}

export async function createSupplierDebitNote(id: number, items: Record<string, unknown>[]) {
  const { data } = await apiClient.post(`/complaints/supplier/${id}/create-debit-note/`, { items });
  return unwrapData<{ id: number; existing: boolean; warning?: string }>(data);
}

export async function supplierComplaintReport() {
  const { data } = await apiClient.get('/complaints/supplier/report/');
  return unwrapData<{
    byCategory: { category: string; count: number }[];
    resolved: number;
    resolvedWithDocument: number;
    resolvedWithoutDocument: number;
    averageResolutionSeconds: number | null;
  }>(data);
}

export function listSupplierComplaintAttachments(id: number) {
  return apiClient.get(`/complaints/supplier/${id}/attachments/`).then(({ data }) => unwrapData<AttachmentRow[]>(data));
}

export function uploadSupplierComplaintAttachment(id: number, file: File) {
  return uploadAttachment(`/complaints/supplier/${id}/attachments/`, file);
}

export function deleteSupplierComplaintAttachment(id: number, attachmentId: number) {
  return apiClient.delete(`/complaints/supplier/${id}/attachments/`, { params: { attachment: attachmentId } });
}

export async function complaintReport() {
  const { data } = await apiClient.get('/complaints/report/');
  return unwrapData<{
    byCategory: { category: string; count: number }[];
    resolved: number;
    resolvedWithDocument: number;
    resolvedWithoutDocument: number;
    averageResolutionSeconds: number | null;
  }>(data);
}

export function listTicketsPage(params?: PageParams) {
  return fetchPage<TicketRow>('/support/tickets/', params);
}

export async function getTicket(id: number) {
  const { data } = await apiClient.get(`/support/tickets/${id}/`);
  return unwrapData<TicketRow>(data);
}

export async function createTicket(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/support/tickets/', payload);
  return unwrapData<TicketRow>(data);
}

export async function transitionTicket(id: number, status: string) {
  const { data } = await apiClient.post(`/support/tickets/${id}/transition/`, { status });
  return unwrapData<TicketRow>(data);
}

export async function listTicketComments(id: number) {
  const { data } = await apiClient.get(`/support/tickets/${id}/comments/`);
  return unwrapData<TicketComment[]>(data);
}

export async function addTicketComment(id: number, body: string) {
  const { data } = await apiClient.post(`/support/tickets/${id}/comments/`, { body, is_internal: true });
  return unwrapData<TicketComment>(data);
}

export async function ticketReport() {
  const { data } = await apiClient.get('/support/tickets/report/');
  return unwrapData<{ byStatus: { status: string; count: number }[]; averageResolutionSeconds: number | null }>(data);
}

export function listContractsPage(params?: PageParams) {
  return fetchPage<ContractRow>('/contracts/', params);
}

export async function getContract(id: number) {
  const { data } = await apiClient.get(`/contracts/${id}/`);
  return unwrapData<ContractRow>(data);
}

export async function createContract(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/contracts/', payload);
  return unwrapData<ContractRow>(data);
}

export async function updateContract(id: number, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/contracts/${id}/`, payload);
  return unwrapData<ContractRow>(data);
}

export async function listServiceEvents(id: number) {
  const { data } = await apiClient.get(`/contracts/${id}/service-events/`);
  return unwrapData<ServiceEvent[]>(data);
}

export async function logServiceEvent(id: number, payload: { notes: string; ticket?: number }) {
  const { data } = await apiClient.post(`/contracts/${id}/service-events/`, payload);
  return unwrapData<ServiceEvent>(data);
}

export async function contractTimeline(id: number) {
  const { data } = await apiClient.get(`/contracts/${id}/timeline/`);
  return unwrapData<{ contract: ContractRow; events: ServiceEvent[] }>(data);
}

export async function contractReport() {
  const { data } = await apiClient.get('/contracts/report/');
  return unwrapData<{ status: string; contractType: string; value: string | null }[]>(data);
}

async function uploadAttachment(path: string, file: File) {
  const body = new FormData();
  body.append('file', file);
  const { data } = await apiClient.post(path, body);
  return unwrapData<AttachmentRow>(data);
}

export function listComplaintAttachments(id: number) {
  return apiClient.get(`/complaints/${id}/attachments/`).then(({ data }) => unwrapData<AttachmentRow[]>(data));
}
export function uploadComplaintAttachment(id: number, file: File) {
  return uploadAttachment(`/complaints/${id}/attachments/`, file);
}
export function deleteComplaintAttachment(id: number, attachmentId: number) {
  return apiClient.delete(`/complaints/${id}/attachments/`, { params: { attachment: attachmentId } });
}

export function listTicketAttachments(id: number) {
  return apiClient.get(`/support/tickets/${id}/attachments/`).then(({ data }) => unwrapData<AttachmentRow[]>(data));
}
export function uploadTicketAttachment(id: number, file: File) {
  return uploadAttachment(`/support/tickets/${id}/attachments/`, file);
}
export function deleteTicketAttachment(id: number, attachmentId: number) {
  return apiClient.delete(`/support/tickets/${id}/attachments/`, { params: { attachment: attachmentId } });
}

export function listContractAttachments(id: number) {
  return apiClient.get(`/contracts/${id}/attachments/`).then(({ data }) => unwrapData<AttachmentRow[]>(data));
}
export function uploadContractAttachment(id: number, file: File) {
  return uploadAttachment(`/contracts/${id}/attachments/`, file);
}
export function deleteContractAttachment(id: number, attachmentId: number) {
  return apiClient.delete(`/contracts/${id}/attachments/`, { params: { attachment: attachmentId } });
}

export async function issueReferralCode(payload: { referrer_customer?: number; referrer_user?: number; reward_type?: string; reward_value?: string }) {
  const { data } = await apiClient.post('/crm/referrals/codes/issue/', payload);
  return unwrapData<{ id: number; code: string }>(data);
}

export async function referralLeaderboard() {
  const { data } = await apiClient.get('/crm/referrals/codes/leaderboard/');
  return unwrapData<{ code: string; referrerType: string; approvedTotal: string }[]>(data);
}

export function listReferralRewards() {
  return fetchPage<ReferralReward>('/crm/referrals/rewards/', { pageSize: 100 });
}

export async function decideReferralReward(id: number, decision: 'approve' | 'reject' | 'mark-paid') {
  const headers = decision === 'mark-paid' ? idempotencyHeaders(`referral-reward-${id}`) : undefined;
  const { data } = await apiClient.post(`/crm/referrals/rewards/${id}/${decision}/`, {}, { headers });
  return unwrapData<ReferralReward>(data);
}
