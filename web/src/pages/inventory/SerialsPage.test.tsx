import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { serialActionsFor } from '@/pages/inventory/serialActions';
import { SerialsPage } from '@/pages/inventory/SerialsPage';

const listSerials = vi.hoisted(() => vi.fn());
const transitionSerial = vi.hoisted(() => vi.fn());
const getSerialDocument = vi.hoisted(() => vi.fn());
const navigateMock = vi.hoisted(() => vi.fn());
const auth = vi.hoisted(() => ({ role: 'OWNER' }));

vi.mock('@/api/resources', () => ({
  listSerials: (...args: unknown[]) => listSerials(...args),
  transitionSerial: (...args: unknown[]) => transitionSerial(...args),
  getSerialDocument: (...args: unknown[]) => getSerialDocument(...args),
}));
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 1, role: auth.role } }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) =>
    children({
      rows: Array.from({ length: rowCount }, (_, i) => ({ index: i, start: i * 52, end: (i + 1) * 52, size: 52, key: i })),
      totalSize: rowCount * 52,
      measureElement: () => undefined,
    }),
}));

const row = (id: number, serialNumber: string, status: string) => ({
  id, serialNumber, status, productName: 'Phone', warehouseName: 'Main',
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SerialsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Answers the in-app confirmation (the window.confirm replacement), checking what it says. */
async function answerConfirm(user: ReturnType<typeof userEvent.setup>, ok: boolean, text: string) {
  const dialog = await screen.findByRole('dialog', { name: 'Confirm' });
  expect(dialog.textContent).toContain(text);
  await user.click(within(dialog).getByRole('button', { name: ok ? 'Confirm' : 'Cancel' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Confirm' })).toBeNull());
}

describe('serialActionsFor', () => {
  // These are the transitions SerialNumberViewSet.transition accepts (backend test_inventory_serials_wp02).
  it('only offers moves the server allows', () => {
    expect(serialActionsFor('AVAILABLE').map((a) => a.target)).toEqual(['SCRAPPED']);
    // A sold unit comes back through a sales return, not a button on this list.
    expect(serialActionsFor('SOLD')).toEqual([]);
    expect(serialActionsFor('RETURNED').map((a) => a.target)).toEqual(['SCRAPPED']);
    expect(serialActionsFor('SCRAPPED')).toEqual([]);
  });

  it('never offers a hand-made SOLD', () => {
    for (const status of ['AVAILABLE', 'SOLD', 'RETURNED', 'SCRAPPED']) {
      expect(serialActionsFor(status).some((a) => (a.target as string) === 'SOLD')).toBe(false);
    }
  });
});

describe('SerialsPage', () => {
  beforeEach(() => {
    listSerials.mockReset();
    transitionSerial.mockReset();
    getSerialDocument.mockReset();
    navigateMock.mockReset();
  });

  it('scraps an available serial after naming it in the confirmation', async () => {
    listSerials.mockResolvedValue([row(1, 'SN-1', 'AVAILABLE')]);
    transitionSerial.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Scrap' }));
    await answerConfirm(user, true, 'SN-1');
    await waitFor(() => expect(transitionSerial).toHaveBeenCalledWith(1, { status: 'SCRAPPED' }, { idempotencyKey: expect.any(String) }));
    expect(screen.queryByRole('button', { name: /mark sold/i })).toBeNull();
  });

  it('opens the sale a sold unit went out on, and says so when it cannot be traced', async () => {
    listSerials.mockResolvedValue([row(2, 'SN-2', 'SOLD')]);
    getSerialDocument.mockResolvedValueOnce({ type: 'invoice', id: 9, number: 'INV-9', path: '/sales/invoices/9' });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'View sale' }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/sales/invoices/9'));

    getSerialDocument.mockResolvedValueOnce(null);
    await user.click(screen.getByRole('button', { name: 'View sale' }));
    expect(await screen.findByText('This unit could not be traced to a sale document.')).toBeTruthy();
    expect(navigateMock).toHaveBeenCalledTimes(1);
  });

  it('opens the sales return for the invoice a sold unit went out on', async () => {
    listSerials.mockResolvedValue([row(2, 'SN-2', 'SOLD')]);
    getSerialDocument.mockResolvedValue({ type: 'invoice', id: 55, number: 'INV-55', path: '/sales/invoices/55' });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Create sales return' }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/sales/returns?invoice=55'));
    expect(transitionSerial).not.toHaveBeenCalled();
  });

  it('lets only an owner put a sold unit back without a return, and only with a reason', async () => {
    listSerials.mockResolvedValue([row(2, 'SN-2', 'SOLD')]);
    transitionSerial.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Put back without a return' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Put back in stock' }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await user.type(within(dialog).getByLabelText(/Reason/), 'Credit note raised on paper');
    expect(confirm.disabled).toBe(false);
    await user.click(confirm);
    await waitFor(() =>
      expect(transitionSerial).toHaveBeenCalledWith(
        2,
        { status: 'AVAILABLE', reason: 'Credit note raised on paper', confirmNoDocument: true },
        { idempotencyKey: expect.any(String) },
      ),
    );
  });

  it('offers no manual put-back to anyone but an owner', async () => {
    auth.role = 'MANAGER';
    listSerials.mockResolvedValue([row(2, 'SN-2', 'SOLD')]);
    renderPage();
    await screen.findByText('SN-2');
    expect(screen.getByRole('button', { name: 'Create sales return' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Put back without a return' })).toBeNull();
    auth.role = 'OWNER';
  });

  it('shows no action on a scrapped serial', async () => {
    listSerials.mockResolvedValue([row(3, 'SN-3', 'SCRAPPED')]);
    renderPage();
    await screen.findByText('SN-3');
    expect(screen.queryByRole('button', { name: 'Scrap' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Create sales return' })).toBeNull();
  });

  it('searches by part of a serial number', async () => {
    listSerials.mockResolvedValue([row(1, 'ABC-1', 'AVAILABLE')]);
    const user = userEvent.setup();
    renderPage();
    await user.type(await screen.findByLabelText('Search serial number'), 'abc');
    await waitFor(() => expect(listSerials).toHaveBeenLastCalledWith({ q: 'abc' }));
  });
});
