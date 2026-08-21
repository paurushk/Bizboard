import { apiClient, unwrapData } from '../client';
import { mockCompany, mockDashboard, mockUsers } from '@/mocks/data';
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
  }, mockCompany);
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
}): Promise<CompanyUser & { inviteUrl?: string; inviteToken?: string }> {
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
    const { data } = await apiClient.post('/company/users/', body);
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

export async function updateCompanyUser(
  id: number,
  payload: Partial<CompanyUser>,
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

