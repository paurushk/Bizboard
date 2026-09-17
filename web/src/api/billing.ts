import { apiClient, unwrapData } from './client';
import { withMocks } from './legacy/common';
import { getStoredUser } from '@/auth/session';

export interface BillingPlan {
  id: number;
  name: string;
  slug: string;
  seatLimit: number;
  modules: Record<string, boolean>;
  pricePaise: number;
  razorpayPlanId?: string;
  isActive?: boolean;
  monthlyCompleteLimit?: number;
  storageBytesLimit?: number;
  apiRatePerMinute?: number;
}

export interface BillingUsageMeter {
  limit: number;
  used: number;
}

export interface BillingUsageSnapshot {
  seats: BillingUsageMeter;
  completes: BillingUsageMeter;
  storageBytes: BillingUsageMeter;
  apiRatePerMinute: number;
}

export interface BillingSubscription {
  id: number;
  status: 'trial' | 'active' | 'past_due' | 'suspended' | string;
  trialEndsAt?: string | null;
  razorpaySubscriptionId?: string;
  currentPeriodEnd?: string | null;
  plan?: BillingPlan;
  planId?: number;
  writeBlocked?: boolean;
  billingOverrideActive?: boolean;
  seatLimit?: number;
  quotas?: BillingUsageSnapshot;
}

export interface BillingDeadLetterEvent {
  id: number;
  provider: string;
  eventId: string;
  status: 'pending' | 'replayed' | 'discarded' | string;
  error: string;
  attempts: number;
  createdAt: string;
}

export async function listBillingPlans(): Promise<BillingPlan[]> {
  const { data } = await apiClient.get('/billing/plans/');
  const body = unwrapData<BillingPlan[] | { results?: BillingPlan[] }>(data);
  return Array.isArray(body) ? body : body.results ?? [];
}

export async function getBillingSubscription(): Promise<BillingSubscription | null> {
  return withMocks(
    async () => {
      const { data } = await apiClient.get('/billing/subscription/');
      const body = unwrapData<BillingSubscription | { subscription?: BillingSubscription | null }>(data);
      if (!body) return null;
      if ('subscription' in body && !('id' in body)) {
        return body.subscription ?? null;
      }
      return body as BillingSubscription;
    },
    () => {
      const email = getStoredUser()?.email?.toLowerCase() ?? '';
      if (email.includes('writes-blocked')) {
        return { id: 1, status: 'suspended', writeBlocked: true };
      }
      return { id: 1, status: 'active' };
    },
  );
}

export async function startBillingCheckout(planId: number): Promise<{
  subscription: BillingSubscription;
  checkoutOrderId: string;
  /** F3-033: present when the gateway returns a hosted-checkout page. */
  checkoutUrl?: string | null;
}> {
  const { data } = await apiClient.post('/billing/checkout/', { planId });
  return unwrapData(data);
}

export async function getBillingPortal(): Promise<{
  subscription: BillingSubscription | null;
  plans: BillingPlan[];
  portalUrl?: string | null;
  billingOverrideActive?: boolean;
  seatLimit?: number | null;
}> {
  const { data } = await apiClient.get('/billing/portal/');
  return unwrapData(data);
}

/** 9.5 gap fix: parked webhook/recon failures had no frontend surface at all. */
export async function listBillingDeadLetters(): Promise<BillingDeadLetterEvent[]> {
  const { data } = await apiClient.get('/billing/dlq/');
  const body = unwrapData<BillingDeadLetterEvent[]>(data);
  return Array.isArray(body) ? body : [];
}

export async function replayBillingDeadLetter(id: number): Promise<{ ok: boolean; status: string; id: number }> {
  const { data } = await apiClient.post(`/billing/dlq/${id}/replay/`);
  return unwrapData(data);
}
