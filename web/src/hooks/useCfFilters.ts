import { useCallback, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { listProductCustomFieldValues } from '@/api/resources';
import { isItemCustomFieldsV2Enabled } from '@/config/features';

export type CfFilterMap = Record<string, string[]>;

export function parseCfSearchParams(params: URLSearchParams): CfFilterMap {
  const out: CfFilterMap = {};
  for (const [name, value] of params.entries()) {
    if (!name.startsWith('cf.') || !value.trim()) continue;
    const key = name.slice(3);
    (out[key] ??= []).push(value);
  }
  return out;
}

export function extraValuesFromProducts(
  products: Array<{ customFields?: Record<string, string> }> | undefined,
): Record<string, string[]> {
  const extra: Record<string, string[]> = {};
  for (const product of products ?? []) {
    for (const [key, value] of Object.entries(product.customFields ?? {})) {
      const text = String(value ?? '').trim();
      if (!text) continue;
      const bucket = extra[key] ?? [];
      if (!bucket.some((item) => item.toLowerCase() === text.toLowerCase())) bucket.push(text);
      extra[key] = bucket;
    }
  }
  return extra;
}

export function useCustomFieldExtraValues(enabled = true) {
  const query = useQuery({
    queryKey: ['products', 'cf-extra-values'],
    queryFn: listProductCustomFieldValues,
    enabled: enabled && isItemCustomFieldsV2Enabled(),
    staleTime: 60_000,
  });
  return query.data ?? {};
}

export function useCfFilters() {
  const [params, setParams] = useSearchParams();
  const enabled = isItemCustomFieldsV2Enabled();
  const value = useMemo(
    () => (enabled ? parseCfSearchParams(params) : {}),
    [enabled, params],
  );

  useEffect(() => {
    if (enabled) return;
    const stale = [...params.keys()].some((key) => key.startsWith('cf.'));
    if (!stale) return;
    const updated = new URLSearchParams(params);
    for (const key of [...updated.keys()]) {
      if (key.startsWith('cf.')) updated.delete(key);
    }
    setParams(updated, { replace: true });
  }, [enabled, params, setParams]);

  const onChange = useCallback(
    (next: CfFilterMap) => {
      const updated = new URLSearchParams(params);
      for (const key of [...updated.keys()]) {
        if (key.startsWith('cf.')) updated.delete(key);
      }
      for (const [key, values] of Object.entries(next)) {
        for (const item of values) {
          if (item.trim()) updated.append(`cf.${key}`, item);
        }
      }
      setParams(updated, { replace: true });
    },
    [params, setParams],
  );

  return { value, onChange };
}
