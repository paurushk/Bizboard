import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PlanningTable, type PlanningSelection } from './PlanningTable';
import type { PlanSummary } from './planningTypes';

const api = vi.hoisted(() => ({ listRouteCandidates: vi.fn() }));
const auth = vi.hoisted(() => ({ role: 'OWNER' }));
vi.mock('@/api/resources', () => ({ ...api }));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, role: auth.role, companyId: 1 } }) }));

const summary = (over: Partial<PlanSummary> & { order: number }): PlanSummary => ({
  number: `SO-${over.order}`,
  status: 'CONFIRMED',
  orderDate: '2026-10-10',
  expectedDelivery: '2026-10-15',
  customer: { id: over.order, name: `Customer ${over.order}`, phone: '9876543210', pincode: '560001', hasLocation: true, status: 'ACTIVE' },
  deliveryAddress: '12 Market Road',
  lines: [{ product: 1, name: 'Widget', quantity: '2', unit: 'PCS', available: '10', short: '0' }],
  lineCount: 1,
  totalQuantity: '2',
  grandTotal: '200.00',
  bill: { billStatus: 'order_only', paymentTermsDays: 0, onCredit: false, amountToCollect: '200.00', invoices: [] },
  risks: [],
  ready: true,
  hasWarnings: false,
  ...over,
});

const risk = (code: string, level: 'block' | 'warn' | 'info', message: string, override = 'any') => ({ code, level, message, override: override as 'any' });

function page(results: PlanSummary[], count = results.length) {
  api.listRouteCandidates.mockResolvedValue({ count, page: 1, pageSize: 25, results });
}

function mount(props: Partial<React.ComponentProps<typeof PlanningTable>> = {}) {
  const onChange = vi.fn<(s: PlanningSelection) => void>();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PlanningTable open onChange={onChange} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onChange;
}

const last = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1][0] as PlanningSelection;

beforeEach(() => {
  auth.role = 'OWNER';
  api.listRouteCandidates.mockReset();
});

describe('Planning table — what a dispatcher sees (PL-20)', () => {
  it('shows customer, area, date, lines, value, what to collect, stock, bill and risks in words', async () => {
    page([
      summary({
        order: 1,
        risks: [risk('no_phone', 'warn', 'No phone number for the customer.'), risk('late', 'info', '3 day(s) past the expected delivery date.')],
        lines: [{ product: 1, name: 'Widget', quantity: '5', unit: 'PCS', available: '2', short: '3' }],
      }),
    ]);
    mount();
    const r = await screen.findByTestId('plan-row-1');
    expect(within(r).getByText('SO-1')).toBeInTheDocument();
    expect(within(r).getByText('Customer 1')).toBeInTheDocument();
    expect(within(r).getByText(/560001 · 9876543210/)).toBeInTheDocument();
    expect(within(r).getByText('2026-10-15')).toBeInTheDocument();
    expect(within(r).getByText('1 / 2')).toBeInTheDocument();
    expect(within(r).getAllByText(/200\.00/).length).toBeGreaterThanOrEqual(2); // value and to collect
    expect(within(r).getByText('Short')).toBeInTheDocument();
    expect(within(r).getByText('Order only, no bill yet')).toBeInTheDocument();
    expect(within(r).getByText('No phone')).toBeInTheDocument();
    expect(within(r).getByText('Late')).toBeInTheDocument();
  });

  it('a credit sale shows Credit instead of an amount to collect', async () => {
    page([summary({ order: 1, bill: { billStatus: 'order_only', paymentTermsDays: 30, onCredit: true, amountToCollect: '0.00', invoices: [] } })]);
    mount();
    expect(within(await screen.findByTestId('plan-row-1')).getByText('Credit')).toBeInTheDocument();
  });

  it('marks a customer with no map location', async () => {
    page([summary({ order: 1, customer: { id: 1, name: 'Far Away', phone: '1', pincode: '560001', hasLocation: false } })]);
    mount();
    expect(within(await screen.findByTestId('plan-row-1')).getByText(/no map location/)).toBeInTheDocument();
  });

  it('asks the server for the first page and shows an empty state', async () => {
    page([]);
    mount();
    expect(await screen.findByText(/No confirmed or shipped orders are waiting/)).toBeInTheDocument();
    expect(api.listRouteCandidates.mock.calls[0][0]).toMatchObject({ page: 1, page_size: 25 });
  });

  it('leaves out orders already on the route being edited', async () => {
    page([summary({ order: 1 }), summary({ order: 2 })]);
    mount({ excludeIds: [1] });
    await screen.findByTestId('plan-row-2');
    expect(screen.queryByTestId('plan-row-1')).toBeNull();
  });
});

describe('Blocked rows cannot be ticked, and say why (PL-22)', () => {
  it('an order on another route is disabled with its reason shown in words', async () => {
    page([summary({ order: 1, ready: false, risks: [risk('already_on_route', 'block', 'Already on route RT-7. Remove it from there first.', 'none')] })]);
    mount();
    const r = await screen.findByTestId('plan-row-1');
    expect((within(r).getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
    expect(within(r).getByText(/Cannot go on a route: Already on route RT-7/)).toBeInTheDocument();
  });

  it.each(['SALES_STAFF', 'OWNER'])('a draft cannot be ticked, even by %s', async (role) => {
    auth.role = role;
    page([summary({ order: 1, status: 'DRAFT', ready: false, risks: [risk('not_ready', 'block', 'Not confirmed yet.', 'none')] })]);
    mount();
    const r = await screen.findByTestId('plan-row-1');
    expect((within(r).getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  });

  it('only the owner is offered unconfirmed orders', async () => {
    page([]);
    auth.role = 'SALES_STAFF';
    mount();
    await screen.findByText(/No confirmed or shipped orders/);
    expect(screen.queryByLabelText('Also show unconfirmed orders')).toBeNull();
  });

  it('the owner can switch on unconfirmed orders and orders already on a route', async () => {
    page([]);
    mount();
    const u = userEvent.setup();
    await u.click(await screen.findByLabelText('Also show unconfirmed orders'));
    await u.click(screen.getByLabelText('Also show orders already on a route'));
    await waitFor(() =>
      expect(api.listRouteCandidates.mock.calls.some((c) => c[0].include_drafts === true && c[0].show_unavailable === true)).toBe(true),
    );
  });
});

describe('Warnings need a reason before the row is ticked (PL-22, PL-06)', () => {
  const warned = () =>
    summary({
      order: 1,
      hasWarnings: true,
      risks: [risk('no_phone', 'warn', 'No phone number for the customer.'), risk('stock_short', 'warn', 'Not enough stock for: Widget.')],
    });

  it('shows what is being accepted, requires a reason, and sends it for every risk of that order', async () => {
    page([warned()]);
    const onChange = mount();
    const u = userEvent.setup();
    await u.click(within(await screen.findByTestId('plan-row-1')).getByRole('checkbox'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('No phone number for the customer.')).toBeInTheDocument();
    expect(within(dialog).getByText('Not enough stock for: Widget.')).toBeInTheDocument();
    const accept = within(dialog).getByRole('button', { name: 'Accept and add' }) as HTMLButtonElement;
    expect(accept.disabled).toBe(true);
    await u.type(within(dialog).getByLabelText(/Reason/), 'ab');
    expect(accept.disabled).toBe(true); // too short
    await u.type(within(dialog).getByLabelText(/Reason/), 'c');
    expect(accept.disabled).toBe(false);
    await u.click(accept);
    await waitFor(() => expect(last(onChange).orderIds).toEqual([1]));
    expect(last(onChange).acknowledgements).toEqual([
      { order: 1, code: 'no_phone', reason: 'abc' },
      { order: 1, code: 'stock_short', reason: 'abc' },
    ]);
  });

  it('cancelling the dialog leaves the row unticked', async () => {
    page([warned()]);
    const onChange = mount();
    const u = userEvent.setup();
    await u.click(within(await screen.findByTestId('plan-row-1')).getByRole('checkbox'));
    await u.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect((within(screen.getByTestId('plan-row-1')).getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('unticking removes the acceptance', async () => {
    page([warned()]);
    const onChange = mount();
    const u = userEvent.setup();
    const box = within(await screen.findByTestId('plan-row-1')).getByRole('checkbox');
    await u.click(box);
    await u.type(within(await screen.findByRole('dialog')).getByLabelText(/Reason/), 'Driver knows');
    await u.click(screen.getByRole('button', { name: 'Accept and add' }));
    await waitFor(() => expect(last(onChange).orderIds).toEqual([1]));
    await u.click(box);
    await waitFor(() => expect(last(onChange)).toEqual({ orderIds: [], acknowledgements: [] }));
  });

  it('a risk this role cannot accept blocks the tick even though it is only a warning', async () => {
    auth.role = 'SALES_STAFF';
    page([summary({ order: 1, risks: [risk('over_credit_limit', 'warn', 'Customer is over their credit limit.', 'manager')] })]);
    mount();
    const r = await screen.findByTestId('plan-row-1');
    expect((within(r).getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
    expect(within(r).getByText(/Customer is over their credit limit/)).toBeInTheDocument();
  });
});

describe('Ticking, totals and selecting the easy ones (PL-20, PL-25)', () => {
  it('a clean row ticks straight away and the totals follow', async () => {
    page([summary({ order: 1 }), summary({ order: 2, grandTotal: '300.00', totalQuantity: '3', bill: { billStatus: 'order_only', paymentTermsDays: 0, onCredit: false, amountToCollect: '300.00', invoices: [] } })]);
    const onChange = mount();
    const u = userEvent.setup();
    await u.click(within(await screen.findByTestId('plan-row-1')).getByRole('checkbox'));
    await u.click(within(screen.getByTestId('plan-row-2')).getByRole('checkbox'));
    expect(last(onChange)).toEqual({ orderIds: [1, 2], acknowledgements: [] });
    const totals = screen.getByTestId('plan-totals').textContent ?? '';
    expect(totals).toMatch(/2 selected/);
    expect(totals).toMatch(/qty 5/);
    expect(totals).toMatch(/500\.00/);
  });

  it('“Select the N that can go” ticks only the rows that need nothing accepted', async () => {
    page([
      summary({ order: 1 }),
      summary({ order: 2, risks: [risk('no_phone', 'warn', 'No phone.')] }),
      summary({ order: 3, ready: false, risks: [risk('already_on_route', 'block', 'On route.', 'none')] }),
      summary({ order: 4, risks: [risk('late', 'info', 'Late.')] }),
    ]);
    const onChange = mount();
    const u = userEvent.setup();
    await screen.findByTestId('plan-row-1');
    await u.click(screen.getByRole('button', { name: 'Select the 2 that can go' }));
    expect(last(onChange).orderIds).toEqual([1, 4]);
    expect(last(onChange).acknowledgements).toEqual([]);
  });

  it('picked orders only: the list is limited to the ids it was given', async () => {
    page([]);
    mount({ onlyIds: [4, 9] });
    await waitFor(() => expect(api.listRouteCandidates).toHaveBeenCalled());
    expect(api.listRouteCandidates.mock.calls[0][0].ids).toBe('4,9');
  });
});

describe('Filters, areas and paging', () => {
  it('sends search, pincode and dates to the server', async () => {
    page([]);
    mount();
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText('Search'), 'Ravi');
    await u.type(screen.getByLabelText('Pincode'), '5600');
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-10-14' } });
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-20' } });
    await waitFor(() =>
      expect(
        api.listRouteCandidates.mock.calls.some(
          (c) => c[0].q === 'Ravi' && c[0].pincode === '5600' && c[0].date_from === '2026-10-14' && c[0].date_to === '2026-10-20',
        ),
      ).toBe(true),
    );
  });

  it('groups by area, in pincode order, with the count', async () => {
    page([
      summary({ order: 1, customer: { id: 1, name: 'A', pincode: '560090', phone: '1' } }),
      summary({ order: 2, customer: { id: 2, name: 'B', pincode: '560010', phone: '1' } }),
      summary({ order: 3, customer: { id: 3, name: 'C', pincode: '560010', phone: '1' } }),
    ]);
    mount();
    await screen.findByTestId('plan-row-1');
    await userEvent.setup().click(screen.getByLabelText('Group by area'));
    const headers = screen.getAllByText(/^Area /).map((el) => el.textContent);
    expect(headers).toEqual(['Area 560010: 2 order(s)', 'Area 560090: 1 order(s)']);
  });

  it('pages through a long list', async () => {
    api.listRouteCandidates.mockResolvedValue({ count: 60, page: 1, pageSize: 25, results: [summary({ order: 1 })] });
    mount();
    const u = userEvent.setup();
    await screen.findByTestId('plan-row-1');
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(api.listRouteCandidates.mock.calls.some((c) => c[0].page === 2)).toBe(true));
  });
});

describe('The order drawer (PL-21)', () => {
  const full = () =>
    summary({
      order: 1,
      lines: [
        { product: 1, name: 'Widget', quantity: '5', unit: 'PCS', available: '2', short: '3' },
        { product: 2, name: 'Bolt', quantity: '10', unit: 'KG', available: '40', short: '0' },
      ],
      bill: {
        billStatus: 'invoiced', paymentTermsDays: 0, onCredit: false, amountToCollect: '118.00',
        invoices: [{ id: 9, number: 'INV-9', status: 'COMPLETED', grandTotal: '118.00', balance: '118.00' }],
      },
      risks: [risk('stock_short', 'warn', 'Not enough stock for: Widget.'), risk('over_credit_limit', 'warn', 'Customer is over their credit limit by ₹100.00.', 'manager')],
      money: { outstanding: '5000.00', overdue: '1200.00', creditLimit: '4000.00', exposure: '5100.00', collectionStatus: 'overdue' },
    });

  it('shows the customer, items with stock, the bill, the money position and each risk with who can accept it', async () => {
    page([full()]);
    mount();
    await userEvent.setup().click(within(await screen.findByTestId('plan-row-1')).getByRole('button', { name: 'Details' }));
    const drawer = await screen.findByTestId('order-drawer');
    expect(within(drawer).getByText('12 Market Road')).toBeInTheDocument();
    expect(within(drawer).getByText('Widget')).toBeInTheDocument();
    expect(within(drawer).getByText(/short by 3/)).toBeInTheDocument();
    expect(within(drawer).getByRole('link', { name: /INV-9/ }).getAttribute('href')).toBe('/sales/history/9');
    expect(within(drawer).getByText(/Customer’s account/)).toBeInTheDocument();
    expect(within(drawer).getByText(/5,000\.00|5000\.00/)).toBeInTheDocument();
    expect(within(drawer).getByText('Anyone planning the route can accept this.')).toBeInTheDocument();
    expect(within(drawer).getByText('A manager or the owner can accept this.')).toBeInTheDocument();
  });

  it('leaves the money section out when the server did not send it', async () => {
    const { money: _money, ...rest } = full();
    void _money;
    page([rest as PlanSummary]);
    mount();
    await userEvent.setup().click(within(await screen.findByTestId('plan-row-1')).getByRole('button', { name: 'Details' }));
    const drawer = await screen.findByTestId('order-drawer');
    expect(within(drawer).queryByText(/Customer’s account/)).toBeNull();
  });

  it('closing it keeps the selection', async () => {
    page([summary({ order: 1 })]);
    const onChange = mount();
    const u = userEvent.setup();
    const r = await screen.findByTestId('plan-row-1');
    await u.click(within(r).getByRole('checkbox'));
    await u.click(within(r).getByRole('button', { name: 'Details' }));
    await u.click(await screen.findByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByTestId('order-drawer')).toBeNull());
    expect((within(screen.getByTestId('plan-row-1')).getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
    expect(last(onChange).orderIds).toEqual([1]);
  });
});
