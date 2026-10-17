import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listLeadsPage, type Lead } from '@/api/crm';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';

/** Server-side lead search for pickers, so a company with more than one page of leads can still find any of them. */
export function useLeadSearch(opts: { selected?: Pick<Lead, 'id' | 'name'> | null } = {}) {
  const [query, setQuery] = useState('');
  const q = useDebouncedValue(query, 300).trim();
  const result = useQuery({
    queryKey: ['lead-search-page', q],
    queryFn: () => listLeadsPage({ q: q || undefined, page: 1, pageSize: 50 }),
  });
  const options = useMemo(() => {
    const rows = (result.data?.results ?? []) as Array<Pick<Lead, 'id' | 'name'>>;
    const selected = opts.selected;
    return selected && !rows.some((row) => row.id === selected.id) ? [selected, ...rows] : rows;
  }, [result.data, opts.selected]);
  return { options, setQuery, isFetching: result.isFetching };
}
