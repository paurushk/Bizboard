import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GoodsToCheckIn } from './GoodsToCheckIn';
import { ageInDays } from './ageInDays';

const api = vi.hoisted(() => ({ listDeliveryChallanReturnsPage: vi.fn(), completeDeliveryChallanReturn: vi.fn() }));
vi.mock('@/api/resources', () => ({ ...api }));

function mount(canWrite = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <GoodsToCheckIn canWrite={canWrite} />
    </QueryClientProvider>,
  );
}

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.completeDeliveryChallanReturn.mockResolvedValue({});
});

describe('ageInDays', () => {
  it('counts whole days and never goes negative or throws', () => {
    const now = Date.parse('2026-10-14T12:00:00Z');
    expect(ageInDays('2026-10-14T01:00:00Z', now)).toBe(0);
    expect(ageInDays('2026-10-12T11:00:00Z', now)).toBe(2);
    expect(ageInDays('2026-10-20T00:00:00Z', now)).toBe(0);
    expect(ageInDays(undefined, now)).toBe(0);
    expect(ageInDays('not a date', now)).toBe(0);
  });
});

describe('GoodsToCheckIn — the godown’s queue (OG-31)', () => {
  it('asks only for draft returns that came from a route', async () => {
    api.listDeliveryChallanReturnsPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    mount();
    await waitFor(() => expect(api.listDeliveryChallanReturnsPage).toHaveBeenCalled());
    expect(api.listDeliveryChallanReturnsPage.mock.calls[0][0]).toMatchObject({ status: 'DRAFT', from_route: true });
  });

  it('shows nothing when there is nothing to check in', async () => {
    api.listDeliveryChallanReturnsPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    mount();
    await waitFor(() => expect(api.listDeliveryChallanReturnsPage).toHaveBeenCalled());
    expect(screen.queryByTestId('goods-to-check-in')).toBeNull();
  });

  it('lists customer, route and items, and marks the old ones', async () => {
    api.listDeliveryChallanReturnsPage.mockResolvedValue({
      results: [
        { id: 1, customerName: 'Ravi Stores', challanNumber: 'DC-1', reason: 'Stop FAILED on route RT-9 (SO-3)', createdAt: hoursAgo(2), items: [{ productName: 'Widget', quantity: '3.000' }] },
        { id: 2, customerName: 'Meena Traders', challanNumber: 'DC-2', reason: 'Stop REJECTED on route RT-8 (SO-2)', createdAt: hoursAgo(80), items: [{ productName: 'Bolt', quantity: '10.000' }] },
      ],
      count: 2, next: null, previous: null,
    });
    mount();
    const panel = await screen.findByTestId('goods-to-check-in');
    expect(within(panel).getByText('Goods to check in (2)')).toBeInTheDocument();
    expect(within(panel).getByText(/Stop FAILED on route RT-9/)).toBeInTheDocument();
    expect(within(panel).getByText('Widget × 3')).toBeInTheDocument();
    expect(within(panel).getByText('today')).toBeInTheDocument();
    expect(within(panel).getByText('3 day(s) waiting')).toBeInTheDocument();
  });

  it('checks the goods in only after the godown confirms', async () => {
    api.listDeliveryChallanReturnsPage.mockResolvedValue({
      results: [{ id: 7, customerName: 'Ravi Stores', challanNumber: 'DC-1', reason: 'Stop FAILED', createdAt: hoursAgo(1), items: [] }],
      count: 1, next: null, previous: null,
    });
    const u = userEvent.setup();
    mount();
    await u.click(await screen.findByRole('button', { name: 'Check in' }));
    expect(api.completeDeliveryChallanReturn).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Do this only once the goods are in the godown/)).toBeInTheDocument();
    await u.click(within(dialog).getByRole('button', { name: 'Check in' }));
    await waitFor(() => expect(api.completeDeliveryChallanReturn).toHaveBeenCalledWith(7));
  });

  it('a user who cannot write sees the queue but no button', async () => {
    api.listDeliveryChallanReturnsPage.mockResolvedValue({
      results: [{ id: 7, customerName: 'Ravi Stores', reason: 'Stop FAILED', createdAt: hoursAgo(1), items: [] }],
      count: 1, next: null, previous: null,
    });
    mount(false);
    await screen.findByTestId('goods-to-check-in');
    expect(screen.queryByRole('button', { name: 'Check in' })).toBeNull();
  });

  it('shows the server’s refusal instead of closing silently', async () => {
    api.listDeliveryChallanReturnsPage.mockResolvedValue({
      results: [{ id: 7, customerName: 'Ravi Stores', reason: 'Stop FAILED', createdAt: hoursAgo(1), items: [] }],
      count: 1, next: null, previous: null,
    });
    api.completeDeliveryChallanReturn.mockRejectedValue(new Error('Only a completed delivery challan can be returned.'));
    const u = userEvent.setup();
    mount();
    await u.click(await screen.findByRole('button', { name: 'Check in' }));
    const dialog = await screen.findByRole('dialog');
    await u.click(within(dialog).getByRole('button', { name: 'Check in' }));
    expect(await screen.findByText(/Only a completed delivery challan can be returned/)).toBeInTheDocument();
  });
});
