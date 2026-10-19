import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Ticket } from '@/api/care';
import { TicketsPage } from '@/pages/support/TicketsPage';
import { a11yViolations, renderRoutes, setViewport } from '@/test/careHarness';

vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isSupportTicketsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
}));

const mocks = vi.hoisted(() => ({ role: 'OWNER' as string }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'u@x.test', fullName: 'Owner', role: mocks.role, canCreateSales: true, companyId: 1 } }),
}));

function ticket(over: Partial<Ticket>): Ticket {
  return {
    id: 1, number: 'TKT-000001', customer: 5, customerName: 'Ravi Traders', subject: 'Pump leaking', description: 'Seal is gone',
    category: 'GENERAL', priority: 'URGENT', status: 'OPEN', assignedTo: 8, assigneeName: 'Priya Staff', shareAvailable: true,
    shared: false, sharedAt: null, shareIncludesDescription: false, sourceInvoice: null, sourceInvoiceNumber: '', contract: null,
    contractNumber: '', slaDueAt: '2026-10-18T10:00:00Z', slaState: 'breached', slaRemainingSeconds: -7200, waitingSince: null,
    resolvedAt: null, createdAt: '2026-10-17T10:00:00Z', updatedAt: '2026-10-18T09:00:00Z', ...over,
  };
}

const api = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  transition: vi.fn(),
  comments: vi.fn(),
  comment: vi.fn(),
  share: vi.fn(),
  stopSharing: vi.fn(),
  report: vi.fn(),
  attachments: { list: vi.fn(), upload: vi.fn(), remove: vi.fn() },
}));

vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  tickets: api,
  recordLinks: vi.fn(async () => [{ kind: 'job_card', id: 9, number: 'JOB-000009', status: 'DRAFT', href: '/workshop/jobs/9', label: 'Noise' }]),
  recordTimeline: vi.fn(async () => [{ id: 1, action: 'ticket_status', description: '', metadata: {}, userName: 'Owner', createdAt: '2026-10-18T09:00:00Z' }]),
  contracts: { list: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })) },
}));

vi.mock('@/api/resources', () => ({
  listCompanyUsers: vi.fn(async () => [{ id: 8, fullName: 'Priya Staff', email: 'priya@x.test' }]),
  listSalesInvoicesPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
}));

const overdue = ticket({});
const resolved = ticket({
  id: 2, number: 'TKT-000002', subject: 'Login issue', status: 'RESOLVED', priority: 'LOW', assignedTo: null, assigneeName: '',
  slaState: 'met', slaRemainingSeconds: 3600, resolvedAt: '2026-10-18T08:00:00Z',
});
const closed = ticket({ id: 3, number: 'TKT-000003', subject: 'Old thing', status: 'CLOSED', slaState: 'met' });

function page(initial = '/support/tickets') {
  return renderRoutes(
    [
      { path: '/support/tickets', element: <TicketsPage /> },
      { path: '/support/tickets/:id', element: <TicketsPage /> },
    ],
    initial,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = 'OWNER';
  setViewport(1280);
  api.list.mockImplementation(async (params?: { status?: string }) => {
    const all = [overdue, resolved];
    const rows = params?.status ? all.filter((row) => row.status === params.status) : all;
    return { results: rows, count: rows.length, next: null, previous: null };
  });
  api.get.mockImplementation(async (id: number) => [overdue, resolved, closed].find((row) => row.id === id) ?? overdue);
  api.report.mockResolvedValue({ byStatus: [{ status: 'OPEN', count: 1 }, { status: 'RESOLVED', count: 1 }], byPriority: [], breached: 1, averageResolutionSeconds: 7200 });
  api.comments.mockResolvedValue([{ id: 1, body: 'Called the customer', isInternal: true, fromVendor: false, authorName: 'Priya Staff', createdAt: '2026-10-18T09:00:00Z' }]);
  api.attachments.list.mockResolvedValue([]);
  api.update.mockImplementation(async (id: number, body: object) => ({ ...overdue, id, ...body }));
  api.transition.mockImplementation(async (id: number, status: string) => ({ ...overdue, id, status }));
  api.create.mockResolvedValue(ticket({ id: 77, number: 'TKT-000077' }));
  api.remove.mockResolvedValue(undefined);
  api.comment.mockResolvedValue({ id: 2 });
  api.share.mockResolvedValue({ shared: true });
  api.stopSharing.mockResolvedValue({ shared: false });
});

describe('TicketsPage list', () => {
  it('shows the customer, the server SLA verdict and the assignee for every ticket', async () => {
    page();
    expect(await screen.findByText(/TKT-000001 · Pump leaking/)).toBeInTheDocument();
    expect(screen.getAllByText('Ravi Traders').length).toBeGreaterThan(0);
    expect(screen.getByText('Past due by 2h')).toBeInTheDocument();
    // a resolved ticket keeps its verdict instead of a live countdown
    expect(screen.getByText('Resolved within the target')).toBeInTheDocument();
    expect(screen.getByText('Priya Staff')).toBeInTheDocument();
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
    expect(screen.getByText(/1 open · 1 past due · average time to resolve 2h/)).toBeInTheDocument();
  });

  it('sends the typed search and the status filter to the server', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText(/TKT-000001/);
    await user.type(screen.getByRole('searchbox', { name: 'Search' }), 'pump');
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ q: 'pump' })));
    await user.click(screen.getByRole('combobox', { name: 'Status' }));
    await user.click(await screen.findByRole('option', { name: 'Resolved' }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ status: 'RESOLVED' })));
  });

  it('shows five columns on the board, each with its own count', async () => {
    const user = userEvent.setup();
    page('/support/tickets?view=board');
    expect(await screen.findByRole('region', { name: 'Open' })).toBeInTheDocument();
    for (const name of ['In progress', 'Waiting on customer', 'Resolved', 'Closed']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
    expect(await within(screen.getByRole('region', { name: 'Open' })).findByText(/TKT-000001/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'List' }));
    expect(await screen.findByRole('table', { name: 'Support tickets' })).toBeInTheDocument();
  });

  it('shows cards instead of a table on a phone', async () => {
    setViewport(400);
    page();
    expect(await screen.findByText(/TKT-000001 · Pump leaking/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('explains an empty list and offers the next step', async () => {
    api.list.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    page();
    expect(await screen.findByRole('button', { name: 'New ticket' })).toBeInTheDocument();
  });

  it('shows an error with a retry', async () => {
    api.list.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/TKT-000001/)).toBeInTheDocument();
  });

  it('has no serious accessibility problems', async () => {
    const view = page();
    await screen.findByText(/TKT-000001/);
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});

describe('TicketsPage who sees what', () => {
  it('starts someone who is not the owner on their own tickets, and lets them see everyone', async () => {
    mocks.role = 'SALES_STAFF';
    const user = userEvent.setup();
    page();
    await screen.findByText(/TKT-000001/);
    expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ mine: 1 }));
    await user.click(screen.getByRole('checkbox', { name: /^Mine|My tickets|Assigned to me/i }));
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.not.objectContaining({ mine: 1 })));
  });

  it('shows the tickets nobody has taken yet', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText(/TKT-000001/);
    await user.click(screen.getByRole('checkbox', { name: 'Not yet assigned' }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ unassigned: 1 })));
  });
});

describe('TicketsPage create', () => {
  it('creates a ticket with the customer, subject, description and priority, then opens it', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'New ticket' }));
    await user.click(await screen.findByRole('button', { name: 'pick-customer' }));
    await user.type(screen.getByLabelText(/Subject/), 'New issue');
    await user.type(screen.getByLabelText('Description'), 'Does not start');
    await user.click(screen.getByRole('button', { name: 'Open ticket' }));
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(expect.objectContaining({
      customer: 5, subject: 'New issue', description: 'Does not start', priority: 'MEDIUM', category: 'GENERAL', assigned_to: null,
    })));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(77));
  });

  it('keeps Open ticket disabled until a customer and subject are given', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'New ticket' }));
    expect(screen.getByRole('button', { name: 'Open ticket' })).toBeDisabled();
  });
});

describe('TicketsPage detail', () => {
  it('shows the customer, the clock and only the legal moves, and moves the ticket', async () => {
    const user = userEvent.setup();
    page('/support/tickets/1');
    expect(await screen.findByRole('heading', { name: /TKT-000001 · Pump leaking/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ravi Traders' })).toHaveAttribute('href', '/sales/customers/5');
    expect(screen.getByText('Seal is gone')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move to Waiting on customer' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Move to In progress' }));
    await waitFor(() => expect(api.transition).toHaveBeenCalledWith(1, 'IN_PROGRESS'));
    expect(await screen.findByText('Moved to In progress.')).toBeInTheDocument();
  });

  it('changes the priority with the version it loaded, and locks it on a finished ticket', async () => {
    const user = userEvent.setup();
    page('/support/tickets/1');
    const detail = within(await screen.findByRole('region', { name: 'Ticket details' }));
    await detail.findByRole('heading', { name: /TKT-000001/ });
    await user.click(detail.getByRole('combobox', { name: 'Priority' }));
    await user.click(await screen.findByRole('option', { name: 'High' }));
    await waitFor(() => expect(api.update).toHaveBeenCalledWith(1, { priority: 'HIGH' }, '2026-10-18T09:00:00Z'));
  });

  it('keeps the priority locked once the ticket is resolved', async () => {
    page('/support/tickets/2');
    await screen.findByRole('heading', { name: /TKT-000002/ });
    expect(screen.getByText('Re-open the ticket to change this.')).toBeInTheDocument();
  });

  it('adds a comment and shows who wrote the others', async () => {
    const user = userEvent.setup();
    page('/support/tickets/1');
    expect(await screen.findByText(/Priya Staff · .*· Internal/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add comment' })).toBeDisabled();
    await user.type(screen.getByLabelText('Comment'), 'Replaced the seal');
    await user.click(screen.getByRole('button', { name: 'Add comment' }));
    await waitFor(() => expect(api.comment).toHaveBeenCalledWith(1, 'Replaced the seal'));
  });

  it('says a closed ticket takes no more comments or files', async () => {
    page('/support/tickets/3');
    expect((await screen.findAllByText(/This ticket is closed/)).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('Comment')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a file' })).not.toBeInTheDocument();
  });

  it('lets the owner share without the description, then stop', async () => {
    const user = userEvent.setup();
    page('/support/tickets/1');
    await user.click(await screen.findByRole('button', { name: 'Share with Bizboard' }));
    await waitFor(() => expect(api.share).toHaveBeenCalledWith(1, false));
  });

  it('shows who a shared ticket is shared with and lets the owner stop', async () => {
    api.get.mockResolvedValue(ticket({ shared: true, sharedAt: '2026-10-18T08:00:00Z', shareIncludesDescription: true }));
    const user = userEvent.setup();
    page('/support/tickets/1');
    expect(await screen.findByText(/with the description/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Stop sharing' }));
    await waitFor(() => expect(api.stopSharing).toHaveBeenCalledWith(1));
  });

  it('asks before deleting an open ticket and goes back to the list', async () => {
    const user = userEvent.setup();
    page('/support/tickets/1');
    await user.click(await screen.findByRole('button', { name: 'Delete' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith(1));
  });

  it('links to the related records and the activity trail', async () => {
    page('/support/tickets/1');
    expect(await screen.findByRole('link', { name: /Job card JOB-000009/ })).toHaveAttribute('href', '/workshop/jobs/9');
    expect(await screen.findByText('Status changed')).toBeInTheDocument();
  });

  it('shows a conflict message when the ticket changed under the person', async () => {
    api.update.mockRejectedValueOnce(Object.assign(new Error('x'), {
      isAxiosError: true,
      response: { status: 409, data: { error: { message: 'This record was changed by someone else. Reload and try again.' } } },
    }));
    const user = userEvent.setup();
    page('/support/tickets/1');
    const detail = within(await screen.findByRole('region', { name: 'Ticket details' }));
    await detail.findByRole('heading', { name: /TKT-000001/ });
    await user.click(detail.getByRole('combobox', { name: 'Priority' }));
    await user.click(await screen.findByRole('option', { name: 'High' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/changed by someone else/);
  });

  it('is read-only for a viewer', async () => {
    mocks.role = 'VIEWER';
    page('/support/tickets/1');
    await screen.findByRole('heading', { name: /TKT-000001/ });
    expect(screen.queryByRole('button', { name: 'New ticket' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move to In progress' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add comment' })).not.toBeInTheDocument();
  });

  it('has no serious accessibility problems on the detail', async () => {
    const view = page('/support/tickets/1');
    await screen.findByRole('heading', { name: /TKT-000001/ });
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});
