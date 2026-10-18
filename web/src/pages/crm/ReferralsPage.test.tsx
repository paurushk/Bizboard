import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
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

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false }),
}));

vi.mock('@/api/crm', () => ({
  issueLeadFormToken: async () => ({ token: 'form-tok' }),
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

const {
  decideReferralReward, deactivateReferralCode, issueReferralCode, listReferralCodes, listReferralRewards, referralLeaderboard,
} = vi.hoisted(() => {
  const pending: ReferralReward = {
    id: 1, referralCode: 3, code: 'AB12CD34', opportunity: 42, opportunityTitle: 'Deal 42', customerName: 'Buyer Co',
    referrerName: 'Ravi', rewardAmount: '25.00', basis: 'FLAT', rewardStatus: 'PENDING',
  };
  const code = {
    id: 3, code: 'AB12CD34', referrerCustomer: 5, referrerUser: null, referrerName: 'Ravi', rewardType: 'PERCENT',
    rewardValue: '10.00', active: true, deactivatedAt: null, uses: 2, rewardsEarned: 1,
  };
  return {
    decideReferralReward: vi.fn(async (id: number, decision: string) => ({ ...pending, id, rewardStatus: decision === 'approve' ? 'APPROVED' : 'REJECTED' })),
    deactivateReferralCode: vi.fn(async () => ({ ...code, active: false })),
    issueReferralCode: vi.fn(async () => ({ id: 3, code: 'AB12CD34' })),
    listReferralCodes: vi.fn(async () => ({ results: [code], count: 1, next: null, previous: null })),
    listReferralRewards: vi.fn(async () => ({ results: [pending], count: 1, next: null, previous: null })),
    referralLeaderboard: vi.fn(async () => [{ code: 'AB12CD34', referrerType: 'customer', referrerName: 'Ravi', approvedTotal: '25.00' }]),
  };
});

vi.mock('@/api/growth', () => ({
  decideReferralReward: (...args: unknown[]) => decideReferralReward(...args),
  deactivateReferralCode: (...args: unknown[]) => deactivateReferralCode(...args),
  issueReferralCode: (...args: unknown[]) => issueReferralCode(...args),
  listReferralCodes: () => listReferralCodes(),
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
  it('issues a code and shows it, and renders the leaderboard with the referrer name', async () => {
    role.current = 'OWNER';
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText(/AB12CD34 · Ravi/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'pick-customer' }));
    await user.click(screen.getByRole('button', { name: 'Issue code' }));

    await waitFor(() => expect(issueReferralCode).toHaveBeenCalledWith({
      referrer_customer: 5, reward_type: 'FLAT', reward_value: '0',
    }));
    expect(await screen.findByText('Code: AB12CD34')).toBeInTheDocument();
  });

  it('refuses a percent reward above 100', async () => {
    role.current = 'OWNER';
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/AB12CD34 · Ravi/);
    await user.click(screen.getByRole('button', { name: 'pick-customer' }));
    await user.click(screen.getByRole('combobox', { name: 'Reward type' }));
    await user.click(await screen.findByRole('option', { name: 'Percent of deal' }));
    const value = screen.getByLabelText('Reward value');
    await user.clear(value);
    await user.type(value, '150');
    expect(screen.getByText(/between 0 and 100/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Issue code' })).toBeDisabled();
  });

  it('lists codes with uses and lets a manager deactivate one after confirming', async () => {
    role.current = 'MANAGER';
    const user = userEvent.setup();
    wrap();
    const row = (await screen.findByText('Active')).closest('tr') as HTMLElement;
    expect(within(row).getByText('Ravi')).toBeInTheDocument();
    await user.click(within(row).getByRole('button', { name: 'Deactivate' }));
    expect(deactivateReferralCode).not.toHaveBeenCalled();
    await user.click(await screen.findByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(deactivateReferralCode).toHaveBeenCalledWith(3));
  });

  it('lets an OWNER approve a pending reward and shows names and a translated status', async () => {
    role.current = 'OWNER';
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText('Buyer Co')).toBeInTheDocument();
    expect(screen.getByText('Waiting for a decision')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark paid' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(decideReferralReward).toHaveBeenCalledWith(1, 'approve'));
  });

  it('asks before marking an approved reward paid, with neutral copy', async () => {
    role.current = 'OWNER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{
        id: 7, referralCode: 3, code: 'AB12CD34', opportunity: 42, referrerName: 'Ravi',
        rewardAmount: '0.00', basis: 'PERCENT', rewardStatus: 'APPROVED',
      }],
      count: 1, next: null, previous: null,
    });
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText('Set when paid')).toBeInTheDocument();
    expect(screen.queryByText(/Draft credit note/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/does not post a journal/i)).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Mark paid' }));
    expect(decideReferralReward).not.toHaveBeenCalledWith(7, 'mark-paid');
    expect(await screen.findByText(/creates and completes a credit note for Ravi/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(decideReferralReward).toHaveBeenCalledWith(7, 'mark-paid'));
  });

  it('lets a manager reverse an approved reward after confirming', async () => {
    role.current = 'MANAGER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{ id: 12, referralCode: 3, opportunity: 42, rewardAmount: '40.00', basis: 'FLAT', rewardStatus: 'APPROVED' }],
      count: 1, next: null, previous: null,
    });
    const user = userEvent.setup();
    wrap();
    await user.click(await screen.findByRole('button', { name: 'Reverse' }));
    expect(decideReferralReward).not.toHaveBeenCalledWith(12, 'reverse');
    await user.click(await screen.findByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(decideReferralReward).toHaveBeenCalledWith(12, 'reverse'));
  });

  it('warns on a reward for someone who was already a customer', async () => {
    role.current = 'OWNER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{
        id: 11, referralCode: 3, opportunity: 42, rewardAmount: '25.00', basis: 'FLAT',
        rewardStatus: 'PENDING', reviewNote: 'existing_customer',
      }],
      count: 1, next: null, previous: null,
    });
    wrap();
    expect(await screen.findByText(/Already a customer/)).toBeInTheDocument();
  });

  it('shows the self-referral reason on a rejected reward', async () => {
    role.current = 'OWNER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{
        id: 9, referralCode: 3, opportunity: 42, rewardAmount: '25.00', rewardStatus: 'REJECTED',
        rejectionReason: 'self_referral',
      }],
      count: 1, next: null, previous: null,
    });
    wrap();
    expect(await screen.findByText(/the referrer and the customer are the same person/)).toBeInTheDocument();
  });

  it('hides issuing and decisions from a non-owner, non-manager role', async () => {
    role.current = 'SALES_STAFF';
    wrap();
    await screen.findByText('Buyer Co');
    expect(screen.getByText(/Only an owner or manager can issue codes/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Issue code' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument();
  });

  it('hides mark paid once the reward is already paid', async () => {
    role.current = 'OWNER';
    listReferralRewards.mockResolvedValueOnce({
      results: [{ id: 8, referralCode: 3, opportunity: 42, rewardAmount: '40.00', basis: 'FLAT', rewardStatus: 'PAID' }],
      count: 1, next: null, previous: null,
    });
    wrap();
    await screen.findByText('Paid');
    expect(screen.queryByRole('button', { name: 'Mark paid' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
  });
});
