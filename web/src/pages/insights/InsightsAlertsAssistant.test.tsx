import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { InsightsAlertsPage } from '@/pages/insights/InsightsAlertsPage';
import { InsightsAssistantPage } from '@/pages/insights/InsightsAssistantPage';

const state = vi.hoisted(() => ({
  alerts: [] as unknown[],
  alertsFail: false,
  messages: [] as unknown[],
  send: vi.fn(async () => ({})),
  create: vi.fn(async () => ({ id: 9 })),
}));

vi.mock('@/components/insights/AiConsentGate', () => ({
  useAiConsentOn: () => true,
  AiConsentOffScreen: () => null,
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'OWNER', company: { aiFeaturesEnabled: true } } }),
}));
vi.mock('@/config/features', () => ({ isHelpV2Enabled: () => false }));
vi.mock('@/api/resources', () => ({
  listBusinessAlerts: async () => {
    if (state.alertsFail) throw new Error('alerts are down');
    return state.alerts;
  },
  snoozeBusinessAlert: vi.fn(),
  unsnoozeBusinessAlert: vi.fn(),
  refreshBusinessAlerts: vi.fn(),
  listAssistantThreads: async () => [{ id: 1, title: 'Chat' }],
  getAssistantThread: async () => ({ id: 1, title: 'Chat', messages: state.messages }),
  createAssistantThread: (...a: unknown[]) => state.create(...(a as [])),
  postAssistantMessage: (...a: unknown[]) => state.send(...(a as [])),
  confirmAssistantAction: vi.fn(),
  dismissAssistantAction: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InsightsAlertsPage', () => {
  it('shows an error, not the empty message, when the request fails', async () => {
    state.alertsFail = true;
    wrap(<InsightsAlertsPage />);
    expect(await screen.findByText(/alerts are down/)).toBeTruthy();
    expect(screen.queryByText('No open business alerts.')).toBeNull();
    state.alertsFail = false;
  });

  it('lists an alert with a snooze menu and hides raw codes until asked', async () => {
    state.alerts = [{ id: 1, code: 'AR_OVERDUE_CRITICAL', severity: 'critical', message: 'Overdue receivables', status: 'OPEN', ctaPath: '/reports/customer-ledger' }];
    wrap(<InsightsAlertsPage />);
    expect(await screen.findByText('Overdue receivables')).toBeTruthy();
    expect(screen.queryByText('AR_OVERDUE_CRITICAL')).toBeNull();
    expect(screen.getByText('Snooze…')).toBeTruthy();
  });
});

describe('InsightsAssistantPage', () => {
  it('shows who a reminder goes to, and blocks confirm when the customer has no contact', async () => {
    state.messages = [
      {
        id: 5,
        role: 'assistant',
        content: 'Reminder draft ready',
        toolName: 'basic',
        proposedAction: { type: 'send_reminder', customerName: 'Pay Me', email: '', phone: '', text: 'Please pay' },
      },
    ];
    wrap(<InsightsAssistantPage />);
    expect(await screen.findByText('To: Pay Me')).toBeTruthy();
    expect(screen.getByText(/no email or phone/)).toBeTruthy();
    expect((screen.getByText('Confirm & send') as HTMLButtonElement).closest('button')!.disabled).toBe(true);
  });

  it('does not send while an input method is composing', async () => {
    state.messages = [];
    wrap(<InsightsAssistantPage />);
    const box = await screen.findByPlaceholderText(/Ask about sales/);
    fireEvent.change(box, { target: { value: 'बिक्री' } });
    fireEvent.keyDown(box, { key: 'Enter', isComposing: true });
    expect(state.send).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: 'Enter' });
    await waitFor(() => expect(state.send).toHaveBeenCalled());
  });
});
