import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ServiceQualityPage } from '@/pages/care/ServiceQualityPage';
import { a11yViolations, renderRoutes } from '@/test/careHarness';

const kpis = vi.hoisted(() => vi.fn());
vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  careKpis: (...args: unknown[]) => kpis(...args),
}));

function page() {
  return renderRoutes([{ path: '/care/quality', element: <ServiceQualityPage /> }], '/care/quality');
}

beforeEach(() => {
  vi.clearAllMocks();
  kpis.mockResolvedValue({
    days: 90,
    tickets: { opened: 12, resolved: 9, slaMetPercent: 78, averageResolutionSeconds: 7200, openNow: 3 },
    complaints: {
      customerTotal: 7, customerResolved: 4, customerRejected: 1, supplierTotal: 2,
      repeatProducts: [{ product: 3, name: 'Motor', complaints: 3 }], bySupplier: [{ supplier: 7, supplierName: 'Mega Mills', count: 2 }],
    },
    workshop: { jobs: 20, invoiced: 15, withContract: 6, freeLines: 8, paidLines: 40, warrantyCostAtListPrice: '12500.00' },
    projects: { openProjects: 2, plannedTotal: '90000.00', invoicedTotal: '30000.00', overdueMilestones: 1 },
    contracts: { live: 11, expiring: 2, expired: 4 },
  });
});

describe('ServiceQualityPage', () => {
  it('shows every module that is on, with the numbers in plain words', async () => {
    const view = page();
    expect(await screen.findByRole('region', { name: 'Support tickets' })).toHaveTextContent('78%');
    expect(screen.getByRole('region', { name: 'Support tickets' })).toHaveTextContent('2h');
    expect(screen.getByRole('region', { name: 'Complaints' })).toHaveTextContent('Motor: 3');
    expect(screen.getByRole('region', { name: 'Complaints' })).toHaveTextContent('Mega Mills: 2');
    expect(screen.getByRole('region', { name: 'Job cards' })).toHaveTextContent('₹12,500.00');
    expect(screen.getByRole('region', { name: 'Projects' })).toHaveTextContent('Overdue milestones');
    expect(screen.getByRole('region', { name: 'Contracts' })).toHaveTextContent('Ending soon');
    expect(await a11yViolations(view.container)).toEqual([]);
  });

  it('asks the server again when the period changes', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByRole('region', { name: 'Contracts' });
    await user.click(screen.getByRole('combobox', { name: 'Period' }));
    await user.click(await screen.findByRole('option', { name: 'Last 365 days' }));
    await waitFor(() => expect(kpis).toHaveBeenCalledWith(365));
  });

  it('leaves out a module that is off and says so when all are off', async () => {
    kpis.mockResolvedValue({ days: 90 });
    page();
    expect(await screen.findByText(/Nothing to show yet/)).toBeInTheDocument();
  });

  it('shows an error with a retry', async () => {
    kpis.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('region', { name: 'Contracts' })).toBeInTheDocument();
  });
});
