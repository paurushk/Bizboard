import { apiClient, unwrapData } from './client';

export interface BillingPlan {
  id: number;
  name: string;
  slug: string;
  seatLimit: number;
  modules: Record<string, boolean>;
  pricePaise: number;
  razorpayPlanId?: string;
  isActive?: boolean;
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
}

export async function listBillingPlans(): Promise<BillingPlan[]> {
  const { data } = await apiClient.get('/billing/plans/');
  const body = unwrapData<BillingPlan[] | { results?: BillingPlan[] }>(data);
  return Array.isArray(body) ? body : body.results ?? [];
}

export async function getBillingSubscription(): Promise<BillingSubscription | null> {
  const { data } = await apiClient.get('/billing/subscription/');
  const body = unwrapData<BillingSubscription | { subscription?: BillingSubscription | null }>(data);
  if (!body) return null;
  if ('subscription' in body && !('id' in body)) {
    return body.subscription ?? null;
  }
  return body as BillingSubscription;
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
