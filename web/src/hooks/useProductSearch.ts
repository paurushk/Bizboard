import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listProductsPage } from '@/api/resources';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { Product } from '@/types/domain';

/** Cap for product Autocomplete server search (BB-000118). */
export const PRODUCT_SEARCH_PAGE_SIZE = 200;
export const PRODUCT_SEARCH_MIN_CHARS = 2;

type UseProductSearchOptions = {
  /** When true, only ACTIVE products are offered. */
  activeOnly?: boolean;
  minChars?: number;
  pageSize?: number;
  /** Keep a currently selected product in options even if outside the current page. */
  selected?: Product | null;
};

/**
 * Server-side product search for Autocomplete pickers.
 * Requires minChars (default 2); uses listProductsPage and surfaces truncation.
 */
export function useProductSearch(opts: UseProductSearchOptions = {}) {
  const minChars = opts.minChars ?? PRODUCT_SEARCH_MIN_CHARS;
  const pageSize = opts.pageSize ?? PRODUCT_SEARCH_PAGE_SIZE;
  const [productQuery, setProductQuery] = useState('');
  const debounced = useDebouncedValue(productQuery, 300);
  const q = debounced.trim();
  const enabled = q.length >= minChars;

  const query = useQuery({
    queryKey: ['product-search-page', q, pageSize],
    queryFn: () => listProductsPage({ q, page: 1, pageSize }),
    enabled,
  });

  const options = useMemo(() => {
    let results = query.data?.results ?? [];
    if (opts.activeOnly) {
      results = results.filter((p) => p.status === 'ACTIVE');
    }
    if (opts.selected && !results.some((p) => p.id === opts.selected!.id)) {
      results = [opts.selected, ...results];
    }
    return results;
  }, [query.data?.results, opts.activeOnly, opts.selected]);

  const resultCount = query.data?.results.length ?? 0;
  const truncated =
    enabled && ((query.data?.count ?? 0) > resultCount || Boolean(query.data?.next));

  const helperText = !enabled
    ? productQuery.trim().length > 0
      ? `Type at least ${minChars} characters to search`
      : 'Type to search products'
    : truncated
      ? `Showing first ${pageSize} matches — refine your search`
      : undefined;

  return {
    productQuery,
    setProductQuery,
    options,
    isFetching: query.isFetching,
    truncated,
    helperText,
    enabled,
    count: query.data?.count ?? 0,
  };
}
