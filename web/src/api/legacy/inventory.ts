import { apiClient, idempotencyHeaders, unwrapData } from '../client';
import { mockStock } from '@/mocks/data';
import type { StockAdjustment, StockAdjustmentResult, StockBalance } from '@/types/domain';
import { withMocks, fetchAllPagesMasters, fetchPage, flattenQueryParams } from './common';

const STOCK_ID_CHUNK = 250;

/** One item with its stock summed over godowns and lots (INV-IDR-10). */
export interface StockByProductRow {
  product: number;
  productName: string;
  sku: string;
  rackCode?: string;
  customFields?: Record<string, string>;
  /** Set when the list was asked for one godown. */
  warehouse: number | null;
  onHand: string | number;
  reserved: string | number;
  available: string | number;
  /** How many godown/lot rows make up the total. */
  lots: number;
  nearestExpiry: string | null;
}

export interface StockByProductPage {
  results: StockByProductRow[];
  count: number;
  next: string | null;
  /** Counted over the whole filtered list, not just this page. */
  summary: { items: number; itemsInStock: number; itemsOut: number };
}

export interface StockByProductParams {
  q?: string;
  cf?: Record<string, string[]>;
  warehouse?: number;
  ordering?: string;
  negative?: boolean;
  page?: number;
  pageSize?: number;
}

export const STOCK_PAGE_SIZE = 100;

function mockStockByProduct(params: StockByProductParams): StockByProductPage {
  let rows = mockStock;
  if (params.q) {
    const term = params.q.toLowerCase();
    rows = rows.filter(
      (s) =>
        s.productName.toLowerCase().includes(term) ||
        s.sku.toLowerCase().includes(term) ||
        Object.values(s.customFields ?? {}).some((value) => value.toLowerCase().includes(term)),
    );
  }
  if (params.cf) {
    rows = rows.filter((s) =>
      Object.entries(params.cf!).every(([key, values]) => {
        if (!values.length) return true;
        const current = (s.customFields?.[key] ?? '').toLowerCase();
        return values.some((value) => current === value.toLowerCase());
      }),
    );
  }
  if (params.negative) rows = rows.filter((s) => Number(s.available) <= 0);
  const results: StockByProductRow[] = rows.map((s) => ({
    product: s.product,
    productName: s.productName,
    sku: s.sku,
    customFields: s.customFields,
    warehouse: params.warehouse ?? null,
    onHand: s.onHand,
    reserved: s.reserved,
    available: s.available,
    lots: 1,
    nearestExpiry: null,
  }));
  const itemsOut = results.filter((r) => Number(r.available) <= 0).length;
  return {
    results,
    count: results.length,
    next: null,
    summary: { items: results.length, itemsInStock: results.length - itemsOut, itemsOut },
  };
}

export async function listStockByProduct(params: StockByProductParams = {}): Promise<StockByProductPage> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/inventory/balances/by-product/', {
      params: flattenQueryParams({
        ...params,
        negative: params.negative ? '1' : undefined,
        pageSize: params.pageSize ?? STOCK_PAGE_SIZE,
      }),
      paramsSerializer: { indexes: null },
    });
    const body = unwrapData<Partial<StockByProductPage> & { results?: StockByProductRow[] }>(data);
    return {
      results: body.results ?? [],
      count: body.count ?? (body.results ?? []).length,
      next: body.next ?? null,
      summary: body.summary ?? { items: 0, itemsInStock: 0, itemsOut: 0 },
    };
  }, () => mockStockByProduct(params));
}

/** Every page of the grouped list, for a print view. */
export async function listAllStockByProduct(params: StockByProductParams = {}): Promise<StockByProductRow[]> {
  const rows: StockByProductRow[] = [];
  for (let page = 1; page <= 200; page += 1) {
    const result = await listStockByProduct({ ...params, page, pageSize: 200 });
    rows.push(...result.results);
    if (!result.next) break;
  }
  return rows;
}

export async function listStock(params?: {
  q?: string;
  cf?: Record<string, string[]>;
  productIds?: number[];
  warehouse?: number;
}): Promise<StockBalance[]> {
  const allIds = params?.productIds?.filter((id) => Number.isFinite(id));
  if (allIds && allIds.length > STOCK_ID_CHUNK) {
    // The query string takes at most STOCK_ID_CHUNK ids. Dropping the rest would return rows for
    // only part of the list with no error, so ask in chunks and join the answers.
    const parts: StockBalance[][] = [];
    for (let i = 0; i < allIds.length; i += STOCK_ID_CHUNK) {
      parts.push(await listStock({ ...params, productIds: allIds.slice(i, i + STOCK_ID_CHUNK) }));
    }
    return parts.flat();
  }
  const productIds = allIds;
  const query = {
    q: params?.q,
    cf: params?.cf,
    warehouse: params?.warehouse,
    ...(productIds?.length ? { product_ids: productIds.join(',') } : {}),
  };
  return withMocks(
    async () => fetchAllPagesMasters<StockBalance>('/inventory/balances/', query),
    () => {
      let rows = mockStock;
      if (params?.q) {
        const term = params.q.toLowerCase();
        rows = rows.filter(
          (s) =>
            s.productName.toLowerCase().includes(term) ||
            s.sku.toLowerCase().includes(term) ||
            Object.values(s.customFields ?? {}).some((value) => value.toLowerCase().includes(term)),
        );
      }
      if (params?.cf) {
        rows = rows.filter((s) =>
          Object.entries(params.cf!).every(([key, values]) => {
            if (!values.length) return true;
            const current = (s.customFields?.[key] ?? '').toLowerCase();
            return values.some((value) => current === value.toLowerCase());
          }),
        );
      }
      return rows;
    },
  );
}

/**
 * Items at or below their reorder level (default), items out of stock with no reorder rule
 * (`out`), or both (`all`; rows carry `hasReorderRule` so a page can split them).
 */
export async function listLowStock(status?: unknown): Promise<StockBalance[]> {
  // Some callers hand this straight to react-query as the queryFn, which passes its context object.
  const wanted = status === 'out' || status === 'all' ? status : 'low';
  return withMocks(async () => {
    const { data } = await apiClient.get('/inventory/alerts/', wanted === 'low' ? undefined : { params: { status: wanted } });
    const body = unwrapData<{ count: number; items: StockBalance[] }>(data);
    return body.items ?? [];
  }, mockStock.filter((s) => Number(s.available) <= Number(s.reorderLevel)));
}

export async function createStockAdjustment(
  payload: StockAdjustment,
  options?: { idempotencyKey?: string },
): Promise<StockAdjustmentResult> {
  return withMocks(async () => {
    const response = await apiClient.post('/inventory/adjustments/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    const body = unwrapData<{ status?: string; approvalId?: number; warnings?: string[] }>(response.data) ?? {};
    // A 202 means "waiting for a second approver": nothing has moved. Anything else posted.
    const pending = response.status === 202 || body.status === 'PENDING';
    return {
      status: pending ? 'PENDING' : 'APPLIED',
      approvalId: body.approvalId,
      warnings: Array.isArray(body.warnings) ? body.warnings : undefined,
    };
  }, { status: 'APPLIED', approvalId: undefined, warnings: undefined });
}

export async function createOpeningStock(
  payload: import('@/types/domain').OpeningStockInput,
  options?: { idempotencyKey?: string },
): Promise<void> {
  return withMocks(async () => {
    await apiClient.post('/inventory/opening-stock/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
  }, undefined);
}

export const listWarehouses = () => fetchAllPagesMasters<import('@/types/domain').Warehouse>('/inventory/warehouses/');
export const createWarehouse = (payload: Record<string, unknown>) => apiClient.post('/inventory/warehouses/', payload).then(({ data }) => unwrapData(data));
export const updateWarehouse = (id: number, payload: Record<string, unknown>) => apiClient.patch(`/inventory/warehouses/${id}/`, payload).then(({ data }) => unwrapData(data));
export const listTransfers = () => fetchAllPagesMasters<import('@/types/domain').StockTransfer>('/inventory/transfers/');
export const createTransfer = (payload: Record<string, unknown>, options?: { idempotencyKey?: string }) =>
  apiClient
    .post('/inventory/transfers/', payload, { headers: idempotencyHeaders(options?.idempotencyKey) })
    .then(({ data }) => unwrapData(data));
export const completeTransfer = (id: number, options?: { idempotencyKey?: string }) =>
  apiClient
    .post(`/inventory/transfers/${id}/complete/`, {}, { headers: idempotencyHeaders(options?.idempotencyKey) })
    .then(({ data }) => unwrapData(data));
export const receiveTransfer = (
  id: number,
  options?: { idempotencyKey?: string; receipts?: Array<{ line: number; quantity: string; reason: string }> },
) =>
  apiClient
    .post(
      `/inventory/transfers/${id}/receive/`,
      options?.receipts?.length ? { receipts: options.receipts } : {},
      { headers: idempotencyHeaders(options?.idempotencyKey) },
    )
    .then(({ data }) => unwrapData(data));
export const resolveTransferShortage = (
  id: number,
  resolutions: Array<{ line: number; action: 'WRITE_OFF' | 'RETURN' }>,
  options?: { idempotencyKey?: string },
) =>
  apiClient
    .post(`/inventory/transfers/${id}/resolve-shortage/`, { resolutions }, { headers: idempotencyHeaders(options?.idempotencyKey) })
    .then(({ data }) => unwrapData(data));
export const cancelTransfer = (id: number) => apiClient.post(`/inventory/transfers/${id}/cancel/`).then(({ data }) => unwrapData(data));
export const listSerials = (params?: Record<string, string>) =>
  fetchAllPagesMasters<Record<string, unknown>>('/inventory/serials/', params);
export const transitionSerial = (id: number, payload: Record<string, unknown>, options?: { idempotencyKey?: string }) =>
  apiClient
    .post(`/inventory/serials/${id}/transition/`, payload, { headers: idempotencyHeaders(options?.idempotencyKey) })
    .then(({ data }) => unwrapData(data));
export const getExpiryAlerts = (days = 30, warehouse?: number) =>
  apiClient.get('/inventory/alerts/expiry/', { params: { days, warehouse } }).then(({ data }) => {
    const body = unwrapData<{ items?: Record<string, unknown>[] }>(data);
    return body.items ?? [];
  });
export const writeOffExpiry = (payload: {
  product: number;
  warehouse?: number;
  batch: number;
  quantity: number;
  /** Why the stock goes: EXPIRED (default) or DAMAGED. */
  reason?: 'EXPIRED' | 'DAMAGED';
}, options?: { idempotencyKey?: string }) =>
  apiClient
    .post('/inventory/alerts/expiry/', payload, { headers: idempotencyHeaders(options?.idempotencyKey) })
    .then(({ data }) => unwrapData(data));
export const listStockCounts = () => fetchAllPagesMasters<Record<string, unknown>>('/inventory/stock-counts/');
export const getStockCount = (id: number) =>
  apiClient.get(`/inventory/stock-counts/${id}/`).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const createStockCount = (payload: Record<string, unknown>) =>
  apiClient.post('/inventory/stock-counts/', payload).then(({ data }) => unwrapData(data));
export const updateStockCount = (id: number, payload: Record<string, unknown>) =>
  apiClient.patch(`/inventory/stock-counts/${id}/`, payload).then(({ data }) => unwrapData(data));
export const postStockCount = (
  id: number,
  payload?: Record<string, unknown>,
  opts?: { idempotencyKey?: string },
) =>
  apiClient
    .post(`/inventory/stock-counts/${id}/post/`, payload ?? {}, {
      headers: idempotencyHeaders(opts?.idempotencyKey),
    })
    .then(({ data }) => unwrapData(data));
/** The count sheet with system quantities, differences and what each is worth (even for a blind count). */
export const reviewStockCount = (id: number) =>
  apiClient.get(`/inventory/stock-counts/${id}/review/`).then(({ data }) => unwrapData<Record<string, unknown>>(data));
/** Count an item that is not on the sheet. */
export const addStockCountLine = (
  id: number,
  payload: { product: number; batch?: number; countedQty: string },
) =>
  apiClient
    .post(`/inventory/stock-counts/${id}/add-line/`, payload)
    .then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const cancelStockCount = (id: number) =>
  apiClient.post(`/inventory/stock-counts/${id}/cancel/`).then(({ data }) => unwrapData(data));
export const listReorderLevels = () => fetchAllPagesMasters<Record<string, unknown>>('/inventory/reorder-levels/');
export const createReorderLevel = (payload: Record<string, unknown>) =>
  apiClient.post('/inventory/reorder-levels/', payload).then(({ data }) => unwrapData(data));
export const deleteWarehouse = (id: number) => apiClient.delete(`/inventory/warehouses/${id}/`);
export const getStockValuation = (params?: Record<string, string>) => apiClient.get('/inventory/valuation/', { params }).then(({ data }) => unwrapData<Record<string, unknown>>(data));

/** One line of the item ledger (INV-WP-13). `runningBalance` is only filled when one item is chosen. */
export interface StockLedgerRow {
  id: number;
  movementDate: string;
  product: number;
  productName: string;
  sku: string;
  warehouse: number | null;
  warehouseName: string | null;
  batch: number | null;
  batchNo: string | null;
  movementType: string;
  movementTypeLabel: string;
  quantity: string | number;
  runningBalance: string | number | null;
  /** Null unless the user may see costs. */
  unitCost: string | number | null;
  reason: string;
  referenceType: string;
  referenceId: string;
  createdByName: string;
}

export interface LedgerFilters {
  product?: number;
  warehouse?: number;
  movementType?: string;
  dateFrom?: string;
  dateTo?: string;
  search?: string;
}

const ledgerParams = (filters: LedgerFilters) => ({
  product: filters.product || undefined,
  warehouse: filters.warehouse || undefined,
  movement_type: filters.movementType || undefined,
  date_from: filters.dateFrom || undefined,
  date_to: filters.dateTo || undefined,
  search: filters.search || undefined,
});

export const listStockLedger = (filters: LedgerFilters, page = 1) =>
  fetchPage<StockLedgerRow>('/inventory/movements/', { ...ledgerParams(filters), page });

export async function exportStockLedger(filters: LedgerFilters): Promise<{ url: string }> {
  const response = await apiClient.get('/inventory/movements/export/', {
    responseType: 'blob',
    // CSV bypasses the JSON envelope renderer
    transformResponse: [(d) => d],
    params: ledgerParams(filters),
  });
  const blob =
    response.data instanceof Blob ? response.data : new Blob([response.data as BlobPart], { type: 'text/csv' });
  return { url: URL.createObjectURL(blob) };
}

/** Raw ZPL for a thermal label printer: the item's name and barcode, `copies` times (the server caps it). */
export async function downloadLabelZpl(
  product: number,
  copies: number,
  options?: { size?: string; batch?: number | null; price?: boolean },
): Promise<{ url: string }> {
  const response = await apiClient.get('/inventory/labels.zpl', {
    params: {
      product,
      copies,
      size: options?.size,
      batch: options?.batch || undefined,
      price: options?.price === false ? 0 : undefined,
    },
    responseType: 'blob',
    transformResponse: [(d) => d],
  });
  const blob =
    response.data instanceof Blob ? response.data : new Blob([response.data as BlobPart], { type: 'text/plain' });
  return { url: URL.createObjectURL(blob) };
}

/** Every row of the sheet in one thermal-printer file. */
export async function downloadLabelsZpl(
  labels: Array<{ product: number; copies: number; batch?: number | null }>,
  options?: { size?: string; price?: boolean },
): Promise<{ url: string }> {
  const response = await apiClient.post(
    '/inventory/labels.zpl',
    { labels, size: options?.size, price: options?.price === false ? 0 : 1 },
    { responseType: 'blob', transformResponse: [(d) => d] },
  );
  const blob =
    response.data instanceof Blob ? response.data : new Blob([response.data as BlobPart], { type: 'text/plain' });
  return { url: URL.createObjectURL(blob) };
}

/** The sale document (invoice or challan) a sold serial went out on; null when it cannot be traced. */
export async function getSerialDocument(
  id: number,
): Promise<{ type: 'invoice' | 'challan'; id: number; number: string; path: string } | null> {
  const { data } = await apiClient.get(`/inventory/serials/${id}/document/`);
  return (data?.document as { type: 'invoice' | 'challan'; id: number; number: string; path: string } | null) ?? null;
}
