import { apiClient, shouldUseMocks, unwrapData } from '@/api/client';

export type RuntimeFeatureFlags = Record<string, boolean>;

let cachedFlags: RuntimeFeatureFlags | null = null;

// BB-000597: mock defaults keep ERP dark. E2E that needs manufacturing/payroll/CRM
// must hit a live API (VITE_USE_MOCKS=false) with ENABLE_* — these stubs are not ERP coverage.
const MOCK_FLAGS: RuntimeFeatureFlags = {
  ENABLE_MANUFACTURING: false,
  ENABLE_PAYROLL: false,
  ENABLE_CRM: false,
  ENABLE_TDS: false,
  ENABLE_WHATSAPP_CLOUD: false,
  ENABLE_ACCOUNT_AGGREGATOR: false,
  ENABLE_CASHFREE: false,
  ENABLE_PAYU: false,
  ENABLE_POS: false,
  ENABLE_ACCOUNTING: false,
  ENABLE_AI: false,
  ENABLE_GSTR: false,
  ENABLE_TALLY: false,
  ENABLE_SETUP_WIZARD: false,
};

export async function fetchFeatureFlags(force = false): Promise<RuntimeFeatureFlags> {
  if (!force && cachedFlags) return cachedFlags;
  if (shouldUseMocks()) {
    cachedFlags = { ...MOCK_FLAGS };
    return cachedFlags;
  }
  const { data } = await apiClient.get('/feature-flags/');
  cachedFlags = unwrapData<RuntimeFeatureFlags>(data);
  return cachedFlags;
}

export function getCachedFeatureFlags(): RuntimeFeatureFlags | null {
  return cachedFlags;
}

export function isRuntimeFlagEnabled(key: string): boolean {
  return Boolean(cachedFlags?.[key]);
}

export function clearFeatureFlagsCache() {
  cachedFlags = null;
}
