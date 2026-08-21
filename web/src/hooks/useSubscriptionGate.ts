import { useQuery } from '@tanstack/react-query';
import { getBillingSubscription, type BillingSubscription } from '@/api/billing';
import { shouldUseMocks } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';

export function subscriptionWritesBlocked(sub: BillingSubscription | null | undefined): boolean {
  if (!sub) return false;
  if (sub.billingOverrideActive) return false;
  if (sub.writeBlocked) return true;
  if (sub.status === 'suspended') return true;
  if (sub.status === 'trial' && sub.trialEndsAt) {
    const ends = Date.parse(sub.trialEndsAt);
    if (!Number.isNaN(ends) && ends < Date.now()) return true;
  }
  return false;
}

export function useSubscriptionGate() {
  const { user, isAuthenticated } = useAuth();
  const query = useQuery({
    queryKey: ['billing-subscription', user?.companyId],
    queryFn: getBillingSubscription,
    enabled: isAuthenticated && !shouldUseMocks(),
    staleTime: 30_000,
  });
  const subscription = query.data;
  return {
    subscription,
    writesBlocked: subscriptionWritesBlocked(subscription),
    isLoading: query.isLoading,
    refetch: query.refetch,
  };
}
