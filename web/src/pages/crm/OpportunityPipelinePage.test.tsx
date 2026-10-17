import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { OpportunityPipelinePage } from '@/pages/crm/OpportunityPipelinePage';
import type { OpportunityLine, OpportunityRow } from '@/api/growth';

vi.mock('@/pages/erp/erpShared', () => ({
  ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, subscription: null, isLoading: false }),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'u@x.test', fullName: 'U', role: 'OWNER', companyId: 9 } }),
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 8, name: 'Chosen Buyer' })}>pick-customer</button>
  ),
  ProductField: ({ onChange }: { onChange: (p: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 9, name: 'Widget' })}>pick-product</button>
  ),
}));

const {
  getForecast, getPipelineBoard, listOpportunitiesByStage, listOpportunityLines, patchOpportunity, reopenOpportunity, board,
} = vi.hoisted(() => {
  const STAGE_KEYS = ['OPEN', 'QUALIFIED', 'NEGOTIATION', 'WON', 'LOST'];
  const board = (rows: Array<{ stage: string }>, extra: Record<string, Partial<{ count: number; older: number }>> = {}) => ({
    closedDays: 90,
    limit: 25,
    stages: Object.fromEntries(STAGE_KEYS.map((stage) => {
      const results = rows.filter((row) => row.stage === stage);
      return [stage, { count: results.length, totalAmount: '0', older: 0, results, ...(extra[stage] ?? {}) }];
    })),
  });
  const open: OpportunityRow = {
    id: 1, title: 'Deal A', stage: 'OPEN', amount: '500.00', probability: 40,
    expectedCloseDate: null, customer: 3,
  };
  const won: OpportunityRow = {
    id: 2, title: 'Deal B', stage: 'WON', amount: '300.00', probability: 100,
    expectedCloseDate: '2026-10-01', customer: 4,
  };
  const line: OpportunityLine = { id: 11, product: 9, description: '', quantity: '2', unitPrice: '15.00' };
  return {
    getForecast: vi.fn(async () => ({ months: [{ month: '2026-10', amount: '200.00' }], unscheduled: '500.00' })),
    board,
    getPipelineBoard: vi.fn(async () => board([open, won])),
    listOpportunitiesByStage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
    listOpportunityLines: vi.fn(async () => ({ results: [line], count: 1, next: null, previous: null })),
    patchOpportunity: vi.fn(async (id: number, payload: Record<string, unknown>) => ({ id, ...payload })),
    reopenOpportunity: vi.fn(async (id: number) => ({ id, stage: 'OPEN' })),
  };
});

vi.mock('@/api/growth', () => ({
  getPipelineBoard: (...args: unknown[]) => getPipelineBoard(...args),
  listOpportunitiesByStage: (...args: unknown[]) => listOpportunitiesByStage(...args),
  getForecast: () => getForecast(),
  getWonVersusInvoices: async () => ({ month: '2026-09', wonAmount: '300.00', invoicedAmount: '118.00' }),
  patchOpportunity: (...args: unknown[]) => patchOpportunity(...args),
  listOpportunityLines: (...args: unknown[]) => listOpportunityLines(...args),
  reopenOpportunity: (...args: unknown[]) => reopenOpportunity(...args),
  LOST_REASONS: ['PRICE', 'COMPETITOR', 'NO_RESPONSE', 'NOT_A_FIT', 'DUPLICATE', 'OTHER'],
  createOpportunityLine: vi.fn(),
  deleteOpportunityLine: vi.fn(),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/crm/pipeline']}>
        <Routes>
          <Route path="/crm/pipeline" element={<OpportunityPipelinePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('OpportunityPipelinePage', () => {
  it('renders the board by stage and the forecast bars', async () => {
    wrap();
    expect(await screen.findByText('Deal A')).toBeInTheDocument();
    expect(screen.getByText('Deal B')).toBeInTheDocument();
    expect(screen.getByText('2026-10')).toBeInTheDocument();
    expect(screen.getAllByText('₹500.00').length).toBeGreaterThan(0);
    expect(await screen.findByText(/Won this month: ₹300.00/)).toBeInTheDocument();
    expect(screen.getByText(/Invoices for those customers: ₹118.00/)).toBeInTheDocument();
  });

  it('moves an OPEN deal to WON via the explicit action button, not a LOST or already-closed one', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText('Deal A');
    const wonButtons = screen.getAllByRole('button', { name: 'Move to Won' });
    expect(wonButtons).toHaveLength(1); // only the OPEN card gets move buttons
    await user.click(wonButtons[0]);
    // A routine stage change is confirmed with a click, not by retyping the deal title.
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(patchOpportunity).toHaveBeenCalledWith(1, { stage: 'WON' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Move to Qualified' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move to Lost' })).toBeInTheDocument();
  });

  it('moves a qualified deal to negotiation and leaves a lost deal closed', async () => {
    getPipelineBoard.mockResolvedValueOnce(board([
        {
          id: 3, title: 'Deal C', stage: 'QUALIFIED', amount: '10.00', probability: 20,
          expectedCloseDate: null, customer: 1,
        },
        {
          id: 4, title: 'Deal D', stage: 'LOST', amount: '10.00', probability: 0,
          expectedCloseDate: null, customer: 1,
        },
    ]));
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText('Deal C')).toBeInTheDocument();
    expect(screen.getByText('Deal D')).toBeInTheDocument();
    const moves = screen.getAllByRole('button', { name: /Move to / });
    expect(moves.map((button) => button.textContent)).toEqual([
      'Move to Negotiation', 'Move to Won', 'Move to Lost',
    ]);
    await user.click(screen.getByRole('button', { name: 'Move to Negotiation' }));
    await waitFor(() => expect(patchOpportunity).toHaveBeenCalledWith(3, { stage: 'NEGOTIATION' }));
  });

  it('shows column counts, loads more of a long column, and offers older closed deals', async () => {
    const mk = (id: number, stage: string) => ({
      id, title: `Deal ${id}`, stage, amount: '10.00', probability: 10, expectedCloseDate: null, customer: 1,
    });
    getPipelineBoard.mockResolvedValueOnce(board([mk(21, 'OPEN'), mk(22, 'OPEN')], {
      OPEN: { count: 3 },
      LOST: { older: 4 },
    }));
    listOpportunitiesByStage.mockResolvedValueOnce({ results: [mk(23, 'OPEN')], count: 3, next: null, previous: null });
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText('Deal 21')).toBeInTheDocument();
    expect(screen.getByText(/^Open · 3/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load more' }));
    expect(await screen.findByText('Deal 23')).toBeInTheDocument();
    expect(listOpportunitiesByStage).toHaveBeenCalledWith({ stage: 'OPEN', page: 2, closedDays: 90 });
    await user.click(screen.getByRole('button', { name: 'Show 4 older' }));
    await waitFor(() => expect(getPipelineBoard).toHaveBeenLastCalledWith(0));
  });

  it('opens a deal from the keyboard', async () => {
    const user = userEvent.setup();
    wrap();
    const card = await screen.findByRole('button', { name: 'Deal A' });
    card.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByLabelText('Probability %')).toBeInTheDocument();
  });

  it('asks why a deal was lost before moving it to Lost', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText('Deal A');
    await user.click(screen.getByRole('button', { name: 'Move to Lost' }));
    const confirmLost = await screen.findByRole('button', { name: 'Mark lost' });
    expect(confirmLost).toBeDisabled();
    await user.click(screen.getByLabelText(/Why was it lost/));
    await user.click(await screen.findByRole('option', { name: 'Price' }));
    expect(confirmLost).toBeEnabled();
    await user.click(confirmLost);
    await waitFor(() => expect(patchOpportunity).toHaveBeenCalledWith(1, {
      stage: 'LOST', lost_reason: 'PRICE', lost_reason_note: '',
    }));
  });

  it('lets an owner reopen a closed deal after confirming, and locks its lines', async () => {
    const user = userEvent.setup();
    wrap();
    await user.click(await screen.findByText('Deal B'));
    expect(await screen.findByText(/This deal is closed/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add line' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Reopen deal' }));
    await user.click(await screen.findByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(reopenOpportunity).toHaveBeenCalledWith(2));
  });

  it('opens a detail view with line items and validates probability on save', async () => {
    const user = userEvent.setup();
    wrap();
    await user.click(await screen.findByText('Deal A'));
    expect(await screen.findByText(/#9 · 2 × 15.00/)).toBeInTheDocument();

    const probabilityInput = screen.getByLabelText('Probability %');
    await user.clear(probabilityInput);
    await user.type(probabilityInput, '150');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Probability must be a whole number from 0 to 100.')).toBeInTheDocument();
    expect(patchOpportunity).not.toHaveBeenCalledWith(1, expect.objectContaining({ probability: 150 }));

    await user.clear(probabilityInput);
    await user.type(probabilityInput, '60');
    await user.type(screen.getByLabelText('Competitor'), 'Rival Co');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchOpportunity).toHaveBeenCalledWith(1, {
      probability: 60,
      expected_close_date: null,
      competitor: 'Rival Co',
    }));
  });
});
