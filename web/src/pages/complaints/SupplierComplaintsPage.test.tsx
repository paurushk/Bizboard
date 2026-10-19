import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Complaint } from '@/api/care';
import { SupplierComplaintsPage } from '@/pages/complaints/SupplierComplaintsPage';
import { a11yViolations, renderRoutes, setViewport } from '@/test/careHarness';

vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isComplaintsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: () => null,
  SupplierField: ({ onChange }: { onChange: (s: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 7, name: 'Mega Mills' })}>pick-supplier</button>
  ),
}));

const mocks = vi.hoisted(() => ({ role: 'OWNER' as string }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: mocks.role, canCreatePurchases: true, companyId: 1 } }),
}));

const api = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), transition: vi.fn(), saveNotes: vi.fn(),
  unlink: vi.fn(), document: vi.fn(), report: vi.fn(), activity: vi.fn(),
  attachments: { list: vi.fn(), upload: vi.fn(), remove: vi.fn() },
}));
const resources = vi.hoisted(() => ({ getPurchase: vi.fn(), getPurchaseDebitNote: vi.fn() }));

vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  complaints: () => api,
  recordLinks: vi.fn(async () => []),
  recordTimeline: vi.fn(async () => []),
}));

vi.mock('@/api/resources', () => ({
  listCompanyUsers: vi.fn(async () => []),
  listPurchasesPage: vi.fn(async () => ({ results: [{ id: 50, number: 'PB-000050' }], count: 1, next: null, previous: null })),
  listSalesInvoicesPage: vi.fn(),
  getCustomer: vi.fn(),
  getSalesInvoice: vi.fn(),
  getSalesCreditNote: vi.fn(),
  getSalesReturn: vi.fn(),
  getSalesOrder: vi.fn(),
  completeSalesCreditNote: vi.fn(),
  getPurchase: (...args: unknown[]) => resources.getPurchase(...args),
  getPurchaseDebitNote: (...args: unknown[]) => resources.getPurchaseDebitNote(...args),
}));

function complaint(over: Partial<Complaint> = {}): Complaint {
  return {
    id: 1, number: 'SCN-000001', supplier: 7, supplierName: 'Mega Mills', sourceInvoice: 50, sourceInvoiceNumber: 'PB-000050',
    category: 'QUALITY', description: 'Wrong grade of yarn', status: 'OPEN', inspectionNotes: '', resolutionNote: '', purchaseDebitNote: null,
    assignedTo: null, assigneeName: '', resolvedAt: null, createdAt: '2026-10-15T10:00:00Z', updatedAt: '2026-10-16T10:00:00Z', ...over,
  };
}

function page(initial = '/complaints/suppliers') {
  return renderRoutes(
    [
      { path: '/complaints/suppliers', element: <SupplierComplaintsPage /> },
      { path: '/complaints/suppliers/:id', element: <SupplierComplaintsPage /> },
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
  api.create.mockResolvedValue(complaint({ id: 8 }));
  api.transition.mockImplementation(async (_id: number, body: { status: string }) => ({ ...current, status: body.status }));
  api.document.mockResolvedValue({ id: 90, existing: false });
  api.report.mockResolvedValue({ byCategory: [], byStatus: [], ageing: [], resolved: 0, resolvedWithDocument: 0, resolvedWithoutDocument: 0, averageResolutionSeconds: null });
  api.activity.mockResolvedValue([]);
  api.attachments.list.mockResolvedValue([]);
  resources.getPurchase.mockResolvedValue({ id: 50, items: [{ id: 5, product: 3, productName: 'Yarn', quantity: '10.000', unitPrice: '40.00' }] });
  resources.getPurchaseDebitNote.mockResolvedValue({ number: 'DN-000009', status: 'DRAFT' });
});

describe('SupplierComplaintsPage', () => {
  it('lists supplier complaints with the supplier and the bill', async () => {
    page();
    expect(await screen.findByText(/SCN-000001 · Wrong grade of yarn/)).toBeInTheDocument();
    expect(screen.getByText('Mega Mills')).toBeInTheDocument();
    expect(screen.getByText('PB-000050')).toBeInTheDocument();
  });

  it('logs a complaint against the picked supplier and bill', async () => {
    const user = userEvent.setup();
    page('/complaints/suppliers?new=1');
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'pick-supplier' }));
    await user.type(within(dialog).getByLabelText(/Description/), 'Short delivery');
    await user.click(within(dialog).getByRole('button', { name: 'Log complaint' }));
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(expect.objectContaining({ supplier: 7, description: 'Short delivery', category: 'OTHER' })));
  });

  it('offers only a debit note, built from the bill lines, once approved', async () => {
    current = complaint({ status: 'APPROVED' });
    const user = userEvent.setup();
    page('/complaints/suppliers/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    const create = await detail.findByRole('button', { name: 'Create debit note' });
    expect(detail.queryByRole('button', { name: 'Create credit note' })).not.toBeInTheDocument();
    expect(detail.queryByRole('button', { name: 'Create return' })).not.toBeInTheDocument();
    expect(create).toBeDisabled();
    await user.click(await detail.findByRole('checkbox', { name: 'Include Yarn' }));
    await user.click(create);
    await waitFor(() => expect(api.document).toHaveBeenCalledWith(
      1, 'create-debit-note', [{ product: 3, quantity: '1', unit_price: '40.00' }], expect.any(String),
    ));
  });

  it('shows the linked debit note and no replacement or return options', async () => {
    current = complaint({ status: 'APPROVED', purchaseDebitNote: 90 });
    page('/complaints/suppliers/1');
    expect(await screen.findByRole('link', { name: 'DN-000009' })).toHaveAttribute('href', '/purchases/debit-notes/90');
    expect(screen.queryByText(/replacement/i)).not.toBeInTheDocument();
  });

  it('asks for a reason to reject and a note to resolve without a debit note', async () => {
    current = complaint({ status: 'INSPECTING' });
    const user = userEvent.setup();
    page('/complaints/suppliers/1');
    const detail = within(await screen.findByRole('region', { name: 'Complaint details' }));
    await user.click(await detail.findByRole('button', { name: 'Move to Rejected' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: 'Reject' })).toBeDisabled();
    await user.type(dialog.getByLabelText(/Why is it being rejected[?]/), 'Within tolerance');
    await user.click(dialog.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(api.transition).toHaveBeenCalledWith(1, { status: 'REJECTED', inspection_notes: 'Within tolerance' }));
  });

  it('does not show customer-only actions', async () => {
    page('/complaints/suppliers/1');
    await screen.findByRole('heading', { name: 'SCN-000001' });
    expect(screen.queryByRole('button', { name: 'Open a ticket' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Create a job card' })).not.toBeInTheDocument();
  });

  it('has no serious accessibility problems', async () => {
    current = complaint({ status: 'APPROVED' });
    const view = page('/complaints/suppliers/1');
    await screen.findByRole('button', { name: 'Create debit note' });
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});
