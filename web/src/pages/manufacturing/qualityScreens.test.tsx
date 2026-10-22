import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  role: 'OWNER',
  flags: { MFG_QUALITY: true } as Record<string, boolean>,
  inspections: [] as unknown[],
  inspection: null as unknown,
  ncrs: [] as unknown[],
  templates: [] as unknown[],
  defects: [] as unknown[],
  scorecard: [] as unknown[],
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
  listSuppliers: async () => [],
  listCustomers: async () => [],
}));
vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    listInspections: vi.fn(async () => state.inspections),
    getInspection: vi.fn(async () => state.inspection),
    recordResults: vi.fn(async () => state.inspection),
    completeInspection: vi.fn(async () => ({ ...(state.inspection as object), status: 'COMPLETED', decision: 'PASS' })),
    cancelInspection: vi.fn(async () => state.inspection),
    createInspection: vi.fn(async () => ({ id: 77 })),
    listTemplates: vi.fn(async () => state.templates),
    saveTemplate: vi.fn(async () => ({ id: 5 })),
    listNcrs: vi.fn(async () => state.ncrs),
    saveNcr: vi.fn(async () => ({ id: 8 })),
    advanceNcr: vi.fn(async () => ({ id: 8 })),
    listDefectCodes: vi.fn(async () => state.defects),
    saveDefectCode: vi.fn(async () => ({ id: 3 })),
    getScorecard: vi.fn(async () => ({ suppliers: state.scorecard })),
    searchBatches: vi.fn(async () => []),
  };
});

import { advanceNcr, completeInspection, recordResults, saveDefectCode, saveNcr, saveTemplate } from '@/api/mfg';
import { QualityPage } from './QualityPage';

const draftInspection = {
  id: 12, number: 'QI-12', templateName: 'Final', stage: 'FINAL', status: 'DRAFT', decision: 'PENDING', sourceType: 'BATCH',
  product: 1, productName: 'Widget', batch: 3, batchNo: 'LOT-3', grnItem: null, qtyInspected: '10', qtyAccepted: '0', qtyRejected: '0',
  decidedAt: null, notes: '',
  results: [{ id: 91, name: 'Weight', kind: 'NUMERIC', minValue: '9', maxValue: '11', unit: 'g', mandatory: true, valueNumeric: null, valueText: '', passed: null }],
  createdAt: '2026-10-21',
};

describe('Quality screens', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.flags = { MFG_QUALITY: true };
    state.inspections = [];
    state.inspection = draftInspection;
    state.ncrs = [];
    state.templates = [];
    state.defects = [];
    state.scorecard = [];
    vi.clearAllMocks();
  });

  it('opens an inspection from its row, saves the results typed in and finishes it', async () => {
    state.inspections = [draftInspection];
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByText('QI-12'));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Weight *')).toBeTruthy();
    await userEvent.type(within(dialog).getAllByRole('textbox')[0], '10.5');
    await userEvent.click(within(dialog).getByRole('button', { name: t('mfg.quality.saveResults') }));
    await waitFor(() => expect(recordResults).toHaveBeenCalledWith(12, { '91': '10.5' }));
    await userEvent.click(within(dialog).getByRole('button', { name: t('mfg.quality.complete') }));
    await waitFor(() => expect(completeInspection).toHaveBeenCalledTimes(1));
    expect(vi.mocked(completeInspection).mock.calls[0][0]).toBe(12);
  });

  it('does not let a role that cannot inspect save or finish', async () => {
    state.role = 'AUDITOR';
    state.inspections = [draftInspection];
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByText('QI-12'));
    const dialog = await screen.findByRole('dialog');
    expect((await within(dialog).findByRole('button', { name: t('mfg.quality.complete') }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: t('mfg.quality.newInspection'), hidden: true }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers the certificate for a finished inspection only', async () => {
    state.inspection = { ...draftInspection, status: 'COMPLETED', decision: 'PASS' };
    state.inspections = [state.inspection];
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByText('QI-12'));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByRole('button', { name: t('mfg.quality.certificate') })).toBeTruthy();
    expect(within(dialog).queryByRole('button', { name: t('mfg.quality.complete') })).toBeNull();
  });

  it('reports a quality problem as an internal one and moves it one step forward', async () => {
    state.ncrs = [{ id: 8, number: 'NCR-8', sourceType: 'INTERNAL', product: 1, productName: 'Widget', description: 'Cracked lids', status: 'OPEN', dueDate: null, qty: '3' }];
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.quality.tabNcr') }));
    expect(await screen.findByText('Cracked lids')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: t('mfg.quality.ncr_ACTION') }));
    await waitFor(() => expect(advanceNcr).toHaveBeenCalledWith(8, { status: 'ACTION' }));
    await userEvent.click(screen.getByRole('button', { name: t('mfg.quality.newNcr') }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(t('mfg.common.description')), 'Label peeling');
    await userEvent.click(within(dialog).getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(saveNcr).toHaveBeenCalledTimes(1));
    expect(vi.mocked(saveNcr).mock.calls[0][0]).toBeNull();
    expect(vi.mocked(saveNcr).mock.calls[0][1]).toMatchObject({ sourceType: 'INTERNAL', description: 'Label peeling' });
  });

  it('builds a checklist with a numeric range and saves it', async () => {
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.quality.tabTemplates') }));
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.quality.newTemplate') }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getAllByLabelText(t('mfg.common.name'))[0], 'Dispatch check');
    await userEvent.click(within(dialog).getByRole('button', { name: t('mfg.quality.addParam') }));
    await userEvent.type(within(dialog).getAllByLabelText(t('mfg.common.name'))[1], 'Weight');
    await userEvent.type(within(dialog).getByLabelText(t('mfg.quality.min')), '9');
    await userEvent.type(within(dialog).getByLabelText(t('mfg.quality.max')), '11');
    await userEvent.click(within(dialog).getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(saveTemplate).toHaveBeenCalledTimes(1));
    const body = vi.mocked(saveTemplate).mock.calls[0][1] as { name: string; stage: string; parameters: Array<Record<string, unknown>> };
    expect(body).toMatchObject({ name: 'Dispatch check', stage: 'FINAL' });
    expect(body.parameters[0]).toMatchObject({ name: 'Weight', kind: 'NUMERIC', minValue: '9', maxValue: '11' });
  });

  it('adds a defect type only when it has a code and a name, and only for a manager', async () => {
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.quality.tabDefects') }));
    const add = await screen.findByRole('button', { name: t('common.add') });
    expect((add as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText(t('mfg.common.code')), 'CRK');
    await userEvent.type(screen.getByLabelText(t('mfg.common.name')), 'Crack');
    await userEvent.click(add);
    await waitFor(() => expect(saveDefectCode).toHaveBeenCalledWith(null, { code: 'CRK', name: 'Crack', severity: 'MINOR' }));
  });

  it('locks defect set-up for the floor', async () => {
    state.role = 'INVENTORY_STAFF';
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.quality.tabDefects') }));
    await userEvent.type(await screen.findByLabelText(t('mfg.common.code')), 'CRK');
    await userEvent.type(screen.getByLabelText(t('mfg.common.name')), 'Crack');
    expect((screen.getByRole('button', { name: t('common.add') }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows a supplier scorecard with rejection and on-time rates', async () => {
    state.scorecard = [{ supplier: 5, name: 'Acme Metals', receipts: 4, receivedQty: '400', rejectedQty: '20', rejectionPct: '5.0', onTimePct: null, avgLeadDays: '3.5', openNcrs: 1 }];
    renderRoutes([{ path: '/q', element: <QualityPage /> }], '/q');
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.quality.tabScorecard') }));
    expect(await screen.findByText('Acme Metals')).toBeTruthy();
    expect(screen.getByText('5.0%')).toBeTruthy();
    expect(screen.getByText('—')).toBeTruthy(); // no on-time figure yet
  });
});
