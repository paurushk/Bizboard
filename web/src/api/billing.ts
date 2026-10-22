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
  /** WP-BL3: a change waiting for the period end, or an upgrade already in effect. */
  pendingPlanName?: string;
  upgradePlanName?: string;
  upgradeGraceUntil?: string | null;
  prorationAmountPaise?: number;
  prorationPaidAt?: string | null;
  /** WP-BL4: how renewals are collected and the mandate's state. */
  paymentMethod?: string;
  mandateStatus?: string;
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
  /** WP-BL3: the one-time prorated charge for an upgrade. */
  prorationUrl?: string | null;
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

/** WP-BL2: Bizboard's own GST invoices and credit notes to this company. */
export interface PlatformInvoice {
  id: number;
  kind: 'INVOICE' | 'CREDIT_NOTE';
  number: string;
  financialYear: string;
  originalNumber: string;
  createdAt: string;
  buyerGstin: string;
  buyerLegalName: string;
  placeOfSupply: string;
  sacCode: string;
  taxableAmount: string;
  cgst: string;
  sgst: string;
  igst: string;
  total: string;
}

export async function listPlatformInvoices(): Promise<PlatformInvoice[]> {
  const { data } = await apiClient.get('/billing/invoices/');
  const body = unwrapData<PlatformInvoice[]>(data);
  return Array.isArray(body) ? body : [];
}

/** WP-BL1: TDS deducted on Bizboard's fees, claimed back with Form 16A. */
export interface TdsSection {
  code: string;
  label: string;
  rate: string;
}

export interface TdsClaim {
  id: number;
  status: 'SUBMITTED' | 'VERIFIED' | 'SETTLED' | 'REJECTED';
  section: string;
  rate: string;
  taxableTotal: string;
  amount: string;
  quarter: string;
  invoiceNumbers: string[];
  reviewNote: string;
  createdAt: string;
  settleBy: 'CREDIT' | 'REFUND';
  creditRemaining: string;
}

export async function getTdsClaims(): Promise<{ claims: TdsClaim[]; sections: TdsSection[] }> {
  const { data } = await apiClient.get('/billing/tds-claims/');
  return unwrapData(data);
}

export async function submitTdsClaim(input: {
  invoiceIds: number[];
  section: string;
  certificateId: number;
  settleBy: 'CREDIT' | 'REFUND';
}): Promise<TdsClaim> {
  const { data } = await apiClient.post('/billing/tds-claims/', {
    invoice_ids: input.invoiceIds,
    section: input.section,
    certificate_id: input.certificateId,
    settle_by: input.settleBy,
  });
  return unwrapData(data);
}

/** WP-BL1 (Q5): refund the credit still left on a claim instead of taking it off renewals. */
export async function refundTdsClaim(id: number): Promise<TdsClaim> {
  const { data } = await apiClient.post(`/billing/tds-claims/${id}/refund/`);
  return unwrapData(data);
}
