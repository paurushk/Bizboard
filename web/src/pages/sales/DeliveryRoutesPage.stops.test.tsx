import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DeliveryRoutesPage } from '@/pages/sales/DeliveryRoutesPage';

const api = vi.hoisted(() => ({
  getDeliveryRoute: vi.fn(),
  listDeliveryRoutesPage: vi.fn(),
  listSalesOrdersPage: vi.fn(),
  listRouteCandidates: vi.fn(),
  getDeliveryRoutePreflight: vi.fn(),
  setDeliveryRouteStopStatus: vi.fn(),
  completeDeliveryRoute: vi.fn(),
  cancelDeliveryRoute: vi.fn(),
  verifyDeliveryRouteHandover: vi.fn(),
  linkDeliveryRouteReceipt: vi.fn(),
  listReceiptsPage: vi.fn(),
  addOrdersToDeliveryRoute: vi.fn(),
  updateDeliveryRoute: vi.fn(),
  startDeliveryRoute: vi.fn(),
  removeDeliveryRouteStop: vi.fn(),
}));
const user = vi.hoisted(() => ({ value: { id: 1, role: 'OWNER', companyId: 1, canCreateSales: true } as Record<string, unknown> }));

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: user.value }) }));
vi.mock('@/api/resources', () => ({
  ...api,
  createDeliveryRoute: vi.fn(),
  downloadDeliveryRouteManifest: vi.fn(),
  searchSalespeople: async () => [{ id: 7, name: 'Ganesh Rao', code: 'E7' }],
}));
vi.mock('@/lib/native', () => ({ capturePodPhoto: async () => null }));
vi.mock('@/offline/photoOutbox', () => ({ queuePodPhoto: vi.fn() }));

function wrap(path: string, ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/sales/delivery-routes" element={ui} />
          <Route path="/sales/delivery-routes/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const stop = (over: Record<string, unknown> = {}) => ({
  id: 9,
  salesOrder: 1,
  orderNumber: 'SO-1',
  customerName: 'Ravi Stores',
  customer: 31,
  customerPhone: '9876543210',
  deliveryAddress: '12 Market Road',
  status: 'PENDING',
  sequence: 1,
  bill: {
    orderTotal: '500.00', paymentTermsDays: 0, billStatus: 'order_only', invoices: [],
    amountToCollect: '500.00', onCredit: false,
  },
  ...over,
});

const route = (over: Record<string, unknown> = {}) => ({
  id: 4,
  number: 'RT-4',
  routeDate: '2026-10-14',
  vehicleNumber: 'KA01AB1234',
  driverName: 'Asha',
  status: 'IN_TRANSIT',
  rollup: null,
  stops: [stop()],
  warnings: [],
  progress: { stopsTotal: 1, pending: 1, delivered: 0, failed: 0, collected: '0.00', needsAttention: [] },
  cashHandover: null,
  ...over,
});

beforeEach(() => {
  user.value = { id: 1, role: 'OWNER', companyId: 1, canCreateSales: true };
  Object.values(api).forEach((fn) => fn.mockReset());
  api.setDeliveryRouteStopStatus.mockResolvedValue({});
  api.listDeliveryRoutesPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
  api.listSalesOrdersPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
});

describe('Stop card — one place to record what happened (RT-20, OG-10)', () => {
  it('shows who, where, the bill and what to collect', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText('Ravi Stores')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '9876543210' }).getAttribute('href')).toBe('tel:9876543210');
    expect(screen.getByText('12 Market Road')).toBeInTheDocument();
    expect(screen.getByText(/Order only, no bill yet/)).toBeInTheDocument();
    expect(screen.getByText(/To collect/)).toBeInTheDocument();
    expect(screen.getAllByText(/500\.00/, { selector: 'b' })).toHaveLength(2); // order total and to collect
  });

  it('warns when a stop has no phone or no address', async () => {
    api.getDeliveryRoute.mockResolvedValue(route({ stops: [stop({ customerPhone: '', deliveryAddress: '' })] }));
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText('No phone number on file')).toBeInTheDocument();
    expect(screen.getByText(/No delivery address/)).toBeInTheDocument();
  });

  it('a credit sale says nothing is collected at the door', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({ stops: [stop({ bill: { orderTotal: '500.00', paymentTermsDays: 30, billStatus: 'invoiced', invoices: [], amountToCollect: '0.00', onCredit: true } })] }),
    );
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText(/On credit: 30 days/)).toBeInTheDocument();
    expect(screen.queryByText(/To collect/)).toBeNull();
  });

  it('will not send a delivery without who received it, and says so', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    fireEvent.click(screen.getByRole('button', { name: 'Record outcome' }));
    expect(await screen.findByText('Enter who received the goods.')).toBeInTheDocument();
    expect(api.setDeliveryRouteStopStatus).not.toHaveBeenCalled();
  });

  it('UPI needs its reference, and amounts cannot be negative', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    await u.type(screen.getByLabelText(/Received by/), 'Asha');
    await u.type(screen.getByLabelText('UPI collected'), '200');
    await u.click(screen.getByRole('button', { name: 'Record outcome' }));
    expect(await screen.findByText('Enter the UPI reference for the UPI amount.')).toBeInTheDocument();
    await u.clear(screen.getByLabelText('UPI collected'));
    await u.type(screen.getByLabelText('UPI collected'), '-5');
    await u.click(screen.getByRole('button', { name: 'Record outcome' }));
    expect(await screen.findByText('Amounts cannot be negative.')).toBeInTheDocument();
    expect(api.setDeliveryRouteStopStatus).not.toHaveBeenCalled();
  });

  it('records a delivery from the office with the amounts, and asks for no customer code', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    expect(screen.queryByLabelText('Delivery OTP')).toBeNull();
    await u.type(screen.getByLabelText(/Received by/), 'Asha');
    await u.type(screen.getByLabelText('Cash collected'), '300');
    await u.type(screen.getByLabelText('UPI collected'), '200');
    await u.type(screen.getByLabelText(/UPI reference/), 'UPI-77');
    await u.click(screen.getByRole('button', { name: 'Record outcome' }));
    await waitFor(() => expect(api.setDeliveryRouteStopStatus).toHaveBeenCalledTimes(1));
    const [routeId, stopId, status, extra] = api.setDeliveryRouteStopStatus.mock.calls[0];
    expect([routeId, stopId, status]).toEqual([4, 9, 'DELIVERED']);
    expect(extra).toMatchObject({
      completionSource: 'OFFICE', receivedByName: 'Asha', collectedCash: '300', collectedUpi: '200', upiReference: 'UPI-77',
    });
    expect(extra.otp).toBeUndefined();
  });

  it('a customer-given code is asked for only when that box is ticked', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    await u.click(screen.getByLabelText(/delivery code/));
    expect(screen.getByLabelText('Delivery OTP')).toBeInTheDocument();
  });

  it('changing a recorded outcome asks for a reason first', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({ stops: [stop({ status: 'DELIVERED', receivedByName: 'Asha', completionSource: 'OFFICE' })] }),
    );
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText(/recorded by office/)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Change outcome' }));
    await u.click(screen.getByRole('button', { name: 'Save the change' }));
    expect(await screen.findByText('Give a reason to change an outcome that was already recorded.')).toBeInTheDocument();
    expect(api.setDeliveryRouteStopStatus).not.toHaveBeenCalled();
  });

  it('a stop that did not deliver on an invoiced order names the invoice', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({ stops: [stop({ status: 'FAILED', activeInvoice: { id: 77, number: 'INV-0077' } })] }),
    );
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText(/Invoice INV-0077 is still active/)).toBeInTheDocument();
  });

  it('big enough to tap: the main controls are at least 44 px tall', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    const record = screen.getByRole('button', { name: 'Record outcome' });
    expect(getComputedStyle(record).minHeight).toBe('44px');
    expect(getComputedStyle(screen.getByRole('link', { name: '9876543210' })).minHeight).toBe('44px');
  });
});

describe('Goods that come back (OG-32, OG-30)', () => {
  const shipped = (over: Record<string, unknown> = {}) =>
    route({
      stops: [stop({ returnableLines: [{ product: 5, productName: 'Widget', quantity: '10.000' }], ...over })],
    });

  it('a failed delivery offers the quantities that came back, all of it by default, and sends them', async () => {
    api.getDeliveryRoute.mockResolvedValue(shipped());
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    await u.click(screen.getByLabelText('Outcome'));
    await u.click(await screen.findByRole('option', { name: /Refused by the customer/ }));
    const field = await screen.findByLabelText(/Widget \(up to 10\)/);
    expect((field as HTMLInputElement).value).toBe('10');
    await u.clear(field);
    await u.type(field, '3');
    await u.click(screen.getByRole('button', { name: 'Record outcome' }));
    await waitFor(() => expect(api.setDeliveryRouteStopStatus).toHaveBeenCalledTimes(1));
    const [, , status, extra] = api.setDeliveryRouteStopStatus.mock.calls[0];
    expect(status).toBe('REJECTED');
    expect(extra.returnedLines).toEqual([{ product: 5, quantity: '3' }]);
  });

  it('more than went out is caught before anything is sent', async () => {
    api.getDeliveryRoute.mockResolvedValue(shipped());
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    await u.click(screen.getByLabelText('Outcome'));
    await u.click(await screen.findByRole('option', { name: /Not delivered/ }));
    const field = await screen.findByLabelText(/Widget/);
    await u.clear(field);
    await u.type(field, '11');
    await u.click(screen.getByRole('button', { name: 'Record outcome' }));
    expect(await screen.findByText('More came back than went out on this order.')).toBeInTheDocument();
    expect(api.setDeliveryRouteStopStatus).not.toHaveBeenCalled();
  });

  it('a delivered stop asks about returns only when some of it came back', async () => {
    api.getDeliveryRoute.mockResolvedValue(shipped());
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    expect(screen.queryByLabelText(/Widget/)).toBeNull();
    await u.type(screen.getByLabelText(/Received by/), 'Asha');
    await u.click(screen.getByLabelText('Some of it came back'));
    await u.type(await screen.findByLabelText(/Widget/), '2');
    await u.click(screen.getByRole('button', { name: 'Record outcome' }));
    await waitFor(() => expect(api.setDeliveryRouteStopStatus).toHaveBeenCalledTimes(1));
    expect(api.setDeliveryRouteStopStatus.mock.calls[0][3].returnedLines).toEqual([{ product: 5, quantity: '2' }]);
  });

  it('a plain delivery sends no returned lines', async () => {
    api.getDeliveryRoute.mockResolvedValue(shipped());
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    await u.type(screen.getByLabelText(/Received by/), 'Asha');
    await u.click(screen.getByRole('button', { name: 'Record outcome' }));
    await waitFor(() => expect(api.setDeliveryRouteStopStatus).toHaveBeenCalledTimes(1));
    expect(api.setDeliveryRouteStopStatus.mock.calls[0][3].returnedLines).toBeUndefined();
  });

  it('a delivered stop with no bill yet points to the order so it can be invoiced', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({
        stops: [stop({ status: 'DELIVERED', receivedByName: 'Asha', bill: { orderTotal: '500.00', billStatus: 'challan', invoices: [], amountToCollect: '500.00', onCredit: false } })],
      }),
    );
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText(/Delivered, but no invoice has been made for it yet/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the order' }).getAttribute('href')).toBe('/sales/orders/1');
  });

  it('a delivered stop that is already invoiced says nothing about billing', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({
        stops: [stop({ status: 'DELIVERED', receivedByName: 'Asha', bill: { orderTotal: '500.00', billStatus: 'invoiced', invoices: [{ id: 9, number: 'INV-9', balance: '500.00' }], amountToCollect: '500.00', onCredit: false } })],
      }),
    );
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    expect(screen.queryByText(/no invoice has been made/)).toBeNull();
  });
});

describe('Closing and cancelling a route (RT-01, RT-02)', () => {
  it('names the stops that still need an outcome and will not offer to close', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText(/1 stop\(s\) still need an outcome: SO-1/)).toBeInTheDocument();
    expect((screen.getByRole('button', { name: 'Close route' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('closes once every stop has an outcome', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({ stops: [stop({ status: 'FAILED' })], progress: { stopsTotal: 1, pending: 0, delivered: 0, failed: 1, collected: '0.00', needsAttention: ['failed_stops', 'ready_to_close'] } }),
    );
    api.completeDeliveryRoute.mockResolvedValue({});
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    const close = await screen.findByRole('button', { name: 'Close route' });
    expect((close as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(close);
    await waitFor(() => expect(api.completeDeliveryRoute).toHaveBeenCalledTimes(1));
  });

  it('a route on the road cannot be cancelled without a reason', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    api.cancelDeliveryRoute.mockResolvedValue({});
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await u.click(await screen.findByRole('button', { name: 'Cancel route' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Cancel route' }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await u.type(within(dialog).getByLabelText(/Reason/), 'Van broke down');
    expect(confirm.disabled).toBe(false);
    await u.click(confirm);
    await waitFor(() => expect(api.cancelDeliveryRoute).toHaveBeenCalledWith(4, 'Van broke down'));
  });

  it('a planned route cancels without a reason', async () => {
    api.getDeliveryRoute.mockResolvedValue(route({ status: 'PLANNED' }));
    api.cancelDeliveryRoute.mockResolvedValue({});
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await u.click(await screen.findByRole('button', { name: 'Cancel route' }));
    const dialog = await screen.findByRole('dialog');
    await u.click(within(dialog).getByRole('button', { name: 'Cancel route' }));
    await waitFor(() => expect(api.cancelDeliveryRoute).toHaveBeenCalledWith(4, undefined));
  });

  it('shows the same-day vehicle clash as a warning', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({ status: 'PLANNED', warnings: [{ code: 'vehicle_clash', route: 2, number: 'RT-2', message: 'Vehicle KA01AB1234 is also on route RT-2 that day.' }] }),
    );
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText(/is also on route RT-2/)).toBeInTheDocument();
  });

  it('a planned route can take more orders (add to an existing route)', async () => {
    api.getDeliveryRoute.mockResolvedValue(route({ status: 'PLANNED' }));
    api.listRouteCandidates.mockResolvedValue({
      count: 1, page: 1, pageSize: 25,
      results: [{
        order: 2, number: 'SO-2', status: 'CONFIRMED', orderDate: '2026-10-10', expectedDelivery: null,
        customer: { id: 2, name: 'Meena Traders', phone: '9', pincode: '560001', hasLocation: true },
        deliveryAddress: 'x', lines: [], lineCount: 1, totalQuantity: '1', grandTotal: '10.00',
        bill: { billStatus: 'order_only', paymentTermsDays: 0, onCredit: false, amountToCollect: '10.00', invoices: [] },
        risks: [], ready: true, hasWarnings: false,
      }],
    });
    api.addOrdersToDeliveryRoute.mockResolvedValue({});
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await u.click(await screen.findByRole('button', { name: 'Add orders' }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Meena Traders')).toBeInTheDocument();
    await u.click(within(dialog).getByRole('checkbox', { name: /SO-2/ }));
    await u.click(within(dialog).getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(api.addOrdersToDeliveryRoute).toHaveBeenCalledWith(4, [2], []));
  });
});

describe('Cashier count (RT-23, OG-21)', () => {
  const collected = (over: Record<string, unknown> = {}) =>
    route({
      stops: [stop({ status: 'DELIVERED', receivedByName: 'Asha', collectedCash: '100.00', collectedUpi: '0.00', customerReceipt: null })],
      progress: { stopsTotal: 1, pending: 0, delivered: 1, failed: 0, collected: '100.00', needsAttention: ['cash_unverified', 'ready_to_close'] },
      ...over,
    });

  it('shows what the driver reported and takes the count', async () => {
    api.getDeliveryRoute.mockResolvedValue(collected());
    api.verifyDeliveryRouteHandover.mockResolvedValue({});
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    const panel = await screen.findByTestId('cashier-panel');
    expect(within(panel).getByText(/Driver reported/)).toBeInTheDocument();
    expect(within(panel).getByText('Not counted yet')).toBeInTheDocument();
    await u.type(within(panel).getByLabelText('Cash counted'), '100');
    await u.type(within(panel).getByLabelText('UPI counted'), '0');
    await u.click(within(panel).getByRole('button', { name: 'Record the count' }));
    await waitFor(() => expect(api.verifyDeliveryRouteHandover).toHaveBeenCalledWith(4, { cashCounted: '100', upiCounted: '0', varianceNote: undefined }));
  });

  it('a short count asks why, and sends the reason', async () => {
    api.getDeliveryRoute.mockResolvedValue(collected());
    api.verifyDeliveryRouteHandover.mockResolvedValue({});
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    const panel = await screen.findByTestId('cashier-panel');
    await u.type(within(panel).getByLabelText('Cash counted'), '90');
    await u.type(within(panel).getByLabelText('UPI counted'), '0');
    expect(await within(panel).findByText(/The count is .*10\.00 short/)).toBeInTheDocument();
    await u.type(within(panel).getByLabelText('Why does it differ?'), 'Toll paid from cash');
    await u.click(within(panel).getByRole('button', { name: 'Record the count' }));
    await waitFor(() =>
      expect(api.verifyDeliveryRouteHandover).toHaveBeenCalledWith(4, { cashCounted: '90', upiCounted: '0', varianceNote: 'Toll paid from cash' }),
    );
  });

  it('a route with no money collected has no cashier panel', async () => {
    api.getDeliveryRoute.mockResolvedValue(route());
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await screen.findByText('Ravi Stores');
    expect(screen.queryByTestId('cashier-panel')).toBeNull();
  });

  it('shows the recorded count and its reason', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      collected({ cashHandover: { status: 'VARIANCE', countedCash: '90.00', countedUpi: '0.00', varianceAmount: '-10.00', varianceNote: 'Toll' } }),
    );
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    const panel = await screen.findByTestId('cashier-panel');
    expect(within(panel).getByText('Counted, differs')).toBeInTheDocument();
    expect(within(panel).getByText(/Toll/)).toBeInTheDocument();
  });
});

describe('Linking the cashier’s receipt (RT-24, OG-22)', () => {
  const withCollection = () =>
    route({
      status: 'COMPLETED',
      stops: [stop({ status: 'DELIVERED', receivedByName: 'Asha', collectedCash: '100.00', collectedUpi: '0.00', customerReceipt: null })],
      progress: { stopsTotal: 1, pending: 0, delivered: 1, failed: 0, collected: '100.00', needsAttention: [] },
    });

  it('lists only the receipts the API returns for this customer and links the chosen one', async () => {
    api.getDeliveryRoute.mockResolvedValue(withCollection());
    api.listReceiptsPage.mockResolvedValue({
      results: [{ id: 5, number: 'RC-5', amount: '100.00', receiptDate: '2026-10-14', mode: 'CASH' }],
      count: 1, next: null, previous: null,
    });
    api.linkDeliveryRouteReceipt.mockResolvedValue({});
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await u.click(await screen.findByRole('button', { name: 'Link receipt' }));
    const dialog = await screen.findByRole('dialog');
    await u.click(await within(dialog).findByText(/RC-5/));
    await u.click(within(dialog).getByRole('button', { name: 'Link receipt' }));
    await waitFor(() => expect(api.linkDeliveryRouteReceipt).toHaveBeenCalledWith(4, { stopId: 9, receiptId: 5, reason: undefined }));
    expect(api.listReceiptsPage.mock.calls[0][0]).toMatchObject({ customer: 31, status: 'POSTED' });
  });

  it('a receipt that differs from the collection needs a reason', async () => {
    api.getDeliveryRoute.mockResolvedValue(withCollection());
    api.listReceiptsPage.mockResolvedValue({
      results: [{ id: 6, number: 'RC-6', amount: '90.00', receiptDate: '2026-10-14', mode: 'CASH' }],
      count: 1, next: null, previous: null,
    });
    api.linkDeliveryRouteReceipt.mockResolvedValue({});
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await u.click(await screen.findByRole('button', { name: 'Link receipt' }));
    const dialog = await screen.findByRole('dialog');
    await u.click(await within(dialog).findByText(/RC-6/));
    expect(await within(dialog).findByText(/10\.00 less than what was collected/)).toBeInTheDocument();
    const link = within(dialog).getByRole('button', { name: 'Link receipt' }) as HTMLButtonElement;
    expect(link.disabled).toBe(true);
    await u.type(within(dialog).getByLabelText('Reason for the difference'), 'Kept for crate');
    expect(link.disabled).toBe(false);
  });

  it('says plainly when there is no receipt yet, instead of creating one', async () => {
    api.getDeliveryRoute.mockResolvedValue(withCollection());
    api.listReceiptsPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    const u = userEvent.setup();
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    await u.click(await screen.findByRole('button', { name: 'Link receipt' }));
    expect(await screen.findByText(/No posted receipts for this customer yet/)).toBeInTheDocument();
  });

  it('a stop that already has its receipt says so', async () => {
    api.getDeliveryRoute.mockResolvedValue(
      route({
        status: 'COMPLETED',
        stops: [stop({ status: 'DELIVERED', receivedByName: 'Asha', collectedCash: '100.00', customerReceipt: 5 })],
      }),
    );
    wrap('/sales/delivery-routes/4', <DeliveryRoutesPage />);
    expect(await screen.findByText('Receipt linked')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Link receipt' })).toBeNull();
  });
});

describe('Route list — progress and what needs the office (RT-27, OG-14)', () => {
  const listRow = (over: Record<string, unknown>) => ({
    id: 1, number: 'RT-1', routeDate: '2026-10-14', vehicleNumber: 'KA01', driverName: 'Asha', status: 'IN_TRANSIT',
    rollup: null, progress: { stopsTotal: 4, pending: 1, delivered: 3, failed: 0, collected: '250.00', needsAttention: [] }, ...over,
  });

  it('shows progress and collected, puts routes that need attention first, hides profit without permission', async () => {
    api.listDeliveryRoutesPage.mockResolvedValue({
      results: [
        listRow({ id: 1, number: 'RT-1' }),
        listRow({ id: 2, number: 'RT-2', progress: { stopsTotal: 2, pending: 0, delivered: 1, failed: 1, collected: '0.00', needsAttention: ['failed_stops'] } }),
      ],
      count: 2, next: null, previous: null,
    });
    wrap('/sales/delivery-routes', <DeliveryRoutesPage />);
    const rows = await screen.findAllByRole('row');
    expect(within(rows[1]).getByText('RT-2')).toBeInTheDocument(); // needs attention: first
    expect(within(rows[1]).getByText('Failed stops')).toBeInTheDocument();
    expect(within(rows[1]).getByText(/1 of 2 delivered/)).toBeInTheDocument();
    expect(within(rows[2]).getByText(/3 of 4 delivered/)).toBeInTheDocument();
    expect(screen.queryByText('Expected / estimated profit')).toBeNull();
    expect(screen.queryByText(/Expected profit uses current purchase price/)).toBeNull();
  });

  it('shows the profit column and its note to people who may see it', async () => {
    api.listDeliveryRoutesPage.mockResolvedValue({
      results: [listRow({ rollup: { expectedProfit: '120.00' } })],
      count: 1, next: null, previous: null,
    });
    wrap('/sales/delivery-routes', <DeliveryRoutesPage />);
    expect(await screen.findByText('Expected / estimated profit')).toBeInTheDocument();
    expect(screen.getByText(/Expected profit uses current purchase price/)).toBeInTheDocument();
  });

  it('searches by number, vehicle or driver and filters by status', async () => {
    api.listDeliveryRoutesPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    const u = userEvent.setup();
    wrap('/sales/delivery-routes', <DeliveryRoutesPage />);
    await u.type(await screen.findByLabelText('Search'), 'KA01');
    await waitFor(() => expect(api.listDeliveryRoutesPage.mock.calls.some((c) => c[0]?.q === 'KA01')).toBe(true));
  });

  it('a user who cannot create sales sees routes but no create button', async () => {
    user.value = { id: 2, role: 'VIEWER', companyId: 1, canCreateSales: false };
    api.listDeliveryRoutesPage.mockResolvedValue({ results: [listRow({})], count: 1, next: null, previous: null });
    wrap('/sales/delivery-routes', <DeliveryRoutesPage />);
    await screen.findByText('RT-1');
    expect(screen.queryByRole('button', { name: 'New delivery route' })).toBeNull();
  });
});
