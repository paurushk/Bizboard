import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  role: 'OWNER',
  runs: [] as unknown[],
  issues: [] as unknown[],
  flags: {} as Record<string, boolean>,
  postIssueError: '' as string,
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 7, role: state.role } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return { ...actual, isRuntimeFlagEnabled: (key: string) => Boolean(state.flags[key]) };
});
vi.mock('@/pages/erp/erpShared', () => ({ ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('@/api/resources', () => ({
  listProducts: async () => [
    { id: 1, name: 'Widget', sku: 'W-1' },
    { id: 2, name: 'Bolt', sku: 'B-1' },
  ],
  listWarehouses: async () => [{ id: 1, name: 'Main', code: 'M' }],
  listSuppliers: async () => [{ id: 5, name: 'Shine Platers' }],
  listCustomers: async () => [],
}));

const wo = {
  id: 11,
  number: 'WO-11',
  kind: 'STANDARD',
  bom: 3,
  product: 1,
  productName: 'Widget',
  qty: '100',
  status: 'RELEASED',
  warehouse: 1,
  fgWarehouse: null,
  dueDate: null,
  plannedStart: null,
  priority: 3,
  delayReason: '',
  salesOrder: null,
  principal: null,
  issueMode: 'SEPARATE',
  qtyCompleted: '0',
  qtyRejected: '0',
  qtyRework: '0',
  notes: '',
  componentLines: [{ id: 21, component: 2, qty: '100', qtyIssued: '0', qtyReturned: '0', issueMethod: 'MANUAL', principalSupplied: false, batch: null }],
  plannedOutputs: [],
  releasedAt: null,
  completedAt: null,
  closedAt: null,
  createdAt: '2026-10-20',
};

vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    getWorkOrder: vi.fn(async () => wo),
    listIssues: vi.fn(async () => state.issues),
    listReturns: vi.fn(async () => []),
    listReceipts: vi.fn(async () => []),
    listJobCards: vi.fn(async () => []),
    getAvailability: vi.fn(async () => ({ lines: [] })),
    createIssue: vi.fn(async () => ({ id: 70, status: 'DRAFT' })),
    postIssue: vi.fn(async () => {
      if (state.postIssueError) {
        throw Object.assign(new Error('far over'), { isAxiosError: true, response: { status: 400, data: { error: { code: state.postIssueError, message: 'far over' } } } });
      }
      return { id: 70, status: 'POSTED' };
    }),
    requestIssueApproval: vi.fn(async () => ({ id: 70, approval: 'REQUESTED' })),
    approveIssue: vi.fn(async () => ({ id: 70, status: 'POSTED' })),
    rejectIssue: vi.fn(async () => ({ id: 70, approval: 'REJECTED' })),
    listRevaluations: vi.fn(async () => state.runs),
    previewRevaluation: vi.fn(async () => ({ id: 31 })),
    postRevaluation: vi.fn(async () => ({ id: 31, status: 'POSTED' })),
    reverseRevaluation: vi.fn(async () => ({ id: 31, status: 'REVERSED' })),
    discardRevaluation: vi.fn(async () => undefined),
    getSubcontractDefaults: vi.fn(async () => ({ supplier: 5, lines: [{ product: 2, qty: '100' }] })),
    sendStepToJobWorker: vi.fn(async () => ({ card: {}, order: { id: 1, number: 'JWO-1' }, challan: { id: 1, number: 'JWC-1', status: 'ISSUED' } })),
  };
});

import { requestIssueApproval, approveIssue, postRevaluation, previewRevaluation, rejectIssue, sendStepToJobWorker, type JobCard } from '@/api/mfg';
import { RevaluationPanel } from './RevaluationPanel';
import { SubcontractDialog } from './SubcontractDialog';
import { WorkOrderDetailPage } from './WorkOrderDetailPage';

const draftRun = {
  id: 31,
  number: '',
  status: 'DRAFT',
  asOf: '2026-10-21',
  product: null,
  productName: null,
  notes: '',
  totalBefore: '1000.00',
  totalAfter: '1200.00',
  totalChange: '200.00',
  lines: [
    { id: 1, product: 1, productName: 'Widget', warehouse: 1, warehouseName: 'Main', batch: null, batchNo: null, qty: '100', oldUnitCost: '10', newUnitCost: '12', oldValue: '1000.00', newValue: '1200.00', change: '200.00' },
  ],
  postedAt: null,
  reversedAt: null,
  reverseReason: '',
};

describe('Manufacturing workflows', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.runs = [];
    state.issues = [];
    state.flags = {};
    state.postIssueError = '';
    vi.clearAllMocks();
  });

  it('re-pricing shows the effect first and posts only on the button', async () => {
    state.runs = [draftRun];
    renderRoutes([{ path: '/r', element: <RevaluationPanel /> }], '/r');
    expect(await screen.findByText('Widget')).toBeTruthy();
    expect(screen.getByText(/Value at standard/)).toBeTruthy();
    expect(postRevaluation).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /post the re-pricing/i }));
    await waitFor(() => expect(postRevaluation).toHaveBeenCalledWith(31));
  });

  it('a preview is asked for with the chosen date', async () => {
    renderRoutes([{ path: '/r', element: <RevaluationPanel /> }], '/r');
    await userEvent.click(await screen.findByRole('button', { name: /^preview$/i }));
    await waitFor(() => expect(previewRevaluation).toHaveBeenCalledTimes(1));
    expect(vi.mocked(previewRevaluation).mock.calls[0][0]).toMatchObject({ asOf: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) });
  });

  it('only a manager can post a re-pricing', async () => {
    state.role = 'INVENTORY_STAFF';
    state.runs = [draftRun];
    renderRoutes([{ path: '/r', element: <RevaluationPanel /> }], '/r');
    expect(((await screen.findByRole('button', { name: /post the re-pricing/i })) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a step goes to the job worker with the material shown, and sends what is left after edits', async () => {
    const card = { id: 8, name: 'Plating', isSubcontract: true, status: 'PLANNED' } as JobCard;
    const done = vi.fn();
    renderRoutes([{ path: '/d', element: <SubcontractDialog card={card} onClose={() => undefined} onDone={done} /> }], '/d');
    expect(await screen.findByText(/Send "Plating" to a job worker/)).toBeTruthy();
    const qty = await screen.findByLabelText(/^quantity/i);
    await userEvent.clear(qty);
    await userEvent.type(qty, '60');
    await userEvent.click(screen.getByRole('button', { name: /^send to job worker$/i }));
    await waitFor(() => expect(sendStepToJobWorker).toHaveBeenCalledTimes(1));
    expect(vi.mocked(sendStepToJobWorker).mock.calls[0]).toEqual([
      8,
      expect.objectContaining({ supplier: 5, lines: [{ product: 2, qty: '60' }], issue: true }),
    ]);
    await waitFor(() => expect(done).toHaveBeenCalled());
  });

  it('extra material the floor cannot post keeps the draft and offers to ask a manager', async () => {
    state.role = 'INVENTORY_STAFF';
    state.postIssueError = 'MFG_EXTRA_NEEDS_MANAGER';
    renderRoutes([{ path: '/w/:id', element: <WorkOrderDetailPage /> }], '/w/11');
    await userEvent.click(await screen.findByRole('tab', { name: /material/i }));
    await userEvent.type(await screen.findByLabelText(/^quantity/i), '130');
    await userEvent.type(await screen.findByLabelText(/why extra/i), 'Spill');
    await userEvent.click(screen.getByRole('button', { name: /^issue material$/i }));
    expect(await screen.findByText(/A manager can approve it/i)).toBeTruthy();
    await userEvent.type(screen.getByLabelText(/note for the manager/i), 'need it today');
    await userEvent.click(screen.getByRole('button', { name: /ask a manager to approve/i }));
    await waitFor(() => expect(requestIssueApproval).toHaveBeenCalledWith(70, 'need it today'));
  });

  it('a manager sees a waiting request and can approve or turn it down', async () => {
    state.issues = [{ id: 70, number: '', status: 'DRAFT', approval: 'REQUESTED', workOrder: 11, docDate: '2026-10-21', notes: '', lines: [{ id: 1, componentName: 'Bolt', qty: '130' }] }];
    renderRoutes([{ path: '/w/:id', element: <WorkOrderDetailPage /> }], '/w/11');
    await userEvent.click(await screen.findByRole('tab', { name: /material/i }));
    expect(await screen.findByText(/waiting for a manager/i)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /approve and post/i }));
    await waitFor(() => expect(approveIssue).toHaveBeenCalledWith(70));
    await userEvent.click(screen.getByRole('button', { name: /^turn down$/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByRole('textbox'), 'use the leftover first');
    await userEvent.click(within(dialog).getByRole('button', { name: /confirm/i }));
    await waitFor(() => expect(rejectIssue).toHaveBeenCalledWith(70, 'use the leftover first'));
  });
});
