/**
 * Manufacturing, quality, job work and shop floor (docs/MANUFACTURING_IMPLEMENTATION_PLAN.md).
 *
 * The server speaks snake_case and the client converts to camelCase, so every field here is camelCase.
 * Quantities and money arrive as strings and are sent as strings.
 */
import axios from 'axios';
import { apiClient, idempotencyHeaders, unwrapData } from '@/api/client';
import { fetchPage } from '@/api/legacy/common';
import { apiPath } from '@/api/typedClient';

const M = apiPath('/manufacturing');
const Q = apiPath('/quality');
const J = apiPath('/jobwork');

type Id = number;

/** Query strings are not run through the server's camelCase layer, so filters go out as snake_case. */
function snakeParams(params?: Record<string, unknown>): Record<string, unknown> | undefined {
  if (!params) return undefined;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    out[key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`)] = value;
  }
  return out;
}

async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const { data } = await apiClient.get(url, { params: snakeParams(params) });
  return unwrapData<T>(data);
}

async function post<T>(url: string, body?: unknown, idempotent = false): Promise<T> {
  const { data } = await apiClient.post(url, body ?? {}, idempotent ? { headers: idempotencyHeaders() } : undefined);
  return unwrapData<T>(data);
}

async function patch<T>(url: string, body: unknown): Promise<T> {
  const { data } = await apiClient.patch(url, body);
  return unwrapData<T>(data);
}

async function put<T>(url: string, body: unknown): Promise<T> {
  const { data } = await apiClient.put(url, body);
  return unwrapData<T>(data);
}

async function del(url: string): Promise<void> {
  await apiClient.delete(url);
}

/** A list endpoint as a plain array (the first page; these lists are bounded by their filters). */
async function list<T>(url: string, params?: Record<string, unknown>): Promise<T[]> {
  const page = await fetchPage<T>(url, { pageSize: 200, ...(snakeParams(params) ?? {}) } as never);
  return page.results;
}

export async function downloadFile(url: string, params?: Record<string, unknown>): Promise<Blob> {
  const res = await apiClient.get(url, { params: snakeParams(params), responseType: 'blob' });
  return res.data as Blob;
}

/** Save a blob under a name, in the browser. */
export function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
}

/** The code the server put on a rule error, if any (for example MFG_REVERSAL_ORDER). */
export function errorCode(err: unknown): string {
  if (!axios.isAxiosError(err)) return '';
  const data = err.response?.data as { error?: { code?: string }; code?: string } | undefined;
  return data?.error?.code ?? data?.code ?? '';
}

// --- settings ----------------------------------------------------------------------------------------

export type MfgSettings = {
  id: Id;
  defaultIssueMode: 'AUTO_AT_RELEASE' | 'SEPARATE';
  backflushDefault: boolean;
  rmWarehouse: Id | null;
  fgWarehouse: Id | null;
  scrapWarehouse: Id | null;
  quarantineWarehouse: Id | null;
  backdateDays: number;
  extraIssueApprovalPct: string;
  finalReceiptTolerancePct: string | null;
  autoCloseDays: number | null;
  overReceiptPct: string;
  itc04Frequency: 'ANNUAL' | 'HALF_YEARLY';
  jwInputLimitDays: number;
  jwCapitalLimitDays: number;
  jwInputAlertDays: number;
  jwCapitalAlertDays: number;
};

export const getMfgSettings = () => get<MfgSettings>(`${M}/settings/`);
export const updateMfgSettings = (body: Partial<MfgSettings>) => patch<MfgSettings>(`${M}/settings/`, body);

// --- recipes ------------------------------------------------------------------------------------------

export type RecipeLine = {
  id?: Id;
  component: Id;
  qty: string;
  unit?: Id | null;
  scrapPct?: string;
  issueMethod?: 'MANUAL' | 'BACKFLUSH';
  isOptional?: boolean;
  isPhantom?: boolean;
  alternateGroup?: number | null;
  alternatePriority?: number;
  sourceWarehouse?: Id | null;
  sequence?: number;
  notes?: string;
};

export type RecipeOutput = {
  id?: Id;
  product: Id;
  kind: 'CO_PRODUCT' | 'BY_PRODUCT' | 'SCRAP';
  qty: string;
  costSharePct?: string;
  recoveryRate?: string | null;
  targetWarehouse?: Id | null;
};

export type RecipeExtraCost = {
  id?: Id;
  label: string;
  element: 'OTHER' | 'LABOUR' | 'OVERHEAD' | 'MACHINE';
  basis: 'PER_UNIT' | 'PER_BATCH';
  amount: string;
};

export type Recipe = {
  id: Id;
  product: Id;
  name: string;
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED';
  revisionNo: number;
  effectiveFrom: string | null;
  effectiveTo: string | null;
  isDefault: boolean;
  customer: Id | null;
  parentRevision: Id | null;
  changeReason: string;
  outputQty: string;
  yieldPct: string;
  fgWarehouse: Id | null;
  notes: string;
  isLocked: boolean;
  lines: RecipeLine[];
  outputs: RecipeOutput[];
  additionalCosts?: RecipeExtraCost[];
  createdAt: string;
};

export const listRecipes = (params?: { product?: Id; status?: string }) => list<Recipe>(`${M}/boms/`, params);
export const getRecipe = (id: Id) => get<Recipe>(`${M}/boms/${id}/`);
export const saveRecipe = (id: Id | null, body: Partial<Recipe>) =>
  id ? patch<Recipe>(`${M}/boms/${id}/`, body) : post<Recipe>(`${M}/boms/`, body, true);
export const reviseRecipe = (id: Id, reason: string) => post<Recipe>(`${M}/boms/${id}/revise/`, { reason });
export const activateRecipe = (id: Id, body?: { makeDefault?: boolean; effectiveFrom?: string }) =>
  post<Recipe>(`${M}/boms/${id}/activate/`, body);
export const archiveRecipe = (id: Id) => post<Recipe>(`${M}/boms/${id}/archive/`);
export const deleteRecipe = (id: Id) => del(`${M}/boms/${id}/`);

export type ImportResult = {
  recipes: Array<{ product: string; name: string; materials: number; outputs: number; firstRow: number }>;
  errors: Array<{ row: number; message: string }>;
  created: number;
  committed: boolean;
};

export async function importRecipes(file: File, commit: boolean): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('commit', commit ? 'true' : 'false');
  try {
    const { data } = await apiClient.post(`${M}/boms/import/`, form, { headers: { 'Content-Type': 'multipart/form-data' } });
    return unwrapData<ImportResult>(data);
  } catch (err) {
    // A file with bad rows comes back 422 with the row list; show it rather than an error banner.
    if (axios.isAxiosError(err) && err.response?.status === 422) return unwrapData<ImportResult>(err.response.data);
    throw err;
  }
}
export const downloadRecipeTemplate = () => downloadFile(`${M}/boms/import-template/`);
export const downloadRecipeExport = () => downloadFile(`${M}/boms/export/`);

export type RoutingOp = {
  id?: Id;
  sequence: number;
  name: string;
  workCentre: Id;
  workCentreCode?: string;
  setupMinutes: string;
  runMinutesPerUnit: string;
  isSubcontract?: boolean;
  subcontractSupplier?: Id | null;
  notes?: string;
};
export const getRouting = (bomId: Id) => get<{ bom: Id; operations: RoutingOp[] }>(`${M}/boms/${bomId}/routing/`);
export const saveRouting = (bomId: Id, operations: RoutingOp[]) =>
  put<{ bom: Id; operations: RoutingOp[] }>(`${M}/boms/${bomId}/routing/`, { operations });

// --- work orders ----------------------------------------------------------------------------------------

export type WorkOrderRow = {
  id: Id;
  number: string;
  kind: 'STANDARD' | 'REWORK';
  bom: Id | null;
  product: Id | null;
  productName: string;
  qty: string;
  status: 'DRAFT' | 'RELEASED' | 'IN_PROGRESS' | 'COMPLETED' | 'CLOSED' | 'CANCELLED';
  warehouse: Id | null;
  fgWarehouse: Id | null;
  dueDate: string | null;
  plannedStart: string | null;
  priority: number;
  delayReason: string;
  salesOrder: Id | null;
  principal: Id | null;
  issueMode: 'AUTO_AT_RELEASE' | 'SEPARATE';
  qtyCompleted: string;
  qtyRejected: string;
  qtyRework: string;
  estimatedUnitCost?: string | null;
  costIssued?: string;
  costReturned?: string;
  costAbsorbed?: string;
  costReceived?: string;
  costVariance?: string;
  wipValue?: string;
  notes: string;
  componentLines: Array<{
    id: Id;
    component: Id;
    qty: string;
    qtyIssued: string;
    qtyReturned: string;
    issueMethod: string;
    principalSupplied: boolean;
    batch: Id | null;
  }>;
  plannedOutputs: Array<{ id: Id; product: Id; kind: string; qty: string; costSharePct: string }>;
  releasedAt: string | null;
  completedAt: string | null;
  closedAt: string | null;
  createdAt: string;
};

export const listWorkOrders = (params?: { status?: string; product?: Id; dueBefore?: string }) =>
  list<WorkOrderRow>(`${M}/work-orders/`, params);
export const getWorkOrder = (id: Id) => get<WorkOrderRow>(`${M}/work-orders/${id}/`);
export const saveWorkOrder = (id: Id | null, body: Record<string, unknown>) =>
  id ? patch<WorkOrderRow>(`${M}/work-orders/${id}/`, body) : post<WorkOrderRow>(`${M}/work-orders/`, body, true);
export const workOrderAction = (id: Id, action: 'release' | 'complete' | 'cancel' | 'close' | 'reopen', body?: unknown) =>
  post<WorkOrderRow>(`${M}/work-orders/${id}/${action}/`, body);
export const setPriority = (id: Id, body: { priority: number; delayReason?: string; dueDate?: string }) =>
  post<{ id: Id; priority: number }>(`${M}/work-orders/${id}/set-priority/`, body);
export const fromSalesOrder = (salesOrder: Id) =>
  post<{ created: Array<{ id: Id; number: string; qty: string }>; skipped: Array<{ item: Id; reason: string }> }>(
    `${M}/work-orders/from-sales-order/`,
    { salesOrder },
  );

export type Availability = {
  workOrder: Id;
  lines: Array<{
    lineId: Id;
    product: { id: Id; name: string; sku: string };
    need: string;
    held: string;
    free: string;
    short: string;
    alternates: Array<{ product: { id: Id; name: string }; free: string }>;
  }>;
};
export const getAvailability = (id: Id) => get<Availability>(`${M}/work-orders/${id}/availability/`);

// --- documents: issue, return, receipt ------------------------------------------------------------------

export type DocStatus = 'DRAFT' | 'POSTED' | 'REVERSED';
export type IssueDoc = {
  id: Id;
  number: string;
  status: DocStatus;
  workOrder: Id;
  docDate: string | null;
  notes: string;
  lines: Array<{
    id: Id;
    woLine: Id | null;
    component: Id;
    componentName: string;
    warehouse: Id;
    batch: Id | null;
    qty: string;
    isExtra: boolean;
    extraReason: string;
    unitCost?: string | null;
    costAmount?: string;
  }>;
  approval?: 'NONE' | 'REQUESTED' | 'APPROVED' | 'REJECTED';
  approvalNote?: string;
  reversedAt: string | null;
  reverseReason: string;
};
export type ReturnDoc = Omit<IssueDoc, 'lines'> & {
  lines: Array<{ id: Id; woLine: Id | null; component: Id; componentName: string; warehouse: Id; qty: string; costAmount?: string }>;
};
export type ReceiptDoc = {
  id: Id;
  number: string;
  status: DocStatus;
  workOrder: Id;
  docDate: string | null;
  isFinal: boolean;
  batchNo: string;
  expDate: string | null;
  notes: string;
  totalCost?: string;
  absorbedCost?: string;
  lines: Array<{
    id: Id;
    kind: 'MAIN' | 'CO_PRODUCT' | 'BY_PRODUCT' | 'SCRAP';
    product: Id;
    productName: string;
    warehouse: Id;
    qtyGood: string;
    qtyRejected: string;
    qtyRework: string;
    costAmount?: string;
    unitCost?: string | null;
  }>;
  reversedAt: string | null;
  reverseReason: string;
};

export type IssueLineIn = { woLine?: Id; component?: Id; qty: string; warehouse?: Id; batch?: Id; serialNumbers?: string[]; extraReason?: string };
export const listIssues = (workOrder: Id) => list<IssueDoc>(`${M}/material-issues/`, { workOrder });
export const createIssue = (body: { workOrder: Id; docDate?: string; notes?: string; lines?: IssueLineIn[] }) =>
  post<IssueDoc>(`${M}/material-issues/`, body, true);
export const postIssue = (id: Id) => post<IssueDoc>(`${M}/material-issues/${id}/post/`, {}, true);
export const reverseIssue = (id: Id, reason: string) => post<IssueDoc>(`${M}/material-issues/${id}/reverse/`, { reason }, true);
export const discardIssue = (id: Id) => del(`${M}/material-issues/${id}/discard/`);
/** A floor user asks a manager to approve a draft that goes over the plan; the manager's approval posts it. */
export const requestIssueApproval = (id: Id, note?: string) => post<IssueDoc>(`${M}/material-issues/${id}/request-approval/`, { note: note ?? '' });
export const approveIssue = (id: Id, note?: string) => post<IssueDoc>(`${M}/material-issues/${id}/approve/`, { note: note ?? '' }, true);
export const rejectIssue = (id: Id, note: string) => post<IssueDoc>(`${M}/material-issues/${id}/reject/`, { note });
export const listIssuesWaitingForApproval = () => list<IssueDoc & { workOrderNumber: string }>(`${M}/material-issues/`, { approval: 'REQUESTED' });

export const listReturns = (workOrder: Id) => list<ReturnDoc>(`${M}/material-returns/`, { workOrder });
export const createReturn = (body: {
  workOrder: Id;
  docDate?: string;
  notes?: string;
  lines: Array<{ woLine: Id; qty: string; warehouse?: Id; batch?: Id; serialNumbers?: string[] }>;
}) => post<ReturnDoc>(`${M}/material-returns/`, body, true);
export const postReturn = (id: Id) => post<ReturnDoc>(`${M}/material-returns/${id}/post/`, {}, true);
export const reverseReturn = (id: Id, reason: string) => post<ReturnDoc>(`${M}/material-returns/${id}/reverse/`, { reason }, true);
export const discardReturn = (id: Id) => del(`${M}/material-returns/${id}/discard/`);

export type ReceiptLineIn = {
  kind?: 'MAIN' | 'CO_PRODUCT' | 'BY_PRODUCT' | 'SCRAP';
  product?: Id;
  qtyGood?: string;
  qtyRejected?: string;
  qtyRework?: string;
  warehouse?: Id;
  serialNumbers?: string[];
};
export const listReceipts = (workOrder: Id) => list<ReceiptDoc>(`${M}/production-receipts/`, { workOrder });
export const createReceipt = (body: {
  workOrder: Id;
  docDate?: string;
  isFinal?: boolean;
  batchNo?: string;
  expDate?: string;
  mfgDate?: string;
  notes?: string;
  lines?: ReceiptLineIn[];
}) => post<ReceiptDoc>(`${M}/production-receipts/`, body, true);
export const postReceipt = (id: Id, overrideWip = false) =>
  post<ReceiptDoc>(`${M}/production-receipts/${id}/post/`, { overrideWip }, true);
export const reverseReceipt = (id: Id, reason: string) =>
  post<ReceiptDoc>(`${M}/production-receipts/${id}/reverse/`, { reason }, true);
export const discardReceipt = (id: Id) => del(`${M}/production-receipts/${id}/discard/`);

export type QuickProductionIn = {
  product: Id;
  qty: string;
  docDate?: string;
  customer?: Id;
  warehouse?: Id;
  fgWarehouse?: Id;
  batchNo?: string;
  expDate?: string;
  mfgDate?: string;
  notes?: string;
  components?: Array<{ component: Id; qty: string }>;
};
export const quickProduction = (body: QuickProductionIn, key?: string) =>
  apiClient
    .post(`${M}/quick-production/`, body, { headers: idempotencyHeaders(key) })
    .then((r) => unwrapData<WorkOrderRow>(r.data));

// --- trace ---------------------------------------------------------------------------------------------

export type TraceBack = {
  batch: string;
  direction: 'back';
  inputs: Array<{
    depth: number;
    outputBatch: string;
    product: string;
    batch: string;
    serial: string;
    qty: string;
    workOrder: Id;
    source?: { movementType: string; number?: string; supplier?: string } | null;
  }>;
};
export type TraceForward = {
  batch: string;
  direction: 'forward';
  madeFromIt: Array<{ depth: number; fromBatch: string; batch: string; product: string; workOrder: Id }>;
  sentTo: Array<{ batch: string; product: string; qty: string; date: string; number?: string; customer?: string }>;
};
export type BatchHit = { id: Id; batchNo: string; product: Id; productName: string; expiryDate: string | null; qualityStatus: string };
export const searchBatches = (q: string, product?: Id) =>
  get<{ results: BatchHit[] }>(`${M}/batches/`, { q, product }).then((r) => r.results);
export const traceBatch = (batch: Id, direction: 'back' | 'forward') =>
  get<TraceBack | TraceForward>(`${M}/trace/`, { batch, direction });

// --- planning --------------------------------------------------------------------------------------------

export type BoardRow = {
  id: Id;
  number: string;
  product: string;
  qty: string;
  qtyDone: string;
  status: string;
  priority: number;
  dueDate: string | null;
  late: boolean;
  dueSoon: boolean;
  shortMaterial: boolean;
  delayReason: string;
};
export const getBoard = () => get<{ orders: BoardRow[] }>(`${M}/board/`);
export const getShortages = () =>
  get<{
    orders: Array<{
      workOrder: { id: Id; number: string; dueDate: string | null; priority: number };
      lines: Array<{ product: { id: Id; name: string; sku: string }; need: string; allocated: string; short: string }>;
    }>;
  }>(`${M}/shortages/`);
export const getCanMake = (product: Id) =>
  get<{ product: Id; qty: string; limitedBy: Id | null; limitedByName: string }>(`${M}/can-make/`, { product });
export const getAtp = (product: Id, date?: string) =>
  get<{ product: Id; asOf: string; supply: string; committed: string; available: string }>(`${M}/atp/`, { product, date });
export const getExplosion = (product: Id, qty: string) =>
  get<{ rows: Array<{ level: number; product: { id: Id; name: string; sku: string }; qty: string; hasBom: boolean; phantom: boolean; unit: string }> }>(
    `${M}/explode/`,
    { product, qty },
  );
export const getWhereUsed = (product: Id) =>
  get<{ usedIn: Array<{ level: number; productId: Id; product: string; qtyPerBatch: string }> }>(`${M}/where-used/`, { product });
export const getCostRollup = (product: Id, qty?: string) =>
  get<{ unitCost: string; total: string }>(`${M}/cost-rollup/`, { product, qty });
export const getSalesOrderStatus = (salesOrder: Id) =>
  get<{
    lines: Array<{ item: Id; product: string; ordered: string; shipped: string; planned: string; made: string; expected: string | null; workOrders: Array<{ id: Id; number: string; status: string }> }>;
  }>(`${M}/sales-order-status/`, { salesOrder });

export type MrpLineRow = {
  id: Id;
  product: { id: Id; name: string; sku: string };
  kind: 'PURCHASE' | 'MAKE';
  level: number;
  needDate: string | null;
  orderBy: string | null;
  grossQty: string;
  safetyQty: string;
  onHandQty: string;
  incomingQty: string;
  netQty: string;
  suggestedQty: string;
  supplier: { id: Id; name: string } | null;
  status: 'OPEN' | 'CONVERTED' | 'SKIPPED';
  convertedType: string;
  convertedId: Id | null;
  note: string;
};
export type MrpRunRow = {
  id: Id;
  number: string;
  asOf: string;
  horizonDays: number;
  status: string;
  summary: { lines?: number; purchase?: number; make?: number };
  createdAt: string;
  lines?: MrpLineRow[];
};
export const listMrpRuns = () => get<MrpRunRow[]>(`${M}/mrp-runs/`);
export const getMrpRun = (id: Id) => get<MrpRunRow>(`${M}/mrp-runs/${id}/`);
export const runMrp = (horizonDays: number) => post<MrpRunRow>(`${M}/mrp-runs/run/`, { horizonDays });
export const convertMrp = (id: Id, body: { lines?: Id[]; suppliers?: Record<string, Id> }) =>
  post<{ purchaseOrders: Array<{ id: Id; supplier: string }>; workOrders: Array<{ id: Id; number: string }>; skipped: Id[] }>(
    `${M}/mrp-runs/${id}/convert/`,
    body,
  );

// --- reports ---------------------------------------------------------------------------------------------

export type ReportSlug =
  | 'wip'
  | 'work-order-cost'
  | 'variance'
  | 'yield-wastage'
  | 'consumption'
  | 'output'
  | 'on-time'
  | 'scrap-register'
  | 'profitability'
  | 'reconciliation';
export const getReport = (slug: ReportSlug, params?: Record<string, unknown>) =>
  get<Record<string, unknown>>(`${M}/reports/${slug}/`, params);
export const downloadReport = (slug: ReportSlug, params?: Record<string, unknown>) =>
  downloadFile(`${M}/reports/${slug}/`, { ...(params ?? {}), export: 'csv' });

export type StandardCost = {
  id: Id;
  product: Id;
  productName: string;
  effectiveFrom: string;
  material: string;
  labour: string;
  overhead: string;
  unitCost: string;
  notes: string;
};
export const listStandardCosts = (product?: Id) => list<StandardCost>(`${M}/standard-costs/`, { product });
export const saveStandardCost = (id: Id | null, body: Partial<StandardCost>) =>
  id ? patch<StandardCost>(`${M}/standard-costs/${id}/`, body) : post<StandardCost>(`${M}/standard-costs/`, body);
export const deleteStandardCost = (id: Id) => del(`${M}/standard-costs/${id}/`);

export type RevaluationLine = {
  id: Id;
  product: Id;
  productName: string;
  warehouse: Id;
  warehouseName: string;
  batch: Id | null;
  batchNo: string | null;
  qty: string;
  oldUnitCost: string;
  newUnitCost: string;
  oldValue: string;
  newValue: string;
  change: string;
};
export type Revaluation = {
  id: Id;
  number: string;
  status: 'DRAFT' | 'POSTED' | 'REVERSED';
  asOf: string;
  product: Id | null;
  productName: string | null;
  notes: string;
  totalBefore: string;
  totalAfter: string;
  totalChange: string;
  lines: RevaluationLine[];
  postedAt: string | null;
  reversedAt: string | null;
  reverseReason: string;
};
/** Preview what re-pricing stock to the standard cost in force would do. Nothing moves until it is posted. */
export const previewRevaluation = (body: { asOf?: string; product?: Id; notes?: string }) => post<Revaluation>(`${M}/standard-revaluations/`, body);
export const listRevaluations = () => list<Revaluation>(`${M}/standard-revaluations/`);
export const postRevaluation = (id: Id) => post<Revaluation>(`${M}/standard-revaluations/${id}/post/`, {}, true);
export const reverseRevaluation = (id: Id, reason: string) => post<Revaluation>(`${M}/standard-revaluations/${id}/reverse/`, { reason }, true);
export const discardRevaluation = (id: Id) => del(`${M}/standard-revaluations/${id}/discard/`);

// --- quality ---------------------------------------------------------------------------------------------

export type InspectionTemplate = {
  id: Id;
  name: string;
  product: Id | null;
  stage: 'INCOMING' | 'IN_PROCESS' | 'FINAL';
  sampleSize: number;
  notes: string;
  isActive: boolean;
  parameters: Array<{
    id?: Id;
    name: string;
    kind: 'NUMERIC' | 'TEXT' | 'PASS_FAIL';
    minValue: string | null;
    maxValue: string | null;
    unit: string;
    mandatory: boolean;
    sequence?: number;
  }>;
};
export const listTemplates = (params?: { product?: Id; stage?: string }) => list<InspectionTemplate>(`${Q}/templates/`, params);
export const saveTemplate = (id: Id | null, body: Partial<InspectionTemplate>) =>
  id ? patch<InspectionTemplate>(`${Q}/templates/${id}/`, body) : post<InspectionTemplate>(`${Q}/templates/`, body);
export const deleteTemplate = (id: Id) => del(`${Q}/templates/${id}/`);

export type Inspection = {
  id: Id;
  number: string;
  templateName: string;
  stage: string;
  status: 'DRAFT' | 'COMPLETED' | 'CANCELLED';
  decision: 'PENDING' | 'PASS' | 'FAIL' | 'HOLD' | 'REWORK';
  sourceType: string;
  product: Id;
  productName: string;
  batch: Id | null;
  batchNo: string;
  grnItem: Id | null;
  qtyInspected: string;
  qtyAccepted: string;
  qtyRejected: string;
  decidedAt: string | null;
  notes: string;
  results: Array<{
    id: Id;
    name: string;
    kind: 'NUMERIC' | 'TEXT' | 'PASS_FAIL';
    minValue: string | null;
    maxValue: string | null;
    unit: string;
    mandatory: boolean;
    valueNumeric: string | null;
    valueText: string;
    passed: boolean | null;
  }>;
  createdAt: string;
};
export const listInspections = (params?: { status?: string; decision?: string; stage?: string; batch?: Id }) =>
  list<Inspection>(`${Q}/inspections/`, params);
export const getInspection = (id: Id) => get<Inspection>(`${Q}/inspections/${id}/`);
export const createInspection = (body: {
  product: Id;
  qty: string;
  stage: string;
  sourceType?: string;
  template?: Id;
  batch?: Id;
  grnItem?: Id;
  notes?: string;
}) => post<Inspection>(`${Q}/inspections/`, body, true);
export const recordResults = (id: Id, results: Record<string, string>) =>
  post<Inspection>(`${Q}/inspections/${id}/record-results/`, { results });
export const completeInspection = (id: Id, body?: { decision?: string; qtyAccepted?: string; notes?: string }) =>
  post<Inspection>(`${Q}/inspections/${id}/complete/`, body, true);
export const cancelInspection = (id: Id) => post<Inspection>(`${Q}/inspections/${id}/cancel/`);
/** A print-ready page from the server, opened in its own window so the browser can print it. */
export async function openPrintPage(url: string): Promise<void> {
  const res = await apiClient.get(url, { responseType: 'text' });
  const w = window.open('', '_blank');
  if (w) {
    w.document.write(String(res.data));
    w.document.close();
    w.focus();
  }
}
export const printWorkOrder = (id: Id) => openPrintPage(`${M}/work-orders/${id}/print/`);
export const printIssueSlip = (id: Id) => openPrintPage(`${M}/material-issues/${id}/print/`);export const printBatchLabels = (receiptId: Id, copies = 1) => openPrintPage(`${M}/production-receipts/${receiptId}/print-label/?copies=${copies}`);
export const exportWorkOrders = (params?: Record<string, unknown>) => downloadFile(`${M}/work-orders/export/`, params);
export const certificateUrl = (id: Id) => `${Q}/inspections/${id}/certificate/`;
export const fetchCertificate = async (id: Id): Promise<string> => {
  const res = await apiClient.get(certificateUrl(id), { responseType: 'text' });
  return String(res.data);
};

export type Ncr = {
  id: Id;
  number: string;
  sourceType: string;
  product: Id | null;
  productName: string;
  batch: Id | null;
  supplier: Id | null;
  customer: Id | null;
  defectCode: Id | null;
  qty: string;
  description: string;
  rootCause: string;
  actionTaken: string;
  preventiveAction: string;
  dueDate: string | null;
  status: 'OPEN' | 'ACTION' | 'VERIFIED' | 'CLOSED';
  closedAt: string | null;
  createdAt: string;
};
export const listNcrs = (params?: { status?: string; supplier?: Id }) => list<Ncr>(`${Q}/non-conformances/`, params);
export const saveNcr = (id: Id | null, body: Partial<Ncr>) =>
  id ? patch<Ncr>(`${Q}/non-conformances/${id}/`, body) : post<Ncr>(`${Q}/non-conformances/`, body);
export const advanceNcr = (
  id: Id,
  body: { status?: string; rootCause?: string; actionTaken?: string; preventiveAction?: string; description?: string; dueDate?: string | null },
) => post<Ncr>(`${Q}/non-conformances/${id}/advance/`, body);

export type DefectCode = { id: Id; code: string; name: string; severity: 'MINOR' | 'MAJOR' | 'CRITICAL'; isActive: boolean };
export const listDefectCodes = () => list<DefectCode>(`${Q}/defect-codes/`);
export const saveDefectCode = (id: Id | null, body: Partial<DefectCode>) =>
  id ? patch<DefectCode>(`${Q}/defect-codes/${id}/`, body) : post<DefectCode>(`${Q}/defect-codes/`, body);

export type ScorecardRow = {
  supplier: Id;
  name: string;
  receipts: number;
  receivedQty: string;
  rejectedQty: string;
  rejectionPct: string;
  onTimePct: string | null;
  avgLeadDays: string | null;
  openNcrs: number;
};
export const getScorecard = (params?: { from?: string; to?: string }) => get<{ suppliers: ScorecardRow[] }>(`${Q}/supplier-scorecard/`, params);
export const setBatchStatus = (batch: Id, status: string, reason: string) =>
  post<{ id: Id; batchNo: string; qualityStatus: string }>(`${Q}/batches/${batch}/status/`, { status, reason });

// --- job work ----------------------------------------------------------------------------------------------

export type JobWorkOrder = {
  id: Id;
  number: string;
  direction: 'OUT' | 'IN';
  status: 'OPEN' | 'CLOSED' | 'CANCELLED';
  supplier: Id | null;
  supplierName: string;
  customer: Id | null;
  customerName: string;
  process: string;
  expectedReturnDate: string | null;
  serviceSac: string;
  directSupplyDeclared: boolean;
  notes: string;
  createdAt: string;
};
export const listJobWorkOrders = (params?: { direction?: string; status?: string }) => list<JobWorkOrder>(`${J}/orders/`, params);
export const createJobWorkOrder = (body: {
  direction: 'OUT' | 'IN';
  supplier?: Id;
  customer?: Id;
  process?: string;
  expectedReturnDate?: string;
  directSupplyDeclared?: boolean;
  notes?: string;
}) => post<JobWorkOrder>(`${J}/orders/`, body, true);
export const closeJobWorkOrder = (id: Id) => post<JobWorkOrder>(`${J}/orders/${id}/close/`);

export type Challan = {
  id: Id;
  number: string;
  status: 'DRAFT' | 'ISSUED' | 'REVERSED';
  order: Id;
  orderNumber: string;
  challanDate: string;
  origin: string;
  vehicleNo: string;
  ewayBillNo: string;
  purpose: string;
  notes: string;
  lines: Array<{ id: Id; product: Id; productName: string; qty: string; goodsKind: string; unitCost: string | null; qtySettled: string; qtyOpen: string }>;
};
export const listChallans = (params?: { order?: Id; status?: string }) => list<Challan>(`${J}/challans/`, params);
export const createChallan = (body: {
  order: Id;
  challanDate?: string;
  warehouse?: Id;
  vehicleNo?: string;
  notes?: string;
  lines: Array<{ product: Id; qty: string; batch?: Id; goodsKind?: string; serialNumbers?: string[] }>;
}) => post<Challan>(`${J}/challans/`, body, true);
export const issueChallan = (id: Id) => post<Challan>(`${J}/challans/${id}/issue/`, {}, true);
export const reverseChallan = (id: Id, reason: string) => post<Challan>(`${J}/challans/${id}/reverse/`, { reason });

export type JwReceiptKind =
  | 'PROCESSED'
  | 'UNPROCESSED_RETURN'
  | 'SCRAP_RETURNED'
  | 'SCRAP_RETAINED'
  | 'SENT_TO_OTHER'
  | 'SUPPLIED_FROM_JW';
export type JwReceipt = {
  id: Id;
  number: string;
  status: 'DRAFT' | 'POSTED' | 'REVERSED';
  order: Id;
  orderNumber: string;
  receiptDate: string;
  notes: string;
  lines: Array<{ id: Id; kind: JwReceiptKind; product: Id; productName: string; qty: string; inputProduct: Id | null; inputQty: string; chargeAmount: string; costAmount: string }>;
};
export const listJwReceipts = (params?: { order?: Id; status?: string }) => list<JwReceipt>(`${J}/receipts/`, params);
export const createJwReceipt = (body: {
  order: Id;
  receiptDate?: string;
  warehouse?: Id;
  notes?: string;
  lines: Array<{
    kind: JwReceiptKind;
    product?: Id;
    qty?: string;
    inputProduct?: Id;
    inputQty?: string;
    chargeAmount?: string;
    unitCost?: string;
    otherOrder?: Id;
    invoiceRef?: string;
    lossQty?: string;
  }>;
}) => post<JwReceipt>(`${J}/receipts/`, body, true);
export const postJwReceipt = (id: Id) => post<JwReceipt>(`${J}/receipts/${id}/post/`, {}, true);
export const reverseJwReceipt = (id: Id, reason: string) => post<JwReceipt>(`${J}/receipts/${id}/reverse/`, { reason });

export const getJwBalance = () =>
  get<{
    atJobWorkers: Array<{ supplier: Id; supplierName: string; product: Id; productName: string; qty: string; value: string }>;
    customersMaterial: Array<{ principal: Id; principalName: string; product: Id; productName: string; qty: string }>;
  }>(`${J}/balance/`);
export type AgeingRow = {
  challanLine: Id;
  challan: string;
  challanDate: string;
  supplier: string;
  product: string;
  openQty: string;
  value: string;
  goodsKind: string;
  days: number;
  limitDays: number;
  dueBy: string;
  status: 'OK' | 'ALERT' | 'OVERDUE';
};
export const getJwAgeing = (asOf?: string) => get<{ rows: AgeingRow[]; overdue: number }>(`${J}/ageing/`, { asOf });

export type Itc04Tables = {
  from: string;
  to: string;
  table4: Array<Record<string, unknown>>;
  table5a: Array<Record<string, unknown>>;
  table5b: Array<Record<string, unknown>>;
  table5c: Array<Record<string, unknown>>;
  summary: Record<string, unknown>;
};
export const getItc04 = (from: string, to: string) => get<Itc04Tables>(`${J}/itc04/`, { from, to });
export const downloadItc04 = (from: string, to: string) => downloadFile(`${J}/itc04/`, { from, to, export: 'csv' });
export type Itc04Filing = { id: Id; periodLabel: string; fromDate: string; toDate: string; status: 'DRAFT' | 'EXPORTED' | 'FILED'; summary: Record<string, unknown>; filedOn: string | null; acknowledgement: string };
export const listItc04Filings = () => list<Itc04Filing>(`${J}/itc04-filings/`);
export const prepareItc04 = (fy: number, half?: number) => post<Itc04Filing & { dueDate: string }>(`${J}/itc04-filings/prepare/`, { fy, half });
export const markItc04Filed = (id: Id, body: { filedOn?: string; acknowledgement?: string }) =>
  post<Itc04Filing>(`${J}/itc04-filings/${id}/mark-filed/`, body);
export const getItc04Due = () =>
  get<{ frequency: string; periods: Array<{ label: string; from: string; to: string; dueDate: string; filed: boolean }> }>(`${J}/itc04-filings/due/`);

export const receiveCustomerMaterial = (order: Id, body: { challanDate?: string; vehicleNo?: string; lines: Array<{ product: Id; qty: string }> }) =>
  post<Challan>(`${J}/orders/${order}/receive-material/`, body, true);
export const returnCustomerMaterial = (order: Id, body: { challanDate?: string; vehicleNo?: string; lines: Array<{ product: Id; qty: string }> }) =>
  post<Challan>(`${J}/orders/${order}/return-material/`, body, true);
export const recordCustomerLoss = (order: Id, body: { product: Id; qty: string; reference?: string }) =>
  post<unknown>(`${J}/orders/${order}/record-loss/`, body);

// --- shop floor --------------------------------------------------------------------------------------------

export type WorkCentre = { id: Id; code: string; name: string; kind: string; hoursPerDay: string; labourRate: string; machineRate: string; overheadRate: string; isActive: boolean };
export const listWorkCentres = () => list<WorkCentre>(`${M}/work-centres/`);
export const saveWorkCentre = (id: Id | null, body: Partial<WorkCentre>) =>
  id ? patch<WorkCentre>(`${M}/work-centres/${id}/`, body) : post<WorkCentre>(`${M}/work-centres/`, body);

export type JobCard = {
  id: Id;
  workOrder: Id;
  workOrderNumber: string;
  sequence: number;
  name: string;
  workCentre: Id;
  workCentreCode: string;
  status: 'PLANNED' | 'IN_PROGRESS' | 'PAUSED' | 'DONE' | 'CANCELLED';
  qtyPlanned: string;
  qtyGood: string;
  qtyRejected: string;
  plannedMinutes: string;
  minutesWorked: string;
  isSubcontract: boolean;
  running: boolean;
  labourCost: string;
  machineCost: string;
  overheadCost: string;
  jobworkOrderId?: Id | null;
  outsideCost?: string;
};
export const listJobCards = (params?: { workOrder?: Id; status?: string; workCentre?: Id }) => list<JobCard>(`${M}/job-cards/`, params);
export const createJobCards = (workOrder: Id) => post<JobCard[]>(`${M}/job-cards/create-for-order/`, { workOrder });
export const jobCardAction = (id: Id, action: 'start' | 'pause' | 'report' | 'finish' | 'reopen', body?: { qtyGood?: string; qtyRejected?: string }) =>
  post<JobCard>(`${M}/job-cards/${id}/${action}/`, body);

export type SubcontractDefaults = { supplier: Id | null; lines: Array<{ product: Id; qty: string }> };
export const getSubcontractDefaults = (cardId: Id) => get<SubcontractDefaults>(`${M}/job-cards/${cardId}/subcontract-defaults/`);
/** Raise the job-work order and challan for a step done by a job worker. */
export const sendStepToJobWorker = (
  cardId: Id,
  body: { supplier?: Id; lines: Array<{ product: Id; qty: string }>; expectedReturnDate?: string; vehicleNo?: string; notes?: string; issue: boolean },
) => post<{ card: JobCard; order: { id: Id; number: string }; challan: { id: Id; number: string; status: string } }>(`${M}/job-cards/${cardId}/subcontract/`, body, true);

export type LoadGrid = { from: string; to: string; workCentres: Array<{ workCentre: Id; code: string; name: string; overloadedDays: number; days: Array<{ date: string; minutes: string; capacity: string; overloaded: boolean }> }> };
export const getLoad = (from?: string, days = 14) => get<LoadGrid>(`${M}/load/`, { from, days });
export const getUtilisation = (from: string, to: string) =>
  get<{ workCentres: Array<{ code: string; name: string; workedMinutes: string; availableMinutes: string; utilisationPct: string | null; downtimeMinutes: string; good: string; goodPerHour: string | null }>; people: Array<{ who: string; hours: string; cards: number }> }>(
    `${M}/utilisation/`,
    { from, to },
  );

export type DowntimeReason = { id: Id; code: string; name: string; isPlanned: boolean; isActive: boolean };
export const listDowntimeReasons = () => list<DowntimeReason>(`${M}/downtime-reasons/`);
export const saveDowntimeReason = (id: Id | null, body: Partial<DowntimeReason>) =>
  id ? patch<DowntimeReason>(`${M}/downtime-reasons/${id}/`, body) : post<DowntimeReason>(`${M}/downtime-reasons/`, body);
export type DowntimeEvent = { id: Id; workCentre: Id; workCentreCode: string; reasonName: string; startedAt: string; endedAt: string | null; minutes: string; notes: string };
export const listDowntime = (open?: boolean) => list<DowntimeEvent>(`${M}/downtime/`, open ? { open: 1 } : undefined);
export const startDowntime = (body: { workCentre: Id; reason: Id; notes?: string }) => post<DowntimeEvent>(`${M}/downtime/start/`, body);
export const endDowntime = (id: Id) => post<DowntimeEvent>(`${M}/downtime/${id}/end/`);

export type Machine = { id: Id; code: string; name: string; workCentre: Id | null; runHours: string; isActive: boolean; notes: string };
export const listMachines = () => list<Machine>(`${M}/machines/`);
export const saveMachine = (id: Id | null, body: Partial<Machine>) =>
  id ? patch<Machine>(`${M}/machines/${id}/`, body) : post<Machine>(`${M}/machines/`, body);
export const reportBreakdown = (id: Id, description: string) => post<MaintenanceLog>(`${M}/machines/${id}/breakdown/`, { description });
export type MaintenancePlan = { id: Id; machine: Id; name: string; intervalDays: number | null; intervalHours: number | null; lastDoneOn: string | null; lastDoneHours: string; isActive: boolean };
export const listMaintenancePlans = () => list<MaintenancePlan>(`${M}/maintenance-plans/`);
export const saveMaintenancePlan = (id: Id | null, body: Partial<MaintenancePlan>) =>
  id ? patch<MaintenancePlan>(`${M}/maintenance-plans/${id}/`, body) : post<MaintenancePlan>(`${M}/maintenance-plans/`, body);
export const completeMaintenance = (id: Id, body?: { doneOn?: string; cost?: string; notes?: string }) =>
  post<MaintenanceLog>(`${M}/maintenance-plans/${id}/complete/`, body);
export const getMaintenanceDue = () =>
  get<{ plans: Array<{ plan: Id; machine: string; name: string; dueOn: string | null; hoursLeft: string | null; overdue: boolean }> }>(`${M}/maintenance-plans/due/`);
export type MaintenanceLog = { id: Id; machine: Id; machineName: string; kind: 'PREVENTIVE' | 'BREAKDOWN'; reportedAt: string; resolvedAt: string | null; description: string; cost: string; downtimeMinutes: string };
export const listMaintenanceLog = (open?: boolean) => list<MaintenanceLog>(`${M}/maintenance-log/`, open ? { open: 1 } : undefined);
export const resolveBreakdown = (id: Id, body: { cost?: string; notes?: string }) => post<MaintenanceLog>(`${M}/maintenance-log/${id}/resolve/`, body);

export type Operator = { id: Id; code: string; name: string; isActive: boolean; lockedUntil: string | null };
export const listOperators = () => list<Operator>(`${M}/operators/`);
export const createOperator = (body: { code: string; name: string; pin: string }) => post<Operator>(`${M}/operators/`, body);
export const setOperatorPin = (id: Id, pin: string) => post<{ ok: boolean }>(`${M}/operators/${id}/set-pin/`, { pin });
export const setOperatorActive = (id: Id, active: boolean) => post<Operator>(`${M}/operators/${id}/${active ? 'activate' : 'deactivate'}/`);

// --- the tablet (no account: operator code and PIN) ---------------------------------------------------------

const tabletClient = axios.create({ baseURL: apiClient.defaults.baseURL, withCredentials: false });
tabletClient.interceptors.request.use((cfg) => {
  const token = sessionStorage.getItem('bb.floor.token');
  if (token) cfg.headers.set('X-Operator-Token', token);
  return cfg;
});

export type TabletSession = { token: string; operator: { id: Id; name: string }; expiresIn: number };

export async function tabletLogin(company: number, code: string, pin: string): Promise<TabletSession> {
  const { data } = await tabletClient.post(`${M}/tablet/login/`, { company, code, pin });
  return unwrapData<TabletSession>(data);
}
export async function tabletCards(workCentre?: Id): Promise<JobCard[]> {
  const { data } = await tabletClient.get(`${M}/tablet/cards/`, { params: workCentre ? { work_centre: workCentre } : undefined });
  return unwrapData<{ cards: JobCard[] }>(data).cards;
}
export async function tabletCardAction(id: Id, verb: 'start' | 'pause' | 'report' | 'finish', body?: { qtyGood?: string; qtyRejected?: string }): Promise<JobCard> {
  const { data } = await tabletClient.post(`${M}/tablet/cards/${id}/${verb}/`, {
    qty_good: body?.qtyGood,
    qty_rejected: body?.qtyRejected,
  });
  return unwrapData<JobCard>(data);
}
// A tablet on a poor connection keeps what the operator tapped and sends it later, in order, with the moment of the tap
// and a key so a resend can never be applied twice. Kept in this tablet's own storage, tagged with the operator.

const QUEUE_KEY = 'bb.floor.queue';
const OPERATOR_KEY = 'bb.floor.operator';

export type TabletVerb = 'start' | 'pause' | 'report' | 'finish';
export type QueuedTap = { key: string; operator: number; cardId: Id; verb: TabletVerb; at: string; qtyGood?: string; qtyRejected?: string };

function readQueue(): QueuedTap[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(QUEUE_KEY) ?? '[]');
    return Array.isArray(parsed) ? (parsed as QueuedTap[]) : [];
  } catch {
    return [];
  }
}
function writeQueue(items: QueuedTap[]) {
  try {
    if (items.length) localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
    else localStorage.removeItem(QUEUE_KEY);
  } catch {
    /* storage full or blocked: the taps already sent are safe, the rest cannot be kept */
  }
}
export const tabletQueue = (): QueuedTap[] => readQueue();
export const rememberTabletOperator = (id: Id) => sessionStorage.setItem(OPERATOR_KEY, String(id));
const currentOperator = () => Number(sessionStorage.getItem(OPERATOR_KEY) ?? 0);

/** The server could not take the tap just now (busy, restarting, same tap still being handled, or signed out): try again later. */
export function shouldRetryLater(err: unknown): boolean {
  const status = axios.isAxiosError(err) ? (err.response?.status ?? 0) : 0;
  return [401, 403, 408, 409, 425, 429].includes(status) || status >= 500;
}

/** True when the call never reached the server (no signal, server down), as opposed to the server saying no. */
export function isOffline(err: unknown): boolean {
  return axios.isAxiosError(err) && !err.response;
}

async function sendTap(tap: QueuedTap): Promise<JobCard> {
  const { data } = await tabletClient.post(
    `${M}/tablet/cards/${tap.cardId}/${tap.verb}/`,
    { qty_good: tap.qtyGood, qty_rejected: tap.qtyRejected, occurred_at: tap.at },
    { headers: { 'Idempotency-Key': tap.key } },
  );
  return unwrapData<JobCard>(data);
}

/** Send a tap now; when there is no connection, keep it and say so. The queue goes first so order is kept. */
export async function tabletTap(
  cardId: Id,
  verb: TabletVerb,
  body?: { qtyGood?: string; qtyRejected?: string },
): Promise<{ queued: boolean; card?: JobCard }> {
  const tap: QueuedTap = {
    key: crypto.randomUUID(),
    operator: currentOperator(),
    cardId,
    verb,
    at: new Date().toISOString(),
    qtyGood: body?.qtyGood,
    qtyRejected: body?.qtyRejected,
  };
  // Behind this operator's own waiting taps, never behind another operator's.
  if (readQueue().some((q) => q.operator === tap.operator)) {
    writeQueue([...readQueue(), tap]);
    return { queued: true };
  }
  try {
    return { queued: false, card: await sendTap(tap) };
  } catch (err) {
    // No signal or a server that could not take it just now is kept; a refusal (and a sign-out) is shown to the operator.
    const status = axios.isAxiosError(err) ? (err.response?.status ?? 0) : 0;
    if (!isOffline(err) && !(shouldRetryLater(err) && ![401, 403].includes(status))) throw err;
    writeQueue([...readQueue(), tap]);
    return { queued: true };
  }
}

/** The cards as the operator would expect to see them, with the taps still waiting to be sent already applied. */
export function applyQueued(cards: JobCard[], queue: QueuedTap[]): JobCard[] {
  const next = cards.map((c) => ({ ...c }));
  for (const tap of queue) {
    const card = next.find((c) => c.id === tap.cardId);
    if (!card) continue;
    if (tap.verb === 'start') card.status = 'IN_PROGRESS';
    else if (tap.verb === 'pause') card.status = 'PAUSED';
    else if (tap.verb === 'finish') card.status = 'DONE';
    if (tap.verb === 'report' || tap.verb === 'finish') {
      card.qtyGood = String(Number(card.qtyGood) + Number(tap.qtyGood || 0));
      card.qtyRejected = String(Number(card.qtyRejected) + Number(tap.qtyRejected || 0));
    }
  }
  return next.filter((c) => c.status !== 'DONE');
}

/** Send what is waiting. Stops at the first tap that cannot reach the server; a tap the server refuses is dropped and reported. */
export async function flushTabletQueue(): Promise<{ sent: number; left: number; refused: string[] }> {
  const operator = currentOperator();
  const refused: string[] = [];
  let sent = 0;
  for (;;) {
    const all = readQueue();
    const next = all.find((q) => q.operator === operator);
    if (!next) break;
    try {
      await sendTap(next);
      sent += 1;
    } catch (err) {
      // No signal, the sign-in ended, or the server is busy or briefly down (a duplicate still in flight is 409):
      // none of these is the server refusing the tap, so keep it and everything behind it for the next try.
      if (isOffline(err) || shouldRetryLater(err)) break;
      refused.push(tabletErrorMessage(err));
    }
    writeQueue(readQueue().filter((q) => q.key !== next.key));
  }
  return { sent, left: readQueue().length, refused };
}

export function tabletErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: { message?: string }; detail?: string } | undefined;
    return data?.error?.message ?? data?.detail ?? err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
