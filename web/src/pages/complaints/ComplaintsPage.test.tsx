import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ComplaintsPage } from '@/pages/complaints/ComplaintsPage';
import type { ComplaintRow } from '@/api/growth';

vi.mock('@/config/features', () => ({
  isComplaintsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
  ProductField: ({ onChange }: { onChange: (p: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 9, name: 'Widget' })}>pick-product</button>
  ),
  AttachmentEditor: () => null,
}));

const {
  complaintDocument, complaintReport, createComplaint, getComplaint,
  listComplaintAttachments, listComplaintsPage, transitionComplaint,
} = vi.hoisted(() => {
  const open: ComplaintRow = {
    id: 1, number: 'RMA-000001', customer: 5, sourceInvoice: null, category: 'DAMAGED',
    description: 'Box crushed', status: 'OPEN', inspectionNotes: '', salesReturn: null,
    salesCreditNote: null, replacementOrder: null, assignedTo: null,
  };
  const inspecting: ComplaintRow = { ...open, id: 2, number: 'RMA-000002', status: 'INSPECTING', sourceInvoice: 77 };
  return {
    complaintDocument: vi.fn(async (id: number, kind: string) => ({ id: 99, existing: false, kind })),
    createComplaint: vi.fn(async () => open),
    complaintReport: vi.fn(async () => ({
      byCategory: [{ category: 'DAMAGED', count: 2 }],
      resolved: 1, resolvedWithDocument: 1, resolvedWithoutDocument: 0, averageResolutionSeconds: 3600,
    })),
    getComplaint: vi.fn(async (id: number) => (id === 2 ? inspecting : open)),
    listComplaintAttachments: vi.fn(async () => []),
    listComplaintsPage: vi.fn(async () => ({ results: [open, inspecting], count: 2, next: null, previous: null })),
    transitionComplaint: vi.fn(async (id: number, payload: Record<string, unknown>) => ({ ...open, id, ...payload })),
  };
});

vi.mock('@/api/growth', () => ({
  createComplaint: (...args: unknown[]) => createComplaint(...args),
  complaintReport: () => complaintReport(),
  complaintDocument: (...args: unknown[]) => complaintDocument(...args),
  deleteComplaintAttachment: vi.fn(),
  getComplaint: (...args: unknown[]) => getComplaint(...args),
  listComplaintAttachments: (...args: unknown[]) => listComplaintAttachments(...args),
  listComplaintsPage: (...args: unknown[]) => listComplaintsPage(...args),
  transitionComplaint: (...args: unknown[]) => transitionComplaint(...args),
  updateComplaint: vi.fn(async () => ({})),
  uploadComplaintAttachment: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  listSalesInvoicesPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
  getSalesInvoice: vi.fn(async () => ({ items: [] })),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/complaints']}>
        <Routes>
          <Route path="/complaints" element={<ComplaintsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ComplaintsPage', () => {
  it('lists complaints, shows the report, and creates a new complaint', async () => {
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText(/RMA-000001 · Damaged goods · Open/)).toBeInTheDocument();
    expect(screen.getByText(/RMA-000002 · Damaged goods · Being inspected/)).toBeInTheDocument();
    expect(screen.getByText(/Resolved: 1/)).toBeInTheDocument();
    expect(screen.getByText(/With a document: 1/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'New complaint' }));
    await user.click(screen.getByRole('button', { name: 'pick-customer' }));
    await user.type(screen.getByLabelText('Description'), 'Screen cracked');
    await user.click(screen.getByRole('button', { name: 'Log complaint' }));

    await waitFor(() => expect(createComplaint).toHaveBeenCalledWith({
      customer: 5, category: 'OTHER', description: 'Screen cracked',
    }));
  });

  it('shows only the legal next transitions for the selected complaint', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/RMA-000001/);
    const detailButtons = screen.getAllByRole('button', { name: 'Detail' });
    await user.click(detailButtons[0]); // RMA-000001, status OPEN

    expect(await screen.findByText('RMA-000001 · Open')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move to Being inspected' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move to Resolved' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move to Rejected' })).not.toBeInTheDocument();

    // Create-document actions are disabled with no source invoice / line selected yet.
    expect(screen.getByRole('button', { name: 'Create return' })).toBeDisabled();
  });

  it('transitions status with the current inspection notes', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/RMA-000002/);
    const detailButtons = screen.getAllByRole('button', { name: 'Detail' });
    await user.click(detailButtons[1]); // RMA-000002, status INSPECTING

    await screen.findByText('RMA-000002 · Being inspected');
    expect(screen.getByRole('button', { name: 'Move to Approved' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move to Rejected' })).toBeInTheDocument();

    await user.type(screen.getByLabelText('Inspection notes'), 'Confirmed damaged');
    await user.click(screen.getByRole('button', { name: 'Move to Approved' }));

    await waitFor(() => expect(transitionComplaint).toHaveBeenCalledWith(2, {
      status: 'APPROVED',
      inspection_notes: 'Confirmed damaged',
    }));
  });

  it('creates a replacement order once a product and quantity are picked', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/RMA-000002/);
    await user.click(screen.getAllByRole('button', { name: 'Detail' })[1]); // RMA-000002, INSPECTING

    const replacementButton = await screen.findByRole('button', { name: 'Create replacement order' });
    expect(replacementButton).toBeDisabled(); // no product picked yet

    await user.click(screen.getByRole('button', { name: 'pick-product' }));
    expect(replacementButton).toBeEnabled();
    await user.click(replacementButton);

    await waitFor(() => expect(complaintDocument).toHaveBeenCalledWith(
      2, 'create-replacement-order', [{ product: 9, quantity: '1', unit_price: '0' }],
    ));
  });
});
