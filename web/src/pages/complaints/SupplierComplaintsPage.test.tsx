import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SupplierComplaintsPage } from '@/pages/complaints/SupplierComplaintsPage';

vi.mock('@/config/features', () => ({
  isComplaintsEnabled: () => true,
}));

vi.mock('@/pages/growth/widgets', () => ({
  SupplierField: ({ onChange }: { onChange: (s: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 4, name: 'Mill' })}>pick-supplier</button>
  ),
  AttachmentEditor: () => null,
}));

const { createSupplierComplaint, createSupplierDebitNote, transitionSupplierComplaint } = vi.hoisted(() => ({
  createSupplierComplaint: vi.fn(async () => ({ id: 1, number: 'SCN-000001', status: 'OPEN' })),
  createSupplierDebitNote: vi.fn(async () => ({ id: 4, existing: false })),
  transitionSupplierComplaint: vi.fn(async () => ({ id: 2, status: 'REJECTED' })),
}));

const { listSupplierComplaintsPage, getSupplierComplaint } = vi.hoisted(() => ({
  listSupplierComplaintsPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
  getSupplierComplaint: vi.fn(async () => ({
    id: 2, number: 'SCN-000002', status: 'INSPECTING', category: 'DAMAGED', supplier: 4,
    description: 'Torn bags', sourceInvoice: 8, inspectionNotes: '',
  })),
}));

vi.mock('@/api/legacy/purchases', () => ({
  listPurchasesPage: vi.fn(async () => ({ results: [{ id: 8, number: 'PINV-1' }], count: 1, next: null, previous: null })),
  getPurchase: vi.fn(async () => ({ id: 8, items: [] })),
}));

vi.mock('@/api/growth', () => ({
  createSupplierComplaint: (...args: unknown[]) => createSupplierComplaint(...args),
  listSupplierComplaintsPage: (...args: unknown[]) => listSupplierComplaintsPage(...args),
  supplierComplaintReport: vi.fn(async () => ({
    byCategory: [], resolved: 1, resolvedWithDocument: 0, resolvedWithoutDocument: 1, averageResolutionSeconds: null,
  })),
  getSupplierComplaint: (...args: unknown[]) => getSupplierComplaint(...args),
  listSupplierComplaintAttachments: vi.fn(async () => []),
  transitionSupplierComplaint: (...args: unknown[]) => transitionSupplierComplaint(...args),
  updateSupplierComplaint: vi.fn(),
  createSupplierDebitNote: (...args: unknown[]) => createSupplierDebitNote(...args),
  uploadSupplierComplaintAttachment: vi.fn(),
  deleteSupplierComplaintAttachment: vi.fn(),
}));

describe('SupplierComplaintsPage', () => {
  it('creates a complaint for the chosen supplier', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <SupplierComplaintsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Supplier complaints')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'pick-supplier' }));
    await user.type(screen.getByLabelText('Description'), 'Torn bags');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(createSupplierComplaint).toHaveBeenCalledWith({
      supplier: 4, category: 'OTHER', description: 'Torn bags',
    });
  });

  it('rejects from inspection and keeps a debit note disabled until a bill line is chosen', async () => {
    listSupplierComplaintsPage.mockResolvedValueOnce({
      results: [{ id: 2, number: 'SCN-000002', category: 'DAMAGED', status: 'INSPECTING' }],
      count: 1, next: null, previous: null,
    });
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <SupplierComplaintsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Resolved: 1/)).toBeInTheDocument();
    expect(screen.getByText(/Without a document: 1/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Detail' }));
    expect(await screen.findByRole('button', { name: 'Move to REJECTED' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move to APPROVED' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move to RESOLVED' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create debit note' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Move to REJECTED' }));
    expect(transitionSupplierComplaint).toHaveBeenCalledWith(2, {
      status: 'REJECTED', inspection_notes: '',
    });
    expect(createSupplierDebitNote).not.toHaveBeenCalled();
  });
});
