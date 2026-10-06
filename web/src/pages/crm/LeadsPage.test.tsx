import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { listLeadsPage } from '@/api/crm';
import { LeadsPage } from '@/pages/crm/LeadsPage';

vi.mock('@/pages/erp/erpShared', () => ({
  ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  MvpModuleBanner: () => null,
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, subscription: null, isLoading: false }),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'u@x.test', fullName: 'U', role: 'OWNER', companyId: 9 } }),
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
  convertLead: vi.fn(),
  assignLead: vi.fn(),
  createLeadActivity: vi.fn(),
  issueLeadFormToken: vi.fn(),
  issueWhatsappWebhookToken: vi.fn(),
  whatsappWebhookUrl: () => '',
}));

vi.mock('@/api/resources', () => ({
  listCompanyUsers: vi.fn(async () => []),
  listCustomersPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
}));

vi.mock('@/api/growth', () => ({
  listCampaignsPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
}));

describe('LeadsPage CSV import result', () => {
  it('shows created, pending review, and the bad row', async () => {
    importLeadsCsv.mockResolvedValueOnce({
      created: 2,
      pendingReview: 1,
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
    expect(await screen.findByText('Imported 2. 1 need review.')).toBeInTheDocument();
    expect(screen.getByText('Row 3: Phone is required')).toBeInTheDocument();
    await waitFor(() => expect(importLeadsCsv).toHaveBeenCalled());
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
