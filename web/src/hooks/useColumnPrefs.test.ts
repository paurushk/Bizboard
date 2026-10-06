import { afterEach, describe, expect, it } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useColumnPrefs } from './useColumnPrefs';

const COLUMNS = [
  { id: 'name', label: 'Name', group: 'standard' as const, removable: false },
  { id: 'sku', label: 'SKU', group: 'standard' as const },
  { id: 'cf:color', label: 'Color', group: 'custom' as const },
];

describe('useColumnPrefs', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('defaults to all visible and persists hidden ids', () => {
    const { result } = renderHook(() => useColumnPrefs('items', COLUMNS, 1, 2));
    expect(result.current.isVisible('cf:color')).toBe(true);
    act(() => result.current.toggle('cf:color'));
    expect(result.current.isVisible('cf:color')).toBe(false);
    expect(JSON.parse(localStorage.getItem('bb:cols:1:2:items') ?? '{}').hidden).toEqual(['cf:color']);
  });

  it('falls back to all visible when storage is corrupt', () => {
    localStorage.setItem('bb:cols:1:2:items', '{not json');
    const { result } = renderHook(() => useColumnPrefs('items', COLUMNS, 1, 2));
    expect(result.current.visibleIds).toEqual(['name', 'sku', 'cf:color']);
  });
});

describe('useColumnPrefs when the owner changes', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('reloads the saved columns when the user or company changes', () => {
    localStorage.setItem('bb:cols:1:2:items', JSON.stringify({ hidden: ['sku'] }));
    localStorage.setItem('bb:cols:1:3:items', JSON.stringify({ hidden: ['cf:color'] }));
    const { result, rerender } = renderHook(
      ({ userId }: { userId: number }) => useColumnPrefs('items', COLUMNS, 1, userId),
      { initialProps: { userId: 2 } },
    );
    expect(result.current.isVisible('sku')).toBe(false);
    expect(result.current.isVisible('cf:color')).toBe(true);

    rerender({ userId: 3 });
    expect(result.current.isVisible('sku')).toBe(true);
    expect(result.current.isVisible('cf:color')).toBe(false);
  });

  it('shows every column when there is no signed-in owner', () => {
    localStorage.setItem('bb:cols:1:2:items', JSON.stringify({ hidden: ['sku'] }));
    const { result, rerender } = renderHook(
      ({ userId }: { userId: number | null }) => useColumnPrefs('items', COLUMNS, 1, userId),
      { initialProps: { userId: 2 as number | null } },
    );
    expect(result.current.isVisible('sku')).toBe(false);
    rerender({ userId: null });
    expect(result.current.isVisible('sku')).toBe(true);
  });

  it('never hides a column that cannot be removed', () => {
    localStorage.setItem('bb:cols:1:2:items', JSON.stringify({ hidden: ['name'] }));
    const { result } = renderHook(() => useColumnPrefs('items', COLUMNS, 1, 2));
    expect(result.current.isVisible('name')).toBe(true);
  });
});
