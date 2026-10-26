import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { a11yViolations, renderRoutes } from '@/test/careHarness';
import { NpsPrompt } from './NpsPrompt';

const api = vi.hoisted(() => ({ getNpsDue: vi.fn(), sendSatisfaction: vi.fn() }));
vi.mock('@/api/platformSupport', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/platformSupport')>()),
  getNpsDue: () => api.getNpsDue(),
  sendSatisfaction: (input: unknown) => api.sendSatisfaction(input),
}));

const mount = () => renderRoutes([{ path: '/', element: <NpsPrompt /> }], '/');

/** BB-136 (D-08): the recommend-us card shows only when the server says it is due. */
describe('NpsPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.sendSatisfaction.mockResolvedValue(undefined);
  });

  it('shows nothing when the prompt is not due (survey off, new member or asked recently)', async () => {
    api.getNpsDue.mockResolvedValue({ due: false, enabled: true });
    mount();
    await waitFor(() => expect(api.getNpsDue).toHaveBeenCalled());
    expect(screen.queryByRole('region', { name: 'Quick question' })).toBeNull();
  });

  it('sends the chosen score with the reason, then thanks the person', async () => {
    api.getNpsDue.mockResolvedValue({ due: true, enabled: true });
    const user = userEvent.setup();
    const view = mount();
    expect(await screen.findByRole('region', { name: 'Quick question' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Score 9' }));
    await user.type(screen.getByLabelText(/main reason/), 'Fast billing');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(api.sendSatisfaction).toHaveBeenCalledWith({ kind: 'NPS', score: 9, comment: 'Fast billing' }));
    expect(await screen.findByText(/Thank you/)).toBeInTheDocument();
    expect(await a11yViolations(view.container)).toEqual([]);
  });

  it('records "Not now" without a score and goes away', async () => {
    api.getNpsDue.mockResolvedValue({ due: true, enabled: true });
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Not now' }));
    await waitFor(() => expect(api.sendSatisfaction).toHaveBeenCalledWith({ kind: 'NPS', score: null, comment: '' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Quick question' })).toBeNull());
  });
});
