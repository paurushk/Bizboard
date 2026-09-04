import { useEffect, useState } from 'react';
import { apiClient, shouldUseMocks, unwrapData } from '@/api/client';

export type RuntimeFeatureFlags = Record<string, boolean>;

let cachedFlags: RuntimeFeatureFlags | null = null;
let flagEpoch = 0;
const listeners = new Set<() => void>();

function notifyFeatureFlags() {
  flagEpoch += 1;
  listeners.forEach((fn) => fn());
}

export function subscribeFeatureFlags(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Re-render when runtime flags are fetched or cleared. */
export function useFeatureFlagEpoch(): number {
  const [epoch, setEpoch] = useState(flagEpoch);
  useEffect(() => subscribeFeatureFlags(() => setEpoch(flagEpoch)), []);
  return epoch;
}

// BB-000597: mock defaults keep ERP dark except POS, which stays on so
// item-custom-fields e2e can cover the POS finder without a live API.
const MOCK_FLAGS: RuntimeFeatureFlags = {
  ENABLE_MANUFACTURING: false,
  ENABLE_PAYROLL: false,
  ENABLE_CRM: false,
  ENABLE_TDS: false,
  ENABLE_WHATSAPP_CLOUD: false,
  ENABLE_ACCOUNT_AGGREGATOR: false,
  ENABLE_CASHFREE: false,
  ENABLE_PAYU: false,
  ENABLE_POS: true,
  ENABLE_ACCOUNTING: false,
  ENABLE_AI: false,
  ENABLE_GSTR: false,
  ENABLE_TALLY: false,
  ENABLE_SETUP_WIZARD: false,
  item_custom_fields_v2: true,
  itemCustomFieldsV2: true,
  helpV2: false,
};

export async function fetchFeatureFlags(force = false): Promise<RuntimeFeatureFlags> {
  if (!force && cachedFlags) return cachedFlags;
  if (shouldUseMocks()) {
    cachedFlags = { ...MOCK_FLAGS };
    notifyFeatureFlags();
    return cachedFlags;
  }
  try {
    const { data } = await apiClient.get('/feature-flags/');
    cachedFlags = unwrapData<RuntimeFeatureFlags>(data);
    notifyFeatureFlags();
    return cachedFlags;
  } catch (err) {
    // F1-017: a transient /feature-flags/ failure must not wipe the cache to
    // null — that silently strips Manufacturing/Payroll/CRM nav + routes for an
    // entitled tenant until the next successful refresh. Keep the last known
    // flags (or an empty map on a cold failure) and let the caller proceed.
    if (import.meta.env.DEV) {
      console.warn('[featureFlags] fetch failed, keeping cached flags', err);
    }
    return cachedFlags ?? {};
  }
}

export function getCachedFeatureFlags(): RuntimeFeatureFlags | null {
  return cachedFlags;
}

export function isRuntimeFlagEnabled(key: string): boolean {
  return Boolean(cachedFlags?.[key]);
}

export function clearFeatureFlagsCache() {
  cachedFlags = null;
  notifyFeatureFlags();
}
