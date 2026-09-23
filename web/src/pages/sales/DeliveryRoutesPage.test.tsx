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
