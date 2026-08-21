import { apiClient, unwrapData } from '../client';
import { mockStock } from '@/mocks/data';
import type { StockAdjustment, StockBalance } from '@/types/domain';
import { withMocks, fetchAllPagesMasters } from './common';

export async function listStock(): Promise<StockBalance[]> {
  return withMocks(async () => fetchAllPagesMasters<StockBalance>('/inventory/balances/'), mockStock);
}

export async function listLowStock(): Promise<StockBalance[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/inventory/alerts/');
    const body = unwrapData<{ count: number; items: StockBalance[] }>(data);
    return body.items ?? [];
  }, mockStock.filter((s) => Number(s.available) <= Number(s.reorderLevel)));
}

export async function createStockAdjustment(payload: StockAdjustment): Promise<void> {
  return withMocks(async () => {
    await apiClient.post('/inventory/adjustments/', payload);
  }, undefined);
}

export async function createOpeningStock(payload: import('@/types/domain').OpeningStockInput): Promise<void> {
  return withMocks(async () => {
    await apiClient.post('/inventory/opening-stock/', payload);
  }, undefined);
}

export const listWarehouses = () => fetchAllPagesMasters<import('@/types/domain').Warehouse>('/inventory/warehouses/');
export const createWarehouse = (payload: Record<string, unknown>) => apiClient.post('/inventory/warehouses/', payload).then(({ data }) => unwrapData(data));
export const updateWarehouse = (id: number, payload: Record<string, unknown>) => apiClient.patch(`/inventory/warehouses/${id}/`, payload).then(({ data }) => unwrapData(data));
export const listTransfers = () => fetchAllPagesMasters<import('@/types/domain').StockTransfer>('/inventory/transfers/');
export const createTransfer = (payload: Record<string, unknown>) => apiClient.post('/inventory/transfers/', payload).then(({ data }) => unwrapData(data));
export const completeTransfer = (id: number) => apiClient.post(`/inventory/transfers/${id}/complete/`).then(({ data }) => unwrapData(data));
export const cancelTransfer = (id: number) => apiClient.post(`/inventory/transfers/${id}/cancel/`).then(({ data }) => unwrapData(data));
export const listSerials = (params?: Record<string, string>) =>
  fetchAllPagesMasters<Record<string, unknown>>('/inventory/serials/', params);
export const transitionSerial = (id: number, payload: Record<string, unknown>) =>
  apiClient.post(`/inventory/serials/${id}/transition/`, payload).then(({ data }) => unwrapData(data));
export const getExpiryAlerts = (days = 30) => apiClient.get('/inventory/alerts/expiry/', { params: { days } }).then(({ data }) => {
  const body = unwrapData<{ items?: Record<string, unknown>[] }>(data);
  return body.items ?? [];
});
export const getStockValuation = (params?: Record<string, string>) => apiClient.get('/inventory/valuation/', { params }).then(({ data }) => unwrapData<Record<string, unknown>>(data));
