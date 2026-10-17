import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PreflightPanel, type Preflight, type PreflightStop } from './PreflightPanel';
import type { PlanRisk, PlanSummary } from './planningTypes';

const api = vi.hoisted(() => ({ getDeliveryRoutePreflight: vi.fn(), startDeliveryRoute: vi.fn() }));
vi.mock('@/api/resources', () => ({ ...api }));

const summary = {
  order: 1, status: 'CONFIRMED', customer: { id: 1, name: 'Ravi' }, lines: [], lineCount: 1, totalQuantity: '2', grandTotal: '100.00',
  bill: { billStatus: 'order_only', paymentTermsDays: 0, onCredit: false, amountToCollect: '100.00', invoices: [] },
  risks: [], ready: true, hasWarnings: false,
} as PlanSummary;

const risk = (code: string, level: PlanRisk['level'], canAccept: boolean, extra: Partial<PlanRisk> = {}): PlanRisk => ({
  code, level, message: `${code} message`, override: canAccept ? 'any' : 'none', canAccept, ...extra,
});
const stop = (id: number, risks: PlanRisk[], status: PreflightStop['status'] = 'ok'): PreflightStop => ({
  stop: id, order: id, number: `SO-${id}`, customer: `Cust ${id}`, status, risks, summary,
});
const data = (stops: PreflightStop[]): Preflight => ({
  stops,
  totals: { orders: stops.length, lines: stops.length, quantity: '2', value: '100.00', toCollect: '100.00', warnings: 1, blocks: 0 },
  openProblems: 0,
  canStart: true,
});

function mount(pre: Preflight, props: { canWrite?: boolean; hidden?: boolean } = {}) {
  api.getDeliveryRoutePreflight.mockResolvedValue(pre);
  const onStarted = vi.fn();
  const onError = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <PreflightPanel routeId={4} canWrite={props.canWrite ?? true} hidden={props.hidden} onStarted={onStarted} onError={onError} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onStarted, onError };
}

beforeEach(() => {
  api.getDeliveryRoutePreflight.mockReset();
  api.startDeliveryRoute.mockReset();
});

describe('Preflight panel (PL-23)', () => {
  it('a clean route says so and starts with no acknowledgements', async () => {
    api.startDeliveryRoute.mockResolvedValue({});
    const { onStarted } = mount(data([stop(1, [risk('late', 'info', true)])]));
    expect(await screen.findByText(/Nothing needs your attention/)).toBeInTheDocument();
    expect(screen.getByTestId('preflight-totals').textContent).toMatch(/1 order\(s\).*100\.00/);
    await userEvent.setup().click(screen.getByRole('button', { name: /Start/ }));
    await waitFor(() => expect(api.startDeliveryRoute).toHaveBeenCalledWith(4, []));
    expect(onStarted).toHaveBeenCalled();
  });

  it('a stop with a risk nobody here can accept blocks the start and names it', async () => {
    mount(data([stop(1, [risk('customer_blocked', 'block', false)], 'blocked')]));
    expect(await screen.findByText('customer_blocked message')).toBeInTheDocument();
    expect(screen.getByText(/Must be fixed or removed/)).toBeInTheDocument();
    expect((screen.getByRole('button', { name: /Start/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a warning is accepted here with a reason, and the start carries it', async () => {
    api.startDeliveryRoute.mockResolvedValue({});
    mount(data([stop(7, [risk('stock_short', 'warn', true)], 'needs_ack')]));
    const u = userEvent.setup();
    expect(await screen.findByText(/Needs your decision/)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Accept and add' }));
    const dialog = await screen.findByRole('dialog');
    await u.type(within(dialog).getByLabelText(/Reason/), 'Stock arrives at 9');
    await u.click(within(dialog).getByRole('button', { name: 'Accept and add' }));
    await waitFor(() => expect(screen.queryByText(/Needs your decision/)).toBeNull());
    await u.click(await screen.findByRole('button', { name: 'Accept and start' }));
    await waitFor(() =>
      expect(api.startDeliveryRoute).toHaveBeenCalledWith(4, [{ stop: 7, code: 'stock_short', reason: 'Stock arrives at 9' }]),
    );
  });

  it('shows risks already accepted earlier, with the reason', async () => {
    mount(data([stop(1, [risk('no_phone', 'warn', true, { acknowledged: true, acknowledgedReason: 'Driver knows the shop' })])]));
    expect(await screen.findByText(/Accepted: Driver knows the shop/)).toBeInTheDocument();
    expect(screen.getByText('No phone')).toBeInTheDocument();
  });

  it('a start error is reported, not swallowed', async () => {
    api.startDeliveryRoute.mockRejectedValue(new Error('boom'));
    const { onError } = mount(data([stop(1, [])]));
    await userEvent.setup().click(await screen.findByRole('button', { name: /Start/ }));
    await waitFor(() => expect(onError).toHaveBeenCalled());
    expect(onError.mock.calls.at(-1)?.[0]).toBeTruthy();
  });

  it('read-only users see the check but no buttons', async () => {
    mount(data([stop(1, [risk('stock_short', 'warn', true)], 'needs_ack')]), { canWrite: false });
    await screen.findByText(/Needs your decision/);
    expect(screen.queryByRole('button', { name: /Start/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Accept and add' })).toBeNull();
  });

  it('renders nothing when hidden', () => {
    mount(data([stop(1, [])]), { hidden: true });
    expect(screen.queryByTestId('preflight-panel')).toBeNull();
    expect(api.getDeliveryRoutePreflight).not.toHaveBeenCalled();
  });
});
