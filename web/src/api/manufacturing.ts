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
    serialNumbers?: string[];
    batchNo?: string;
    expDate?: string | null;
    mfgDate?: string | null;
    createdAt: string;
    updatedAt: string;
  }
> & {
  // docs/openapi-snapshot.json predates batch tracking on WorkOrder
  // (backend/manufacturing/serializers.py's WorkOrderSerializer.Meta.fields
  // already lists batch_no/exp_date/mfg_date/batch) — the schema snapshot
  // needs a `python manage.py spectacular` regen to catch up. Until then,
  // SchemaOr resolves the real (but stale) "WorkOrder" component and drops
  // these from the fallback, so they're patched back in here.
  batchNo?: string;
  expDate?: string | null;
  mfgDate?: string | null;
  batch?: number | null;
};

const BASE = apiPath('/manufacturing');

export function listBomsPage(params?: { page?: number; pageSize?: number }) {
  return fetchPage<Bom>(`${BASE}/boms/`, params);
}

export async function getBom(id: number): Promise<Bom> {
  const { data } = await apiClient.get(`${BASE}/boms/${id}/`);
  return unwrapData<Bom>(data);
}

// BomSerializer.update() always deletes and recreates lines (see
// backend/manufacturing/serializers.py), and `id` on BomLine is read-only —
// a write only ever needs component + qty per line, never a line id.
type BomWritePayload = Partial<Omit<Bom, 'lines'>> & {
  lines?: Array<Pick<BomLine, 'component' | 'qty'>>;
};

export async function createBom(payload: BomWritePayload): Promise<Bom> {
  const { data } = await apiClient.post(`${BASE}/boms/`, payload, {
    headers: idempotencyHeaders(),
  });
  return unwrapData<Bom>(data);
}

export async function updateBom(id: number, payload: BomWritePayload): Promise<Bom> {
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

export async function releaseWorkOrder(
  id: number,
  payload?: { componentSerials?: Record<string, string[]> },
): Promise<WorkOrder> {
  const { data } = await apiClient.post(`${BASE}/work-orders/${id}/release/`, {
    componentSerials: payload?.componentSerials,
  });
  return unwrapData<WorkOrder>(data);
}

export async function completeWorkOrder(
  id: number,
  payload?: { serialNumbers?: string[]; batchNo?: string; expDate?: string | null; mfgDate?: string | null },
): Promise<WorkOrder> {
  if (payload && (payload.serialNumbers?.length || payload.batchNo || payload.expDate || payload.mfgDate)) {
    await updateWorkOrder(id, payload);
  }
  const { data } = await apiClient.post(`${BASE}/work-orders/${id}/complete/`, payload ?? {});
  return unwrapData<WorkOrder>(data);
}

export async function cancelWorkOrder(id: number): Promise<WorkOrder> {
  const { data } = await apiClient.post(`${BASE}/work-orders/${id}/cancel/`);
  return unwrapData<WorkOrder>(data);
}
