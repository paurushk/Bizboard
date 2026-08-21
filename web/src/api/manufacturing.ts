import { apiClient, idempotencyHeaders, unwrapData } from '@/api/client';
import { fetchPage } from '@/api/resources';
import { apiPath, type SchemaOr } from '@/api/typedClient';

export type BomLine = SchemaOr<
  'BomLine',
  {
    id?: number;
    component: number;
    qty: string;
  }
>;

export type Bom = SchemaOr<
  'Bom',
  {
    id: number;
    product: number;
    name: string;
    status: string;
    lines: BomLine[];
    createdAt: string;
    updatedAt: string;
  }
>;

export type WorkOrder = SchemaOr<
  'WorkOrder',
  {
    id: number;
    bom: number;
    qty: string;
    status: string;
    warehouse: number | null;
    createdAt: string;
    updatedAt: string;
  }
>;

const BASE = apiPath('/manufacturing');

export function listBomsPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<Bom>(`${BASE}/boms/`, params);
}

export async function getBom(id: number): Promise<Bom> {
  const { data } = await apiClient.get(`${BASE}/boms/${id}/`);
  return unwrapData<Bom>(data);
}

export async function createBom(payload: Partial<Bom>): Promise<Bom> {
  const { data } = await apiClient.post(`${BASE}/boms/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<Bom>(data);
}

export async function updateBom(id: number, payload: Partial<Bom>): Promise<Bom> {
  const { data } = await apiClient.patch(`${BASE}/boms/${id}/`, payload);
  return unwrapData<Bom>(data);
}

export function listWorkOrdersPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<WorkOrder>(`${BASE}/work-orders/`, params);
}

export async function createWorkOrder(payload: Partial<WorkOrder>): Promise<WorkOrder> {
  const { data } = await apiClient.post(`${BASE}/work-orders/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<WorkOrder>(data);
}

export async function updateWorkOrder(id: number, payload: Partial<WorkOrder>): Promise<WorkOrder> {
  const { data } = await apiClient.patch(`${BASE}/work-orders/${id}/`, payload);
  return unwrapData<WorkOrder>(data);
}

export async function releaseWorkOrder(id: number): Promise<WorkOrder> {
  const { data } = await apiClient.post(`${BASE}/work-orders/${id}/release/`);
  return unwrapData<WorkOrder>(data);
}

export async function completeWorkOrder(id: number): Promise<WorkOrder> {
  const { data } = await apiClient.post(`${BASE}/work-orders/${id}/complete/`);
  return unwrapData<WorkOrder>(data);
}

export async function cancelWorkOrder(id: number): Promise<WorkOrder> {
  const { data } = await apiClient.post(`${BASE}/work-orders/${id}/cancel/`);
  return unwrapData<WorkOrder>(data);
}
