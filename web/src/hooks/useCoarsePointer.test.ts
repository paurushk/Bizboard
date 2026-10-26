import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useCoarsePointer } from './useCoarsePointer';

function stubPointer(coarse: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: coarse && query.includes('pointer: coarse'),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

/** BB-100 F5: phones skip the load-time focus and the keyboard-shortcut hints. */
describe('useCoarsePointer', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('is true on a touch-first device', () => {
    stubPointer(true);
    expect(renderHook(() => useCoarsePointer()).result.current).toBe(true);
  });

  it('is false with a mouse', () => {
    stubPointer(false);
    expect(renderHook(() => useCoarsePointer()).result.current).toBe(false);
  });
});
