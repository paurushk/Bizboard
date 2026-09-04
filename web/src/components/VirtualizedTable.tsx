import Box from '@mui/material/Box';
import { useVirtualizer, type VirtualItem, type Virtualizer } from '@tanstack/react-virtual';
import { useRef, type ReactNode } from 'react';

/** F3-042: what a render-prop consumer needs to size rows dynamically instead
 * of re-deriving spacer heights from the same `rowHeight` magic number the
 * virtualizer was seeded with (estimateSize is only a starting guess). */
export type VirtualizedTableRenderArgs = {
  rows: VirtualItem[];
  /** Total content height — use this for the trailing spacer, not `rows.length * rowHeight`. */
  totalSize: number;
  /** Attach as `ref` on each row's DOM node (with `data-index={row.index}` on
   * the same node) so react-virtual measures its real rendered height —
   * required for any row that can wrap to more than one line. */
  measureElement: Virtualizer<HTMLDivElement, Element>['measureElement'];
};

/** Wave 19F: windowed row children when `rowCount` is provided; otherwise a contained scroller. */
export function VirtualizedTable({
  children,
  maxHeight = 560,
  rowCount,
  rowHeight = 52,
}: {
  children: ReactNode | ((args: VirtualizedTableRenderArgs) => ReactNode);
  maxHeight?: number;
  rowCount?: number;
  rowHeight?: number;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rowCount ?? 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
    enabled: typeof rowCount === 'number' && rowCount > 0,
  });

  if (typeof rowCount === 'number' && typeof children === 'function') {
    return (
      // UXW2B-007 (regression of BB-000117): `contain: 'strict'` implies size
      // containment, which needs a *definite* height to do anything — with only
      // `maxHeight` set (no `height`), the box collapsed to 0px, so react-virtual's
      // ResizeObserver measured a 0-height viewport and getVirtualItems() always
      // returned []. `contain: 'layout paint'` keeps the perf isolation without
      // requiring a definite height.
      <Box ref={parentRef} sx={{ maxHeight, overflow: 'auto', contain: 'layout paint', width: '100%' }}>
        <Box sx={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
          {children({
            rows: virtualizer.getVirtualItems(),
            totalSize: virtualizer.getTotalSize(),
            measureElement: virtualizer.measureElement,
          })}
        </Box>
      </Box>
    );
  }

  return (
    <Box ref={parentRef} sx={{ maxHeight, overflow: 'auto', contain: 'layout paint', width: '100%' }}>
      {typeof children === 'function'
        ? children({ rows: [], totalSize: 0, measureElement: virtualizer.measureElement })
        : children}
    </Box>
  );
}
