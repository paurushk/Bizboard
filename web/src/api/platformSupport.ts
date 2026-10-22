/** WP-PO3: ask Bizboard support for help (not the merchant's own customer helpdesk). */
import { apiClient, getLastRequestId, getRecentErrorCodes, unwrapData } from './client';

export type SupportSeverity = 'P0' | 'P1' | 'P2' | 'P3';

export interface PlatformTicket {
  id: number;
  subject: string;
  description: string;
  severity: SupportSeverity;
  status: 'OPEN' | 'IN_PROGRESS' | 'WAITING_CUSTOMER' | 'RESOLVED';
  raisedByEmail: string;
  slaDueAt: string | null;
  createdAt: string;
  messages?: Array<{ id: number; body: string; fromStaff: boolean; authorEmail: string; createdAt: string }>;
}

export async function listPlatformTickets(): Promise<PlatformTicket[]> {
  const { data } = await apiClient.get('/support/platform-tickets/');
  const body = unwrapData<PlatformTicket[]>(data);
  return Array.isArray(body) ? body : [];
}

export async function getPlatformTicket(id: number): Promise<PlatformTicket> {
  const { data } = await apiClient.get(`/support/platform-tickets/${id}/`);
  return unwrapData(data);
}

/** Attaches the Support ID, the screen and recent error codes — never form contents. */
export async function openPlatformTicket(input: {
  subject: string;
  description: string;
  severity: SupportSeverity;
  route?: string;
  tag?: string;
}): Promise<PlatformTicket> {
  const { data } = await apiClient.post('/support/platform-tickets/', {
    subject: input.subject,
    description: input.description,
    severity: input.severity,
    tag: input.tag ?? '',
    route: input.route ?? (typeof window !== 'undefined' ? window.location.pathname : ''),
    support_id: getLastRequestId() ?? '',
    app_version: String(import.meta.env.VITE_APP_VERSION ?? ''),
    error_codes: getRecentErrorCodes(),
  });
  return unwrapData(data);
}

export async function replyPlatformTicket(id: number, body: string): Promise<void> {
  await apiClient.post(`/support/platform-tickets/${id}/reply/`, { body });
}

/** WP-ID4: the owner lets Bizboard support view the company's data, read-only, up to 72 hours. */
export interface SupportAccessGrant {
  id: number;
  ticketId: number;
  ticketSubject: string;
  staffEmail: string;
  expiresAt: string;
  revokedAt: string | null;
  live: boolean;
  views: Array<{ at: string; section: string; query: string; rows: number; staffEmail: string }>;
}

export async function listSupportAccessGrants(): Promise<SupportAccessGrant[]> {
  const { data } = await apiClient.get('/support/access-grants/');
  const body = unwrapData<SupportAccessGrant[]>(data);
  return Array.isArray(body) ? body : [];
}

export async function grantSupportAccess(input: {
  ticketId: number;
  hours: number;
  password: string;
  code?: string;
}): Promise<SupportAccessGrant> {
  const { data } = await apiClient.post('/support/access-grants/', {
    ticket_id: input.ticketId,
    hours: input.hours,
    password: input.password,
    code: input.code ?? '',
  });
  return unwrapData(data);
}

export async function revokeSupportAccess(id: number): Promise<void> {
  await apiClient.post(`/support/access-grants/${id}/revoke/`);
}
