import { apiClient, unwrapData } from '../client';
import { mockCustomers, mockProducts, mockReceipts, mockSupplierPayments, mockSuppliers } from '@/mocks/data';
import type { Customer, CustomerReceipt, Product, Supplier, SupplierPayment, Unit } from '@/types/domain';
import { withMocks, fetchPage, fetchMoneyListFirstPage, fetchAllPagesMasters, type PageResult, type PageParams } from './common';

export async function listCustomers(params?: { q?: string }): Promise<Customer[]> {
  return withMocks(async () => fetchAllPagesMasters<Customer>('/customers/', params), mockCustomers);
}

export async function listCustomersPage(params?: {
  page?: number;
  pageSize?: number;
  q?: string;
  gstin?: string;
}): Promise<PageResult<Customer>> {
  return withMocks(
    async () => fetchPage<Customer>('/customers/', params),
    () => {
      let results = mockCustomers;
      if (params?.q) {
        results = results.filter((c) => c.name.toLowerCase().includes(params.q!.toLowerCase()));
      }
      if (params?.gstin) {
        const g = params.gstin.trim().toUpperCase();
        results = results.filter((c) => (c.gstin ?? '').toUpperCase() === g);
      }
      return { results, count: results.length, next: null, previous: null };
    },
  );
}

export async function getCustomer(id: number | string): Promise<Customer> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/customers/${id}/`);
    return unwrapData<Customer>(data);
  }, () => {
    const found = mockCustomers.find((c) => c.id === Number(id));
    if (!found) throw new Error('Customer not found');
    return found;
  });
}

export async function createCustomer(payload: Partial<Customer>): Promise<Customer> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/customers/', payload);
    return unwrapData<Customer>(data);
  }, { id: Date.now(), name: payload.name ?? '', status: 'ACTIVE', ...payload } as Customer);
}

export async function updateCustomer(id: number, payload: Partial<Customer>): Promise<Customer> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/customers/${id}/`, payload);
    return unwrapData<Customer>(data);
  }, { ...(mockCustomers[0] ?? { id, name: '', status: 'ACTIVE' }), ...payload, id } as Customer);
}

export async function listSuppliers(): Promise<Supplier[]> {
  return withMocks(async () => fetchAllPagesMasters<Supplier>('/suppliers/'), mockSuppliers);
}

export async function listSuppliersPage(params?: {
  page?: number;
  pageSize?: number;
  q?: string;
  gstin?: string;
}): Promise<PageResult<Supplier>> {
  return withMocks(
    async () => fetchPage<Supplier>('/suppliers/', params),
    () => {
      let results = mockSuppliers;
      if (params?.q) {
        results = results.filter((s) => s.name.toLowerCase().includes(params.q!.toLowerCase()));
      }
      if (params?.gstin) {
        const g = params.gstin.trim().toUpperCase();
        results = results.filter((s) => (s.gstin ?? '').toUpperCase() === g);
      }
      return { results, count: results.length, next: null, previous: null };
    },
  );
}

export async function getSupplier(id: number | string): Promise<Supplier> {
  return withMocks(async () => {
    const { data } = await apiClient.get(`/suppliers/${id}/`);
    return unwrapData<Supplier>(data);
  }, () => {
    const found = mockSuppliers.find((s) => s.id === Number(id));
    if (!found) throw new Error('Supplier not found');
    return found;
  });
}

export async function createSupplier(payload: Partial<Supplier>): Promise<Supplier> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/suppliers/', payload);
    return unwrapData<Supplier>(data);
  }, { id: Date.now(), name: payload.name ?? '', isActive: true, ...payload } as Supplier);
}

export async function updateSupplier(id: number, payload: Partial<Supplier>): Promise<Supplier> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/suppliers/${id}/`, payload);
    return unwrapData<Supplier>(data);
  }, { ...(mockSuppliers[0] ?? { id, name: '', isActive: true }), ...payload, id } as Supplier);
}

export async function listUnits(): Promise<Unit[]> {
  return withMocks(async () => fetchAllPagesMasters<Unit>('/masters/units/'), []);
}

export async function createUnit(payload: Partial<Unit>): Promise<Unit> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/masters/units/', payload);
    return unwrapData<Unit>(data);
  }, { id: Date.now(), name: payload.name ?? '', shortName: payload.shortName, uqcCode: payload.uqcCode } as Unit);
}

export async function updateUnit(id: number, payload: Partial<Unit>): Promise<Unit> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/masters/units/${id}/`, payload);
    return unwrapData<Unit>(data);
  }, { id, name: payload.name ?? '', ...payload } as Unit);
}

export async function listProducts(params?: { q?: string }): Promise<Product[]> {
  return withMocks(async () => fetchAllPagesMasters<Product>('/products/', params), () => filterProducts(params?.q));
}

export async function listProductsPage(params?: {
  page?: number;
  pageSize?: number;
  q?: string;
}): Promise<PageResult<Product>> {
  return withMocks(
    async () => fetchPage<Product>('/products/', params),
    () => {
      const all = filterProducts(params?.q);
      const pageSize = params?.pageSize ?? 50;
      const page = Math.max(1, params?.page ?? 1);
      const start = (page - 1) * pageSize;
      const results = all.slice(start, start + pageSize);
      const hasNext = start + pageSize < all.length;
      return {
        results,
        count: all.length,
        next: hasNext ? `mock://products/?page=${page + 1}` : null,
        previous: page > 1 ? `mock://products/?page=${page - 1}` : null,
      };
    },
  );
}

function filterProducts(q?: string): Product[] {
  if (!q) return mockProducts;
  const term = q.toLowerCase();
  return mockProducts.filter(
    (p) =>
      p.name.toLowerCase().includes(term) ||
      p.sku.toLowerCase().includes(term) ||
      (p.barcode && p.barcode.includes(term)),
  );
}

export async function searchProducts(q: string): Promise<Product[]> {
  return listProducts({ q });
}

export async function createProduct(payload: Partial<Product>): Promise<Product> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/products/', payload);
    return unwrapData<Product>(data);
  }, {
    id: Date.now(),
    name: payload.name ?? '',
    sku: payload.sku ?? '',
    gstRate: payload.gstRate ?? 18,
    purchasePrice: payload.purchasePrice ?? 0,
    sellingPrice: payload.sellingPrice ?? 0,
    reorderLevel: payload.reorderLevel ?? 0,
    status: 'ACTIVE',
    ...payload,
  } as Product);
}

export async function updateProduct(id: number, payload: Partial<Product>): Promise<Product> {
  return withMocks(async () => {
    const { data } = await apiClient.patch(`/products/${id}/`, payload);
    return unwrapData<Product>(data);
  }, { ...mockProducts[0], ...payload, id } as Product);
}

export async function listReceipts(): Promise<CustomerReceipt[]> {
  return withMocks(async () => fetchMoneyListFirstPage<CustomerReceipt>('/payments/receipts/'), mockReceipts);
}

export async function listSupplierPayments(params?: Record<string, string>): Promise<SupplierPayment[]> {
  return withMocks(
    async () => fetchMoneyListFirstPage<SupplierPayment>('/payments/supplier-payments/', params),
    mockSupplierPayments,
  );
}

export async function listSupplierPaymentsPage(params?: PageParams): Promise<PageResult<SupplierPayment>> {
  return withMocks(async () => fetchPage<SupplierPayment>('/payments/supplier-payments/', params), {
    results: mockSupplierPayments,
    count: mockSupplierPayments.length,
    next: null,
    previous: null,
  });
}

export async function createSupplierPayment(payload: {
  supplier: number;
  amount: number | string;
  mode: string;
  paymentDate?: string;
  reference?: string;
  notes?: string;
}): Promise<SupplierPayment> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/supplier-payments/', payload);
    return unwrapData<SupplierPayment>(data);
  }, {
    id: Date.now(),
    supplier: payload.supplier,
    amount: payload.amount,
    mode: payload.mode as SupplierPayment['mode'],
    paymentDate: payload.paymentDate ?? new Date().toISOString().slice(0, 10),
    allocated: 0,
    unallocated: payload.amount,
  });
}

export async function voidSupplierPayment(id: number, reason = ''): Promise<SupplierPayment> {
  const { data } = await apiClient.post(
    `/payments/supplier-payments/${id}/void/`,
    reason ? { reason } : {},
  );
  return unwrapData<SupplierPayment>(data);
}

export async function verifyCustomerGstin(id: number) {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/customers/${id}/verify-gstin/`);
    return unwrapData(data);
  }, { valid: true, status: 'ACTIVE', tradeName: 'Mock Customer' });
}

export async function verifySupplierGstin(id: number) {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/suppliers/${id}/verify-gstin/`);
    return unwrapData(data);
  }, { valid: true, status: 'ACTIVE', tradeName: 'Mock Supplier' });
}

export const listBatches = (product?: number) =>
  fetchAllPagesMasters<import('@/types/domain').BatchLot>('/inventory/batches/', product ? { product: String(product) } : undefined);
export const listPriceLists = () => fetchAllPagesMasters<Record<string, unknown>>('/masters/price-lists/');
export const createPriceList = (payload: Record<string, unknown>) => apiClient.post('/masters/price-lists/', payload).then(({ data }) => unwrapData(data));

