import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  role: 'OWNER',
  flags: { MFG_PLANNING: true } as Record<string, boolean>,
  board: [] as unknown[],
  shortages: [] as unknown[],
  run: null as unknown,
  report: {} as Record<string, unknown>,
  trace: null as unknown,
  reportCalls: [] as string[],
}));

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 7, role: state.role } }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return { ...actual, isRuntimeFlagEnabled: (key: string) => Boolean(state.flags[key]) };
});
vi.mock('@/pages/erp/erpShared', () => ({ ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('@/api/resources', () => ({
  listProducts: async () => [{ id: 1, name: 'Widget', sku: 'W-1' }],
  listWarehouses: async () => [{ id: 1, name: 'Main', code: 'M' }],
  listSuppliers: async () => [{ id: 5, name: 'Acme Metals' }],
  listCustomers: async () => [],
}));
vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    getBoard: vi.fn(async () => ({ orders: state.board })),
    getShortages: vi.fn(async () => ({ orders: state.shortages })),
    listMrpRuns: vi.fn(async () => (state.run ? [state.run] : [])),
    getMrpRun: vi.fn(async () => state.run),
    runMrp: vi.fn(async () => state.run),
    convertMrp: vi.fn(async () => ({ purchaseOrders: [{ id: 1, supplier: 'Acme Metals' }], workOrders: [], skipped: [] })),
    getLoad: vi.fn(async () => ({ from: '', to: '', workCentres: [] })),
    getCanMake: vi.fn(async () => ({ product: 1, qty: '12', limitedBy: null, limitedByName: '' })),
    getAtp: vi.fn(async () => ({ supply: '30', committed: '10', available: '20' })),
    getReport: vi.fn(async (slug: string) => {
      state.reportCalls.push(slug);
      return state.report;
    }),
    downloadReport: vi.fn(async () => new Blob(['a,b'])),
    saveBlob: vi.fn(),
    searchBatches: vi.fn(async () => [{ id: 9, batchNo: 'LOT-9', product: 1, productName: 'Widget', expiryDate: null, qualityStatus: 'RELEASED' }]),
    traceBatch: vi.fn(async () => state.trace),
    listStandardCosts: vi.fn(async () => []),
    listRevaluations: vi.fn(async () => []),
  };
});

import { convertMrp, getReport, runMrp, traceBatch } from '@/api/mfg';
import { MfgReportsPage } from './MfgReportsPage';
import { PlanningPage } from './PlanningPage';

const line = (over: Record<string, unknown>) => ({
  id: 1, product: { id: 1, name: 'Steel rod', sku: 'S' }, kind: 'PURCHASE', level: 0, needDate: '2026-11-01', orderBy: '2026-10-25',
  grossQty: '100', safetyQty: '0', onHandQty: '20', incomingQty: '0', netQty: '80', suggestedQty: '80', supplier: { id: 5, name: 'Acme Metals' },
  status: 'OPEN', convertedType: '', convertedId: null, note: '', ...over,
});

describe('Planning', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.flags = { MFG_PLANNING: true };
    state.board = [];
    state.shortages = [];
    state.run = null;
    vi.clearAllMocks();
  });

  it('is explained, not loaded, when planning is switched off', async () => {
    state.flags = {};
    renderRoutes([{ path: '/p', element: <PlanningPage /> }], '/p');
    expect(await screen.findByText(/not switched on for your company/i)).toBeTruthy();
  });

  it('counts the open, late and short orders on the board', async () => {
    state.board = [
      { id: 1, number: 'WO-1', product: 'Widget', qty: '10', qtyDone: '4', priority: 2, dueDate: '2026-10-01', status: 'RELEASED', late: true, dueSoon: false, shortMaterial: false, delayReason: 'MATERIAL' },
      { id: 2, number: 'WO-2', product: 'Bolt', qty: '5', qtyDone: '0', priority: 3, dueDate: '2026-12-01', status: 'RELEASED', late: false, dueSoon: false, shortMaterial: true, delayReason: '' },
    ];
    renderRoutes([{ path: '/p', element: <PlanningPage /> }], '/p');
    expect(await screen.findByRole('link', { name: 'WO-1' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'WO-1' }).getAttribute('href')).toBe('/manufacturing/work-orders/1');
    const open = screen.getByText(t('mfg.plan.open')).parentElement!;
    expect(within(open).getByText('2')).toBeTruthy();
    expect(screen.getAllByText(t('mfg.plan.shortMaterial'))[0].parentElement!.textContent).toContain('1');
  });

  it('says so when nothing is short, and names what is when something is', async () => {
    renderRoutes([{ path: '/p', element: <PlanningPage /> }], '/p');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.plan.tabShortages') }));
    expect(await screen.findByText(t('mfg.plan.noShortages'))).toBeTruthy();
  });

  it('lists the shortages of an order', async () => {
    state.shortages = [{ workOrder: { id: 3, number: 'WO-3', dueDate: '2026-11-02', priority: 1 }, lines: [{ product: { id: 4, name: 'Copper wire' }, need: '50', allocated: '10', short: '40' }] }];
    renderRoutes([{ path: '/p', element: <PlanningPage /> }], '/p');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.plan.tabShortages') }));
    expect(await screen.findByText('Copper wire')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'WO-3' })).toBeTruthy();
  });

  it('runs the plan for the chosen number of days and converts only the lines that were ticked', async () => {
    state.run = { id: 11, number: 'MRP-11', asOf: '2026-10-21', horizonDays: 30, summary: { purchase: 2, make: 0 }, lines: [line({ id: 1 }), line({ id: 2, product: { id: 2, name: 'Copper', sku: 'C' } })] };
    renderRoutes([{ path: '/p', element: <PlanningPage /> }], '/p');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.plan.tabMrp') }));
    const horizon = await screen.findByLabelText(t('mfg.plan.horizonDays'));
    await userEvent.clear(horizon);
    await userEvent.type(horizon, '14');
    await userEvent.click(screen.getByRole('button', { name: t('mfg.plan.runMrp') }));
    await waitFor(() => expect(runMrp).toHaveBeenCalledWith(14));
    const convert = await screen.findByRole('button', { name: t('mfg.plan.convert') });
    expect((convert as HTMLButtonElement).disabled).toBe(true); // nothing ticked yet
    const boxes = await screen.findAllByRole('checkbox');
    await userEvent.click(boxes[1]);
    await waitFor(() => expect((screen.getByRole('button', { name: t('mfg.plan.convert') }) as HTMLButtonElement).disabled).toBe(false));
    await userEvent.click(screen.getByRole('button', { name: t('mfg.plan.convert') }));
    await waitFor(() => expect(convertMrp).toHaveBeenCalledTimes(1));
    expect(vi.mocked(convertMrp).mock.calls[0]).toEqual([11, { lines: [2], suppliers: {} }]);
  });

  it('keeps run and convert closed to a role that may not plan', async () => {
    state.role = 'AUDITOR';
    state.run = { id: 11, number: 'MRP-11', asOf: '2026-10-21', horizonDays: 30, summary: {}, lines: [line({})] };
    renderRoutes([{ path: '/p', element: <PlanningPage /> }], '/p');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.plan.tabMrp') }));
    expect((await screen.findByRole('button', { name: t('mfg.plan.runMrp') }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('answers "can I make it" and "what can I promise" once an item is chosen', async () => {
    renderRoutes([{ path: '/p', element: <PlanningPage /> }], '/p');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.plan.tabAsk') }));
    await userEvent.click(await screen.findByLabelText(t('mfg.common.item')));
    await userEvent.click(await screen.findByRole('option', { name: /Widget/ }));
    expect(await screen.findByText('12')).toBeTruthy();
    expect(await screen.findByText(t('mfg.plan.available'))).toBeTruthy();
    expect(screen.getByText('20')).toBeTruthy();
  });
});

describe('Reports and trace', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.flags = {};
    state.report = {};
    state.trace = null;
    state.reportCalls = [];
    vi.clearAllMocks();
  });

  it('shows figures, lists and amounts of the chosen report, with money formatted', async () => {
    state.report = { totalWip: '12500.50', openOrders: 3, orders: [{ number: 'WO-1', product: 'Widget', ageDays: 12, wipValue: '900.00' }] };
    renderRoutes([{ path: '/r', element: <MfgReportsPage /> }], '/r');
    expect(await screen.findByText('WO-1')).toBeTruthy();
    expect(screen.getByText(/12,500\.50/)).toBeTruthy();
    await waitFor(() => expect(getReport).toHaveBeenCalled());
    expect(state.reportCalls[0]).toBe('wip');
  });

  it('hides the cost reports and the standard cost tab from a role that may not see costs', async () => {
    state.role = 'INVENTORY_STAFF';
    state.report = { consumption: [{ material: 'Flour', qty: '10' }] };
    renderRoutes([{ path: '/r', element: <MfgReportsPage /> }], '/r');
    await waitFor(() => expect(state.reportCalls.length).toBeGreaterThan(0));
    expect(state.reportCalls[0]).toBe('yield-wastage'); // the first report this role may see
    expect(screen.queryByRole('tab', { name: t('mfg.reports.tabStandard') })).toBeNull();
  });

  it('says so when a report has nothing in it', async () => {
    state.report = { orders: [] };
    renderRoutes([{ path: '/r', element: <MfgReportsPage /> }], '/r');
    expect(await screen.findByText(t('mfg.common.nothingYet'))).toBeTruthy();
  });

  it('traces a batch back to what went into it and forward to who got it', async () => {
    state.trace = { batch: 'LOT-9', direction: 'back', inputs: [{ depth: 1, outputBatch: 'LOT-9', product: 'Flour', batch: 'RAW-1', serial: '', qty: '20', workOrder: 4, source: { movementType: 'PURCHASE', number: 'PI-7', supplier: 'Mill Co' } }] };
    renderRoutes([{ path: '/r', element: <MfgReportsPage /> }], '/r');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.reports.tabTrace') }));
    await userEvent.click(await screen.findByRole('combobox', { name: new RegExp(t('mfg.common.batchNo'), 'i') }));
    await userEvent.type(screen.getByRole('combobox', { name: new RegExp(t('mfg.common.batchNo'), 'i') }), 'LOT');
    await userEvent.click(await screen.findByRole('option', { name: /LOT-9/ }));
    expect(await screen.findByText('RAW-1')).toBeTruthy();
    expect(screen.getByText(/Mill Co/)).toBeTruthy();
    expect(traceBatch).toHaveBeenCalledWith(9, 'back');
  });
});
