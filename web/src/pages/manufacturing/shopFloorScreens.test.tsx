import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  role: 'OWNER',
  flags: { MFG_SHOP_FLOOR: true } as Record<string, boolean>,
  cards: [] as unknown[],
  centres: [{ id: 2, code: 'CUT', name: 'Cutting', kind: 'MACHINE', hoursPerDay: '8', labourRate: '120', machineRate: '300', overheadRate: '60', isActive: true }] as unknown[],
  reasons: [{ id: 4, code: 'JAM', name: 'Jam', isPlanned: false, isActive: true }] as unknown[],
  downtime: [] as unknown[],
  machines: [] as unknown[],
  plans: [] as unknown[],
  due: { plans: [] } as unknown,
  log: [] as unknown[],
  operators: [] as unknown[],
  util: { workCentres: [], people: [] } as unknown,
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
  listSuppliers: async () => [{ id: 5, name: 'Ravi Dyers' }],
  listCustomers: async () => [],
}));
vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    listJobCards: vi.fn(async () => state.cards),
    jobCardAction: vi.fn(async () => ({})),
    listWorkCentres: vi.fn(async () => state.centres),
    saveWorkCentre: vi.fn(async () => ({ id: 9 })),
    listDowntimeReasons: vi.fn(async () => state.reasons),
    saveDowntimeReason: vi.fn(async () => ({ id: 10 })),
    listDowntime: vi.fn(async () => state.downtime),
    startDowntime: vi.fn(async () => ({ id: 11 })),
    endDowntime: vi.fn(async () => ({ id: 11 })),
    listMachines: vi.fn(async () => state.machines),
    saveMachine: vi.fn(async () => ({ id: 12 })),
    reportBreakdown: vi.fn(async () => ({ id: 13 })),
    listMaintenancePlans: vi.fn(async () => state.plans),
    saveMaintenancePlan: vi.fn(async () => ({ id: 14 })),
    getMaintenanceDue: vi.fn(async () => state.due),
    completeMaintenance: vi.fn(async () => ({ id: 15 })),
    listMaintenanceLog: vi.fn(async () => state.log),
    resolveBreakdown: vi.fn(async () => ({ id: 16 })),
    listOperators: vi.fn(async () => state.operators),
    createOperator: vi.fn(async () => ({ id: 17 })),
    setOperatorActive: vi.fn(async () => ({ id: 17 })),
    setOperatorPin: vi.fn(async () => ({ ok: true })),
    getUtilisation: vi.fn(async () => state.util),
    getSubcontractDefaults: vi.fn(async () => ({ supplier: 5, lines: [] })),
  };
});

import {
  completeMaintenance, createOperator, endDowntime, jobCardAction, reportBreakdown, saveMachine, saveMaintenancePlan,
  saveWorkCentre, setOperatorActive, setOperatorPin, startDowntime,
} from '@/api/mfg';
import { ShopFloorPage } from './ShopFloorPage';

const card = (over: Record<string, unknown>) => ({
  id: 1, workOrder: 4, workOrderNumber: 'WO-4', sequence: 10, name: 'Cut', workCentre: 2, workCentreCode: 'CUT', status: 'PLANNED',
  qtyPlanned: '100', qtyGood: '0', qtyRejected: '0', plannedMinutes: '80', minutesWorked: '0', isSubcontract: false, running: false,
  labourCost: '0', machineCost: '0', overheadCost: '0', jobworkOrderId: null, outsideCost: '0', ...over,
});

function open(tab: string) {
  renderRoutes([{ path: '/s', element: <ShopFloorPage /> }], '/s');
  return screen.findByRole('tab', { name: tab }).then((el) => userEvent.click(el));
}

describe('Shop floor screens', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.flags = { MFG_SHOP_FLOOR: true };
    state.cards = [];
    state.downtime = [];
    state.machines = [];
    state.plans = [];
    state.due = { plans: [] };
    state.log = [];
    state.operators = [];
    state.util = { workCentres: [], people: [] };
    vi.clearAllMocks();
  });

  it('is explained, not loaded, when the shop floor is switched off', async () => {
    state.flags = {};
    renderRoutes([{ path: '/s', element: <ShopFloorPage /> }], '/s');
    expect(await screen.findByText(/not switched on for your company/i)).toBeTruthy();
  });

  it('lists the cards that are running and reopens a finished one', async () => {
    state.cards = [card({ id: 1, status: 'DONE', qtyGood: '100' })];
    renderRoutes([{ path: '/s', element: <ShopFloorPage /> }], '/s');
    expect(await screen.findByText('WO-4')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: t('mfg.wo.reopen') }));
    await waitFor(() => expect(jobCardAction).toHaveBeenCalledWith(1, 'reopen'));
  });

  it('offers to send an outside step to the job worker, and shows one that is already out', async () => {
    state.flags = { MFG_SHOP_FLOOR: true, MFG_JOB_WORK: true };
    state.cards = [card({ id: 1, isSubcontract: true, status: 'PLANNED' }), card({ id: 2, sequence: 20, name: 'Plate', isSubcontract: true, status: 'IN_PROGRESS', jobworkOrderId: 8 })];
    renderRoutes([{ path: '/s', element: <ShopFloorPage /> }], '/s');
    expect(await screen.findByRole('button', { name: t('mfg.sub.sendButton') })).toBeTruthy();
    expect(screen.getByText(t('mfg.sub.atJobWorker'))).toBeTruthy();
  });

  it('starts a stoppage only once a work centre and a reason are chosen, then ends it', async () => {
    state.downtime = [{ id: 11, workCentre: 2, workCentreCode: 'CUT', reasonName: 'Jam', reason: 4, jobCard: null, startedAt: '2026-10-21T05:00:00Z', endedAt: null, minutes: '0', notes: '' }];
    await open(t('mfg.floor.tabDowntime'));
    const start = await screen.findByRole('button', { name: t('mfg.floor.startDowntime') });
    expect((start as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByLabelText(t('mfg.recipe.workCentre')));
    await userEvent.click(await screen.findByRole('option', { name: /CUT/ }));
    await userEvent.click(screen.getByLabelText(t('mfg.floor.reason')));
    await userEvent.click(await screen.findByRole('option', { name: 'Jam' }));
    await userEvent.click(screen.getByRole('button', { name: t('mfg.floor.startDowntime') }));
    await waitFor(() => expect(startDowntime).toHaveBeenCalledWith({ workCentre: 2, reason: 4 }));
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.floor.endDowntime') }));
    await waitFor(() => expect(endDowntime).toHaveBeenCalledWith(11));
  });

  it('adds a machine, plans its servicing, reports a breakdown and marks a service done', async () => {
    state.machines = [{ id: 12, code: 'M1', name: 'Mixer', runHours: '40', isActive: true }];
    state.due = { plans: [{ plan: 14, machine: 'Mixer', name: 'Grease', dueOn: '2026-09-01', hoursLeft: null, overdue: true }] };
    await open(t('mfg.floor.tabMachines'));
    expect(await screen.findByText(t('mfg.floor.maintenanceOverdue'))).toBeTruthy();
    await userEvent.type(screen.getAllByLabelText(t('mfg.common.code'))[0], 'M2');
    await userEvent.type(screen.getAllByLabelText(t('mfg.common.name'))[0], 'Oven');
    await userEvent.click(screen.getByRole('button', { name: t('mfg.floor.addMachine') }));
    await waitFor(() => expect(saveMachine).toHaveBeenCalledWith(null, { code: 'M2', name: 'Oven' }));
    await userEvent.click(screen.getByRole('button', { name: t('mfg.floor.reportBreakdown') }));
    await waitFor(() => expect(reportBreakdown).toHaveBeenCalledWith(12, t('mfg.floor.breakdownDefault')));
    await userEvent.click(screen.getByRole('button', { name: t('mfg.floor.markDone') }));
    await waitFor(() => expect(completeMaintenance).toHaveBeenCalledTimes(1));
    expect(vi.mocked(completeMaintenance).mock.calls[0][0]).toBe(14);
    await userEvent.click(screen.getByLabelText(t('mfg.floor.machine')));
    await userEvent.click(await screen.findByRole('option', { name: 'Mixer' }));
    await userEvent.type(screen.getAllByLabelText(t('mfg.common.name'))[1], 'Clean');
    await userEvent.type(screen.getByLabelText(t('mfg.floor.everyDays')), '15');
    await userEvent.click(screen.getAllByRole('button', { name: t('common.add') })[0]);
    await waitFor(() => expect(saveMaintenancePlan).toHaveBeenCalledWith(null, { machine: 12, name: 'Clean', intervalDays: 15 }));
  });

  it('adds a work centre with its hourly rates', async () => {
    await open(t('mfg.floor.tabCentres'));
    await userEvent.type(await screen.findByLabelText(t('mfg.common.code')), 'PACK');
    await userEvent.type(screen.getByLabelText(t('mfg.common.name')), 'Packing');
    await userEvent.type(screen.getByLabelText(t('mfg.floor.labourRate')), '90');
    await userEvent.click(screen.getByRole('button', { name: t('common.add') }));
    await waitFor(() => expect(saveWorkCentre).toHaveBeenCalledWith(null, { code: 'PACK', name: 'Packing', hoursPerDay: '8', labourRate: '90', machineRate: '0', overheadRate: '0' }));
    expect(screen.getByText('Cutting')).toBeTruthy();
  });

  it('needs a PIN of at least four digits to add an operator, and keeps only digits', async () => {
    await open(t('mfg.floor.tabOperators'));
    await userEvent.type(await screen.findByLabelText(t('mfg.common.code')), 'OP1');
    await userEvent.type(screen.getByLabelText(t('mfg.common.name')), 'Asha');
    const add = screen.getByRole('button', { name: t('common.add') });
    await userEvent.type(screen.getByLabelText(t('mfg.floor.pin')), '12a');
    expect((add as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText(t('mfg.floor.pin')), '34');
    expect((screen.getByLabelText(t('mfg.floor.pin')) as HTMLInputElement).value).toBe('1234');
    await userEvent.click(add);
    await waitFor(() => expect(createOperator).toHaveBeenCalledWith({ code: 'OP1', name: 'Asha', pin: '1234' }));
  });

  it('switches an operator off and changes a PIN', async () => {
    state.operators = [{ id: 17, code: 'OP1', name: 'Asha', isActive: true, lockedUntil: '2026-10-21T09:00:00Z' }];
    await open(t('mfg.floor.tabOperators'));
    await userEvent.click(await screen.findByRole('checkbox'));
    await waitFor(() => expect(setOperatorActive).toHaveBeenCalledWith(17, false));
    const pinBoxes = screen.getAllByDisplayValue('');
    await userEvent.type(pinBoxes[pinBoxes.length - 1], '9988');
    await userEvent.click(screen.getByRole('button', { name: t('mfg.floor.changePin') }));
    await waitFor(() => expect(setOperatorPin).toHaveBeenCalledWith(17, '9988'));
  });

  it('keeps set-up closed to the floor and open to a manager', async () => {
    state.role = 'INVENTORY_STAFF';
    await open(t('mfg.floor.tabCentres'));
    await userEvent.type(await screen.findByLabelText(t('mfg.common.code')), 'X');
    await userEvent.type(screen.getByLabelText(t('mfg.common.name')), 'Y');
    expect((screen.getByRole('button', { name: t('common.add') }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows how busy each work centre was', async () => {
    state.util = { workCentres: [{ code: 'CUT', name: 'Cutting', workedMinutes: '300', availableMinutes: '480', utilisationPct: '62.5', downtimeMinutes: '20', good: '90', goodPerHour: '18' }], people: [] };
    await open(t('mfg.floor.tabUtilisation'));
    expect(await screen.findByText('62.5%')).toBeTruthy();
    expect(screen.getByText('CUT · Cutting')).toBeTruthy();
  });
});
