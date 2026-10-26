import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { convertLead, getDedupeCandidates, listLeadsPage, resolveDedupe } from '@/api/crm';
import { listTeamMembers } from '@/api/resources';
import { LeadsPage } from '@/pages/crm/LeadsPage';

const auth = vi.hoisted(() => ({ role: 'OWNER' }));

vi.mock('@/pages/erp/erpShared', () => ({
  ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  MvpModuleBanner: () => null,
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, subscription: null, isLoading: false }),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'u@x.test', fullName: 'U', role: auth.role, companyId: 9 } }),
}));

vi.mock('@/config/features', () => ({
  isReferralsEnabled: () => false,
}));

const { importLeadsCsv } = vi.hoisted(() => ({
  importLeadsCsv: vi.fn(),
}));

vi.mock('@/api/crm', () => ({
  importLeadsCsv: (...args: unknown[]) => importLeadsCsv(...args),
  listLeadsPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
  listLeadActivities: vi.fn(async () => []),
  createLead: vi.fn(),
  updateLead: vi.fn(),
  convertLead: vi.fn(async () => ({ lead: {}, opportunity: { id: 5 } })),
  draftOpportunityInvoice: vi.fn(async () => ({ id: 77 })),
  assignLead: vi.fn(),
  createLeadActivity: vi.fn(),
  issueLeadFormToken: vi.fn(),
  issueWhatsappWebhookToken: vi.fn(async () => ({ token: 'wa', verifyToken: 'vt', secretConfigured: false })),
  saveWhatsappAppSecret: vi.fn(),
  whatsappWebhookUrl: () => '',
  getDedupeCandidates: vi.fn(async () => ({
    customers: [{ id: 4, name: 'Known Buyer', phone: '+919000000001', email: '', gstin: '' }],
    leads: [{ id: 8, name: 'Earlier Lead', phone: '+919000000001', email: '', status: 'NEW', lastTouchedAt: null }],
  })),
  resolveDedupe: vi.fn(async () => ({})),
}));

vi.mock('@/api/resources', () => ({
  listTeamMembers: vi.fn(async () => []),
  TEAM_MEMBERS_QUERY_KEY: ['company-users', 'team'],
  listCustomersPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
}));

vi.mock('@/api/growth', () => ({
  listCampaignsPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
}));

describe('LeadsPage CSV import result', () => {
  it('shows created, pending review, and the bad row', async () => {
    importLeadsCsv.mockResolvedValueOnce({
      total: 3,
      created: 2,
      pendingReview: 1,
      errorCount: 1,
      errors: [{ row: 3, detail: 'Phone is required' }],
    });
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LeadsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['name,phone\n,\n'], 'leads.csv', { type: 'text/csv' });
    await user.upload(input, file);
    expect(await screen.findByText('Imported 2 of 3. 1 need review. 1 could not be imported.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download the rows that failed' })).toBeInTheDocument();
    expect(screen.getByText('Row 3: Phone is required')).toBeInTheDocument();
    await waitFor(() => expect(importLeadsCsv).toHaveBeenCalled());
  });
});

describe('LeadsPage duplicate review and filters', () => {
  const pendingLead = {
    id: 21, name: 'Maybe Known', phone: '+919000000001', email: '', status: 'NEW', customer: null,
    dedupeReview: 'PENDING_REVIEW', createdAt: '', updatedAt: '',
  };

  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LeadsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('resolves a pending lead from the review dialog and blocks convert meanwhile', async () => {
    vi.mocked(listLeadsPage).mockResolvedValue({ results: [pendingLead as never], count: 1, next: null, previous: null });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByRole('button', { name: 'Convert lead' })).toBeDisabled();
    await user.click(await screen.findByRole('button', { name: 'Review' }));
    expect(await screen.findByText('Known Buyer')).toBeInTheDocument();
    expect(screen.getByText('Earlier Lead')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Same customer' }));
    await waitFor(() => expect(resolveDedupe).toHaveBeenCalledWith(21, { decision: 'same_customer', customer_id: 4 }));
    expect(getDedupeCandidates).toHaveBeenCalledWith(21);
  });

  it('sends search and status filters to the server', async () => {
    vi.mocked(listLeadsPage).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    const user = userEvent.setup();
    renderPage();
    await user.type(await screen.findByLabelText('Search name, phone or email'), 'meera');
    await waitFor(() => expect(listLeadsPage).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'meera' })));
  });
});

describe('LeadsPage capture setup (UX-M08)', () => {
  it('keeps links and import in one Lead capture menu, not as four buttons beside the list', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LeadsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.queryByRole('button', { name: 'Web form link' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Lead capture' }));
    expect(await screen.findByRole('menuitem', { name: 'Web form link' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'WhatsApp webhook link' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Import CSV' })).toBeInTheDocument();
  });
});

describe('LeadsPage assignee target (GM-41)', () => {
  it('keeps the assignee control at least 44px tall', async () => {
    vi.mocked(listLeadsPage).mockResolvedValue({
      results: [{ id: 7, name: 'Asha', phone: '', email: '', status: 'NEW', assignedTo: null } as never],
      count: 1,
      next: null,
      previous: null,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LeadsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const box = await screen.findByRole('combobox', { name: 'Assign Asha' });
    const root = box.closest('.MuiInputBase-root');
    expect(root).toBeTruthy();
    expect(getComputedStyle(root as HTMLElement).minHeight).toBe('44px');
  });
});

describe('LeadsPage assignee list (BB-100 F10)', () => {
  it('lets a manager, not just the owner, pick a teammate by name', async () => {
    auth.role = 'MANAGER';
    vi.mocked(listTeamMembers).mockResolvedValue([{ id: 3, name: 'Ravi Kumar', role: 'SALES_STAFF' }]);
    vi.mocked(listLeadsPage).mockResolvedValue({
      results: [{ id: 7, name: 'Asha', phone: '', email: '', status: 'NEW', assignedTo: null } as never],
      count: 1,
      next: null,
      previous: null,
    });
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LeadsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(await screen.findByRole('combobox', { name: 'Assign Asha' }));
    expect(await screen.findByRole('option', { name: 'Ravi Kumar' })).toBeInTheDocument();
    auth.role = 'OWNER';
  });
});

describe('LeadsPage convert dialog (CRM review F-02)', () => {
  it('does not mark the deal won by default and needs an amount before it can', async () => {
    vi.mocked(listLeadsPage).mockResolvedValue({
      results: [{ id: 7, name: 'Asha', phone: '', email: '', status: 'NEW', assignedTo: null } as never],
      count: 1,
      next: null,
      previous: null,
    });
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LeadsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(await screen.findByRole('button', { name: 'Convert lead' }));
    const won = await screen.findByRole('checkbox', { name: 'Mark as won' });
    expect(won).not.toBeChecked();
    const dialog = screen.getByRole('dialog');
    const submit = () => within(dialog).getAllByRole('button', { name: 'Convert lead' }).at(-1) as HTMLElement;
    expect(submit()).toBeEnabled();

    await user.click(won);
    expect(screen.getByText('Enter an amount above zero before marking this deal won.')).toBeInTheDocument();
    expect(submit()).toBeDisabled();

    const amount = screen.getByLabelText('Opportunity amount');
    await user.clear(amount);
    await user.type(amount, '100');
    expect(submit()).toBeEnabled();
    await user.click(submit());
    await waitFor(() => expect(convertLead).toHaveBeenCalledWith(7, { amount: 100, won: true }));
  });
});
