import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ContractsPage } from '@/pages/contracts/ContractsPage';
import type { ContractRow } from '@/api/growth';

vi.mock('@/config/features', () => ({
  isContractsEnabled: () => true,
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'OWNER' } }),
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
  ProductField: ({ onChange }: { onChange: (p: { id: number; name: string } | null) => void }) => (
    <button onClick={() => {
      const id = productPick.ids[productPick.cursor] ?? productPick.cursor + 1;
      productPick.cursor += 1;
      onChange({ id, name: `Widget ${id}` });
    }}>pick-product</button>
  ),
  AttachmentEditor: () => null,
  localDateInput: () => '2026-09-01',
}));

const { productPick } = vi.hoisted(() => ({ productPick: { ids: [1, 2, 2], cursor: 0 } }));

const {
  contractReport, contractTimeline, createContract, listContractAttachments, listContractsPage, logServiceEvent, updateContract,
} = vi.hoisted(() => {
  const active: ContractRow = {
    id: 1, number: 'CON-000001', customer: 5, product: null, contractType: 'AMC', status: 'ACTIVE',
    startDate: '2026-01-01', endDate: '2027-01-01', renewalReminderDays: 30, value: '5000.00', notes: 'AMC deal',
  };
  const cancelled: ContractRow = { ...active, id: 2, number: 'CON-000002', status: 'CANCELLED' };
  return {
    contractReport: vi.fn(async () => [{ status: 'ACTIVE', contractType: 'AMC', value: '5000.00' }]),
    contractTimeline: vi.fn(async () => ({ contract: active, events: [{ id: 1, ticket: null, notes: 'Installed', occurredAt: '2026-02-01T00:00:00Z' }] })),
    createContract: vi.fn(async () => active),
    listContractAttachments: vi.fn(async () => []),
    listContractsPage: vi.fn(async () => ({ results: [active, cancelled], count: 2, next: null, previous: null })),
    logServiceEvent: vi.fn(async () => ({ id: 2, ticket: null, notes: 'Visit', occurredAt: '2026-03-01T00:00:00Z' })),
    updateContract: vi.fn(async (id: number, payload: Record<string, unknown>) => ({ ...active, id, ...payload })),
  };
});

vi.mock('@/api/growth', () => ({
  contractReport: () => contractReport(),
  contractTimeline: (...args: unknown[]) => contractTimeline(...args),
  createContract: (...args: unknown[]) => createContract(...args),
  createContractSchedule: vi.fn(),
  deleteContractAttachment: vi.fn(),
  listContractAttachments: (...args: unknown[]) => listContractAttachments(...args),
  listContractsPage: (...args: unknown[]) => listContractsPage(...args),
  logServiceEvent: (...args: unknown[]) => logServiceEvent(...args),
  updateContract: (...args: unknown[]) => updateContract(...args),
  uploadContractAttachment: vi.fn(),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/contracts']}>
        <Routes>
          <Route path="/contracts" element={<ContractsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ContractsPage', () => {
  it('lists contracts and creates one with the reminder days coerced to a number', async () => {
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText(/CON-000001 · AMC · ACTIVE/)).toBeInTheDocument();
    expect(screen.getByText('The value is copied onto one recurring invoice.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Create recurring invoice' }).length).toBeGreaterThan(0);
    expect(screen.getByText(/CON-000002 · AMC · CANCELLED/)).toBeInTheDocument();
    expect(screen.getByText('ACTIVE · AMC · 5000.00')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'pick-customer' }));
    await user.type(screen.getByLabelText('End date'), '2027-06-01');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createContract).toHaveBeenCalledWith(expect.objectContaining({
      customer: 5,
      contract_type: 'WARRANTY',
      end_date: '2027-06-01',
      renewal_reminder_days: 30,
      product: null,
      products: [],
    })));
  });

  it('sends every added product and keeps the first as the legacy product', async () => {
    productPick.cursor = 0;
    productPick.ids = [1, 2, 2];
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/CON-000001/);
    await user.click(screen.getByRole('button', { name: 'pick-product' }));
    await user.click(screen.getByRole('button', { name: 'Add line' }));
    await user.click(screen.getByRole('button', { name: 'pick-product' }));
    await user.click(screen.getByRole('button', { name: 'Add line' }));
    await user.click(screen.getByRole('button', { name: 'pick-product' }));
    await user.click(screen.getByRole('button', { name: 'Add line' }));
    expect(screen.getByText('Widget 1, Widget 2')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'pick-customer' }));
    await user.type(screen.getByLabelText('End date'), '2027-06-01');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(createContract).toHaveBeenCalledWith(expect.objectContaining({
      product: 1,
      products: [1, 2],
    })));
  });

  it('offers Cancel for an active contract and Un-cancel for a cancelled one', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/CON-000001/);
    const detailButtons = screen.getAllByRole('button', { name: 'Detail' });

    await user.click(detailButtons[0]); // active
    expect(await screen.findByText('CON-000001 · ACTIVE')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(updateContract).toHaveBeenCalledWith(1, { status: 'CANCELLED' }));

    await user.click(detailButtons[1]); // cancelled
    expect(await screen.findByText('CON-000002 · CANCELLED')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Un-cancel' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Un-cancel' }));
    await waitFor(() => expect(updateContract).toHaveBeenCalledWith(2, { status: 'ACTIVE' }));
  });

  it('logs a service event against a linked ticket and shows the timeline', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/CON-000001/);
    await user.click(screen.getAllByRole('button', { name: 'Detail' })[0]);
    expect(await screen.findByText(/Installed/)).toBeInTheDocument();

    // "Notes" also labels the top create-form field; the detail's own
    // service-event notes field is the second one in DOM order.
    const notesFields = screen.getAllByLabelText('Notes');
    await user.type(notesFields[notesFields.length - 1], 'Replaced filter');
    await user.type(screen.getByLabelText('Ticket id'), '9');
    await user.click(screen.getByRole('button', { name: 'Log service' }));

    await waitFor(() => expect(logServiceEvent).toHaveBeenCalledWith(1, { notes: 'Replaced filter', ticket: 9 }));
  });
});
