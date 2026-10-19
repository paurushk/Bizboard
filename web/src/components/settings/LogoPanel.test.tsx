import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LogoPanel } from '@/components/settings/LogoPanel';
import { t } from '@/i18n';

const api = vi.hoisted(() => ({
  deleteFileAsset: vi.fn(),
  downloadFileAsset: vi.fn(),
  updateCompany: vi.fn(),
  uploadCompanyLogo: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

function renderPanel(logoId: number | null) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <LogoPanel logoId={logoId} />
    </QueryClientProvider>,
  );
}

describe('LogoPanel (SET-17)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    URL.createObjectURL = vi.fn(() => 'blob:logo');
    URL.revokeObjectURL = vi.fn();
    api.downloadFileAsset.mockResolvedValue(new Blob(['x'], { type: 'image/png' }));
    api.uploadCompanyLogo.mockResolvedValue(7);
    api.updateCompany.mockResolvedValue({});
    api.deleteFileAsset.mockResolvedValue(undefined);
  });

  it('uploads an image, then points the company at it', async () => {
    renderPanel(null);
    const file = new File(['png'], 'logo.png', { type: 'image/png' });
    await userEvent.upload(screen.getByLabelText(t('logoPanel.upload')), file);
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledWith({ logo: 7 }));
    expect(api.uploadCompanyLogo).toHaveBeenCalledWith(file);
    expect(await screen.findByRole('button', { name: t('logoPanel.replace') })).toBeTruthy();
  });

  it('refuses a file that is not an image, without sending it', async () => {
    renderPanel(null);
    await userEvent.upload(
      screen.getByLabelText(t('logoPanel.upload')),
      new File(['x'], 'a.pdf', { type: 'application/pdf' }),
      { applyAccept: false },
    );
    expect(await screen.findByText(t('logoPanel.badType'))).toBeTruthy();
    expect(api.uploadCompanyLogo).not.toHaveBeenCalled();
  });

  it('removes the logo only after asking', async () => {
    window.confirm = vi.fn(() => true);
    renderPanel(5);
    await userEvent.click(await screen.findByRole('button', { name: t('logoPanel.remove') }));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledWith({ logo: null }));
    expect(api.deleteFileAsset).toHaveBeenCalledWith(5);
  });

  it('keeps the logo when removal is declined', async () => {
    window.confirm = vi.fn(() => false);
    renderPanel(5);
    await userEvent.click(await screen.findByRole('button', { name: t('logoPanel.remove') }));
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it('shows the server reason when the upload is refused', async () => {
    api.uploadCompanyLogo.mockRejectedValue(new Error('File exceeds maximum size'));
    renderPanel(null);
    await userEvent.upload(screen.getByLabelText(t('logoPanel.upload')), new File(['x'], 'l.png', { type: 'image/png' }));
    expect(await screen.findByText(/exceeds maximum size/)).toBeTruthy();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });
});
