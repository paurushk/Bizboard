import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WarehousesPage } from '@/pages/inventory/WarehousesPage';

const listWarehouses = vi.hoisted(() => vi.fn());
const createWarehouse = vi.hoisted(() => vi.fn());
const updateWarehouse = vi.hoisted(() => vi.fn());
const deleteWarehouse = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  listWarehouses: () => listWarehouses(),
  createWarehouse: (...a: unknown[]) => createWarehouse(...a),
  updateWarehouse: (...a: unknown[]) => updateWarehouse(...a),
  deleteWarehouse: (...a: unknown[]) => deleteWarehouse(...a),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) =>
    children({
      rows: Array.from({ length: rowCount }, (_, i) => ({ index: i, start: i * 52, end: (i + 1) * 52, size: 52, key: i })),
      totalSize: rowCount * 52,
      measureElement: () => undefined,
    }),
}));

const wh = (id: number, name: string, over: Record<string, unknown> = {}) => ({
  id, name, code: name.slice(0, 2).toUpperCase(), isDefault: false, isActive: true, ...over,
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WarehousesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function confirmDialog(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await screen.findByRole('dialog');
  await user.click(within(dialog).getByRole('button', { name: /^(confirm|continue|ok|yes)/i }));
}

describe('WarehousesPage', () => {
  beforeEach(() => {
    for (const fn of [listWarehouses, createWarehouse, updateWarehouse, deleteWarehouse]) fn.mockReset();
    listWarehouses.mockResolvedValue([
      wh(1, 'Main', { isDefault: true }),
      wh(2, 'North'),
      wh(3, 'Old shed', { isActive: false }),
    ]);
  });

  it('lists the godowns in use by default and the switched-off ones on request', async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('North')).toBeTruthy();
    expect(screen.queryByText('Old shed')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Switched off (1)' }));
    expect(await screen.findByText('Old shed')).toBeTruthy();
    expect(screen.queryByText('North')).toBeNull();
  });

  it('offers no switch-off or delete on the default godown', async () => {
    renderPage();
    await screen.findByText('Main');
    const row = screen.getByText('Main').closest('tr') as HTMLElement;
    expect(within(row).queryByRole('button', { name: 'Switch off' })).toBeNull();
    expect(within(row).queryByRole('button', { name: 'Delete' })).toBeNull();
    expect(within(row).getByRole('button', { name: 'Edit' })).toBeTruthy();
  });

  it('renames a godown', async () => {
    updateWarehouse.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText('North')).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog');
    const name = within(dialog).getByLabelText('Name');
    await user.clear(name);
    await user.type(name, 'North yard');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateWarehouse).toHaveBeenCalledWith(2, { name: 'North yard', code: 'NO' }));
  });

  it('makes a godown the default only after confirming', async () => {
    updateWarehouse.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText('North')).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: 'Make default' }));
    await confirmDialog(user);
    await waitFor(() => expect(updateWarehouse).toHaveBeenCalledWith(2, { isDefault: true }));
  });

  it('switches a godown back on', async () => {
    updateWarehouse.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Switched off (1)' }));
    const row = (await screen.findByText('Old shed')).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: 'Switch on' }));
    await confirmDialog(user);
    await waitFor(() => expect(updateWarehouse).toHaveBeenCalledWith(3, { isActive: true }));
  });

  it('shows the server reason when a godown cannot be switched off', async () => {
    updateWarehouse.mockRejectedValue(new Error('Transfer or write off remaining stock before deactivating this godown.'));
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText('North')).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: 'Switch off' }));
    await confirmDialog(user);
    expect(await screen.findByText(/before deactivating this godown/)).toBeTruthy();
  });

  it('asks before deleting and does not delete when the answer is no', async () => {
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText('North')).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: 'Delete' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Delete North\?/)).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(deleteWarehouse).not.toHaveBeenCalled();
  });

  it('adds a godown, filling the code from the name until one is typed', async () => {
    createWarehouse.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Add godown' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Name'), 'South depot');
    expect((within(dialog).getByLabelText('Code') as HTMLInputElement).value.length).toBeGreaterThan(0);
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createWarehouse).toHaveBeenCalledTimes(1));
    expect(createWarehouse.mock.calls[0][0].name).toBe('South depot');
  });
});
