/**
 * RPT-02: an empty state is only honest once the load succeeded. A failed refetch under
 * keepPreviousData can still hold the previous filter's data, so isError is checked too.
 */
export function showEmpty(
  q: { isLoading: boolean; isError: boolean; data?: unknown },
  rowCount: number,
): boolean {
  return !q.isLoading && !q.isError && q.data !== undefined && rowCount === 0;
}
