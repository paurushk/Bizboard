import { apiClient, idempotencyHeaders, unwrapData } from '@/api/client';

export type CollectionRow = {
  invoiceId: number;
  invoiceNumber: string;
  customerId: number;
  customerName: string;
  dueDate: string;
  outstanding: string;
  predictedDaysLate: number | null;
  confident: boolean;
};

export type Customer360 = {
  customerId: number;
  name: string;
  sales: { invoices: number; amount: string | null };
  products: string[];
  pattern: string | null;
  recommendedNextStep: string | null;
  outstanding: string | null;
  aging: Record<string, string> | null;
  profit: { rows?: unknown[]; totals?: Record<string, string> } | null;
};

export type PlanningLine = {
  productId: number;
  productName: string;
  warehouseId: number;
  warehouseName: string;
  suggestedQty: string;
  daysToStockout: number | null;
  supplierId: number | null;
  transferFromWarehouseId: number | null;
  transferFromWarehouseName: string;
};

export type PlanningDocument = {
  kind: 'purchase' | 'transfer';
  supplierId?: number | null;
  fromWarehouseId?: number;
  lines: Array<{ productId: number; qty: string; warehouseId: number }>;
};

export type RouteSuggestion = {
  date: string;
  pincode: string;
  stopIds: number[];
  orderIds: number[];
  routeIds: number[];
};

export type PackState = {
  answers: Record<string, string>;
  proposedPack: string;
  appliedPack: string;
  packs: Record<string, string[]>;
  heldPacks: string[];
  confirmedAt: string | null;
};

export type GateCheck = {
  creditBlocked: boolean;
  creditMessage: string;
  marginWarnings: Array<{ productId: number; productName: string; margin: string }>;
};

export async function listCollectionsWorklist(): Promise<CollectionRow[]> {
  const { data } = await apiClient.get('/insights/collections-worklist/');
  const body = unwrapData<{ rows: CollectionRow[] }>(data);
  return body.rows ?? [];
}

export async function getCustomer360(customerId: number): Promise<Customer360> {
  const { data } = await apiClient.get(`/insights/customers/${customerId}/360/`);
  return unwrapData<Customer360>(data);
}

export async function getPurchasePlan(params?: {
  warehouse?: string;
  supplier?: string;
  urgency?: string;
}): Promise<{ rows: PlanningLine[]; documents: PlanningDocument[] }> {
  const { data } = await apiClient.get('/inventory/purchase-planning/', { params });
  return unwrapData(data);
}

export async function listRouteCombineSuggestions(): Promise<RouteSuggestion[]> {
  const { data } = await apiClient.get('/sales/delivery-routes/combine-suggestions/');
  const body = unwrapData<{ suggestions: RouteSuggestion[] }>(data);
  return body.suggestions ?? [];
}

export async function getPackWizard(): Promise<PackState> {
  const { data } = await apiClient.get('/company/packs/');
  return unwrapData<PackState>(data);
}

export async function proposePack(answers: Record<string, string>): Promise<{ proposedPack: string; applied: boolean }> {
  const { data } = await apiClient.post('/company/packs/', { answers, confirm: false });
  return unwrapData(data);
}

export async function confirmPack(answers: Record<string, string>): Promise<{ proposedPack: string; appliedPack: string; applied: boolean; skippedFlags?: string[] }> {
  const { data } = await apiClient.post('/company/packs/', { answers, confirm: true });
  return unwrapData(data);
}

export async function checkSalesOrderGate(id: number): Promise<GateCheck> {
  const { data } = await apiClient.post(`/sales/orders/${id}/gate-check/`, {});
  return unwrapData<GateCheck>(data);
}

export async function confirmSalesOrder(id: number): Promise<{ marginWarnings?: GateCheck['marginWarnings'] }> {
  const { data } = await apiClient.post(`/sales/orders/${id}/confirm/`, {}, { headers: idempotencyHeaders() });
  return unwrapData(data);
}

export async function submitPublicLead(token: string, payload: {
  name: string;
  phone: string;
  email: string;
  message: string;
  website?: string;
}): Promise<void> {
  await apiClient.post(`/crm/public/lead-form/${token}/`, payload);
}
