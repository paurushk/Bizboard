import { apiClient, idempotencyHeaders, unwrapData } from '@/api/client';
import { fetchPage } from '@/api/resources';
import { apiPath, type SchemaOr } from '@/api/typedClient';

export type Employee = SchemaOr<
  'Employee',
  {
    id: number;
    name: string;
    code: string;
    salary: string;
    basic?: string;
    da?: string;
    tdsRate?: string;
    status: string;
    pfApplicable: boolean;
    pfWageCeiling: string;
    esiApplicable: boolean;
    ptState: string;
    createdAt: string;
    updatedAt: string;
  }
>;

export type PaySlip = SchemaOr<
  'PaySlip',
  {
    id: number;
    employee: number;
    employeeName: string;
    gross: string;
    deductions: string;
    net: string;
    pfEmployee: string;
    esiEmployee: string;
    ptAmount: string;
    pfEmployer?: string;
    esiEmployer?: string;
  }
>;

export type PayRun = SchemaOr<
  'PayRun',
  {
    id: number;
    period: string;
    status: string;
    slips: PaySlip[];
    createdAt: string;
    updatedAt: string;
  }
>;

const BASE = apiPath('/payroll');

export function listEmployeesPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<Employee>(`${BASE}/employees/`, params);
}

export async function createEmployee(payload: Partial<Employee>): Promise<Employee> {
  const { data } = await apiClient.post(`${BASE}/employees/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<Employee>(data);
}

export async function updateEmployee(id: number, payload: Partial<Employee>): Promise<Employee> {
  const { data } = await apiClient.patch(`${BASE}/employees/${id}/`, payload);
  return unwrapData<Employee>(data);
}

export function listPayRunsPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<PayRun>(`${BASE}/pay-runs/`, params);
}

export async function createPayRun(payload: { period: string }): Promise<PayRun> {
  const { data } = await apiClient.post(`${BASE}/pay-runs/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<PayRun>(data);
}

export async function updatePayRun(id: number, payload: { period: string }): Promise<PayRun> {
  const { data } = await apiClient.patch(`${BASE}/pay-runs/${id}/`, payload);
  return unwrapData<PayRun>(data);
}

export async function completePayRun(id: number, payFromCash = true): Promise<PayRun> {
  const { data } = await apiClient.post(`${BASE}/pay-runs/${id}/complete/`, { payFromCash });
  return unwrapData<PayRun>(data);
}

export async function cancelPayRun(id: number): Promise<PayRun> {
  const { data } = await apiClient.post(`${BASE}/pay-runs/${id}/cancel/`);
  return unwrapData<PayRun>(data);
}

export async function applyPayRunLop(
  id: number,
  entries: { employee: number; paidDays: string }[],
): Promise<PayRun> {
  const { data } = await apiClient.post(`${BASE}/pay-runs/${id}/lop/`, {
    entries: entries.map((e) => ({ employee: e.employee, paidDays: e.paidDays })),
  });
  return unwrapData<PayRun>(data);
}
