import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { TicketsPage } from '@/pages/support/TicketsPage';
import type { TicketRow } from '@/api/growth';

vi.mock('@/config/features', () => ({
  isSupportTicketsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
  AttachmentEditor: () => null,
}));

const {
  createTicket, getTicket, listTicketAttachments, listTicketComments, listTicketsPage, ticketReport, transitionTicket,
} = vi.hoisted(() => {
  const overdue: TicketRow = {
    id: 1, number: 'TKT-000001', customer: 5, subject: 'Pump leaking', description: '',
    status: 'OPEN', priority: 'URGENT', assignedTo: 8, slaDueAt: '2020-01-01T00:00:00Z',
  };
  const fresh: TicketRow = {
    id: 2, number: 'TKT-000002', customer: 5, subject: 'Login issue', description: '',
    status: 'IN_PROGRESS', priority: 'LOW', assignedTo: null, slaDueAt: '2999-01-01T00:00:00Z',
  };
  return {
    createTicket: vi.fn(async () => overdue),
    getTicket: vi.fn(async (id: number) => (id === 2 ? fresh : overdue)),
    listTicketAttachments: vi.fn(async () => []),
    listTicketComments: vi.fn(async () => []),
    listTicketsPage: vi.fn(async () => ({ results: [overdue, fresh], count: 2, next: null, previous: null })),
    ticketReport: vi.fn(async () => ({ byStatus: [{ status: 'OPEN', count: 1 }], averageResolutionSeconds: null })),
    transitionTicket: vi.fn(async (id: number, status: string) => ({ ...overdue, id, status })),
  };
});

vi.mock('@/api/growth', () => ({
  addTicketComment: vi.fn(),
  createTicket: (...args: unknown[]) => createTicket(...args),
  deleteTicketAttachment: vi.fn(),
  getTicket: (...args: unknown[]) => getTicket(...args),
  listTicketAttachments: (...args: unknown[]) => listTicketAttachments(...args),
  listTicketComments: (...args: unknown[]) => listTicketComments(...args),
  listTicketsPage: (...args: unknown[]) => listTicketsPage(...args),
  ticketReport: () => ticketReport(),
  transitionTicket: (...args: unknown[]) => transitionTicket(...args),
  uploadTicketAttachment: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  listCompanyUsers: vi.fn(async () => [{ id: 8, fullName: 'Priya Staff', email: 'priya@x.test' }]),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'u@x.test', fullName: 'Staff', role: 'OWNER', companyId: 1 } }),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/support/tickets']}>
        <Routes>
          <Route path="/support/tickets" element={<TicketsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TicketsPage', () => {
  it('boards tickets by status, resolves the assignee name, and flags an SLA breach', async () => {
    wrap();
    expect(await screen.findByText(/TKT-000001 · Pump leaking/)).toBeInTheDocument();
    expect(screen.getByText(/TKT-000002 · Login issue/)).toBeInTheDocument();
    expect(screen.getByText(/^Assignee: Priya Staff/)).toBeInTheDocument();
    expect(screen.getByText(/^Assignee: Unassigned/)).toBeInTheDocument();
    expect(screen.getByText(/^Breached by .+ · Elapsed .+/)).toBeInTheDocument();
  });

  it('creates a ticket with the picked customer, subject, and priority', async () => {
    const user = userEvent.setup();
    wrap();
    await user.click(await screen.findByRole('button', { name: 'New ticket' }));
    await user.click(await screen.findByRole('button', { name: 'pick-customer' }));
    await user.type(screen.getByLabelText('Subject'), 'New issue');
    await user.click(screen.getByRole('button', { name: 'Open ticket' }));

    await waitFor(() => expect(createTicket).toHaveBeenCalledWith({
      customer: 5, subject: 'New issue', priority: 'MEDIUM', category: 'GENERAL', assigned_to: null,
    }));
  });

  it('only offers legal transitions and calls transitionTicket on click', async () => {
    const user = userEvent.setup();
    wrap();
    await user.click(await screen.findByText(/TKT-000001/));
    expect(await screen.findByRole('button', { name: 'Move to In progress' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move to Waiting on customer' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Move to In progress' }));
    await waitFor(() => expect(transitionTicket).toHaveBeenCalledWith(1, 'IN_PROGRESS'));
  });
});
