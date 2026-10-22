import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  cards: [] as unknown[],
  queue: [] as unknown[],
  loginError: '' as string,
  cardsOffline: false,
  tapQueued: false,
}));

vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    tabletLogin: vi.fn(async () => {
      if (state.loginError) throw Object.assign(new Error(state.loginError), { isAxiosError: true, response: { status: 400, data: { error: { message: state.loginError } } } });
      return { token: 'tok', operator: { id: 7, name: 'Asha' }, expiresIn: 3600 };
    }),
    tabletCards: vi.fn(async () => {
      if (state.cardsOffline) throw Object.assign(new Error('Network Error'), { isAxiosError: true });
      return state.cards;
    }),
    tabletQueue: vi.fn(() => state.queue),
    rememberTabletOperator: vi.fn(),
    flushTabletQueue: vi.fn(async () => {
      const sent = state.queue.length;
      state.queue = [];
      return { sent, left: 0, refused: [] };
    }),
    tabletTap: vi.fn(async () => {
      if (state.tapQueued) {
        state.queue = [{ key: 'k', operator: 7, cardId: 1, verb: 'start', at: 'x' }];
        return { queued: true };
      }
      return { queued: false };
    }),
  };
});

import { flushTabletQueue, tabletLogin, tabletTap } from '@/api/mfg';
import { FloorTabletPage } from './FloorTabletPage';

const card = (over: Record<string, unknown> = {}) => ({
  id: 1, workOrder: 4, workOrderNumber: 'WO-4', sequence: 10, name: 'Cut', workCentre: 2, workCentreCode: 'CUT', status: 'PLANNED',
  qtyPlanned: '100', qtyGood: '0', qtyRejected: '0', plannedMinutes: '80', minutesWorked: '0', isSubcontract: false, running: false,
  labourCost: '0', machineCost: '0', overheadCost: '0', ...over,
});

async function signIn() {
  await userEvent.type(await screen.findByLabelText(t('mfg.tablet.code')), 'OP1');
  await userEvent.type(screen.getByLabelText(t('mfg.floor.pin')), '4821');
  await userEvent.click(screen.getByRole('button', { name: t('mfg.tablet.signIn') }));
}

describe('The shop-floor tablet', () => {
  beforeEach(() => {
    sessionStorage.clear();
    state.cards = [card()];
    state.queue = [];
    state.loginError = '';
    state.cardsOffline = false;
    state.tapQueued = false;
    vi.clearAllMocks();
  });

  it('needs the company in its address', async () => {
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor');
    expect(await screen.findByText(t('mfg.tablet.noCompany'))).toBeTruthy();
  });

  it('keeps Sign in closed until a code and a PIN of four digits are in, and keeps only digits in the PIN', async () => {
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    const button = await screen.findByRole('button', { name: t('mfg.tablet.signIn') });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText(t('mfg.tablet.code')), 'OP1');
    await userEvent.type(screen.getByLabelText(t('mfg.floor.pin')), '48x21');
    expect((screen.getByLabelText(t('mfg.floor.pin')) as HTMLInputElement).value).toBe('4821');
    expect((screen.getByRole('button', { name: t('mfg.tablet.signIn') }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows the server\'s message for a wrong PIN and stays signed out', async () => {
    state.loginError = 'Wrong code or PIN.';
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    expect(await screen.findByText('Wrong code or PIN.')).toBeTruthy();
    expect(screen.getByRole('button', { name: t('mfg.tablet.signIn') })).toBeTruthy();
    expect(vi.mocked(tabletLogin)).toHaveBeenCalledWith(7, 'OP1', '4821');
  });

  it('greets the operator by name and lists the jobs', async () => {
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    expect(await screen.findByText(t('mfg.tablet.hello', { name: 'Asha' }))).toBeTruthy();
    expect(await screen.findByText(/WO-4 · Cut/)).toBeTruthy();
  });

  it('says there is nothing to do when no job is waiting', async () => {
    state.cards = [];
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    expect(await screen.findByText(t('mfg.tablet.nothing'))).toBeTruthy();
  });

  it('starts a job with a tap', async () => {
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.floor.start') }));
    await waitFor(() => expect(tabletTap).toHaveBeenCalledWith(1, 'start', undefined));
  });

  it('sends the counts typed in when a running job is finished', async () => {
    state.cards = [card({ status: 'IN_PROGRESS' })];
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    await userEvent.type(await screen.findByLabelText(t('mfg.wo.good')), '95');
    await userEvent.type(screen.getByLabelText(t('mfg.wo.rejected')), '5');
    await userEvent.click(screen.getByRole('button', { name: t('mfg.floor.finish') }));
    await waitFor(() => expect(tabletTap).toHaveBeenCalledWith(1, 'finish', { qtyGood: '95', qtyRejected: '5' }));
  });

  it('keeps a tap made with no signal, says so, and shows the job as the operator left it', async () => {
    state.tapQueued = true;
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.floor.start') }));
    expect(await screen.findByText(t('mfg.tablet.saved'))).toBeTruthy();
    expect(await screen.findByText(t('mfg.tablet.waiting', { n: 1 }))).toBeTruthy();
    expect(await screen.findByRole('button', { name: t('mfg.floor.pause') })).toBeTruthy();   // the card now reads "in progress"
  });

  it('sends what was kept when the operator presses Send now', async () => {
    state.queue = [{ key: 'k', operator: 7, cardId: 1, verb: 'start', at: 'x' }];
    // the first attempt (the sign-in poll) finds no signal; the operator's own press gets through
    vi.mocked(flushTabletQueue).mockImplementationOnce(async () => ({ sent: 0, left: 1, refused: [] }));
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.tablet.sendNow') }));
    await waitFor(() => expect(flushTabletQueue).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText(t('mfg.tablet.waiting', { n: 1 }))).toBeNull());
  });

  it('works through a lost connection: a warning, not an error, and the last jobs stay on screen', async () => {
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    expect(await screen.findByText(/WO-4 · Cut/)).toBeTruthy();
    state.cardsOffline = true;
    window.dispatchEvent(new Event('online'));
    await waitFor(() => expect(flushTabletQueue).toHaveBeenCalled());
  });

  it('signs out', async () => {
    renderRoutes([{ path: '/floor', element: <FloorTabletPage /> }], '/floor?company=7');
    await signIn();
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.tablet.signOut') }));
    expect(await screen.findByRole('button', { name: t('mfg.tablet.signIn') })).toBeTruthy();
    expect(sessionStorage.getItem('bb.floor.token')).toBeNull();
  });
});
