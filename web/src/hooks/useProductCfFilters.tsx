import { useMemo, useState } from 'react';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { isItemCustomFieldsV2Enabled } from '@/config/features';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import type { CfFilterMap } from '@/hooks/useCfFilters';

export function useProductCfFilters() {
  const enabled = isItemCustomFieldsV2Enabled();
  const defs = useVisibleCustomFieldDefs();
  const [cfFilters, setCfFilters] = useState<CfFilterMap>({});
  const filterBar = useMemo(
    () =>
      enabled ? (
        <CustomFieldFilterBar defs={defs} value={cfFilters} onChange={setCfFilters} compact />
      ) : null,
    [enabled, defs, cfFilters],
  );
  return {
    cfFilters: enabled ? cfFilters : undefined,
    filterBar,
    enabled,
    defs,
  };
}
