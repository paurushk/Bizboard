import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OpportunitiesPage } from '@/pages/crm/OpportunitiesPage';

vi.mock('@/pages/erp/erpShared', () => ({
  ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  MvpModuleBanner: () => null,
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, subscription: null, isLoading: false }),
}));

const { role } = vi.hoisted(() => ({ role: { current: 'OWNER' } }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'u@x.test', fullName: 'U', role: role.current, companyId: 9 } }),
}));

const { updateOpportunity, reopenOpportunity, listOpportunitiesPage } = vi.hoisted(() => ({
  updateOpportunity: vi.fn(async (id: number, payload: Record<string, unknown>) => ({ id, ...payload })),
  reopenOpportunity: vi.fn(async (id: number) => ({ id, stage: 'OPEN' })),
  listOpportunitiesPage: vi.fn(),
}));

vi.mock('@/api/crm', () => ({
  listOpportunitiesPage: (...args: unknown[]) => listOpportunitiesPage(...args),
  listLeadsPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
  createOpportunity: vi.fn(),
  updateOpportunity: (...args: unknown[]) => updateOpportunity(...args),
  draftOpportunityInvoice: vi.fn(),
  createQuotationFromOpportunity: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  listCustomersPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
}));

vi.mock('@/api/growth', () => ({
  reopenOpportunity: (...args: unknown[]) => reopenOpportunity(...args),
  LOST_REASONS: ['PRICE', 'COMPETITOR', 'NO_RESPONSE', 'NOT_A_FIT', 'DUPLICATE', 'OTHER'],
}));

function page(rows: Array<Record<string, unknown>>) {
  listOpportunitiesPage.mockResolvedValue({ results: rows, count: rows.length, next: null, previous: null });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const openDeal = {
  id: 4, title: 'Deal with lines', amount: '100.00', stage: 'OPEN', lead: null, customer: 2, competitor: '',
};
const wonDeal = { ...openDeal, id: 5, title: 'Closed deal', stage: 'WON' };

describe('OpportunitiesPage edit (CRM review F-03)', () => {
  beforeEach(() => {
    updateOpportunity.mockClear();
    reopenOpportunity.mockClear();
    role.current = 'OWNER';
  });

  it('sends only the changed fields, so an unchanged derived amount is never re-sent', async () => {
    page([openDeal]);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const title = screen.getByLabelText(/Title/);
    await user.clear(title);
    await user.type(title, 'Renamed');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateOpportunity).toHaveBeenCalledWith(4, { title: 'Renamed' }));
  });

  it('locks a closed deal and lets an owner reopen it after confirming', async () => {
    page([wonDeal]);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    expect(screen.getByText(/This deal is closed/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Title/)).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Reopen deal' }));
    await user.click(await screen.findByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(reopenOpportunity).toHaveBeenCalledWith(5));
  });

  it('does not offer reopen to a sales user', async () => {
    role.current = 'SALES_STAFF';
    page([wonDeal]);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    expect(screen.queryByRole('button', { name: 'Reopen deal' })).toBeNull();
  });
});
