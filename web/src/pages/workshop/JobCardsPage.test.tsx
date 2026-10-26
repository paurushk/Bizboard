import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Job, JobLine } from '@/api/care';
import { JobCardsPage } from '@/pages/workshop/JobCardsPage';
import { JobSlipPage } from '@/pages/workshop/JobSlipPage';
import { a11yViolations, renderRoutes, setViewport } from '@/test/careHarness';

vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isWorkshopEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ value, onChange }: { value: { id: number } | null; onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>{value ? 'customer-chosen' : 'pick-customer'}</button>
  ),
}));

const mocks = vi.hoisted(() => ({ role: 'OWNER' as string, navigate: vi.fn() }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: mocks.role, canCreateSales: true, companyId: 1, company: { name: 'Alpha Garage' } } }),
}));
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => mocks.navigate,
}));

const api = vi.hoisted(() => ({
  jobs: {
    list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), addLine: vi.fn(), editLine: vi.fn(), removeLine: vi.fn(),
    start: vi.fn(), schedule: vi.fn(), convert: vi.fn(), reopen: vi.fn(), cancel: vi.fn(), activity: vi.fn(), stockOptions: vi.fn(),
  },
  bays: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
  coverage: vi.fn(),
}));

vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  jobs: api.jobs,
  bays: api.bays,
  contracts: { coverage: api.coverage, list: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })) },
  recordLinks: vi.fn(async () => []),
  recordTimeline: vi.fn(async () => []),
}));

vi.mock('@/api/resources', () => ({
  getCustomer: vi.fn(async () => ({ id: 5, name: 'Ravi' })),
  listTeamMembers: vi.fn(async () => [{ id: 8, name: 'Priya Staff', role: 'SALES_STAFF' }]),
  TEAM_MEMBERS_QUERY_KEY: ['company-users', 'team'],
  listProductsPage: vi.fn(async (params: { product_type?: string }) => ({
    results: params.product_type === 'SERVICE'
      ? [{ id: 20, name: 'Labour hour', sku: 'LB-1', sellingPrice: '300' }]
      : [{ id: 3, name: 'Brake pad', sku: 'BP-1', sellingPrice: '800' }],
    count: 1, next: null, previous: null,
  })),
}));

function line(over: Partial<JobLine> = {}): JobLine {
  return {
    id: 1, kind: 'PART', product: 3, productName: 'Brake pad', quantity: '2.000', unitPrice: '800.00', labourMinutes: 0,
    technicianCommissionPercent: '0.00', commissionAmount: '0.00', serial: null, batch: null, batchNo: '', coveredByContract: false, ...over,
  };
}

function job(over: Partial<Job> = {}): Job {
  return {
    id: 1, number: 'JOB-000001', customer: 5, customerName: 'Ravi Traders', technician: 8, technicianName: 'Priya Staff', status: 'IN_PROGRESS',
    complaint: 'Brakes squeal', registrationNo: 'KA01AB1234', vehicleModel: 'Alto', odometerReading: '12000.0', serviceBay: 2, serviceBayName: 'Bay A',
    scheduledStart: '2026-10-18T09:00:00Z', scheduledEnd: '2026-10-18T11:00:00Z', salesInvoice: null, invoiceNumber: '', invoiceStatus: '',
    contract: null, contractNumber: '', ticket: null, ticketNumber: '', sourceComplaint: null, complaintNumber: '', warehouse: null,
    subtotal: '1600.00', gstTotal: '288.00', total: '1888.00', lineCount: 1, lines: [line()], serialHistory: [],
    createdAt: '2026-10-17T10:00:00Z', updatedAt: '2026-10-18T08:00:00Z', ...over,
  };
}

let current = job();

function page(initial = '/workshop/jobs') {
  return renderRoutes(
    [
      { path: '/workshop/jobs', element: <JobCardsPage /> },
      { path: '/workshop/jobs/:id', element: <JobCardsPage /> },
      { path: '/workshop/jobs/:id/slip', element: <JobSlipPage /> },
    ],
    initial,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = 'OWNER';
  setViewport(1280);
  current = job();
  api.jobs.list.mockImplementation(async () => ({ results: [current], count: 1, next: null, previous: null }));
  api.jobs.get.mockImplementation(async () => current);
  api.jobs.create.mockResolvedValue(job({ id: 9 }));
  api.jobs.update.mockResolvedValue(current);
  api.jobs.addLine.mockResolvedValue(current);
  api.jobs.editLine.mockResolvedValue(current);
  api.jobs.removeLine.mockResolvedValue(current);
  api.jobs.start.mockResolvedValue(current);
  api.jobs.schedule.mockResolvedValue(current);
  api.jobs.convert.mockResolvedValue({ ...current, salesInvoice: 55 });
  api.jobs.reopen.mockResolvedValue(current);
  api.jobs.cancel.mockResolvedValue(current);
  api.jobs.activity.mockResolvedValue([]);
  api.jobs.stockOptions.mockResolvedValue({ trackSerial: false, trackBatch: false, serials: [], batches: [] });
  api.bays.list.mockResolvedValue({ results: [{ id: 2, name: 'Bay A', isActive: true }, { id: 3, name: 'Bay B', isActive: false }], count: 2, next: null, previous: null });
  api.bays.create.mockResolvedValue({ id: 4, name: 'Bay C', isActive: true });
  api.bays.update.mockResolvedValue({});
  api.bays.remove.mockResolvedValue(undefined);
  api.coverage.mockResolvedValue([]);
});

describe('JobCardsPage list', () => {
  it('shows the customer, vehicle, technician, bay, status and total for each job', async () => {
    page();
    expect(await screen.findByText('JOB-000001')).toBeInTheDocument();
    expect(screen.getByText('Ravi Traders')).toBeInTheDocument();
    expect(screen.getByText('KA01AB1234 · Alto')).toBeInTheDocument();
    expect(screen.getByText('Priya Staff')).toBeInTheDocument();
    expect(screen.getByText('In progress')).toBeInTheDocument();
    expect(screen.getByText('₹1,888.00')).toBeInTheDocument();
  });

  it('searches the vehicle registration on the server', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText('JOB-000001');
    await user.type(screen.getByRole('searchbox'), 'KA01');
    await waitFor(() => expect(api.jobs.list).toHaveBeenCalledWith(expect.objectContaining({ q: 'KA01' })));
  });

  it('shows what is booked in each bay today', async () => {
    const user = userEvent.setup();
    page('/workshop/jobs?view=bays&day=2026-10-18');
    expect(await screen.findByRole('region', { name: 'Bay A' })).toBeInTheDocument();
    expect(await within(screen.getByRole('region', { name: 'Bay A' })).findByRole('link', { name: /JOB-000001/ })).toBeInTheDocument();
    expect(api.jobs.list).toHaveBeenCalledWith(expect.objectContaining({ scheduled_from: '2026-10-18', scheduled_to: '2026-10-18' }));
    await user.click(screen.getByRole('button', { name: 'List' }));
    expect(await screen.findByRole('table', { name: 'Job cards' })).toBeInTheDocument();
  });

  it('manages bays: add, switch off, delete', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Manage bays' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.type(await dialog.findByLabelText('Bay name'), 'Bay C');
    await user.click(dialog.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(api.bays.create).toHaveBeenCalledWith('Bay C'));
    await user.click(dialog.getAllByRole('checkbox')[0]);
    await waitFor(() => expect(api.bays.update).toHaveBeenCalledWith(2, { is_active: false }));
    await user.click(dialog.getAllByRole('button', { name: 'Delete' })[0]);
    await waitFor(() => expect(api.bays.remove).toHaveBeenCalled());
  });

  it('has an empty state with the next step', async () => {
    api.jobs.list.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    page();
    expect(await screen.findAllByRole('button', { name: 'Create job card' })).not.toHaveLength(0);
  });
});

describe('creating a job', () => {
  it('opens from a ticket with the customer filled in, offers the customer warranty, and links the ticket', async () => {
    api.coverage.mockResolvedValue([{ id: 31, number: 'CON-000031', contractType: 'WARRANTY', startDate: '2026-01-01', endDate: '2027-01-01', hasSchedule: false }]);
    const user = userEvent.setup();
    page('/workshop/jobs/new?ticket=3&customer=5');
    const dialog = within(await screen.findByRole('dialog'));
    expect(await dialog.findByText(/Ravi|customer-chosen/)).toBeInTheDocument();
    expect(await dialog.findByText(/active contract, CON-000031/)).toBeInTheDocument();
    await user.click(dialog.getByRole('button', { name: 'Use it' }));
    await user.type(dialog.getByLabelText('Complaint'), 'Noise when braking');
    await user.click(dialog.getByRole('button', { name: 'Create job card' }));
    await waitFor(() => expect(api.jobs.create).toHaveBeenCalledWith(expect.objectContaining({
      customer: 5, ticket: 3, contract: 31, complaint: 'Noise when braking',
    })));
  });

  it('asks before booking a technician who is already busy, then goes ahead', async () => {
    api.jobs.create.mockRejectedValueOnce(Object.assign(new Error('busy'), {
      isAxiosError: true,
      response: { status: 409, data: { error: { details: { code: 'technician_busy', message: 'This technician is already booked for JOB-000002 in that time.' } } } },
    }));
    const user = userEvent.setup();
    page('/workshop/jobs/new?customer=5');
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(await dialog.findByRole('button', { name: 'Create job card' }));
    const warning = within(await screen.findByRole('dialog'));
    expect(await warning.findByText(/already booked for JOB-000002/)).toBeInTheDocument();
    await user.click(warning.getByRole('button', { name: 'Book anyway' }));
    await waitFor(() => expect(api.jobs.create).toHaveBeenLastCalledWith(expect.objectContaining({ allow_overlap: true })));
  });
});

describe('a job card', () => {
  it('lists its lines with covered and no-charge shown in words, and totals', async () => {
    current = job({
      lines: [line(), line({ id: 2, kind: 'LABOUR', productName: 'Labour hour', quantity: '1.000', unitPrice: '0.00', coveredByContract: true }), line({ id: 3, productName: 'Washer', quantity: '1.000', unitPrice: '0.00' })],
    });
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await detail.findByRole('heading', { name: 'JOB-000001' });
    expect(detail.getByText('Covered')).toBeInTheDocument();
    expect(detail.getByText('No charge')).toBeInTheDocument();
    expect(detail.getByText('Subtotal: ₹1,600.00')).toBeInTheDocument();
    expect(detail.getByText('Total: ₹1,888.00')).toBeInTheDocument();
  });

  it('adds a labour line with minutes and a part line with its price', async () => {
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('button', { name: 'Labour' }));
    await user.click(detail.getByRole('combobox', { name: 'Service' }));
    await user.click(await screen.findByRole('option', { name: /Labour hour/ }));
    await user.type(detail.getByLabelText('Minutes'), '45');
    await user.click(detail.getByRole('button', { name: 'Add line' }));
    await waitFor(() => expect(api.jobs.addLine).toHaveBeenCalledWith(1, expect.objectContaining({
      kind: 'LABOUR', product: 20, unit_price: '300', labour_minutes: 45,
    })));
  });

  it('marks a line as no charge so its price becomes zero', async () => {
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('combobox', { name: 'Part' }));
    await user.click(await screen.findByRole('option', { name: /Brake pad/ }));
    await user.click(detail.getByRole('checkbox', { name: 'No charge (goodwill)' }));
    await user.click(detail.getByRole('button', { name: 'Add line' }));
    await waitFor(() => expect(api.jobs.addLine).toHaveBeenCalledWith(1, expect.objectContaining({ product: 3, unit_price: '0' })));
  });

  it('will not add a serial-tracked part until a serial is chosen', async () => {
    api.jobs.stockOptions.mockResolvedValue({ trackSerial: true, trackBatch: false, serials: [{ id: 41, serialNumber: 'SN-41' }], batches: [] });
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('combobox', { name: 'Part' }));
    await user.click(await screen.findByRole('option', { name: /Brake pad/ }));
    const add = detail.getByRole('button', { name: 'Add line' });
    await waitFor(() => expect(detail.getByRole('combobox', { name: /Serial/ })).toBeInTheDocument());
    expect(add).toBeDisabled();
    await user.click(detail.getByRole('combobox', { name: /Serial/ }));
    await user.click(await screen.findByRole('option', { name: 'SN-41' }));
    await user.click(add);
    await waitFor(() => expect(api.jobs.addLine).toHaveBeenCalledWith(1, expect.objectContaining({ serial: 41, quantity: '1' })));
  });

  it('offers covered lines only when the job names a contract', async () => {
    current = job({ contract: 31, contractNumber: 'CON-000031' });
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('combobox', { name: 'Part' }));
    await user.click(await screen.findByRole('option', { name: /Brake pad/ }));
    await user.click(detail.getByRole('checkbox', { name: 'Covered by CON-000031 (no charge)' }));
    await user.click(detail.getByRole('button', { name: 'Add line' }));
    await waitFor(() => expect(api.jobs.addLine).toHaveBeenCalledWith(1, expect.objectContaining({ covered_by_contract: true, unit_price: '0' })));
  });

  it('edits and removes a line while the job is open', async () => {
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('button', { name: 'Edit Brake pad' }));
    const dialog = within(await screen.findByRole('dialog'));
    const quantity = dialog.getByLabelText('Quantity');
    await user.clear(quantity);
    await user.type(quantity, '3');
    await user.click(dialog.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.jobs.editLine).toHaveBeenCalledWith(1, 1, { quantity: '3', unit_price: '800.00' }));
    await user.click(detail.getByRole('button', { name: 'Remove Brake pad' }));
    await waitFor(() => expect(api.jobs.removeLine).toHaveBeenCalledWith(1, 1));
  });

  it('creates the draft invoice and goes to it', async () => {
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('button', { name: 'Create draft invoice' }));
    await waitFor(() => expect(api.jobs.convert).toHaveBeenCalledWith(1, expect.any(String)));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/sales/history/55'));
  });

  it('locks the lines once an invoice draft exists and lets the person revert it', async () => {
    current = job({ salesInvoice: 55, invoiceNumber: '', invoiceStatus: 'DRAFT' });
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    expect(await detail.findByText(/invoice draft exists, so the lines are locked/)).toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Add line' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Remove Brake pad' })).not.toBeInTheDocument();
    await user.click(detail.getByRole('button', { name: 'Revert to editing' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Revert to editing' }));
    await waitFor(() => expect(api.jobs.reopen).toHaveBeenCalledWith(1));
  });

  it('cannot be cancelled once the invoice is complete', async () => {
    current = job({ status: 'INVOICED', salesInvoice: 55, invoiceStatus: 'COMPLETED', invoiceNumber: 'INV-55' });
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    expect(await detail.findByRole('link', { name: 'Open invoice INV-55' })).toHaveAttribute('href', '/sales/history/55');
    expect(detail.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Add line' })).not.toBeInTheDocument();
  });

  it('starts a draft job and cancels an open one after asking', async () => {
    current = job({ status: 'DRAFT', lines: [], lineCount: 0 });
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('button', { name: 'Start job' }));
    await waitFor(() => expect(api.jobs.start).toHaveBeenCalledWith(1));
    await user.click(detail.getByRole('button', { name: 'Cancel' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel this job' }));
    await waitFor(() => expect(api.jobs.cancel).toHaveBeenCalledWith(1));
  });

  it('books a bay with a start and an end', async () => {
    const user = userEvent.setup();
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await user.click(await detail.findByRole('button', { name: 'Book a bay' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: 'Book a bay' })).toBeEnabled();
    await user.click(dialog.getByRole('button', { name: 'Book a bay' }));
    await waitFor(() => expect(api.jobs.schedule).toHaveBeenCalledWith(1, expect.objectContaining({ service_bay: 2 })));
  });

  it('shows the linked ticket and complaint', async () => {
    current = job({ ticket: 3, ticketNumber: 'TKT-000003', sourceComplaint: 4, complaintNumber: 'RMA-000004' });
    page('/workshop/jobs/1');
    expect(await screen.findByRole('link', { name: 'TKT-000003' })).toHaveAttribute('href', '/support/tickets/3');
    expect(screen.getByRole('link', { name: 'RMA-000004' })).toHaveAttribute('href', '/complaints/4');
  });

  it('is read-only for a viewer', async () => {
    mocks.role = 'VIEWER';
    page('/workshop/jobs/1');
    const detail = within(await screen.findByRole('region', { name: 'Job details' }));
    await detail.findByRole('heading', { name: 'JOB-000001' });
    expect(detail.queryByRole('button', { name: 'Add line' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Create draft invoice' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Manage bays' })).not.toBeInTheDocument();
  });

  it('has no serious accessibility problems', async () => {
    const view = page('/workshop/jobs/1');
    await screen.findByRole('heading', { name: 'JOB-000001' });
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});

describe('the job slip', () => {
  it('prints the complaint, the vehicle and the estimate for the customer', async () => {
    page('/workshop/jobs/1/slip');
    expect(await screen.findByRole('heading', { name: 'Job card' })).toBeInTheDocument();
    expect(screen.getByText('Brakes squeal')).toBeInTheDocument();
    expect(screen.getByText('KA01AB1234')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Estimate' })).toBeInTheDocument();
    expect(screen.queryByText(/commission/i)).not.toBeInTheDocument();
  });
});
