import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Complaint } from '@/api/care';
import { ComplaintsPage } from '@/pages/complaints/ComplaintsPage';
import { a11yViolations, renderRoutes, setViewport } from '@/test/careHarness';

vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isComplaintsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
  SupplierField: () => null,
}));

const mocks = vi.hoisted(() => ({ role: 'OWNER' as string }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: mocks.role, canCreateSales: true, companyId: 1 } }),
}));

const api = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), transition: vi.fn(), saveNotes: vi.fn(),
  unlink: vi.fn(), document: vi.fn(), createTicket: vi.fn(), report: vi.fn(), activity: vi.fn(),
  attachments: { list: vi.fn(), upload: vi.fn(), remove: vi.fn() },
}));
const returnable = vi.hoisted(() => vi.fn());
const resources = vi.hoisted(() => ({
  getSalesInvoice: vi.fn(), getSalesCreditNote: vi.fn(), getSalesReturn: vi.fn(), getSalesOrder: vi.fn(),
  completeSalesCreditNote: vi.fn(), getCustomer: vi.fn(),
}));

vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  complaints: () => api,
  returnableLines: (...args: unknown[]) => returnable(...args),
  recordLinks: vi.fn(async () => []),
  recordTimeline: vi.fn(async () => []),
}));

vi.mock('@/api/resources', () => ({
  listTeamMembers: vi.fn(async () => [{ id: 8, name: 'Priya Staff', role: 'SALES_STAFF' }]),
  TEAM_MEMBERS_QUERY_KEY: ['company-users', 'team'],
  listSalesInvoicesPage: vi.fn(async () => ({
    results: [{ id: 30, number: 'INV-000030', invoiceDate: '2026-10-01', customer: 5 }], count: 1, next: null, previous: null,
  })),
  listPurchasesPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
  listProductsPage: vi.fn(async () => ({ results: [{ id: 3, name: 'Motor', sku: 'M-1', sellingPrice: '500' }], count: 1, next: null, previous: null })),
  getPurchase: vi.fn(),
  getPurchaseDebitNote: vi.fn(),
  getSalesInvoice: (...args: unknown[]) => resources.getSalesInvoice(...args),
  getSalesCreditNote: (...args: unknown[]) => resources.getSalesCreditNote(...args),
  getSalesReturn: (...args: unknown[]) => resources.getSalesReturn(...args),
  getSalesOrder: (...args: unknown[]) => resources.getSalesOrder(...args),
  completeSalesCreditNote: (...args: unknown[]) => resources.completeSalesCreditNote(...args),
  getCustomer: (...args: unknown[]) => resources.getCustomer(...args),
}));

function complaint(over: Partial<Complaint> = {}): Complaint {
  return {
    id: 1, number: 'RMA-000001', customer: 5, customerName: 'Ravi Traders', sourceInvoice: 30, sourceInvoiceNumber: 'INV-000030',
    category: 'DAMAGED', description: 'Arrived broken', status: 'OPEN', inspectionNotes: '', resolutionNote: '', salesReturn: null,
    salesCreditNote: null, replacementOrder: null, assignedTo: null, assigneeName: '', ticket: null, ticketNumber: '', resolvedAt: null,
    createdAt: '2026-10-15T10:00:00Z', updatedAt: '2026-10-16T10:00:00Z', ...over,
  };
}

function page(initial = '/complaints') {
  return renderRoutes(
    [
      { path: '/complaints', element: <ComplaintsPage /> },
      { path: '/complaints/:id', element: <ComplaintsPage /> },
    ],
    initial,
  );
}

let current = complaint();

beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = 'OWNER';
  setViewport(1280);
  current = complaint();
  api.list.mockImplementation(async () => ({ results: [current], count: 1, next: null, previous: null }));
  api.get.mockImplementation(async () => current);
  api.create.mockResolvedValue(complaint({ id: 9, number: 'RMA-000009' }));
  api.update.mockImplementation(async (_id: number, body: object) => ({ ...current, ...body }));
  api.transition.mockImplementation(async (_id: number, body: { status: string }) => ({ ...current, status: body.status }));
  api.saveNotes.mockImplementation(async (_id: number, notes: string) => ({ ...current, inspectionNotes: notes }));
  api.document.mockResolvedValue({ id: 70, existing: false });
  api.unlink.mockResolvedValue(complaint());
  api.createTicket.mockResolvedValue({ id: 4, existing: false });
  api.report.mockResolvedValue({
    byCategory: [{ category: 'DAMAGED', count: 1 }], byStatus: [], ageing: [{ bucket: '0-2 days', count: 1 }], resolved: 0,
    resolvedWithDocument: 0, resolvedWithoutDocument: 0, averageResolutionSeconds: null,
  });
  api.activity.mockResolvedValue([]);
  api.attachments.list.mockResolvedValue([]);
  returnable.mockResolvedValue([
    { sourceItem: 11, product: 3, productName: 'Motor', sold: '5.000', returned: '0.000', returnable: '3.000' },
    { sourceItem: 12, product: 4, productName: 'Cable', sold: '2.000', returned: '2.000', returnable: '0.000' },
  ]);
  resources.getSalesInvoice.mockResolvedValue({ id: 30, number: 'INV-000030', items: [{ id: 11, product: 3, unitPrice: '500.00' }, { id: 12, product: 4, unitPrice: '50.00' }] });
  resources.getSalesCreditNote.mockResolvedValue({ number: 'CN-000001', status: 'DRAFT' });
  resources.getCustomer.mockResolvedValue({ id: 5, name: 'Ravi' });
  resources.completeSalesCreditNote.mockResolvedValue({});
});

describe('ComplaintsPage', () => {
  it('lists complaints with the customer, category, status and invoice', async () => {
    page();
    expect(await screen.findByText(/RMA-000001 · Arrived broken/)).toBeInTheDocument();
    expect(screen.getByText('Ravi Traders')).toBeInTheDocument();
    expect(screen.getByText('Damaged goods')).toBeInTheDocument();
    expect(screen.getByText('INV-000030')).toBeInTheDocument();
  });

  it('sends search, status and category to the server', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText(/RMA-000001/);
    await user.type(screen.getByRole('searchbox'), 'ravi');
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ q: 'ravi' })));
    await user.click(screen.getByRole('combobox', { name: 'Category' }));
    await user.click(await screen.findByRole('option', { name: 'Quality problem' }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ category: 'QUALITY' })));
  });

  it('shows the report with the ageing buckets', async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Report' }));
    expect(await screen.findByText(/0-2 days: 1/)).toBeInTheDocument();
  });

  it('opens a new complaint from a ticket with the customer and ticket already named', async () => {
    const user = userEvent.setup();
    page('/complaints?new=1&customer=5&ticket=3&invoice=30');
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Description/), 'Late and damaged');
    await user.click(within(dialog).getByRole('button', { name: 'Log complaint' }));
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(expect.objectContaining({
      customer: 5, ticket: 3, category: 'OTHER', description: 'Late and damaged', source_invoice: 30,
    })));
  });
});

describe('ComplaintsPage detail', () => {
  it('moves OPEN to INSPECTING directly and keeps documents out of reach until approved', async () => {
    const user = userEvent.setup();
    page('/complaints/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    await detail.findByRole('heading', { name: 'RMA-000001' });
    expect(detail.getByText('Approve the complaint before creating a document.')).toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Create credit note' })).not.toBeInTheDocument();
    await user.click(detail.getByRole('button', { name: 'Move to Being inspected' }));
    await waitFor(() => expect(api.transition).toHaveBeenCalledWith(1, { status: 'INSPECTING', inspection_notes: undefined }));
  });

  it('only saves inspection notes when asked and says they are unsaved', async () => {
    const user = userEvent.setup();
    page('/complaints/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    await user.type(await detail.findByLabelText('Inspection notes'), 'Housing cracked');
    expect(detail.getByText('Not saved yet.')).toBeInTheDocument();
    await user.click(detail.getByRole('button', { name: 'Save notes' }));
    await waitFor(() => expect(api.saveNotes).toHaveBeenCalledWith(1, 'Housing cracked'));
  });

  it('will not reject without a reason', async () => {
    current = complaint({ status: 'INSPECTING' });
    const user = userEvent.setup();
    page('/complaints/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    await user.click(await detail.findByRole('button', { name: 'Move to Rejected' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: 'Reject' })).toBeDisabled();
    await user.type(dialog.getByLabelText(/Why is it being rejected[?]/), 'Customer misuse');
    await user.click(dialog.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(api.transition).toHaveBeenCalledWith(1, { status: 'REJECTED', inspection_notes: 'Customer misuse' }));
  });

  it('asks how it was settled when resolving with no document', async () => {
    current = complaint({ status: 'APPROVED' });
    const user = userEvent.setup();
    page('/complaints/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    await user.click(await detail.findByRole('button', { name: 'Move to Resolved' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: 'Resolve' })).toBeDisabled();
    await user.type(dialog.getByLabelText(/How it was settled/), 'Replaced at the counter');
    await user.click(dialog.getByRole('button', { name: 'Resolve' }));
    await waitFor(() => expect(api.transition).toHaveBeenCalledWith(1, { status: 'RESOLVED', resolution_note: 'Replaced at the counter' }));
  });

  it('creates a credit note from ticked lines and stops an over-return', async () => {
    current = complaint({ status: 'APPROVED' });
    const user = userEvent.setup();
    page('/complaints/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    const creditNote = await detail.findByRole('button', { name: 'Create credit note' });
    expect(creditNote).toBeDisabled();
    expect(detail.getByRole('checkbox', { name: 'Include Cable' })).toBeDisabled(); // nothing left to return
    await user.click(detail.getByRole('checkbox', { name: 'Include Motor' }));
    const quantity = detail.getByRole('textbox', { name: 'Quantity of Motor' });
    await user.clear(quantity);
    await user.type(quantity, '9');
    expect(await detail.findByText(/more than can still be returned/)).toBeInTheDocument();
    expect(creditNote).toBeDisabled();
    await user.clear(quantity);
    await user.type(quantity, '2');
    await user.click(creditNote);
    await waitFor(() => expect(api.document).toHaveBeenCalledWith(
      1, 'create-credit-note', [{ product: 3, quantity: '2', unit_price: '500.00', source_item: 11 }], expect.any(String),
    ));
  });

  it('asks for the invoice before a document can be made', async () => {
    current = complaint({ status: 'APPROVED', sourceInvoice: null, sourceInvoiceNumber: '' });
    page('/complaints/1');
    expect(await screen.findByText('Pick the invoice above first.')).toBeInTheDocument();
  });

  it('shows a cancelled document and lets the person unlink it to start again', async () => {
    current = complaint({ status: 'APPROVED', salesCreditNote: 61 });
    resources.getSalesCreditNote.mockResolvedValue({ number: 'CN-000061', status: 'CANCELLED' });
    const user = userEvent.setup();
    page('/complaints/1');
    expect(await screen.findByText('Cancelled: unlink it to make a new one.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Unlink' }));
    await waitFor(() => expect(api.unlink).toHaveBeenCalledWith(1, 'sales_credit_note'));
  });

  it('lets a draft credit note be completed from the complaint', async () => {
    current = complaint({ status: 'APPROVED', salesCreditNote: 61 });
    resources.getSalesCreditNote.mockResolvedValue({ number: 'CN-000061', status: 'DRAFT' });
    const user = userEvent.setup();
    page('/complaints/1');
    await user.click(await screen.findByRole('button', { name: 'Complete credit note' }));
    await waitFor(() => expect(resources.completeSalesCreditNote).toHaveBeenCalled());
    expect(screen.getByRole('link', { name: 'CN-000061' })).toHaveAttribute('href', '/sales/credit-notes/61');
  });

  it('links the return to the return itself', async () => {
    current = complaint({ status: 'APPROVED', salesReturn: 44 });
    resources.getSalesReturn.mockResolvedValue({ number: 'RET-000044', status: 'COMPLETED' });
    page('/complaints/1');
    expect(await screen.findByRole('link', { name: 'RET-000044' })).toHaveAttribute('href', '/sales/returns?return=44');
  });

  it('opens a linked ticket or creates one', async () => {
    const user = userEvent.setup();
    page('/complaints/1');
    await user.click(await screen.findByRole('button', { name: 'Open a ticket' }));
    await waitFor(() => expect(api.createTicket).toHaveBeenCalledWith(1));
  });

  it('freezes files and editing on a closed complaint', async () => {
    current = complaint({ status: 'REJECTED' });
    page('/complaints/1');
    expect(await screen.findByText('This complaint is closed, so files can no longer be changed.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save notes' })).not.toBeInTheDocument();
  });

  it('is read-only for a viewer', async () => {
    mocks.role = 'VIEWER';
    page('/complaints/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    await detail.findByRole('heading', { name: 'RMA-000001' });
    expect(screen.queryByRole('button', { name: 'New complaint' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Move to Being inspected' })).not.toBeInTheDocument();
  });

  it('has no serious accessibility problems', async () => {
    current = complaint({ status: 'APPROVED' });
    const view = page('/complaints/1');
    await screen.findByRole('button', { name: 'Create credit note' });
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});
