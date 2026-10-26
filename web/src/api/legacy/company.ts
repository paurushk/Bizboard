import { apiClient, idempotencyHeaders, LONG_TIMEOUT_MS, unwrapData } from '../client';
import { mockCompany, mockDashboard, mockUsers } from '@/mocks/data';
import { mockUserForEmail } from '../auth';
import { getStoredUser } from '@/auth/session';
import type { Company, CompanyUser, DashboardKpis } from '@/types/domain';
import { withMocks, fetchAllPagesMasters } from './common';

export async function getDashboard(): Promise<DashboardKpis> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/dashboard/');
    return unwrapData<DashboardKpis>(data);
  }, mockDashboard);
}

export async function getCompany(): Promise<Company> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/company/');
    return unwrapData<Company>(data);
  }, () => {
    const stored = getStoredUser();
    if (stored?.email) return mockUserForEmail(stored.email).company ?? mockCompany;
    return mockCompany;
  });
}

export async function updateCompany(payload: Partial<Company> & {
  dismissOnboarding?: boolean;
  confirmTaxProfile?: boolean;
  markOnboardingStarted?: boolean;
}): Promise<Company> {
  return withMocks(async () => {
    const { data } = await apiClient.patch('/company/', payload);
    return unwrapData<Company>(data);
  }, { ...mockCompany, ...payload } as Company);
}

export async function listCompanyUsers(): Promise<CompanyUser[]> {
  return withMocks(async () => fetchAllPagesMasters<CompanyUser>('/company/users/'), mockUsers);
}

/** BB-100 F10: who is on the team (id, name, role) — readable by any member, for assignee pickers. */
export type TeamMember = { id: number; name: string; role: string };

/** Under ['company-users'], so a change on the Users page refreshes the pickers too. */
export const TEAM_MEMBERS_QUERY_KEY = ['company-users', 'team'] as const;

export async function listTeamMembers(): Promise<TeamMember[]> {
  return withMocks(
    async () => {
      const { data } = await apiClient.get('/company/members/');
      return unwrapData<TeamMember[]>(data);
    },
    mockUsers.filter((u) => u.user).map((u) => ({ id: u.id, name: u.fullName || u.email.split('@')[0], role: u.role })),
  );
}

export async function inviteCompanyUser(payload: {
  email: string;
  password?: string;
  fullName?: string;
  phone?: string;
  role?: string;
  canManageInventory?: boolean;
  canImport?: boolean;
  canCancelDocuments?: boolean;
  canViewFinancialReports?: boolean;
  canExport?: boolean;
  canCreateSales?: boolean;
  canCreatePurchases?: boolean;
  canCreatePayments?: boolean;
}, headers: Record<string, string> = {}): Promise<CompanyUser & { inviteUrl?: string; inviteToken?: string }> {
  return withMocks(async () => {
    const body: Record<string, unknown> = {
      email: payload.email,
      full_name: payload.fullName ?? '',
      phone: payload.phone ?? '',
      role: payload.role ?? 'SALES_STAFF',
      can_manage_inventory: payload.canManageInventory ?? false,
      can_import: payload.canImport ?? false,
      can_cancel_documents: payload.canCancelDocuments ?? false,
      can_view_financial_reports: payload.canViewFinancialReports ?? false,
      can_export: payload.canExport ?? false,
      can_create_sales: payload.canCreateSales ?? (payload.role === 'SALES_STAFF' || !payload.role),
      can_create_purchases: payload.canCreatePurchases ?? false,
      can_create_payments: payload.canCreatePayments ?? (payload.role === 'SALES_STAFF' || !payload.role),
    };
    if (payload.password) {
      body.password = payload.password;
    }
    const { data } = await apiClient.post('/company/users/', body, { headers });
    return unwrapData<CompanyUser>(data);
  }, {
    id: Date.now(),
    user: Date.now(),
    email: payload.email,
    fullName: payload.fullName ?? '',
    role: (payload.role as CompanyUser['role']) ?? 'SALES_STAFF',
    canManageInventory: payload.canManageInventory ?? false,
    canImport: payload.canImport ?? false,
    isActive: true,
  });
}

/** A fresh invite link for someone who has not accepted; earlier links stop working. */
export async function resendCompanyUserInvite(id: number): Promise<{ inviteUrl?: string; inviteToken?: string; inviteExpiresAt?: string | null }> {
  const { data } = await apiClient.post(`/company/users/${id}/resend-invite/`, {});
  return unwrapData(data);
}

/** Cancel an invite that has not been accepted. */
export async function revokeCompanyUserInvite(id: number): Promise<{ revoked: number }> {
  const { data } = await apiClient.post(`/company/users/${id}/revoke-invite/`, {});
  return unwrapData(data);
}

export async function updateCompanyUser(
  id: number,
  payload: Partial<CompanyUser> & { expected_updated_at?: string },
): Promise<CompanyUser> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/company/users/${id}/`, payload);
    return unwrapData<CompanyUser>(data);
  }, { ...mockUsers[0], ...payload, id });
}

export interface CompanyGstinRow {
  id: number;
  gstin: string;
  legalName?: string;
  legal_name?: string;
  state?: string;
  address?: string;
  city?: string;
  pincode?: string;
  isPrimary?: boolean;
  is_primary?: boolean;
  isActive?: boolean;
  is_active?: boolean;
}

export async function listCompanyGstins(): Promise<CompanyGstinRow[]> {
  const { data } = await apiClient.get('/company/gstins/');
  const body = unwrapData<CompanyGstinRow[] | { results?: CompanyGstinRow[] }>(data);
  if (Array.isArray(body)) return body;
  return body.results ?? [];
}

export async function createCompanyGstin(payload: Record<string, unknown>): Promise<CompanyGstinRow> {
  const { data } = await apiClient.post('/company/gstins/', payload);
  return unwrapData<CompanyGstinRow>(data);
}

export async function updateCompanyGstin(
  id: number,
  payload: Record<string, unknown>,
): Promise<CompanyGstinRow> {
  const { data } = await apiClient.patch(`/company/gstins/${id}/`, payload);
  return unwrapData<CompanyGstinRow>(data);
}

export interface CompanyStatutoryLicenceRow {
  id: number;
  licenceType: 'DRUG_20B' | 'DRUG_21B' | 'FSSAI';
  licence_type?: 'DRUG_20B' | 'DRUG_21B' | 'FSSAI';
  licenceNumber?: string;
  licence_number?: string;
  premisesAddress?: string;
  premises_address?: string;
  premisesState?: string;
  premises_state?: string;
  premisesCity?: string;
  premises_city?: string;
  premisesPincode?: string;
  premises_pincode?: string;
  validFrom?: string | null;
  valid_from?: string | null;
  validUpto?: string | null;
  valid_upto?: string | null;
  isActive?: boolean;
  is_active?: boolean;
  /** True once the licence is printed on an issued invoice (renew or replace only). */
  isLocked?: boolean;
  is_locked?: boolean;
  /** Same licence types as `licenceType`; POSP and AGENCY exist on the server. */
}

export interface StatutoryLicenceStatus {
  enforcement: boolean;
  regulatedProducts: number;
  activeLicences: number;
  expired: number;
  expiringSoon: number;
}

export async function getStatutoryLicenceStatus(): Promise<StatutoryLicenceStatus> {
  const { data } = await apiClient.get('/company/statutory-licences/status/');
  return unwrapData<StatutoryLicenceStatus>(data);
}

export async function replaceCompanyStatutoryLicence(
  id: number,
  payload: Record<string, unknown>,
): Promise<CompanyStatutoryLicenceRow> {
  const { data } = await apiClient.post(`/company/statutory-licences/${id}/replace/`, payload);
  return unwrapData<CompanyStatutoryLicenceRow>(data);
}

export async function listCompanyStatutoryLicences(): Promise<CompanyStatutoryLicenceRow[]> {
  const { data } = await apiClient.get('/company/statutory-licences/');
  const body = unwrapData<CompanyStatutoryLicenceRow[] | { results?: CompanyStatutoryLicenceRow[] }>(data);
  if (Array.isArray(body)) return body;
  return body.results ?? [];
}

export async function createCompanyStatutoryLicence(
  payload: Record<string, unknown>,
): Promise<CompanyStatutoryLicenceRow> {
  const { data } = await apiClient.post('/company/statutory-licences/', payload);
  return unwrapData<CompanyStatutoryLicenceRow>(data);
}

export async function updateCompanyStatutoryLicence(
  id: number,
  payload: Record<string, unknown>,
): Promise<CompanyStatutoryLicenceRow> {
  const { data } = await apiClient.patch(`/company/statutory-licences/${id}/`, payload);
  return unwrapData<CompanyStatutoryLicenceRow>(data);
}

export async function exportTenantBackup(): Promise<{ url: string; filename: string }> {
  const response = await apiClient.post(
    '/company/export/',
    {},
    {
      responseType: 'blob',
      timeout: LONG_TIMEOUT_MS,
      transformResponse: [(d) => d],
    },
  );
  const blob =
    response.data instanceof Blob
      ? response.data
      : new Blob([response.data as BlobPart], { type: 'application/octet-stream' });
  const header = String(response.headers?.['content-disposition'] || '');
  const match = header.match(/filename="([^"]+)"/i);
  return {
    url: URL.createObjectURL(blob),
    filename: match?.[1] || 'bizboard-tenant-export.bin',
  };
}

export interface TelegramStatus {
  enabled: boolean;
  linked: boolean;
}

export async function getTelegramStatus(): Promise<TelegramStatus> {
  const { data } = await apiClient.get('/telegram/status/');
  return unwrapData<TelegramStatus>(data);
}

export async function requestTelegramLink(): Promise<{ deepLink: string; expiresIn: number }> {
  const { data } = await apiClient.post('/telegram/link/', {});
  const body = unwrapData<{ deep_link?: string; deepLink?: string; expires_in?: number; expiresIn?: number }>(data);
  return {
    deepLink: body.deep_link ?? body.deepLink ?? '',
    expiresIn: Number(body.expires_in ?? body.expiresIn ?? 0),
  };
}

export async function unlinkTelegram(): Promise<void> {
  await apiClient.post('/telegram/unlink/', {});
}

export interface TenantBackupStatus {
  lastExport: null | {
    exportedAt: string;
    bytes: number | null;
    version: number | string | null;
    by: string;
    summary: null | {
      sections: number;
      records: number;
      customers: number;
      suppliers: number;
      products: number;
      salesInvoices: number;
      purchaseInvoices: number;
      receipts: number;
      journals: number;
      filesWithBytes: number;
      filesListedOnly: number;
      fileWarnings: number;
    };
  };
  restoreIntoLiveEnabled: boolean;
  maxSandboxes: number;
}

/** When the last encrypted backup was taken and what it held, from the audit trail. */
export async function getTenantBackupStatus(): Promise<TenantBackupStatus> {
  const { data } = await apiClient.get('/company/export/last/');
  return unwrapData<TenantBackupStatus>(data);
}

export async function restoreTenantSandbox(file: File): Promise<{
  companyId: number;
  mode: string;
  name: string;
  sandboxExpiresAt: string | null;
}> {
  const form = new FormData();
  form.append('file', file);
  form.append('restore', 'sandbox');
  const { data } = await apiClient.post('/company/restore/', form, {
    timeout: LONG_TIMEOUT_MS,
    headers: idempotencyHeaders(),
  });
  const body = unwrapData<{
    company_id?: number;
    companyId?: number;
    mode?: string;
    name?: string;
    sandbox_expires_at?: string | null;
    sandboxExpiresAt?: string | null;
  }>(data);
  return {
    companyId: Number(body.company_id ?? body.companyId),
    mode: body.mode || 'sandbox',
    name: body.name || '',
    sandboxExpiresAt: body.sandbox_expires_at ?? body.sandboxExpiresAt ?? null,
  };
}



/** SET-18: one row of the Settings health checklist. */
export interface SettingsHealthItem {
  id: 'gstin' | 'taxprofile' | 'bank' | 'licences' | 'gateway' | 'users' | 'backup' | 'webhook' | 'plan';
  status: 'ok' | 'todo' | 'warn';
  path: string;
  count?: number;
  expired?: number;
  expiring?: number;
  pending?: number;
  metrics?: string[];
}

export async function getSettingsHealth(): Promise<{ items: SettingsHealthItem[]; needsAttention: number }> {
  const { data } = await apiClient.get('/company/settings-health/');
  return unwrapData<{ items: SettingsHealthItem[]; needsAttention: number }>(data);
}

/** SET-02: one document number series for the chosen GSTIN and financial year. */
export interface NumberSeriesRow {
  docType: string;
  prefix: string;
  nextNumber: number;
  padding: number;
  preview: string;
  length: number;
  lengthWarning: string | null;
  updatedAt: string;
}

export interface NumberSeriesList {
  gstin: string;
  fyLabel: string;
  items: NumberSeriesRow[];
  gstins: string[];
  fyOptions: string[];
  hasSeries: boolean;
}

export async function getNumberSeries(gstin = '', fy = ''): Promise<NumberSeriesList> {
  const { data } = await apiClient.get('/company/number-series/', { params: { gstin: gstin || undefined, fy: fy || undefined } });
  return unwrapData<NumberSeriesList>(data);
}

export async function saveNumberSeries(
  body: { gstin: string; fy: string; items: Array<Record<string, unknown>> },
  headers: Record<string, string> = {},
): Promise<NumberSeriesList> {
  const { data } = await apiClient.patch('/company/number-series/', body, { headers });
  return unwrapData<NumberSeriesList>(data);
}

/** SET-17: upload a logo image and return its file id (the company then points at it). */
export async function uploadCompanyLogo(file: File): Promise<number> {
  const form = new FormData();
  form.append('kind', 'LOGO');
  form.append('file', file);
  const { data } = await apiClient.post('/files/', form);
  return unwrapData<{ id: number }>(data).id;
}

/** SET-08: the weekly automatic backup. */
export interface BackupSchedule {
  enabled: boolean;
  keep: number;
  schedule: string;
  backups: Array<{ id: number; createdAt: string; size: number; name: string }>;
  lastRun: null | { at: string; ok: boolean; error: string };
}

export async function getBackupSchedule(): Promise<BackupSchedule> {
  const { data } = await apiClient.get('/company/export/schedule/');
  return unwrapData<BackupSchedule>(data);
}

export async function setBackupSchedule(enabled: boolean): Promise<BackupSchedule> {
  const { data } = await apiClient.patch('/company/export/schedule/', { enabled });
  return unwrapData<BackupSchedule>(data);
}

export async function takeBackupNow(): Promise<BackupSchedule> {
  const { data } = await apiClient.post('/company/export/schedule/', {}, { timeout: LONG_TIMEOUT_MS });
  return unwrapData<BackupSchedule>(data);
}

/** SET-21: recent changes to one Settings area, read from the audit trail. */
export interface SettingsHistoryItem {
  id: number;
  at: string;
  who: string;
  action: string;
  entity: string;
  what: string;
  changes: Array<{ field: string; from?: unknown; to?: unknown; changed?: boolean }>;
}

export async function getSettingsHistory(area: string, limit = 30): Promise<{ area: string; items: SettingsHistoryItem[] }> {
  const { data } = await apiClient.get('/company/settings-history/', { params: { area, limit } });
  return unwrapData<{ area: string; items: SettingsHistoryItem[] }>(data);
}

/** SET-22: what a high-impact settings change would touch, before it is saved (changes nothing). */
export interface SettingsPreviewLine {
  key: string;
  params: Record<string, string | number | boolean>;
}

export async function previewSettingsChange(area: string, proposed: Record<string, unknown>): Promise<SettingsPreviewLine[]> {
  const { data } = await apiClient.post('/company/settings-preview/', { area, proposed });
  return unwrapData<{ lines: SettingsPreviewLine[] }>(data).lines;
}
