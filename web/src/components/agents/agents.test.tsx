import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentProposal } from '@/api/agents';
import * as api from '@/api/agents';
import { agentForCode } from './useAgents';
import { AgentDraftDrawer } from './AgentDraftDrawer';
import { ProposalBody } from './renderers';

vi.mock('@/api/agents', async (orig) => {
  const actual = await orig<typeof import('@/api/agents')>();
  return {
    ...actual,
    editProposal: vi.fn(),
    approveProposal: vi.fn(),
    retryProposal: vi.fn(),
    rejectProposal: vi.fn(),
    cancelProposal: vi.fn(),
  };
});

function proposal(overrides: Partial<AgentProposal> = {}): AgentProposal {
  return {
    id: 7,
    agent: 'EXAMPLE',
    kind: 'EXAMPLE_NOTE',
    status: 'PENDING',
    title: 'Example note',
    payload: { text: 'Hello 3 items' },
    schemaVersion: 1,
    revision: 0,
    evidence: [{ type: 'invoice', id: 1, label: 'Invoice INV-1', href: '/sales/invoices/1' }],
    dedupeKey: 'k',
    groupKey: '',
    expiresAt: '2026-10-22T00:00:00Z',
    attempts: 0,
    failureCode: '',
    decisionNote: '',
    resultRef: null,
    renderer: 'message',
    canApprove: true,
    bulkApprovable: true,
    createdAt: '2026-10-21T00:00:00Z',
    ...overrides,
  };
}

function renderDrawer(p: AgentProposal | null, props: Partial<React.ComponentProps<typeof AgentDraftDrawer>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AgentDraftDrawer proposal={p} open onClose={() => undefined} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('agentForCode', () => {
  const agents = [
    { kind: 'COLLECTIONS', titleKey: 'x', triggerCodes: ['AR_OVERDUE_*', 'PROMISE_BROKEN'], canPrepare: true, proposalKinds: [] },
    { kind: 'NOPE', titleKey: 'x', triggerCodes: ['AR_OVERDUE_CRITICAL'], canPrepare: false, proposalKinds: [] },
  ];
  it('matches exact codes and prefixes, and ignores agents the user cannot prepare', () => {
    expect(agentForCode(agents, 'AR_OVERDUE_CRITICAL')?.kind).toBe('COLLECTIONS');
    expect(agentForCode(agents, 'PROMISE_BROKEN')?.kind).toBe('COLLECTIONS');
    expect(agentForCode(agents, 'PROMISE_OTHER')).toBeUndefined();
    expect(agentForCode(undefined, 'AR_OVERDUE_CRITICAL')).toBeUndefined();
  });
});

describe('AgentDraftDrawer', () => {
  it('shows the evidence and approves exactly the revision on screen', async () => {
    const user = userEvent.setup();
    vi.mocked(api.approveProposal).mockResolvedValue(proposal({ status: 'EXECUTED' }));
    renderDrawer(proposal({ revision: 4 }));
    expect(screen.getByRole('link', { name: 'Invoice INV-1' })).toHaveAttribute('href', '/sales/invoices/1');
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(api.approveProposal).toHaveBeenCalledWith(7, 4));
  });

  it('forces a save before approving an edited draft, and saves with the current revision', async () => {
    const user = userEvent.setup();
    vi.mocked(api.editProposal).mockResolvedValue(proposal({ revision: 1, payload: { text: 'Hello 3 items!' } }));
    renderDrawer(proposal({ revision: 0 }));
    await user.type(screen.getByLabelText('Message'), '!');
    expect(screen.getByText(/Save before approving/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.editProposal).toHaveBeenCalledWith(7, { text: 'Hello 3 items!' }, 0));
  });

  it('a failed draft shows Try again and retries at the same revision', async () => {
    const user = userEvent.setup();
    vi.mocked(api.retryProposal).mockResolvedValue(proposal({ status: 'EXECUTED' }));
    renderDrawer(proposal({ status: 'FAILED', failureCode: 'AGT_E_PROVIDER', decisionNote: 'try later', revision: 2 }));
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(api.retryProposal).toHaveBeenCalledWith(7, 2));
  });

  it('shows the translated message for an API error code', async () => {
    const user = userEvent.setup();
    const err = Object.assign(new Error('x'), {
      isAxiosError: true,
      response: { status: 409, data: { success: false, error: { code: 'AGT_E_REVISION', message: 'x' } } },
    });
    vi.mocked(api.approveProposal).mockRejectedValue(err);
    renderDrawer(proposal());
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This draft changed');
  });

  it('rejecting asks for an optional reason first', async () => {
    const user = userEvent.setup();
    vi.mocked(api.rejectProposal).mockResolvedValue(proposal({ status: 'REJECTED' }));
    renderDrawer(proposal());
    await user.click(screen.getByRole('button', { name: 'Reject' }));
    await user.type(screen.getByLabelText('Reason (optional)'), 'not now');
    await user.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(api.rejectProposal).toHaveBeenCalledWith(7, 'not now'));
  });

  it('a user who cannot approve sees the draft read-only with no action buttons', () => {
    renderDrawer(proposal({ canApprove: false }));
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Message')).toBeDisabled();
  });

  it('an unknown renderer is read-only with approve disabled', () => {
    renderDrawer(proposal({ renderer: 'unknown' }));
    expect(screen.getByText(/cannot be shown on this version/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
  });

  it('executed drafts have no actions', () => {
    renderDrawer(proposal({ status: 'EXECUTED' }));
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();
  });

  it('warns when the source text looked like an attack', () => {
    renderDrawer(proposal({ evidence: [{ type: 'injection_suspected', id: 'x', label: 'Source text contained instructions' }] }));
    expect(screen.getByText(/contained instructions aimed at software/)).toBeInTheDocument();
  });

  it('keyboard: J moves on, and letters typed into the message box never trigger actions', async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    renderDrawer(proposal(), { hasNext: true, onNext });
    await user.keyboard('j');
    expect(onNext).toHaveBeenCalledOnce();
    await user.click(screen.getByLabelText('Message'));
    await user.keyboard('ar');
    expect(api.approveProposal).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Reason (optional)')).not.toBeInTheDocument();
  });

  it('keyboard: A approves the draft on screen when nothing is being edited', async () => {
    const user = userEvent.setup();
    vi.mocked(api.approveProposal).mockResolvedValue(proposal({ status: 'EXECUTED' }));
    renderDrawer(proposal({ revision: 3 }));
    await user.keyboard('a');
    await waitFor(() => expect(api.approveProposal).toHaveBeenCalledWith(7, 3));
  });

  it('keyboard: R opens the reject box', async () => {
    const user = userEvent.setup();
    renderDrawer(proposal());
    await user.keyboard('r');
    expect(await screen.findByLabelText('Reason (optional)')).toBeInTheDocument();
  });
});

describe('generic renderers', () => {
  it('lines: edits a quantity and reports the new payload', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ProposalBody
        renderer="lines"
        value={{ lines: [{ item: 'Parle G', qty: '2', unit: 'peti', note: '' }] }}
        onChange={onChange}
        disabled={false}
      />,
    );
    expect(screen.getByText('Parle G')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Qty 1'), '0');
    expect(onChange).toHaveBeenLastCalledWith({ lines: [{ item: 'Parle G', qty: '20', unit: 'peti', note: '' }] });
  });

  it('comparison: marks mismatching rows', () => {
    render(
      <ProposalBody
        renderer="comparison"
        value={{ rows: [{ field: 'Rate', left: '18', right: '12', mismatch: true }, { field: 'Qty', left: '5', right: '5' }] }}
        onChange={() => undefined}
        disabled
      />,
    );
    expect(screen.getAllByText('Differs')).toHaveLength(1);
  });
});
