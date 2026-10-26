import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderRoutes } from '@/test/careHarness';
import { ReferralPanel } from './ReferralPanel';

const api = vi.hoisted(() => ({ get: vi.fn(), on: true }));
vi.mock('@/api/billing', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/billing')>()),
  getReferralPanel: () => api.get(),
}));
vi.mock('@/config/featureFlags', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/featureFlags')>()),
  isRuntimeFlagEnabled: (key: string) => key === 'ENABLE_SAAS_REFERRALS' && api.on,
  useFeatureFlagEpoch: () => 0,
}));

const mount = () => renderRoutes([{ path: '/', element: <ReferralPanel companyKey={1} /> }], '/');

/** D-19 (BB-139): the owner's referral link, counts only. */
describe('ReferralPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.on = true;
  });

  it('shows the link, a WhatsApp share and the counts', async () => {
    api.get.mockResolvedValue({ code: 'ABCD2345', isActive: true, signedUp: 3, qualified: 1 });
    mount();
    const field = (await screen.findByLabelText('Your referral link')) as HTMLInputElement;
    expect(field.value).toBe(`${window.location.origin}/register?ref=ABCD2345`);
    const share = screen.getByRole('link', { name: 'Share on WhatsApp' });
    expect(share.getAttribute('href')).toContain('https://wa.me/?text=');
    expect(decodeURIComponent(share.getAttribute('href') ?? '')).toContain('/register?ref=ABCD2345');
    expect(screen.getByText('3 signed up · 1 started paying')).toBeInTheDocument();
    expect(screen.getByText(/not which businesses signed up/)).toBeInTheDocument();
  });

  it('says when the link is switched off', async () => {
    api.get.mockResolvedValue({ code: 'ABCD2345', isActive: false, signedUp: 0, qualified: 0 });
    mount();
    expect(await screen.findByText(/This link has been switched off/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Your referral link')).toBeNull();
  });

  it('renders nothing and asks nothing while the flag is off', () => {
    api.on = false;
    const { container } = mount();
    expect(container.textContent).toBe('');
    expect(api.get).not.toHaveBeenCalled();
  });
});
