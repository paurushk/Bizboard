import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LegalAcceptanceGate } from '@/components/LegalAcceptanceGate';
import { t } from '@/i18n';

const { getLegalStatus, acceptLegal } = vi.hoisted(() => ({ getLegalStatus: vi.fn(), acceptLegal: vi.fn() }));
vi.mock('@/api/auth', () => ({ getLegalStatus, acceptLegal }));

function renderGate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LegalAcceptanceGate />
    </QueryClientProvider>,
  );
}

describe('LegalAcceptanceGate (WP-H5)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows nothing when everything is accepted', async () => {
    getLegalStatus.mockResolvedValue({ pending: [] });
    renderGate();
    await waitFor(() => expect(getLegalStatus).toHaveBeenCalled());
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('blocks until the new versions are accepted', async () => {
    getLegalStatus.mockResolvedValue({
      pending: [
        { document: 'TOS', version: 'v2', companyId: null },
        { document: 'DPA', version: 'v2', companyId: 9 },
      ],
    });
    acceptLegal.mockResolvedValue({ pending: [] });
    renderGate();
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(screen.getByText(`${t('auth.legalDoc_TOS')} (v2)`)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: t('auth.legalAccept') }));
    expect(acceptLegal).toHaveBeenCalledWith(['TOS', 'DPA']);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
