import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { PaymentGatewayPage } from '@/pages/settings/PaymentGatewayPage';

vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

const api = vi.hoisted(() => ({
  getGatewaySettings: vi.fn(),
  updateGatewaySettings: vi.fn(),
  verifyGatewayKeys: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const BASE = {
  provider: 'razorpay',
  testMode: false,
  testModeAvailable: false,
  credentialsConfigured: false,
  credentialsHint: '',
  credentialsMode: 'unknown',
  credentialsVerified: false,
  credentialsVerifiedAt: null,
  verificationSupported: true,
  enabledProviders: ['razorpay', 'cashfree', 'payu'],
  disabledProviders: [],
  webhookPaths: { razorpay: '/api/v1/webhooks/payments/razorpay/?company_id=1' },
};
const SAVED = { ...BASE, credentialsConfigured: true, credentialsHint: '3456', credentialsMode: 'live' };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PaymentGatewayPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PaymentGatewayPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getGatewaySettings.mockResolvedValue(BASE);
    api.updateGatewaySettings.mockResolvedValue(BASE);
  });

  it('holds only the gateway: no Money In rules on this screen', async () => {
    renderPage();
    expect(await screen.findByLabelText(t('gateway.fieldKeyId'))).toBeTruthy();
    expect(screen.queryByLabelText(/cash limit check/i)).toBeNull();
    expect(screen.queryByText(/hold cheques as advances/i)).toBeNull();
  });

  it('warns when no keys are saved and has nothing to check or remove', async () => {
    renderPage();
    await screen.findByLabelText(t('gateway.fieldKeyId'));
    expect(screen.getByText(t('integrations.paymentGatewayClosed'))).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('gateway.checkKeys') })).toBeNull();
    expect(screen.queryByRole('button', { name: t('gateway.removeKeys') })).toBeNull();
  });

  it('sends only the fields this provider uses and only the ones typed', async () => {
    renderPage();
    await userEvent.type(await screen.findByLabelText(t('gateway.fieldKeyId')), 'rzp_test_ABC');
    await userEvent.type(screen.getByLabelText(t('gateway.fieldKeySecret')), 'shh');
    await userEvent.click(screen.getByRole('button', { name: t('sweep2.saveSettings') }));
    await waitFor(() => expect(api.updateGatewaySettings).toHaveBeenCalled());
    expect(api.updateGatewaySettings.mock.calls[0][0]).toEqual({
      provider: 'razorpay',
      credentials: { key_id: 'rzp_test_ABC', key_secret: 'shh' },
    });
  });

  it('does not send keys, or rules, when only the provider changes', async () => {
    renderPage();
    await screen.findByLabelText(t('gateway.fieldKeyId'));
    await userEvent.click(screen.getByLabelText(t('sweep.provider')));
    await userEvent.click(await screen.findByRole('option', { name: 'Cashfree' }));
    await userEvent.click(screen.getByRole('button', { name: t('sweep2.saveSettings') }));
    await waitFor(() => expect(api.updateGatewaySettings).toHaveBeenCalled());
    expect(api.updateGatewaySettings.mock.calls[0][0]).toEqual({ provider: 'cashfree' });
  });

  it('shows the key hint and mode, never the secret, and checks the keys on request', async () => {
    api.getGatewaySettings.mockResolvedValue(SAVED);
    api.verifyGatewayKeys.mockResolvedValue({ status: 'valid', detail: 'Razorpay accepted the keys.', verifiedAt: 'x', provider: 'razorpay' });
    renderPage();
    expect(await screen.findByText(new RegExp('3456'))).toBeTruthy();
    expect(screen.getByText(new RegExp(t('gateway.modeLive')))).toBeTruthy();
    expect(screen.getByText(new RegExp(t('gateway.notChecked')))).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: t('gateway.checkKeys') }));
    expect(await screen.findByText('Razorpay accepted the keys.')).toBeTruthy();
    expect(api.verifyGatewayKeys).toHaveBeenCalledTimes(1);
  });

  it('shows a refusal from the provider as an error', async () => {
    api.getGatewaySettings.mockResolvedValue(SAVED);
    api.verifyGatewayKeys.mockResolvedValue({ status: 'invalid', detail: 'Razorpay did not accept these keys.', verifiedAt: null, provider: 'razorpay' });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('gateway.checkKeys') }));
    expect((await screen.findByText('Razorpay did not accept these keys.')).closest('[role="alert"]')).toBeTruthy();
  });

  it('shows when the provider accepted the keys', async () => {
    api.getGatewaySettings.mockResolvedValue({ ...SAVED, credentialsVerified: true, credentialsVerifiedAt: '2026-10-19T10:00:00Z' });
    renderPage();
    expect(await screen.findByText(new RegExp(t('gateway.verifiedOn', { date: '.*' }).slice(0, 12)))).toBeTruthy();
  });

  it('says a provider cannot be checked and disables the check', async () => {
    api.getGatewaySettings.mockResolvedValue({ ...SAVED, provider: 'payu', verificationSupported: false });
    renderPage();
    expect(await screen.findByText(new RegExp(t('gateway.cannotCheck').slice(0, 20)))).toBeTruthy();
    expect((screen.getByRole('button', { name: t('gateway.checkKeys') }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('warns about test keys on a server that does not run in test mode', async () => {
    api.getGatewaySettings.mockResolvedValue({ ...SAVED, credentialsMode: 'test', testModeAvailable: false });
    renderPage();
    expect(await screen.findByText(t('gateway.testKeysWarning'))).toBeTruthy();
  });

  it('offers the test-mode switch only where the server allows it', async () => {
    renderPage();
    await screen.findByLabelText(t('gateway.fieldKeyId'));
    expect(screen.queryByRole('checkbox', { name: new RegExp(t('sweep.testMode')) })).toBeNull();
  });

  it('removes the keys only after confirmation', async () => {
    api.getGatewaySettings.mockResolvedValue(SAVED);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('gateway.removeKeys') }));
    expect(api.updateGatewaySettings).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: t('gateway.removeKeys') }));
    await waitFor(() => expect(api.updateGatewaySettings).toHaveBeenCalledWith({ clear_credentials: true }));
  });

  it('warns when no webhook secret is saved, and says no notification has arrived yet', async () => {
    api.getGatewaySettings.mockResolvedValue({ ...SAVED, webhookSecretConfigured: false, lastWebhookAt: null });
    renderPage();
    expect(await screen.findByText(t('gateway.webhookSecretMissing'))).toBeTruthy();
    expect(screen.getByText(t('gateway.noEventYet'))).toBeTruthy();
  });

  it('shows that the webhook secret is saved and when the last notification was accepted', async () => {
    api.getGatewaySettings.mockResolvedValue({ ...SAVED, webhookSecretConfigured: true, lastWebhookAt: '2026-10-19T10:00:00Z' });
    renderPage();
    expect(await screen.findByText(t('gateway.webhookSecretSaved'))).toBeTruthy();
    expect(screen.getByText(/Last payment notification accepted/)).toBeTruthy();
  });

  it('sends the webhook secret with the keys when it is typed', async () => {
    renderPage();
    await userEvent.type(await screen.findByLabelText(t('gateway.fieldWebhookSecret')), 'whsec_1');
    await userEvent.click(screen.getByRole('button', { name: t('sweep2.saveSettings') }));
    await waitFor(() => expect(api.updateGatewaySettings).toHaveBeenCalled());
    expect(api.updateGatewaySettings.mock.calls[0][0].credentials).toEqual({ webhook_secret: 'whsec_1' });
  });

  it('shows an error with Retry when the settings cannot load', async () => {
    api.getGatewaySettings.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.queryByLabelText(t('gateway.fieldKeyId'))).toBeNull();
  });
});
