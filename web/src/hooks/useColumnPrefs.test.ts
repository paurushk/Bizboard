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
