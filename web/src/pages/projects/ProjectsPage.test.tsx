import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Milestone, Project } from '@/api/care';
import { ProjectsPage } from '@/pages/projects/ProjectsPage';
import { a11yViolations, renderRoutes, setViewport } from '@/test/careHarness';

vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isProjectsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
}));

const mocks = vi.hoisted(() => ({ role: 'OWNER' as string, navigate: vi.fn() }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: mocks.role, canCreateSales: true, companyId: 1 } }),
}));
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => mocks.navigate,
}));

const api = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), addMilestone: vi.fn(), editMilestone: vi.fn(), deleteMilestone: vi.fn(),
  ready: vi.fn(), unready: vi.fn(), reorder: vi.fn(), invoice: vi.fn(), close: vi.fn(), cancel: vi.fn(), activity: vi.fn(),
}));

vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  projects: api,
  contracts: { list: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })) },
  recordLinks: vi.fn(async () => []),
  recordTimeline: vi.fn(async () => []),
}));

vi.mock('@/api/resources', () => ({
  listTeamMembers: vi.fn(async () => []),
  TEAM_MEMBERS_QUERY_KEY: ['company-users', 'team'],
  listProductsPage: vi.fn(async () => ({ results: [{ id: 20, name: 'Design work', sku: 'D-1' }], count: 1, next: null, previous: null })),
}));

function milestone(over: Partial<Milestone> = {}): Milestone {
  return {
    id: 1, name: 'Foundations', sequence: 1, amount: '1000.00', targetCompletionDate: '2099-01-01', serviceProduct: 20,
    serviceProductName: 'Design work', status: 'PLANNED', salesInvoice: null, invoiceNumber: '', invoiceStatus: '', gstRate: '18.00',
    gstAmount: '180.00', amountInclGst: '1180.00', ...over,
  };
}

function project(over: Partial<Project> = {}): Project {
  return {
    id: 1, number: 'PRJ-000001', customer: 5, customerName: 'Ravi Traders', name: 'Warehouse extension', status: 'OPEN', notes: 'Phase 1',
    startDate: '2026-10-01', endDate: '2027-03-31', contractValue: '3000.00', contract: null, contractNumber: '', plannedTotal: '2000.00',
    invoicedTotal: '1000.00', readyTotal: '0.00', remainingTotal: '1000.00', percentComplete: 50, overBudget: false, milestoneCount: 2,
    milestones: [milestone({ status: 'INVOICED', salesInvoice: 55, invoiceNumber: 'INV-55' }), milestone({ id: 2, name: 'Roof', sequence: 2 })],
    createdAt: '2026-10-01T00:00:00Z', updatedAt: '2026-10-10T00:00:00Z', ...over,
  };
}

let current = project();

function page(initial = '/projects') {
  return renderRoutes(
    [
      { path: '/projects', element: <ProjectsPage /> },
      { path: '/projects/:id', element: <ProjectsPage /> },
    ],
    initial,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = 'OWNER';
  setViewport(1280);
  current = project();
  api.list.mockImplementation(async () => ({ results: [current], count: 1, next: null, previous: null }));
  api.get.mockImplementation(async () => current);
  api.create.mockResolvedValue(project({ id: 6, number: 'PRJ-000006' }));
  for (const name of ['update', 'addMilestone', 'editMilestone', 'deleteMilestone', 'ready', 'unready', 'reorder', 'close', 'cancel'] as const) {
    api[name].mockImplementation(async () => current);
  }
  api.invoice.mockImplementation(async () => ({ ...current, milestones: [milestone({ id: 2, status: 'READY', salesInvoice: 77 })] }));
  api.activity.mockResolvedValue([]);
});

describe('ProjectsPage list', () => {
  it('shows each project with its customer, status and how much is billed', async () => {
    page();
    expect(await screen.findByText(/PRJ-000001 · Warehouse extension/)).toBeInTheDocument();
    expect(screen.getByText('Ravi Traders')).toBeInTheDocument();
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText(/50% · ₹1,000.00 \/ ₹2,000.00/)).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Billing progress of PRJ-000001' })).toBeInTheDocument();
  });

  it('searches and filters on the server', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText(/PRJ-000001/);
    await user.type(screen.getByRole('searchbox'), 'ware');
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ q: 'ware' })));
    await user.click(screen.getByRole('combobox', { name: 'Status' }));
    await user.click(await screen.findByRole('option', { name: 'Closed' }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ status: 'CLOSED' })));
  });

  it('starts a project and opens it', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Start project' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('button', { name: 'pick-customer' }));
    await user.type(dialog.getByLabelText(/Name/), 'Showroom fit-out');
    await user.type(dialog.getByLabelText('Agreed value'), '5000');
    await user.click(dialog.getByRole('button', { name: 'Start project' }));
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(
      expect.objectContaining({ customer: 5, name: 'Showroom fit-out', contract_value: '5000' }), expect.any(String),
    ));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalled());
  });

  it('will not start a project that ends before it begins', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Start project' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('button', { name: 'pick-customer' }));
    await user.type(dialog.getByLabelText(/Name/), 'X');
    await user.type(dialog.getByLabelText('Start date'), '2026-12-01');
    await user.type(dialog.getByLabelText('End date'), '2026-11-01');
    expect(dialog.getByRole('button', { name: 'Start project' })).toBeDisabled();
  });
});

describe('ProjectsPage detail', () => {
  it('shows the money: planned, invoiced, remaining, percent and the GST note', async () => {
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await detail.findByRole('heading', { name: /PRJ-000001/ });
    for (const label of ['Planned', 'Invoiced', 'Remaining', 'Complete']) {
      expect(detail.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(detail.getByText('Amounts are before GST.')).toBeInTheDocument();
    expect(detail.getAllByText('₹1,180.00 with GST', { exact: false }).length).toBeGreaterThan(0);
  });

  it('warns when the milestones add up to more than the agreed value', async () => {
    current = project({ overBudget: true });
    page('/projects/1');
    expect(await screen.findByText('The milestones add up to more than the agreed value.')).toBeInTheDocument();
  });

  it('marks a planned milestone ready, then invoices it and goes to the draft invoice', async () => {
    const user = userEvent.setup();
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await user.click(await detail.findByRole('button', { name: 'Mark Roof ready' }));
    await waitFor(() => expect(api.ready).toHaveBeenCalledWith(1, 2));
  });

  it('can take a ready milestone back to planned so it can be edited or removed', async () => {
    current = project({ milestones: [milestone({ id: 2, name: 'Roof', status: 'READY' })] });
    const user = userEvent.setup();
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await user.click(await detail.findByRole('button', { name: 'Move Roof back to planned' }));
    await waitFor(() => expect(api.unready).toHaveBeenCalledWith(1, 2));
    await user.click(detail.getByRole('button', { name: 'Invoice Roof' }));
    await waitFor(() => expect(api.invoice).toHaveBeenCalledWith(1, 2, 'milestone-2'));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/sales/history/77'));
  });

  it('shows an invoiced milestone with a link to its invoice and no way to change it', async () => {
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    expect(await detail.findByRole('link', { name: 'View invoice' })).toHaveAttribute('href', '/sales/history/55');
    expect(detail.queryByRole('button', { name: 'Delete Foundations' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Mark Foundations ready' })).not.toBeInTheDocument();
  });

  it('adds a milestone with a service item and a before-GST amount', async () => {
    const user = userEvent.setup();
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await user.click(await detail.findByRole('button', { name: 'Add milestone' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: 'Save' })).toBeDisabled();
    await user.type(dialog.getByLabelText(/^Milestone/), 'Paint');
    await user.type(dialog.getByLabelText(/Amount/), '500');
    await user.click(dialog.getByRole('combobox', { name: /Service/ }));
    await user.click(await screen.findByRole('option', { name: /Design work/ }));
    await user.click(dialog.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.addMilestone).toHaveBeenCalledWith(1, expect.objectContaining({ name: 'Paint', amount: '500', service_product: 20, sequence: 3 })));
  });

  it('reorders milestones with the up and down buttons', async () => {
    const user = userEvent.setup();
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await user.click(await detail.findByRole('button', { name: 'Move Roof up' }));
    await waitFor(() => expect(api.reorder).toHaveBeenCalledWith(1, [2, 1]));
  });

  it('asks before deleting a milestone', async () => {
    const user = userEvent.setup();
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await user.click(await detail.findByRole('button', { name: 'Delete Roof' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.deleteMilestone).toHaveBeenCalledWith(1, 2));
  });

  it('closes the project after confirmation', async () => {
    const user = userEvent.setup();
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await user.click(await detail.findByRole('button', { name: 'Close project' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(api.close).toHaveBeenCalledWith(1));
  });

  it('cancels a project only with a reason, and only for the owner', async () => {
    const user = userEvent.setup();
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await user.click(await detail.findByRole('button', { name: 'Cancel project' }));
    const dialog = within(await screen.findByRole('dialog'));
    const confirm = dialog.getAllByRole('button', { name: 'Cancel project' }).pop()!;
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText(/Why is it being cancelled[?]/), 'Client withdrew');
    await user.click(confirm);
    await waitFor(() => expect(api.cancel).toHaveBeenCalledWith(1, 'Client withdrew'));
  });

  it('hides cancel from staff and every change from a viewer', async () => {
    mocks.role = 'VIEWER';
    page('/projects/1');
    const detail = within(await screen.findByRole('region', { name: 'Project details' }));
    await detail.findByRole('heading', { name: /PRJ-000001/ });
    expect(detail.queryByRole('button', { name: 'Close project' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Cancel project' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Add milestone' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start project' })).not.toBeInTheDocument();
  });

  it('has no serious accessibility problems', async () => {
    const view = page('/projects/1');
    await screen.findByRole('heading', { name: /PRJ-000001/ });
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});
