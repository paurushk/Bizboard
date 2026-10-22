import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  role: 'OWNER',
  flags: { MFG_JOB_WORK: true } as Record<string, boolean>,
  orders: [] as unknown[],
  challans: [] as unknown[],
  receipts: [] as unknown[],
  balance: { atJobWorkers: [], customersMaterial: [] } as unknown,
  ageing: { rows: [], overdue: 0 } as unknown,
  due: { frequency: 'HALF_YEARLY', periods: [] } as unknown,
  filings: [] as unknown[],
  tables: { from: '', to: '', table4: [], table5a: [], table5b: [], table5c: [], summary: {} } as unknown,
}));

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 7, role: state.role } }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return { ...actual, isRuntimeFlagEnabled: (key: string) => Boolean(state.flags[key]) };
});
vi.mock('@/pages/erp/erpShared', () => ({ ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('@/api/resources', () => ({
  listProducts: async () => [{ id: 1, name: 'Flour', sku: 'F-1' }, { id: 2, name: 'Dyed cloth', sku: 'D-1' }],
  listWarehouses: async () => [{ id: 1, name: 'Main', code: 'M' }],
  listSuppliers: async () => [{ id: 5, name: 'Ravi Dyers' }],
  listCustomers: async () => [{ id: 6, name: 'Principal Mills' }],
}));
vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    listJobWorkOrders: vi.fn(async () => state.orders),
    createJobWorkOrder: vi.fn(async () => ({ id: 1 })),
    closeJobWorkOrder: vi.fn(async () => ({ id: 1 })),
    listChallans: vi.fn(async () => state.challans),
    createChallan: vi.fn(async () => ({ id: 31 })),
    issueChallan: vi.fn(async () => ({ id: 31 })),
    reverseChallan: vi.fn(async () => ({ id: 31 })),
    listJwReceipts: vi.fn(async () => state.receipts),
    createJwReceipt: vi.fn(async () => ({ id: 41 })),
    postJwReceipt: vi.fn(async () => ({ id: 41 })),
    reverseJwReceipt: vi.fn(async () => ({ id: 41 })),
    getJwBalance: vi.fn(async () => state.balance),
    getJwAgeing: vi.fn(async () => state.ageing),
    getItc04Due: vi.fn(async () => state.due),
    listItc04Filings: vi.fn(async () => state.filings),
    getItc04: vi.fn(async () => state.tables),
    prepareItc04: vi.fn(async () => ({ id: 1 })),
    markItc04Filed: vi.fn(async () => ({ id: 1 })),
    downloadItc04: vi.fn(async () => new Blob(['x'])),
    saveBlob: vi.fn(),
    receiveCustomerMaterial: vi.fn(async () => ({ id: 1 })),
  };
});

import { closeJobWorkOrder, createChallan, createJobWorkOrder, createJwReceipt, issueChallan, markItc04Filed, postJwReceipt, prepareItc04 } from '@/api/mfg';
import { JobWorkPage } from './JobWorkPage';

const order = { id: 3, number: 'JWO-3', direction: 'OUT', status: 'OPEN', supplier: 5, supplierName: 'Ravi Dyers', customer: null, customerName: '', process: 'Dyeing', expectedReturnDate: null, serviceSac: '9988', directSupplyDeclared: false, notes: '', createdAt: '' };

describe('Job work screens', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.flags = { MFG_JOB_WORK: true };
    state.orders = [];
    state.challans = [];
    state.receipts = [];
    state.balance = { atJobWorkers: [], customersMaterial: [] };
    state.ageing = { rows: [], overdue: 0 };
    state.due = { frequency: 'HALF_YEARLY', periods: [] };
    state.filings = [];
    state.tables = { from: '', to: '', table4: [], table5a: [], table5b: [], table5c: [], summary: {} };
    vi.clearAllMocks();
  });

  it('is explained, not loaded, when job work is switched off', async () => {
    state.flags = {};
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    expect(await screen.findByText(/not switched on for your company/i)).toBeTruthy();
  });

  it('will not raise an order until a job worker is chosen, then sends it with the process', async () => {
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    const create = await screen.findByRole('button', { name: t('mfg.jw.newOrder') });
    expect((create as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(await screen.findByRole('combobox', { name: t('mfg.jw.worker') }));
    await userEvent.click(await screen.findByRole('option', { name: /Ravi Dyers/ }));
    await userEvent.type(screen.getByLabelText(t('mfg.jw.process')), 'Dyeing');
    await userEvent.click(screen.getByRole('button', { name: t('mfg.jw.newOrder') }));
    await waitFor(() => expect(createJobWorkOrder).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createJobWorkOrder).mock.calls[0][0]).toMatchObject({ direction: 'OUT', supplier: 5, process: 'Dyeing' });
  });

  it('closes an open order', async () => {
    state.orders = [order];
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.jw.closeOrder') }));
    await waitFor(() => expect(closeJobWorkOrder).toHaveBeenCalledWith(3));
  });

  it('sends goods out with a challan and issues it in the same step', async () => {
    state.orders = [order];
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.jw.tabChallans') }));
    const issue = await screen.findByRole('button', { name: t('mfg.jw.issueChallan') });
    expect((issue as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(await screen.findByRole('combobox', { name: t('mfg.jw.order') }));
    await userEvent.click(await screen.findByRole('option', { name: /JWO-3/ }));
    await userEvent.click(screen.getAllByLabelText(t('mfg.common.item'))[0]);
    await userEvent.click(await screen.findByRole('option', { name: /Flour/ }));
    await userEvent.type(screen.getAllByLabelText(t('mfg.common.quantity'))[0], '20');
    await userEvent.type(screen.getByLabelText(t('mfg.jw.vehicle')), 'KA01AB1234');
    await userEvent.click(screen.getByRole('button', { name: t('mfg.jw.issueChallan') }));
    await waitFor(() => expect(issueChallan).toHaveBeenCalledWith(31));
    expect(vi.mocked(createChallan).mock.calls[0][0]).toMatchObject({ order: 3, vehicleNo: 'KA01AB1234', lines: [{ product: 1, qty: '20', goodsKind: 'INPUT' }] });
  });

  it('shows what is still out on each challan', async () => {
    state.challans = [{
      id: 31, number: 'JWC-31', status: 'ISSUED', order: 3, orderNumber: 'JWO-3', challanDate: '2026-10-01', origin: 'OWN_PREMISES', vehicleNo: '', ewayBillNo: '', purpose: '', notes: '',
      lines: [{ id: 1, product: 1, productName: 'Flour', qty: '20', goodsKind: 'INPUT', unitCost: '10', qtySettled: '5', qtyOpen: '15' }],
    }];
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.jw.tabChallans') }));
    expect(await screen.findByText(new RegExp(`Flour 20 \\(${t('mfg.jw.open')} 15\\)`))).toBeTruthy();
  });

  it('posts finished work coming back with the material used and the charge', async () => {
    state.orders = [order];
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.jw.tabReceipts') }));
    await userEvent.click(await screen.findByRole('combobox', { name: t('mfg.jw.order') }));
    await userEvent.click(await screen.findByRole('option', { name: /JWO-3/ }));
    await userEvent.click(screen.getAllByLabelText(t('mfg.common.item'))[0]);
    await userEvent.click(await screen.findByRole('option', { name: /Dyed cloth/ }));
    await userEvent.type(screen.getAllByLabelText(t('mfg.common.quantity'))[0], '18');
    await userEvent.click(screen.getByLabelText(t('mfg.jw.inputUsed')));
    await userEvent.click(await screen.findByRole('option', { name: /Flour/ }));
    await userEvent.type(screen.getByLabelText(t('mfg.jw.inputQty')), '20');
    await userEvent.type(screen.getByLabelText(t('mfg.jw.charge')), '90');
    await userEvent.click(screen.getByRole('button', { name: t('mfg.jw.postReceipt') }));
    await waitFor(() => expect(postJwReceipt).toHaveBeenCalledWith(41));
    expect(vi.mocked(createJwReceipt).mock.calls[0][0]).toMatchObject({
      order: 3, lines: [{ kind: 'PROCESSED', product: 2, qty: '18', inputProduct: 1, inputQty: '20', chargeAmount: '90' }],
    });
  });

  it('lists who holds what and the goods that are late', async () => {
    state.balance = { atJobWorkers: [{ supplier: 5, supplierName: 'Ravi Dyers', product: 1, productName: 'Flour', qty: '15', value: '150' }], customersMaterial: [] };
    state.ageing = { overdue: 1, rows: [{ challanLine: 1, challan: 'JWC-31', challanDate: '2025-01-01', supplier: 'Ravi Dyers', product: 'Flour', openQty: '15', value: '150', goodsKind: 'INPUT', days: 400, limitDays: 365, dueBy: '2026-01-01', status: 'OVERDUE' }] };
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.jw.tabBalance') }));
    expect(await screen.findByText('Ravi Dyers')).toBeTruthy();
    await userEvent.click(screen.getByRole('tab', { name: t('mfg.jw.tabAgeing') }));
    expect(await screen.findByText('400 / 365')).toBeTruthy();
    expect(screen.getByText('JWC-31')).toBeTruthy();
  });

  it('prepares the ITC-04 return and records that it was filed with its acknowledgement', async () => {
    state.filings = [{ id: 7, periodLabel: 'Apr-Sep 2026', fromDate: '2026-04-01', toDate: '2026-09-30', status: 'DRAFT', summary: {}, filedOn: null, acknowledgement: '' }];
    state.tables = { from: '', to: '', table4: [{ challan: 'JWC-31', qty: '20' }], table5a: [], table5b: [], table5c: [], summary: { unmatched: 2 } };
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.jw.tabItc04') }));
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.jw.showTables') }));
    expect(await screen.findByText('JWC-31')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: t('mfg.jw.prepare') }));
    await waitFor(() => expect(prepareItc04).toHaveBeenCalledTimes(1));
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.jw.markFiled') }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(t('mfg.jw.ack')), 'ARN-99');
    await userEvent.click(within(dialog).getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(markItc04Filed).toHaveBeenCalledTimes(1));
    expect(vi.mocked(markItc04Filed).mock.calls[0]).toEqual([7, expect.objectContaining({ acknowledgement: 'ARN-99' })]);
  });

  it('keeps filing closed to a role that is neither owner nor accountant-level planner', async () => {
    state.role = 'AUDITOR';
    state.filings = [{ id: 7, periodLabel: 'Apr-Sep 2026', fromDate: '', toDate: '', status: 'DRAFT', summary: {}, filedOn: null, acknowledgement: '' }];
    renderRoutes([{ path: '/j', element: <JobWorkPage /> }], '/j');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.jw.tabItc04') }));
    expect((await screen.findByRole('button', { name: t('mfg.jw.prepare') }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: t('mfg.jw.markFiled') }) as HTMLButtonElement).disabled).toBe(true);
  });
});
