import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentProposal } from '@/api/agents';
import * as api from '@/api/agents';
import { AgentDraftDrawer } from './AgentDraftDrawer';
import { DraftsTray } from './DraftsTray';
import { PasteOrderPanel } from './PasteOrderPanel';

vi.mock('@/api/agents', async (orig) => ({
  ...(await orig<typeof import('@/api/agents')>()),
  getAgentCatalog: vi.fn(), startAgentTextRun: vi.fn(), getProposal: vi.fn(), approveProposal: vi.fn(), editProposal: vi.fn(),
  retryProposal: vi.fn(), listProposals: vi.fn(), bulkApproveProposals: vi.fn(), rejectProposal: vi.fn(), cancelProposal: vi.fn(),
}));
vi.mock('@/config/featureFlags', () => ({ isRuntimeFlagEnabled: () => true, useFeatureFlagEpoch: () => 0 }));
vi.mock('@/hooks/usePartySearch', () => ({ useCustomerSearch: () => ({ query: '', setQuery: vi.fn(), options: [], isFetching: false }) }));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({ productQuery: '', setProductQuery: vi.fn(), options: [], isFetching: false, helperText: undefined }),
}));

const READY = {
  customerId: 3, customerName: 'Sharma Traders', customerHint: 'Sharma', customerAlternatives: [], warnings: [],
  lines: [{ raw: '2 sugar', rawNorm: 'sugar', qty: '2', unit: '', productId: 9, productName: 'Sugar 50kg bag', alternatives: [], warnings: [] }],
};
const INCOMPLETE = { ...READY, customerId: null, customerName: '' };

function draft(over: Partial<AgentProposal> = {}): AgentProposal {
  return {
    id: 11, agent: 'ORDER_INTAKE', kind: 'SALES_ORDER_DRAFT', status: 'PENDING', title: 'Order: Sharma (1 line)', payload: READY, schemaVersion: 1,
    revision: 0, evidence: [{ type: 'fact', id: 's', label: 'Pasted order text' }], dedupeKey: 'ORDER:x', groupKey: '', expiresAt: '', attempts: 0,
    failureCode: '', decisionNote: '', resultRef: null, renderer: 'order', canApprove: true, bulkApprovable: false, createdAt: '', ...over,
  };
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const apiError = (status: number, code: string) =>
  Object.assign(new Error('x'), { isAxiosError: true, response: { status, data: { success: false, error: { code, message: 'x' } } } });

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getAgentCatalog).mockResolvedValue({
    agents: [{ kind: 'ORDER_INTAKE', titleKey: 'agents.orderIntake.title', triggerCodes: [], canPrepare: true, proposalKinds: [] }],
  });
  vi.mocked(api.listProposals).mockResolvedValue([]);
});

describe('order drafts in the review drawer', () => {
  it('cannot be approved while the order is incomplete, by button or by the A key', async () => {
    wrap(<AgentDraftDrawer proposal={draft({ payload: INCOMPLETE })} open onClose={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Create draft order' })).toBeDisabled();
    await userEvent.keyboard('a');
    expect(api.approveProposal).not.toHaveBeenCalled();
  });

  it('a complete order is approved with the revision shown, once', async () => {
    vi.mocked(api.approveProposal).mockResolvedValue(draft({ status: 'EXECUTED' }));
    wrap(<AgentDraftDrawer proposal={draft({ revision: 4 })} open onClose={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: 'Create draft order' }));
    expect(api.approveProposal).toHaveBeenCalledTimes(1);
    expect(api.approveProposal).toHaveBeenCalledWith(11, 4);
  });

  it('a failed order draft offers Try again, not Create', () => {
    wrap(<AgentDraftDrawer proposal={draft({ status: 'FAILED', failureCode: 'AGT_E_VALIDATION', decisionNote: 'Pick the customer.' })} open onClose={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Create draft order' })).toBeNull();
  });

  it('links to the help answer about reviewing drafts', () => {
    wrap(<AgentDraftDrawer proposal={draft()} open onClose={() => undefined} />);
    expect(screen.getByRole('link', { name: 'How drafts work' })).toHaveAttribute('href', '/help#agents-review-approve');
  });

  it('has no accessibility violations', async () => {
    wrap(<AgentDraftDrawer proposal={draft()} open onClose={() => undefined} />);
    const results = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});

describe('paste order panel', () => {
  const OK_RUN = { id: 1, agent: 'ORDER_INTAKE', status: 'SUCCEEDED' as const, errorCode: '', rulesOnly: true, proposalIds: [11] };

  async function open() {
    wrap(<PasteOrderPanel />);
    await userEvent.click(await screen.findByRole('button', { name: 'Paste' }));
  }

  it('keeps Read order disabled for blank text', async () => {
    await open();
    expect(screen.getByRole('button', { name: 'Read order' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Customer message'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Read order' })).toBeDisabled();
  });

  it('cuts the text at 6,000 characters', async () => {
    await open();
    const box = screen.getByLabelText('Customer message') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'a'.repeat(6500) } });
    expect(box.value).toHaveLength(6000);
  });

  it('after an edit is saved, approving sends the new revision', async () => {
    vi.mocked(api.startAgentTextRun).mockResolvedValue(OK_RUN);
    vi.mocked(api.getProposal)
      .mockResolvedValueOnce(draft())
      .mockResolvedValueOnce(draft({ revision: 1 }))
      .mockResolvedValue(draft({ revision: 1, status: 'EXECUTED', resultRef: { id: 55, number: 'SO-1' } }));
    vi.mocked(api.editProposal).mockResolvedValue(draft({ revision: 1 }));
    vi.mocked(api.approveProposal).mockResolvedValue(draft({ revision: 1, status: 'EXECUTED' }));
    await open();
    fireEvent.change(screen.getByLabelText('Customer message'), { target: { value: '2 sugar' } });
    await userEvent.click(screen.getByRole('button', { name: 'Read order' }));
    fireEvent.change(await screen.findByLabelText('Qty 1'), { target: { value: '5' } });
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(api.editProposal).toHaveBeenCalledWith(11, expect.objectContaining({ lines: [expect.objectContaining({ qty: '5' })] }), 0);
    await userEvent.click(await screen.findByRole('button', { name: 'Create draft order' }));
    expect(api.approveProposal).toHaveBeenCalledWith(11, 1);
  });

  it('shows the translated stale message when the books changed', async () => {
    vi.mocked(api.startAgentTextRun).mockResolvedValue(OK_RUN);
    vi.mocked(api.getProposal).mockResolvedValue(draft());
    vi.mocked(api.approveProposal).mockRejectedValue(apiError(409, 'AGT_E_STALE'));
    await open();
    fireEvent.change(screen.getByLabelText('Customer message'), { target: { value: '2 sugar' } });
    await userEvent.click(screen.getByRole('button', { name: 'Read order' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Create draft order' }));
    expect(await screen.findByText('The books changed since this draft was made. Prepare it again.')).toBeInTheDocument();
  });

  it('shows the daily-limit message when the read is refused', async () => {
    vi.mocked(api.startAgentTextRun).mockRejectedValue(apiError(429, 'AGT_E_DAILY_CAP'));
    await open();
    fireEvent.change(screen.getByLabelText('Customer message'), { target: { value: '2 sugar' } });
    await userEvent.click(screen.getByRole('button', { name: 'Read order' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Today’s limit for this agent is used up.');
  });

  it('has no accessibility violations when open', async () => {
    await open();
    const results = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});

describe('drafts tray', () => {
  const row = (id: number, over: Partial<AgentProposal> = {}) => draft({ id, title: `Draft ${id}`, ...over });

  async function openTray(rows: AgentProposal[]) {
    vi.mocked(api.listProposals).mockResolvedValue(rows);
    wrap(<DraftsTray />);
    await userEvent.click(await screen.findByRole('button', { name: new RegExp(`${rows.length} drafts waiting`) }));
  }

  it('offers a checkbox only on bulk-approvable drafts', async () => {
    await openTray([row(1, { kind: 'REMINDER', renderer: 'message', bulkApprovable: true }), row(2)]);
    expect(await screen.findByRole('checkbox', { name: 'Draft 1' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Draft 2' })).toBeNull();
  });

  it('approves the selected drafts in one call with their revisions', async () => {
    vi.mocked(api.bulkApproveProposals).mockResolvedValue([{ id: 1, ok: true, status: 'EXECUTED' }]);
    await openTray([row(1, { kind: 'REMINDER', renderer: 'message', bulkApprovable: true, revision: 2 }), row(2)]);
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Draft 1' }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve selected' }));
    await waitFor(() => expect(api.bulkApproveProposals).toHaveBeenCalledWith([{ id: 1, revision: 2 }]));
    expect(await screen.findByText('1 approved, 0 could not be approved.')).toBeInTheDocument();
  });

  it('shows no bulk buttons when nothing can be bulk approved', async () => {
    await openTray([row(2), row(3)]);
    await screen.findByText('Draft 2');
    expect(screen.queryByRole('button', { name: 'Approve selected' })).toBeNull();
  });

  it('says so when nothing is waiting', async () => {
    vi.mocked(api.listProposals).mockResolvedValue([]);
    wrap(<DraftsTray />);
    await userEvent.click(await screen.findByRole('button', { name: 'Open drafts' }));
    expect(await screen.findByText('No drafts waiting for you.')).toBeInTheDocument();
  });
});

describe('paste order panel: why a read ended without a draft', () => {
  it('shows the daily-limit reason when the run itself was refused for it', async () => {
    vi.mocked(api.startAgentTextRun).mockResolvedValue({ id: 1, agent: 'ORDER_INTAKE', status: 'FAILED', errorCode: 'AGT_E_TIMEOUT', rulesOnly: true, proposalIds: [] });
    wrap(<PasteOrderPanel />);
    await userEvent.click(await screen.findByRole('button', { name: 'Paste' }));
    fireEvent.change(screen.getByLabelText('Customer message'), { target: { value: '2 sugar' } });
    await userEvent.click(screen.getByRole('button', { name: 'Read order' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This took too long. Try again.');
  });

  it('keeps the draft closed and says so when reloading it after an approval fails', async () => {
    vi.mocked(api.startAgentTextRun).mockResolvedValue({ id: 1, agent: 'ORDER_INTAKE', status: 'SUCCEEDED', errorCode: '', rulesOnly: true, proposalIds: [11] });
    vi.mocked(api.getProposal).mockResolvedValueOnce(draft()).mockRejectedValue(apiError(500, 'AGT_E_PROVIDER'));
    vi.mocked(api.approveProposal).mockResolvedValue(draft({ status: 'EXECUTED' }));
    wrap(<PasteOrderPanel />);
    await userEvent.click(await screen.findByRole('button', { name: 'Paste' }));
    fireEvent.change(screen.getByLabelText('Customer message'), { target: { value: '2 sugar' } });
    await userEvent.click(screen.getByRole('button', { name: 'Read order' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Create draft order' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create draft order' })).toBeNull();
  });
});
