import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ReferralsPage } from '@/pages/crm/ReferralsPage';
import type { ReferralReward } from '@/api/growth';

vi.mock('@/config/features', () => ({
  isReferralsEnabled: () => true,
}));

vi.mock('@/pages/erp/erpShared', () => ({
  ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: ({ onChange }: { onChange: (c: { id: number; name: string } | null) => void }) => (
    <button onClick={() => onChange({ id: 5, name: 'Ravi' })}>pick-customer</button>
  ),
}));

const { role } = vi.hoisted(() => ({ role: { current: 'OWNER' } }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'u@x.test', fullName: 'U', role: role.current, companyId: 9 } }),
}));

const { decideReferralReward, issueReferralCode, listReferralRewards, referralLeaderboard } = vi.hoisted(() => {
  const pending: ReferralReward = { id: 1, referralCode: 3, opportunity: 42, rewardAmount: '25.00', rewardStatus: 'PENDING' };
  return {
    decideReferralReward: vi.fn(async (id: number, decision: string) => ({ ...pending, id, rewardStatus: decision === 'approve' ? 'APPROVED' : 'REJECTED' })),
    issueReferralCode: vi.fn(async () => ({ id: 3, code: 'AB12CD34' })),
    listReferralRewards: vi.fn(async () => ({ results: [pending], count: 1, next: null, previous: null })),
    referralLeaderboard: vi.fn(async () => [{ code: 'AB12CD34', referrerType: 'customer', approvedTotal: '25.00' }]),
  };
});

vi.mock('@/api/growth', () => ({
  decideReferralReward: (...args: unknown[]) => decideReferralReward(...args),
  issueReferralCode: (...args: unknown[]) => issueReferralCode(...args),
  listReferralRewards: () => listReferralRewards(),
  referralLeaderboard: () => referralLeaderboard(),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/crm/referrals']}>
        <Routes>
          <Route path="/crm/referrals" element={<ReferralsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ReferralsPage', () => {
  it('issues a code and shows it, and renders the leaderboard', async () => {
    role.current = 'OWNER';
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText(/AB12CD34 · customer · 25.00/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'pick-customer' }));
    await user.click(screen.getByRole('button', { name: 'Issue code' }));

    await waitFor(() => expect(issueReferralCode).toHaveBeenCalledWith({
      referrer_customer: 5, reward_type: 'FLAT', reward_value: '0',
    }));
    expect(await screen.findByText('Code: AB12CD34')).toBeInTheDocument();
  });

  it('lets an OWNER approve a pending reward', async () => {
    role.current = 'OWNER';
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark paid' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(decideReferralReward).toHaveBeenCalledWith(1, 'approve'));
  });

  it('lets an OWNER mark an approved reward paid', async () => {
    role.current = 'OWNER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{ id: 7, referralCode: 3, opportunity: 42, rewardAmount: '40.00', rewardStatus: 'APPROVED' }],
      count: 1,
      next: null,
      previous: null,
    });
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText(/drafts a credit note/i)).toBeInTheDocument();
    expect(screen.getByText(/does not send cash/i)).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Mark paid' }));
    await waitFor(() => expect(decideReferralReward).toHaveBeenCalledWith(7, 'mark-paid'));
  });

  it('shows the self-referral reason on a rejected reward', async () => {
    role.current = 'OWNER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{
        id: 9,
        referralCode: 3,
        opportunity: 42,
        rewardAmount: '25.00',
        rewardStatus: 'REJECTED',
        rejectionReason: 'self_referral',
      }],
      count: 1,
      next: null,
      previous: null,
    });
    wrap();
    expect(await screen.findByText(/the referrer and the customer are the same person/)).toBeInTheDocument();
  });

  it('hides the approve/reject actions from a non-owner, non-manager role', async () => {
    role.current = 'SALES_STAFF';
    wrap();
    await screen.findByText(/#42 · 25.00 · PENDING/);
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark paid' })).not.toBeInTheDocument();
  });

  it('hides mark paid once the reward is already paid', async () => {
    role.current = 'OWNER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{ id: 8, referralCode: 3, opportunity: 42, rewardAmount: '40.00', rewardStatus: 'PAID' }],
      count: 1, next: null, previous: null,
    });
    wrap();
    await screen.findByText(/#42 · 40.00 · PAID/);
    expect(screen.queryByRole('button', { name: 'Mark paid' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
  });
});
