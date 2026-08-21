import Box from '@mui/material/Box';
import { useVirtualizer, type VirtualItem } from '@tanstack/react-virtual';
import { useRef, type ReactNode } from 'react';

/** Wave 19F: windowed row children when `rowCount` is provided; otherwise a contained scroller. */
export function VirtualizedTable({
  children,
  maxHeight = 560,
  rowCount,
  rowHeight = 52,
}: {
  children: ReactNode | ((rows: VirtualItem[]) => ReactNode);
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
          {children(virtualizer.getVirtualItems())}
        </Box>
      </Box>
    );
  }

  return (
    <Box ref={parentRef} sx={{ maxHeight, overflow: 'auto', contain: 'layout paint', width: '100%' }}>
      {typeof children === 'function' ? children([]) : children}
    </Box>
  );
}
