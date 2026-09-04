import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listCustomersPage, listSuppliersPage } from '@/api/resources';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { Customer, Supplier } from '@/types/domain';

/**
 * F2-025/F3-018: server-side customer/supplier search for Autocomplete
 * pickers, mirroring useProductSearch — was `listCustomers()`/`listSuppliers()`
 * pulling every row (or a bare pageSize:100 slice) into client-only filtering
 * across many editors; beyond the page cap a party was simply unselectable.
 */
export const PARTY_SEARCH_PAGE_SIZE = 100;
export const PARTY_SEARCH_MIN_CHARS = 2;

type UsePartySearchOptions<T> = {
  minChars?: number;
  pageSize?: number;
  /** Keep a currently selected party in options even if outside the current page. */
  selected?: T | null;
};

function usePartySearchBase<T extends { id: number }>(
  queryKeyPrefix: string,
  fetchPage: (params: { q?: string; page: number; pageSize: number }) => Promise<{ results: T[] }>,
  opts: UsePartySearchOptions<T>,
) {
  const minChars = opts.minChars ?? PARTY_SEARCH_MIN_CHARS;
  const pageSize = opts.pageSize ?? PARTY_SEARCH_PAGE_SIZE;
  const [query, setQuery] = useState('');
  const debounced = useDebouncedValue(query, 300);
  const q = debounced.trim();
  const enabled = q.length >= minChars;

  const result = useQuery({
    queryKey: [queryKeyPrefix, q, pageSize],
    queryFn: () => fetchPage({ q: q || undefined, page: 1, pageSize }),
    enabled,
  });

  let options = result.data?.results ?? [];
  if (opts.selected && !options.some((o) => o.id === opts.selected!.id)) {
    options = [opts.selected, ...options];
  }

  return {
    query,
    setQuery,
    options,
    isFetching: result.isFetching,
    enabled,
  };
}

export function useCustomerSearch(opts: UsePartySearchOptions<Customer> = {}) {
  return usePartySearchBase<Customer>('customer-search-page', listCustomersPage, opts);
}

export function useSupplierSearch(opts: UsePartySearchOptions<Supplier> = {}) {
  return usePartySearchBase<Supplier>('supplier-search-page', listSuppliersPage, opts);
}
