/** Customer care, jobs and contracts API (CCJ plan). Responses arrive camel-cased; bodies go out snake-cased. */
import { apiClient, idempotencyHeaders, unwrapData } from '@/api/client';
import { fetchPage, type PageParams, type PageResult } from '@/api/legacy/common';

export type { PageResult };

type Params = PageParams & Record<string, unknown>;
type Json = Record<string, unknown>;

const send = async <T>(method: 'post' | 'patch' | 'delete', url: string, body?: Json, headers?: Record<string, string>) => {
  const { data } = await apiClient.request({ method, url, data: body, headers });
  return unwrapData<T>(data);
};
const read = async <T>(url: string, params?: Json) => {
  const { data } = await apiClient.get(url, { params });
  return unwrapData<T>(data);
};

/** Header for optimistic concurrency: the `updatedAt` the screen loaded (FND-12). */
const version = (updatedAt?: string | null) => (updatedAt ? { 'X-Expected-Updated-At': updatedAt } : undefined);

// ---- shared ------------------------------------------------------------------------------------------------------------

export type LinkItem = { kind: string; id: number; number: string; status: string; href: string; label: string };
export type TimelineRow = {
  id: number;
  action: string;
  description: string;
  metadata: Record<string, unknown>;
  userName: string;
  createdAt: string;
};
export type AttachmentRow = { id: number; file: number; createdAt?: string };

export const recordLinks = (entity: string, id: number) => read<LinkItem[]>('/links/', { entity, id });
export const recordTimeline = (entity: string, id: number) => read<TimelineRow[]>('/audit-timeline/', { entity, id });
export const careKpis = (days = 90) => read<Record<string, Record<string, unknown>>>('/care-kpis/', { days });

async function upload<T>(url: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post(url, form);
  return unwrapData<T>(data);
}
const attachmentsApi = (base: string) => ({
  list: (id: number) => read<AttachmentRow[]>(`${base}/${id}/attachments/`),
  upload: (id: number, file: File) => upload<AttachmentRow>(`${base}/${id}/attachments/`, file),
  remove: (id: number, attachmentId: number) => send<void>('delete', `${base}/${id}/attachments/?attachment=${attachmentId}`),
});

// ---- tickets ---------------------------------------------------------------------------------------------------------------

export type SlaState = 'none' | 'running' | 'paused' | 'breached' | 'met' | 'breached_resolved';
export type Ticket = {
  id: number;
  number: string;
  customer: number;
  customerName: string;
  subject: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  assignedTo: number | null;
  assigneeName: string;
  shareAvailable: boolean;
  shared: boolean;
  sharedAt: string | null;
  shareIncludesDescription: boolean;
  sourceInvoice: number | null;
  sourceInvoiceNumber: string;
  contract: number | null;
  contractNumber: string;
  slaDueAt: string | null;
  slaState: SlaState;
  slaRemainingSeconds: number | null;
  waitingSince: string | null;
  resolvedAt: string | null;
  createdAt: string;
  updatedAt: string;
};
export type TicketComment = {
  id: number;
  body: string;
  isInternal: boolean;
  fromVendor: boolean;
  authorName: string;
  createdAt: string;
};
export type TicketReport = {
  byStatus: { status: string; count: number }[];
  byPriority: { priority: string; count: number }[];
  breached: number;
  averageResolutionSeconds: number | null;
};

export const tickets = {
  list: (params?: Params) => fetchPage<Ticket>('/support/tickets/', params),
  get: (id: number) => read<Ticket>(`/support/tickets/${id}/`),
  create: (body: Json) => send<Ticket>('post', '/support/tickets/', body),
  update: (id: number, body: Json, updatedAt?: string | null) =>
    send<Ticket>('patch', `/support/tickets/${id}/`, body, version(updatedAt)),
  remove: (id: number) => send<void>('delete', `/support/tickets/${id}/`),
  transition: (id: number, status: string) => send<Ticket>('post', `/support/tickets/${id}/transition/`, { status }),
  comments: (id: number) => read<TicketComment[]>(`/support/tickets/${id}/comments/`),
  comment: (id: number, body: string) => send<TicketComment>('post', `/support/tickets/${id}/comments/`, { body }),
  share: (id: number, includeDescription: boolean) =>
    send<{ shared: boolean }>('post', `/support/tickets/${id}/share/`, { include_description: includeDescription }),
  stopSharing: (id: number) => send<{ shared: boolean }>('post', `/support/tickets/${id}/stop-sharing/`),
  report: (params?: Params) => read<TicketReport>('/support/tickets/report/', params),
  attachments: attachmentsApi('/support/tickets'),
};

export type SharedTicket = {
  id: number;
  sourceCompanyName: string;
  sourceNumber: string;
  subject: string;
  status: string;
  description?: string;
  sharedAt: string;
  replyCount: number;
};
export type VendorReply = { id: number; body: string; authorName: string; createdAt: string };
export const sharedTickets = {
  list: (params?: Params) => fetchPage<SharedTicket>('/support/shared/', params),
  get: (id: number) => read<SharedTicket>(`/support/shared/${id}/`),
  replies: (id: number) => read<VendorReply[]>(`/support/shared/${id}/replies/`),
  reply: (id: number, body: string) => send<VendorReply>('post', `/support/shared/${id}/replies/`, { body }),
};

// ---- complaints (customer and supplier) -----------------------------------------------------------------------------

export type ComplaintKind = 'customer' | 'supplier';
export type Complaint = {
  id: number;
  number: string;
  customer?: number;
  customerName?: string;
  supplier?: number;
  supplierName?: string;
  sourceInvoice: number | null;
  sourceInvoiceNumber: string;
  category: string;
  description: string;
  status: string;
  inspectionNotes: string;
  resolutionNote: string;
  salesReturn?: number | null;
  salesCreditNote?: number | null;
  replacementOrder?: number | null;
  purchaseDebitNote?: number | null;
  assignedTo: number | null;
  assigneeName: string;
  ticket?: number | null;
  ticketNumber?: string;
  resolvedAt: string | null;
  createdAt: string;
  updatedAt: string;
};
export type ComplaintReport = {
  byCategory: { category: string; count: number }[];
  byStatus: { status: string; count: number }[];
  ageing: { bucket: string; count: number }[];
  resolved: number;
  resolvedWithDocument: number;
  resolvedWithoutDocument: number;
  averageResolutionSeconds: number | null;
};
export type ComplaintDocument = 'create-return' | 'create-credit-note' | 'create-replacement-order' | 'create-debit-note';
export type ReturnableLine = {
  sourceItem: number;
  product: number;
  productName: string;
  sold: string;
  returned: string;
  returnable: string;
};

const complaintBase = (kind: ComplaintKind) => (kind === 'supplier' ? '/complaints/supplier' : '/complaints');

export const complaints = (kind: ComplaintKind) => {
  const base = complaintBase(kind);
  return {
    list: (params?: Params) => fetchPage<Complaint>(`${base}/`, params),
    get: (id: number) => read<Complaint>(`${base}/${id}/`),
    create: (body: Json) => send<Complaint>('post', `${base}/`, body),
    update: (id: number, body: Json, updatedAt?: string | null) =>
      send<Complaint>('patch', `${base}/${id}/`, body, version(updatedAt)),
    remove: (id: number) => send<void>('delete', `${base}/${id}/`),
    transition: (id: number, body: { status: string; inspection_notes?: string; resolution_note?: string }) =>
      send<Complaint>('post', `${base}/${id}/transition/`, body),
    saveNotes: (id: number, inspectionNotes: string) =>
      send<Complaint>('post', `${base}/${id}/save-notes/`, { inspection_notes: inspectionNotes }),
    unlink: (id: number, document: string) => send<Complaint>('post', `${base}/${id}/unlink-document/`, { document }),
    document: (id: number, action: ComplaintDocument, items: Json[], key?: string) =>
      send<{ id: number; existing: boolean; warning?: string }>(
        'post', `${base}/${id}/${action}/`, { items }, idempotencyHeaders(key),
      ),
    createTicket: (id: number) => send<{ id: number; existing: boolean }>('post', `${base}/${id}/create-ticket/`),
    report: (params?: Params) => read<ComplaintReport>(`${base}/report/`, params),
    activity: (id: number) => read<TimelineRow[]>(`${base}/${id}/activity/`),
    attachments: attachmentsApi(base),
  };
};

export const returnableLines = (invoiceId: number) =>
  read<ReturnableLine[]>(`/sales/invoices/${invoiceId}/returnable-lines/`);

// ---- contracts ---------------------------------------------------------------------------------------------------------------

export type ContractSchedule = {
  id: number;
  cadence: string;
  isActive: boolean;
  pausedReason: string;
  nextRunAt: string;
} | null;
export type Contract = {
  id: number;
  number: string;
  customer: number;
  customerName: string;
  product: number | null;
  products: number[];
  productNames: string[];
  contractType: string;
  startDate: string;
  endDate: string;
  daysToExpiry: number | null;
  renewalReminderDays: number;
  value: string | null;
  recurringSchedule: number | null;
  schedule: ContractSchedule;
  status: string;
  notes: string;
  createdAt: string;
  updatedAt: string;
};
export type ServiceEvent = {
  id: number;
  ticket: number | null;
  ticketNumber: string;
  occurredAt: string;
  notes: string;
  authorName: string;
  createdAt: string;
};
export type ContractRenewal = {
  id: number;
  previousEndDate: string;
  newEndDate: string;
  previousValue: string | null;
  newValue: string | null;
  note: string;
  createdAt: string;
};
export type ContractCoverage = {
  id: number;
  number: string;
  contractType: string;
  startDate: string;
  endDate: string;
  hasSchedule: boolean;
};

export const contracts = {
  list: (params?: Params) => fetchPage<Contract>('/contracts/', params),
  get: (id: number) => read<Contract>(`/contracts/${id}/`),
  create: (body: Json) => send<Contract>('post', '/contracts/', body),
  update: (id: number, body: Json, updatedAt?: string | null) =>
    send<Contract>('patch', `/contracts/${id}/`, body, version(updatedAt)),
  remove: (id: number) => send<void>('delete', `/contracts/${id}/`),
  renew: (id: number, body: { new_end_date: string; value?: string; note?: string }) =>
    send<Contract>('post', `/contracts/${id}/renew/`, body),
  createSchedule: (id: number, cadence: string, key?: string) =>
    send<{ id: number; invoice: number | null; cadence: string }>(
      'post', `/contracts/${id}/create-schedule/`, { cadence }, idempotencyHeaders(key),
    ),
  syncSchedule: (id: number) => send<Contract>('post', `/contracts/${id}/sync-schedule/`),
  pauseSchedule: (id: number) => send<Contract>('post', `/contracts/${id}/pause-schedule/`),
  resumeSchedule: (id: number) => send<Contract>('post', `/contracts/${id}/resume-schedule/`),
  events: (id: number) => read<ServiceEvent[]>(`/contracts/${id}/service-events/`),
  addEvent: (id: number, body: { notes: string; ticket?: number; occurred_at?: string }) =>
    send<ServiceEvent>('post', `/contracts/${id}/service-events/`, body),
  editEvent: (id: number, event: number, notes: string) =>
    send<ServiceEvent>('patch', `/contracts/${id}/service-event/`, { event, notes }),
  removeEvent: (id: number, event: number) => send<void>('delete', `/contracts/${id}/service-event/?event=${event}`),
  timeline: (id: number) =>
    read<{ contract: Contract; events: ServiceEvent[]; renewals: ContractRenewal[] }>(`/contracts/${id}/timeline/`),
  report: (params?: Params) => read<{ status: string; contractType: string; value: string }[]>('/contracts/report/', params),
  summary: () =>
    read<{ expiringByMonth: { month: string; count: number }[]; monthlyRecurringValue: string }>('/contracts/summary/'),
  coverage: (customer: number, product?: number | null, date?: string) =>
    read<ContractCoverage[]>('/contracts/coverage/', { customer, product: product ?? undefined, date }),
  activity: (id: number) => read<TimelineRow[]>(`/contracts/${id}/activity/`),
  attachments: attachmentsApi('/contracts'),
  exportUrl: (params?: Json) => {
    const search = new URLSearchParams();
    Object.entries(params ?? {}).forEach(([key, value]) => value != null && search.set(key, String(value)));
    return `/contracts/report/export/?${search.toString()}`;
  },
};

// ---- job cards and bays --------------------------------------------------------------------------------------------------

export type JobLine = {
  id: number;
  kind: 'PART' | 'LABOUR';
  product: number;
  productName: string;
  quantity: string;
  unitPrice: string;
  labourMinutes: number;
  technicianCommissionPercent: string;
  commissionAmount: string;
  serial: number | null;
  batch: number | null;
  batchNo: string;
  coveredByContract: boolean;
};
export type Job = {
  id: number;
  number: string;
  customer: number;
  customerName: string;
  technician: number | null;
  technicianName: string;
  status: string;
  complaint: string;
  registrationNo: string;
  vehicleModel: string;
  odometerReading: string | null;
  serviceBay: number | null;
  serviceBayName: string;
  scheduledStart: string | null;
  scheduledEnd: string | null;
  salesInvoice: number | null;
  invoiceNumber: string;
  invoiceStatus: string;
  contract: number | null;
  contractNumber: string;
  ticket: number | null;
  ticketNumber: string;
  sourceComplaint: number | null;
  complaintNumber: string;
  warehouse: number | null;
  subtotal: string;
  gstTotal: string;
  total: string;
  lineCount?: number;
  lines?: JobLine[];
  serialHistory?: { serialId: number; capped: boolean; jobs: { id: number; number: string; status: string; date: string }[] }[];
  createdAt: string;
  updatedAt: string;
};
export type ServiceBay = { id: number; name: string; isActive: boolean };

export type LineInput = {
  kind: 'PART' | 'LABOUR';
  product: number;
  quantity: string;
  unit_price: string;
  serial?: number | null;
  batch?: number | null;
  labour_minutes?: number;
  technician_commission_percent?: string;
  covered_by_contract?: boolean;
};

export const jobs = {
  list: (params?: Params) => fetchPage<Job>('/workshop/job-cards/', params),
  get: (id: number) => read<Job>(`/workshop/job-cards/${id}/`),
  create: (body: Json, key?: string) => send<Job>('post', '/workshop/job-cards/', body, idempotencyHeaders(key)),
  update: (id: number, body: Json, updatedAt?: string | null) =>
    send<Job>('patch', `/workshop/job-cards/${id}/`, body, version(updatedAt)),
  addLine: (id: number, body: LineInput) => send<Job>('post', `/workshop/job-cards/${id}/lines/`, body as unknown as Json),
  editLine: (id: number, line: number, body: Json) =>
    send<Job>('patch', `/workshop/job-cards/${id}/line/`, { line, ...body }),
  removeLine: (id: number, line: number) => send<Job>('delete', `/workshop/job-cards/${id}/line/?line=${line}`),
  start: (id: number) => send<Job>('post', `/workshop/job-cards/${id}/start/`),
  schedule: (id: number, body: Json) => send<Job>('post', `/workshop/job-cards/${id}/schedule/`, body),
  convert: (id: number, key?: string) =>
    send<Job>('post', `/workshop/job-cards/${id}/convert/`, undefined, idempotencyHeaders(key)),
  reopen: (id: number) => send<Job>('post', `/workshop/job-cards/${id}/reopen/`),
  cancel: (id: number) => send<Job>('post', `/workshop/job-cards/${id}/cancel/`),
  activity: (id: number) => read<TimelineRow[]>(`/workshop/job-cards/${id}/activity/`),
  report: () => read<Record<string, unknown>>('/workshop/job-cards/report/'),
  stockOptions: (product: number) =>
    read<{
      trackSerial: boolean;
      trackBatch: boolean;
      serials: { id: number; serialNumber: string }[];
      batches: { id: number; batchNo: string; expiryDate: string | null; available: string }[];
    }>('/workshop/job-cards/stock-options/', { product }),
};

export const bays = {
  list: (includeInactive = false) =>
    fetchPage<ServiceBay>('/workshop/bays/', { pageSize: 100, ...(includeInactive ? { include_inactive: 1 } : {}) }),
  create: (name: string) => send<ServiceBay>('post', '/workshop/bays/', { name }),
  update: (id: number, body: Json) => send<ServiceBay>('patch', `/workshop/bays/${id}/`, body),
  remove: (id: number) => send<void>('delete', `/workshop/bays/${id}/`),
};

// ---- projects ---------------------------------------------------------------------------------------------------------------

export type Milestone = {
  id: number;
  name: string;
  sequence: number;
  amount: string;
  targetCompletionDate: string | null;
  serviceProduct: number;
  serviceProductName: string;
  status: 'PLANNED' | 'READY' | 'INVOICED';
  salesInvoice: number | null;
  invoiceNumber: string;
  invoiceStatus: string;
  gstRate: string;
  gstAmount: string;
  amountInclGst: string;
};
export type Project = {
  id: number;
  number: string;
  customer: number;
  customerName: string;
  name: string;
  status: string;
  notes: string;
  startDate: string | null;
  endDate: string | null;
  contractValue: string | null;
  contract: number | null;
  contractNumber: string;
  plannedTotal: string;
  invoicedTotal: string;
  readyTotal: string;
  remainingTotal: string;
  percentComplete: number;
  overBudget: boolean;
  milestoneCount?: number;
  milestones?: Milestone[];
  warning?: string;
  createdAt: string;
  updatedAt: string;
};

export const projects = {
  list: (params?: Params) => fetchPage<Project>('/projects/', params),
  get: (id: number) => read<Project>(`/projects/${id}/`),
  create: (body: Json, key?: string) => send<Project>('post', '/projects/', body, idempotencyHeaders(key)),
  update: (id: number, body: Json, updatedAt?: string | null) =>
    send<Project>('patch', `/projects/${id}/`, body, version(updatedAt)),
  addMilestone: (id: number, body: Json) => send<Project>('post', `/projects/${id}/milestones/`, body),
  editMilestone: (id: number, milestone: number, body: Json) =>
    send<Project>('post', `/projects/${id}/milestones/${milestone}/edit/`, body),
  deleteMilestone: (id: number, milestone: number) => send<Project>('post', `/projects/${id}/milestones/${milestone}/delete/`),
  ready: (id: number, milestone: number) => send<Project>('post', `/projects/${id}/milestones/${milestone}/ready/`),
  unready: (id: number, milestone: number) => send<Project>('post', `/projects/${id}/milestone-unready/`, { milestone }),
  reorder: (id: number, order: number[]) => send<Project>('post', `/projects/${id}/milestones/reorder/`, { order }),
  invoice: (id: number, milestone: number, key?: string) =>
    send<Project>('post', `/projects/${id}/milestones/${milestone}/invoice/`, undefined, idempotencyHeaders(key)),
  close: (id: number) => send<Project>('post', `/projects/${id}/close/`),
  cancel: (id: number, reason: string) => send<Project>('post', `/projects/${id}/cancel/`, { reason }),
  activity: (id: number) => read<TimelineRow[]>(`/projects/${id}/activity/`),
};
