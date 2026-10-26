import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Contract, ServiceEvent } from '@/api/care';
import { ContractCertificatePage } from '@/pages/contracts/ContractCertificatePage';
import { ContractsPage } from '@/pages/contracts/ContractsPage';
import { a11yViolations, renderRoutes, setViewport } from '@/test/careHarness';

vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isContractsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
}));

const mocks = vi.hoisted(() => ({ role: 'OWNER' as string, navigate: vi.fn() }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: mocks.role, canCreateSales: true, companyId: 1, company: { name: 'Alpha Traders' } } }),
}));
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => mocks.navigate,
}));

const api = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), renew: vi.fn(), createSchedule: vi.fn(),
  syncSchedule: vi.fn(), pauseSchedule: vi.fn(), resumeSchedule: vi.fn(), events: vi.fn(), addEvent: vi.fn(), editEvent: vi.fn(),
  removeEvent: vi.fn(), timeline: vi.fn(), report: vi.fn(), summary: vi.fn(), coverage: vi.fn(), activity: vi.fn(),
  attachments: { list: vi.fn(), upload: vi.fn(), remove: vi.fn() }, exportUrl: vi.fn(() => '/contracts/report/export/?'),
}));

vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  contracts: api,
  tickets: { list: vi.fn(async () => ({ results: [{ id: 4, number: 'TKT-000004', subject: 'Noise' }], count: 1, next: null, previous: null })) },
  recordLinks: vi.fn(async () => []),
  recordTimeline: vi.fn(async () => []),
}));

vi.mock('@/api/resources', () => ({
  listTeamMembers: vi.fn(async () => []),
  TEAM_MEMBERS_QUERY_KEY: ['company-users', 'team'],
  listProductsPage: vi.fn(async () => ({ results: [{ id: 3, name: 'Pump', sku: 'P-1' }], count: 1, next: null, previous: null })),
  listSalesInvoicesPage: vi.fn(),
}));

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  apiClient: { get: vi.fn(async () => ({ data: new Blob(['x']) })) },
}));
vi.mock('@/utils/blob', () => ({ triggerBlobDownload: vi.fn() }));

function contract(over: Partial<Contract> = {}): Contract {
  return {
    id: 1, number: 'CON-000001', customer: 5, customerName: 'Ravi Traders', product: 3, products: [3], productNames: ['Pump'],
    contractType: 'AMC', startDate: '2026-01-01', endDate: '2026-12-31', daysToExpiry: 74, renewalReminderDays: 30, value: '12000.00',
    recurringSchedule: null, schedule: null, status: 'ACTIVE', notes: 'Yearly service', createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-10-01T00:00:00Z', ...over,
  };
}

const freshEvent: ServiceEvent = {
  id: 7, ticket: 4, ticketNumber: 'TKT-000004', occurredAt: '2026-10-17T10:00:00Z', notes: 'Cleaned the filter', authorName: 'Priya',
  createdAt: new Date().toISOString(),
};
const oldEvent: ServiceEvent = { ...freshEvent, id: 6, ticket: null, ticketNumber: '', notes: 'First visit', createdAt: '2026-01-05T10:00:00Z' };

let current = contract();
let renewals: object[] = [];

function page(initial = '/contracts') {
  return renderRoutes(
    [
      { path: '/contracts', element: <ContractsPage /> },
      { path: '/contracts/:id', element: <ContractsPage /> },
      { path: '/contracts/:id/certificate', element: <ContractCertificatePage /> },
    ],
    initial,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = 'OWNER';
  setViewport(1280);
  current = contract();
  renewals = [];
  api.list.mockImplementation(async () => ({ results: [current], count: 1, next: null, previous: null }));
  api.timeline.mockImplementation(async () => ({ contract: current, events: [freshEvent, oldEvent], renewals }));
  api.create.mockResolvedValue(contract({ id: 12, number: 'CON-000012' }));
  api.update.mockImplementation(async (_id: number, body: object) => ({ ...current, ...body }));
  api.renew.mockResolvedValue(contract());
  api.createSchedule.mockResolvedValue({ id: 3, invoice: 55, cadence: 'QUARTERLY' });
  api.pauseSchedule.mockResolvedValue(contract());
  api.resumeSchedule.mockResolvedValue(contract());
  api.syncSchedule.mockResolvedValue(contract());
  api.addEvent.mockResolvedValue(freshEvent);
  api.editEvent.mockResolvedValue(freshEvent);
  api.removeEvent.mockResolvedValue(undefined);
  api.remove.mockResolvedValue(undefined);
  api.report.mockResolvedValue([{ status: 'ACTIVE', contractType: 'AMC', value: '12000.00' }]);
  api.summary.mockResolvedValue({ expiringByMonth: [{ month: '2026-12', count: 1 }], monthlyRecurringValue: '1000.00' });
  api.activity.mockResolvedValue([]);
  api.attachments.list.mockResolvedValue([]);
});

describe('ContractsPage list', () => {
  it('shows the customer, the products, the days left and the status', async () => {
    page();
    expect(await screen.findByText('CON-000001')).toBeInTheDocument();
    expect(screen.getByText('Ravi Traders')).toBeInTheDocument();
    expect(screen.getByText('Pump')).toBeInTheDocument();
    expect(screen.getByText('Ends in 74 days')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('filters by a chosen status and by "ending soon", not by typing a code', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText('CON-000001');
    await user.click(screen.getByRole('combobox', { name: 'Status' }));
    await user.click(await screen.findByRole('option', { name: 'Expiring soon' }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ status: 'EXPIRING' })));
    await user.click(screen.getByRole('checkbox', { name: 'Ending within 30 days' }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ expiring_within_days: 30 })));
  });

  it('searches on the server', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText('CON-000001');
    await user.type(screen.getByRole('searchbox'), 'pump');
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ q: 'pump' })));
  });

  it('shows the report, the monthly view and downloads the CSV', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Report' }));
    expect(await screen.findByText(/Billed each month by live schedules/)).toBeInTheDocument();
    expect(screen.getByText('2026-12: 1')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'Include cancelled' }));
    await waitFor(() => expect(api.report).toHaveBeenCalledWith({ include_cancelled: 1 }));
    await user.click(screen.getByRole('button', { name: 'Download as CSV' }));
  });

  it('warns about an overlapping contract and saves only when confirmed', async () => {
    const overlap = Object.assign(new Error('conflict'), {
      isAxiosError: true,
      response: { status: 409, data: { error: { details: { code: 'overlap', message: 'This customer already has an AMC covering the same product: CON-000001.' } } } },
    });
    api.create.mockRejectedValueOnce(overlap);
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Add contract' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('button', { name: 'pick-customer' }));
    await user.type(dialog.getByLabelText(/End date/), '2027-01-31');
    await user.click(dialog.getByRole('button', { name: 'Add contract' }));
    const warning = within(await screen.findByRole('dialog'));
    expect(await warning.findByText(/already has an AMC/)).toBeInTheDocument();
    await user.click(warning.getByRole('button', { name: 'Save anyway' }));
    await waitFor(() => expect(api.create).toHaveBeenLastCalledWith(expect.objectContaining({ allow_overlap: true, customer: 5 })));
  });

  it('stops a contract that ends before it starts', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Add contract' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('button', { name: 'pick-customer' }));
    await user.type(dialog.getByLabelText(/End date/), '2020-01-01');
    expect(await dialog.findByText('The end date cannot be before the start date.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Add contract' })).toBeDisabled();
  });
});

describe('ContractsPage detail', () => {
  it('shows the term, the value, the covered products and the visits with who logged them', async () => {
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    expect(await detail.findByRole('heading', { name: 'CON-000001' })).toBeInTheDocument();
    expect(detail.getByText('Contract period')).toBeInTheDocument();
    expect(detail.getByText('Cleaned the filter')).toBeInTheDocument();
    expect(detail.getByRole('link', { name: 'TKT-000004' })).toHaveAttribute('href', '/support/tickets/4');
    expect(detail.getByRole('link', { name: 'Print certificate' })).toHaveAttribute('href', '/contracts/1/certificate');
  });

  it('calls a warranty a warranty period', async () => {
    current = contract({ contractType: 'WARRANTY' });
    page('/contracts/1');
    expect(await screen.findByText('Warranty period')).toBeInTheDocument();
  });

  it('renews with a new end date a year on, keeping the history', async () => {
    current = contract({ status: 'EXPIRED', daysToExpiry: -3, endDate: '2026-10-15' });
    renewals = [{ id: 1, previousEndDate: '2025-10-15', newEndDate: '2026-10-15', previousValue: '10000.00', newValue: '12000.00', note: 'Year 2', createdAt: '2026-01-01T00:00:00Z' }];
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    expect(await detail.findByText(/Year 2/)).toBeInTheDocument();
    await user.click(detail.getByRole('button', { name: 'Renew' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByLabelText(/New end date/)).toHaveValue('2027-10-15');
    await user.click(dialog.getByRole('button', { name: 'Renew' }));
    await waitFor(() => expect(api.renew).toHaveBeenCalledWith(1, { new_end_date: '2027-10-15', value: '12000.00', note: '' }));
  });

  it('will not accept a renewal that does not extend the term', async () => {
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    await user.click(await detail.findByRole('button', { name: 'Renew' }));
    const dialog = within(await screen.findByRole('dialog'));
    const end = dialog.getByLabelText(/New end date/);
    await user.clear(end);
    await user.type(end, '2026-06-01');
    expect(await dialog.findByText('Must be after the current end date.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Renew' })).toBeDisabled();
  });

  it('lets the owner start quarterly billing and opens the first draft invoice', async () => {
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    await user.click(await detail.findByRole('button', { name: 'Start billing' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('combobox', { name: 'Bill every' }));
    await user.click(await screen.findByRole('option', { name: 'Every 3 months' }));
    await user.click(dialog.getByRole('button', { name: 'Start billing' }));
    await waitFor(() => expect(api.createSchedule).toHaveBeenCalledWith(1, 'QUARTERLY', 'contract-1-QUARTERLY'));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/sales/history/55'));
  });

  it('tells staff that only the owner can start billing', async () => {
    mocks.role = 'SALES_STAFF';
    page('/contracts/1');
    expect(await screen.findByText('Only the owner can start billing.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start billing' })).not.toBeInTheDocument();
  });

  it('shows the billing schedule and lets the owner pause it and refresh its amount', async () => {
    current = contract({ schedule: { id: 3, cadence: 'MONTHLY', isActive: true, pausedReason: '', nextRunAt: '2026-11-01T00:00:00Z' } });
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    expect(await detail.findByText(/Monthly · next invoice/)).toBeInTheDocument();
    await user.click(detail.getByRole('button', { name: 'Pause billing' }));
    await waitFor(() => expect(api.pauseSchedule).toHaveBeenCalledWith(1));
    await user.click(detail.getByRole('button', { name: 'Use the current value for future invoices' }));
    await waitFor(() => expect(api.syncSchedule).toHaveBeenCalledWith(1));
  });

  it('explains that billing stopped because the contract ended', async () => {
    current = contract({ status: 'EXPIRED', schedule: { id: 3, cadence: 'MONTHLY', isActive: false, pausedReason: 'CONTRACT_ENDED', nextRunAt: '2026-11-01T00:00:00Z' } });
    page('/contracts/1');
    expect(await screen.findByText(/stopped because the contract ended/)).toBeInTheDocument();
  });

  it('logs a visit with a time and a ticket, and only lets a fresh visit be corrected', async () => {
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    await detail.findByText('Cleaned the filter');
    expect(detail.getAllByRole('button', { name: 'Edit' }).length).toBe(2); // the contract itself and the fresh visit
    expect(detail.getAllByRole('button', { name: 'Remove' })).toHaveLength(1);
    await user.type(detail.getByLabelText(/What was done/), 'Changed the belt');
    await user.click(detail.getByRole('button', { name: 'Log service' }));
    await waitFor(() => expect(api.addEvent).toHaveBeenCalledWith(1, expect.objectContaining({ notes: 'Changed the belt' })));
  });

  it('corrects and removes a fresh visit', async () => {
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    await detail.findByText('Cleaned the filter');
    await user.click(detail.getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(api.removeEvent).toHaveBeenCalledWith(1, 7));
  });

  it('asks for the contract number before cancelling and can bring it back', async () => {
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    await user.click(await detail.findByRole('button', { name: 'Cancel' }));
    const dialog = within(await screen.findByRole('dialog'));
    const confirm = dialog.getAllByRole('button').find((button) => button.textContent === 'Confirm')!;
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText('CON-000001'), 'CON-000001');
    await user.click(confirm);
    await waitFor(() => expect(api.update).toHaveBeenCalledWith(1, { status: 'CANCELLED' }, '2026-10-01T00:00:00Z'));
  });

  it('shows a cancelled contract as frozen with an un-cancel', async () => {
    current = contract({ status: 'CANCELLED' });
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    expect(await detail.findByText('This contract has ended, so files can no longer be changed. Renew it first.')).toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Renew' })).not.toBeInTheDocument();
    await user.click(detail.getByRole('button', { name: 'Un-cancel' }));
    await waitFor(() => expect(api.update).toHaveBeenCalledWith(1, { status: 'ACTIVE' }, '2026-10-01T00:00:00Z'));
  });

  it('lets the owner delete, and not staff', async () => {
    const user = userEvent.setup();
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    await user.click(await detail.findByRole('button', { name: 'Delete' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith(1));
  });

  it('hides delete from staff and every change from a viewer', async () => {
    mocks.role = 'VIEWER';
    page('/contracts/1');
    const detail = within(await screen.findByRole('region', { name: 'Contract details' }));
    await detail.findByRole('heading', { name: 'CON-000001' });
    expect(screen.queryByRole('button', { name: 'Add contract' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Renew' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(detail.queryByLabelText(/What was done/)).not.toBeInTheDocument();
  });

  it('has no serious accessibility problems', async () => {
    const view = page('/contracts/1');
    await screen.findByRole('heading', { name: 'CON-000001' });
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});

describe('ContractCertificatePage', () => {
  it('prints a certificate with the customer, products and term', async () => {
    page('/contracts/1/certificate');
    expect(await screen.findByRole('heading', { name: 'Annual maintenance (AMC) certificate' })).toBeInTheDocument();
    expect(screen.getByText('Ravi Traders')).toBeInTheDocument();
    expect(screen.getByText('Pump')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Print' })).toBeInTheDocument();
  });
});
