import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DeliveryRoutesPage } from '@/pages/sales/DeliveryRoutesPage';

const getDeliveryRoute = vi.fn();

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', companyId: 1, canCreateSales: true } }),
}));

vi.mock('@/api/resources', () => ({
  getDeliveryRoute: (...args: unknown[]) => getDeliveryRoute(...args),
  listDeliveryRoutesPage: vi.fn(),
  listSalesOrdersPage: vi.fn(),
  addOrdersToDeliveryRoute: vi.fn(),
  completeDeliveryRoute: vi.fn(),
  createDeliveryRoute: vi.fn(),
  downloadDeliveryRouteManifest: vi.fn(),
  removeDeliveryRouteStop: vi.fn(),
  setDeliveryRouteStopStatus: vi.fn(),
  startDeliveryRoute: vi.fn(),
  cancelDeliveryRoute: vi.fn(),
  updateDeliveryRoute: vi.fn(),
  verifyDeliveryRouteHandover: vi.fn(),
  linkDeliveryRouteReceipt: vi.fn(),
  listReceiptsPage: vi.fn(),
  searchSalespeople: async () => [],
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/sales/delivery-routes/4']}>
        <Routes>
          <Route path="/sales/delivery-routes/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const baseRoute = {
  id: 4,
  number: 'RT-4',
  routeDate: '2026-09-01',
  vehicleNumber: 'KA01',
  driverName: 'Asha',
  status: 'COMPLETED',
  rollup: { expectedProfit: '10' },
  stops: [],
};

describe('Delivery route — a failed stop on an invoiced order (H-14)', () => {
  it('names the invoice that still stands and links to it', async () => {
    getDeliveryRoute.mockResolvedValue({
      ...baseRoute,
      status: 'IN_TRANSIT',
      realizedProfit: null,
      stops: [
        {
          id: 9, salesOrder: 1, orderNumber: 'SO-1', customerName: 'Ravi', status: 'FAILED',
          activeInvoice: { id: 77, number: 'INV-0077' },
        },
      ],
    });
    wrap(<DeliveryRoutesPage />);
    expect(await screen.findByText(/Invoice INV-0077 is still active/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open invoice' }).getAttribute('href')).toBe('/sales/history/77');
  });

  it('says nothing when no invoice stands', async () => {
    getDeliveryRoute.mockResolvedValue({
      ...baseRoute,
      status: 'IN_TRANSIT',
      realizedProfit: null,
      stops: [{ id: 9, salesOrder: 1, orderNumber: 'SO-1', customerName: 'Ravi', status: 'FAILED', activeInvoice: null }],
    });
    wrap(<DeliveryRoutesPage />);
    expect(await screen.findByText('SO-1')).toBeTruthy();
    expect(screen.queryByText(/is still active/)).toBeNull();
  });
});

describe('Delivery route trip profit', () => {
  it('shows the frozen trip profit and invoiced-stop count', async () => {
    getDeliveryRoute.mockResolvedValue({
      ...baseRoute,
      realizedProfit: '40.50',
      invoicedStopCount: 2,
      stopCount: 3,
    });
    wrap(<DeliveryRoutesPage />);
    expect(await screen.findByText(/Trip profit/)).toBeTruthy();
    expect(screen.getByText(/Stops invoiced: 2\/3/)).toBeTruthy();
  });

  it('hides trip profit when the route was completed with the flag off', async () => {
    getDeliveryRoute.mockResolvedValue({ ...baseRoute, realizedProfit: null });
    wrap(<DeliveryRoutesPage />);
    expect(await screen.findByText('RT-4')).toBeTruthy();
    expect(screen.queryByText(/Trip profit/)).toBeNull();
  });
});
