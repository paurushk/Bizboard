import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { WhatsappSettingsDialog } from '@/pages/crm/WhatsappSettingsDialog';

const { issueWhatsappWebhookToken, saveWhatsappAppSecret } = vi.hoisted(() => ({
  issueWhatsappWebhookToken: vi.fn(),
  saveWhatsappAppSecret: vi.fn(),
}));

vi.mock('@/api/crm', () => ({
  issueWhatsappWebhookToken: (...a: unknown[]) => issueWhatsappWebhookToken(...a),
  saveWhatsappAppSecret: (...a: unknown[]) => saveWhatsappAppSecret(...a),
  whatsappWebhookUrl: (token: string) => `https://app.test/hook/${token}`,
}));

function setup() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <WhatsappSettingsDialog open onClose={() => undefined} />
    </QueryClientProvider>,
  );
}

describe('WhatsappSettingsDialog', () => {
  it('shows the webhook URL and verify token read-only, without fetching a rotated token', async () => {
    issueWhatsappWebhookToken.mockResolvedValue({ token: 'tok1', verifyToken: 'ver1', secretConfigured: false });
    setup();
    expect(await screen.findByDisplayValue('https://app.test/hook/tok1')).toHaveAttribute('readonly');
    expect(screen.getByDisplayValue('ver1')).toHaveAttribute('readonly');
    expect(issueWhatsappWebhookToken).toHaveBeenCalledWith(false);
  });

  it('keeps Save disabled until a secret is typed, then saves it trimmed and clears the field', async () => {
    issueWhatsappWebhookToken.mockResolvedValue({ token: 'tok1', verifyToken: 'ver1', secretConfigured: false });
    saveWhatsappAppSecret.mockResolvedValue({ secretConfigured: true });
    setup();
    await screen.findByDisplayValue('ver1');
    const save = screen.getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();
    const field = screen.getByLabelText(/app secret/i);
    await userEvent.type(field, '  s3cret  ');
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(saveWhatsappAppSecret).toHaveBeenCalledWith('s3cret'));
    expect(await screen.findByText('App secret saved.')).toBeInTheDocument();
    expect(field).toHaveValue('');
  });
});
