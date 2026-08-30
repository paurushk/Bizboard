import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { isItemCustomFieldsV2Enabled } from '@/config/features';
import { activeCustomFieldDefs } from '@/pages/inventory/itemCustomFieldDefaults';

export function useActiveCustomFieldDefs() {
  const { user } = useAuth();
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany });
  return useMemo(
    () =>
      activeCustomFieldDefs(
        companyQuery.data?.itemCustomFieldDefs ?? user?.company?.itemCustomFieldDefs,
      ),
    [companyQuery.data?.itemCustomFieldDefs, user?.company?.itemCustomFieldDefs],
  );
}

/** Columns / filters / POS finder — hidden when the utilization flag is off. Capture still uses useActiveCustomFieldDefs. */
export function useVisibleCustomFieldDefs() {
  const defs = useActiveCustomFieldDefs();
  return isItemCustomFieldsV2Enabled() ? defs : [];
}

