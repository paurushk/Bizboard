import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentProposal } from '@/api/agents';
import * as api from '@/api/agents';
import { PasteOrderPanel } from './PasteOrderPanel';
import { isPayloadReady } from './renderers/ready';

vi.mock('@/api/agents', async (orig) => {
  const actual = await orig<typeof import('@/api/agents')>();
  return {
    ...actual,
    getAgentCatalog: vi.fn(),
    startAgentTextRun: vi.fn(),
    getProposal: vi.fn(),
    approveProposal: vi.fn(),
    editProposal: vi.fn(),
  };
});
vi.mock('@/config/featureFlags', () => ({ isRuntimeFlagEnabled: () => true, useFeatureFlagEpoch: () => 0 }));
vi.mock('@/hooks/usePartySearch', () => ({
  useCustomerSearch: () => ({ query: '', setQuery: vi.fn(), options: [], isFetching: false }),
}));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({ productQuery: '', setProductQuery: vi.fn(), options: [], isFetching: false, helperText: undefined }),
}));

const READY = {
  customerId: 3, customerName: 'Sharma Traders', customerHint: 'Sharma Traders', customerAlternatives: [], warnings: [],
  lines: [{ raw: '2 sugar', rawNorm: 'sugar', qty: '2', unit: '', productId: 9, productName: 'Sugar 50kg bag', alternatives: [], warnings: [] }],
};

function draft(overrides: Partial<AgentProposal> = {}): AgentProposal {
  return {
    id: 11, agent: 'ORDER_INTAKE', kind: 'SALES_ORDER_DRAFT', status: 'PENDING', title: 'Order: Sharma Traders (1 line)',
    payload: READY, schemaVersion: 1, revision: 0, evidence: [{ type: 'fact', id: 'source', label: 'Pasted order text' }],
    dedupeKey: 'ORDER:x', groupKey: '', expiresAt: '2026-10-23T00:00:00Z', attempts: 0, failureCode: '', decisionNote: '',
    resultRef: null, renderer: 'order', canApprove: true, bulkApprovable: false, createdAt: '2026-10-21T00:00:00Z', ...overrides,
  };
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PasteOrderPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getAgentCatalog).mockResolvedValue({
    agents: [{ kind: 'ORDER_INTAKE', titleKey: 'agents.orderIntake.title', triggerCodes: [], canPrepare: true, proposalKinds: [] }],
  });
});

describe('isPayloadReady', () => {
  it('needs a customer and a product and quantity on every line', () => {
    expect(isPayloadReady('order', READY)).toBe(true);
    expect(isPayloadReady('order', { ...READY, customerId: null })).toBe(false);
    expect(isPayloadReady('order', { ...READY, lines: [{ ...READY.lines[0], productId: null }] })).toBe(false);
    expect(isPayloadReady('order', { ...READY, lines: [{ ...READY.lines[0], qty: '0' }] })).toBe(false);
    expect(isPayloadReady('message', {})).toBe(true);
  });
});

describe('PasteOrderPanel', () => {
  it('renders nothing when the user cannot use the agent', async () => {
    vi.mocked(api.getAgentCatalog).mockResolvedValue({ agents: [] });
    const { container } = renderPanel();
    await waitFor(() => expect(api.getAgentCatalog).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('reads the text, shows the draft and creates the order on approve', async () => {
    const user = userEvent.setup();
    vi.mocked(api.startAgentTextRun).mockResolvedValue({ id: 1, agent: 'ORDER_INTAKE', status: 'SUCCEEDED', errorCode: '', rulesOnly: true, proposalIds: [11] });
    vi.mocked(api.getProposal)
      .mockResolvedValueOnce(draft())
      .mockResolvedValueOnce(draft({ status: 'EXECUTED', resultRef: { id: 55, number: 'SO-0001' } }));
    vi.mocked(api.approveProposal).mockResolvedValue(draft({ status: 'EXECUTED' }));
    renderPanel();

    await user.click(await screen.findByRole('button', { name: 'Paste' }));
    await user.type(screen.getByLabelText('Customer message'), '2 sugar');
    await user.click(screen.getByRole('button', { name: 'Read order' }));

    expect(api.startAgentTextRun).toHaveBeenCalledWith('ORDER_INTAKE', '2 sugar');
    await user.click(await screen.findByRole('button', { name: 'Create draft order' }));
    expect(api.approveProposal).toHaveBeenCalledWith(11, 0);
    expect(await screen.findByText('Draft order SO-0001 created.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open it' })).toHaveAttribute('href', '/sales/orders/55');
  });

  it('keeps Create disabled while a line has no product', async () => {
    const user = userEvent.setup();
    const incomplete = { ...READY, lines: [{ ...READY.lines[0], productId: null, productName: '' }] };
    vi.mocked(api.startAgentTextRun).mockResolvedValue({ id: 1, agent: 'ORDER_INTAKE', status: 'SUCCEEDED', errorCode: '', rulesOnly: true, proposalIds: [11] });
    vi.mocked(api.getProposal).mockResolvedValue(draft({ payload: incomplete }));
    renderPanel();
    await user.click(await screen.findByRole('button', { name: 'Paste' }));
    await user.type(screen.getByLabelText('Customer message'), '2 sugar');
    await user.click(screen.getByRole('button', { name: 'Read order' }));
    expect(await screen.findByRole('button', { name: 'Create draft order' })).toBeDisabled();
    expect(api.approveProposal).not.toHaveBeenCalled();
  });

  it('tells the person when nothing could be read', async () => {
    const user = userEvent.setup();
    vi.mocked(api.startAgentTextRun).mockResolvedValue({ id: 1, agent: 'ORDER_INTAKE', status: 'FAILED', errorCode: 'AGT_E_VALIDATION', rulesOnly: true, proposalIds: [] });
    renderPanel();
    await user.click(await screen.findByRole('button', { name: 'Paste' }));
    await user.type(screen.getByLabelText('Customer message'), 'hello');
    await user.click(screen.getByRole('button', { name: 'Read order' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No order lines could be read');
  });
});
