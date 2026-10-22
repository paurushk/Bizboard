import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentProposal } from '@/api/agents';
import * as api from '@/api/agents';
import { AgentPrepareButton } from './AgentPrepareButton';

vi.mock('@/api/agents', async (orig) => ({
  ...(await orig<typeof import('@/api/agents')>()),
  getAgentCatalog: vi.fn(),
  startAgentRun: vi.fn(),
  getAgentRun: vi.fn(),
  listProposals: vi.fn(),
}));
vi.mock('@/config/featureFlags', () => ({ isRuntimeFlagEnabled: () => true, useFeatureFlagEpoch: () => 0 }));

const AGENT = (over = {}) => ({ kind: 'BILL_CHECK', titleKey: 'agents.billCheck.title', triggerCodes: [], canPrepare: true, proposalKinds: [], ...over });

function proposal(id: number, over: Partial<AgentProposal> = {}): AgentProposal {
  return {
    id, agent: 'INVENTORY_RISK', kind: 'STOCK_TRANSFER', status: 'PENDING', title: `Draft ${id}`, payload: { text: 'hello' }, schemaVersion: 1,
    revision: 0, evidence: [], dedupeKey: `k${id}`, groupKey: 'ROW:1', expiresAt: '', attempts: 0, failureCode: '', decisionNote: '',
    resultRef: null, renderer: 'message', canApprove: true, bulkApprovable: false, createdAt: '', ...over,
  };
}

function renderButton(props: React.ComponentProps<typeof AgentPrepareButton>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><AgentPrepareButton {...props} /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listProposals).mockResolvedValue([]);
});

describe('AgentPrepareButton', () => {
  it('named by agentKind it uses that agent and the given label', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [AGENT()] });
    vi.mocked(api.startAgentRun).mockResolvedValue({ id: 1, agent: 'BILL_CHECK', status: 'SUCCEEDED', errorCode: '', rulesOnly: true });
    renderButton({ agentKind: 'BILL_CHECK', dedupeKey: 'BILL_CHECK:5', label: 'Check against order' });
    await userEvent.click(await screen.findByRole('button', { name: 'Check against order' }));
    expect(api.startAgentRun).toHaveBeenCalledWith('BILL_CHECK', 'BILL_CHECK:5');
  });

  it('says nothing to send when the run ends without a draft', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [AGENT()] });
    vi.mocked(api.startAgentRun).mockResolvedValue({ id: 1, agent: 'BILL_CHECK', status: 'SUCCEEDED', errorCode: '', rulesOnly: true });
    renderButton({ agentKind: 'BILL_CHECK', dedupeKey: 'BILL_CHECK:5' });
    await userEvent.click(await screen.findByRole('button', { name: 'Prepare draft' }));
    expect(await screen.findByText('Nothing to send: no differences found.')).toBeInTheDocument();
  });

  it('shows a translated error when the start fails', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [AGENT()] });
    vi.mocked(api.startAgentRun).mockRejectedValue(Object.assign(new Error('x'), { isAxiosError: true, response: { status: 429, data: { success: false, error: { code: 'AGT_E_DAILY_CAP', message: 'x' } } } }));
    renderButton({ agentKind: 'BILL_CHECK', dedupeKey: 'BILL_CHECK:5' });
    await userEvent.click(await screen.findByRole('button', { name: 'Prepare draft' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Today’s limit for this agent is used up.'));
  });

  it('renders nothing for a user who cannot prepare, or when the agent is not in the catalogue', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [AGENT({ canPrepare: false })] });
    const { container } = renderButton({ agentKind: 'BILL_CHECK', dedupeKey: 'BILL_CHECK:5' });
    await waitFor(() => expect(api.getAgentCatalog).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('matches a row by its attention code', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [AGENT({ kind: 'INVENTORY_RISK', triggerCodes: ['LOW_STOCK_FAST_MOVER'] })] });
    renderButton({ code: 'LOW_STOCK_FAST_MOVER', dedupeKey: 'LOW_STOCK_FAST_MOVER:product:1' });
    expect(await screen.findByRole('button', { name: 'Prepare draft' })).toBeInTheDocument();
  });

  it('opens linked drafts of one row and steps between them', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [AGENT({ kind: 'INVENTORY_RISK', triggerCodes: ['LOW_STOCK_FAST_MOVER'] })] });
    vi.mocked(api.listProposals).mockResolvedValue([proposal(1), proposal(2)]);
    renderButton({ code: 'LOW_STOCK_FAST_MOVER', dedupeKey: 'ROW:1' });
    await userEvent.click(await screen.findByRole('button', { name: 'Review draft' }));
    expect(await screen.findByText('Draft 1')).toBeInTheDocument();
    await userEvent.keyboard('j');
    expect(await screen.findByText('Draft 2')).toBeInTheDocument();
    await userEvent.keyboard('k');
    expect(await screen.findByText('Draft 1')).toBeInTheDocument();
  });

  it('ignores drafts that are already finished', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [AGENT({ kind: 'INVENTORY_RISK', triggerCodes: ['LOW_STOCK_FAST_MOVER'] })] });
    vi.mocked(api.listProposals).mockResolvedValue([proposal(1, { status: 'EXECUTED' })]);
    renderButton({ code: 'LOW_STOCK_FAST_MOVER', dedupeKey: 'ROW:1' });
    expect(await screen.findByRole('button', { name: 'Prepare draft' })).toBeInTheDocument();
  });
});
