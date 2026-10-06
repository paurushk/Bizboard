import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TwoStepVerificationPanel } from '@/components/TwoStepVerificationPanel';

const api = vi.hoisted(() => ({
  getMfaStatus: vi.fn(),
  startMfaSetup: vi.fn(),
  confirmMfa: vi.fn(),
  disableMfa: vi.fn(),
  regenerateMfaRecoveryCodes: vi.fn(),
}));

vi.mock('@/api/auth', () => api);

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TwoStepVerificationPanel />
    </QueryClientProvider>,
  );
}

describe('TwoStepVerificationPanel', () => {
  beforeEach(() => {
    Object.values(api).forEach((m) => m.mockReset());
  });

  it('offers to turn it on when it is off, and shows the QR + key after starting', async () => {
    api.getMfaStatus.mockResolvedValue({ enabled: false, pendingSetup: false, recoveryCodesRemaining: 0 });
    api.startMfaSetup.mockResolvedValue({ secret: 'ABCD EFGH', otpauthUri: 'otpauth://x', qrPng: 'data:image/png;base64,AAA' });
    renderPanel();
    expect(await screen.findByText('Off')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /turn on/i }));
    expect(await screen.findByText('ABCD EFGH')).toBeTruthy();
    // confirm stays disabled until a full 6-digit code is typed
    const confirm = screen.getByRole('button', { name: /confirm and turn on/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
  });

  it('confirms with the code and then shows the recovery codes exactly once', async () => {
    api.getMfaStatus.mockResolvedValue({ enabled: false, pendingSetup: false, recoveryCodesRemaining: 0 });
    api.startMfaSetup.mockResolvedValue({ secret: 'KEY', otpauthUri: 'otpauth://x', qrPng: 'data:image/png;base64,AAA' });
    api.confirmMfa.mockResolvedValue(['AAAAA-BBBBB', 'CCCCC-DDDDD']);
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: /turn on/i }));
    await userEvent.type(await screen.findByLabelText(/enter the 6-digit code/i), '123456');
    await userEvent.click(screen.getByRole('button', { name: /confirm and turn on/i }));
    await waitFor(() => expect(api.confirmMfa).toHaveBeenCalledWith('123456'));
    expect(await screen.findByText('AAAAA-BBBBB')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /i have saved them/i }));
    await waitFor(() => expect(screen.queryByText('AAAAA-BBBBB')).toBeNull());
  });

  it('shows a server error for a wrong confirmation code and stays on the setup step', async () => {
    api.getMfaStatus.mockResolvedValue({ enabled: false, pendingSetup: false, recoveryCodesRemaining: 0 });
    api.startMfaSetup.mockResolvedValue({ secret: 'KEY', otpauthUri: 'otpauth://x', qrPng: 'data:image/png;base64,AAA' });
    api.confirmMfa.mockRejectedValue(new Error('That code is not valid.'));
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: /turn on/i }));
    await userEvent.type(await screen.findByLabelText(/enter the 6-digit code/i), '000000');
    await userEvent.click(screen.getByRole('button', { name: /confirm and turn on/i }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByLabelText(/enter the 6-digit code/i)).toBeTruthy();
  });

  it('when on, shows the remaining recovery codes and requires password + code to turn off', async () => {
    api.getMfaStatus.mockResolvedValue({ enabled: true, pendingSetup: false, recoveryCodesRemaining: 7 });
    api.disableMfa.mockResolvedValue(undefined);
    renderPanel();
    expect(await screen.findByText('On')).toBeTruthy();
    expect(screen.getByText('7 recovery codes left')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /turn off/i }));
    const off = screen.getByRole('button', { name: /^turn off$/i }) as HTMLButtonElement;
    expect(off.disabled).toBe(true);
    await userEvent.type(screen.getByLabelText(/your password/i), 'pw');
    await userEvent.type(screen.getByLabelText(/authentication code/i), '654321');
    expect(off.disabled).toBe(false);
    await userEvent.click(off);
    await waitFor(() => expect(api.disableMfa).toHaveBeenCalledWith('pw', { code: '654321' }));
  });
});
