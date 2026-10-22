/** WP-GR2: the home-screen onboarding checklist. */
import { apiClient, shouldUseMocks, unwrapData } from './client';

export type OnboardingStep =
  | 'gstin_verified'
  | 'first_item'
  | 'first_party'
  | 'first_invoice'
  | 'first_purchase'
  | 'first_payment'
  | 'invited_user'
  | 'imported';

export interface OnboardingState {
  steps: Array<{ step: OnboardingStep; doneAt: string | null }>;
  done: number;
  total: number;
  dismissed: boolean;
  visible: boolean;
}

export async function getOnboarding(): Promise<OnboardingState | null> {
  if (shouldUseMocks()) return null;
  const { data } = await apiClient.get('/billing/onboarding/');
  return unwrapData<OnboardingState>(data) ?? null;
}

export async function dismissOnboarding(): Promise<OnboardingState> {
  const { data } = await apiClient.post('/billing/onboarding/dismiss/');
  return unwrapData(data);
}
