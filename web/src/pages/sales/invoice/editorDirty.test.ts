import { renderHook, act } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { snapshotDirty, useEditorBaseline } from '@/pages/sales/invoice/editorDirty';

describe('snapshotDirty', () => {
  it('is clean until a baseline exists and the snapshot changes', () => {
    expect(snapshotDirty('{"charges":0}', null)).toBe(false);
    expect(snapshotDirty('{"charges":0}', '{"charges":0}')).toBe(false);
    expect(snapshotDirty('{"charges":999}', '{"charges":0}')).toBe(true);
  });
});

describe('useEditorBaseline', () => {
  it('stays clean for the initial snapshot and dirties after an edit', () => {
    const { result, rerender } = renderHook(
      ({ snapshot }) => useEditorBaseline(snapshot, true),
      { initialProps: { snapshot: '{"manualName":""}' } },
    );
    expect(result.current.dirty).toBe(false);
    rerender({ snapshot: '{"manualName":"Walk-in"}' });
    expect(result.current.dirty).toBe(true);
  });

  it('treats a snapshot applied in the same turn as rearm as the new baseline', () => {
    const { result } = renderHook(() => {
      const [snapshot, setSnapshot] = useState('{"lines":[]}');
      const api = useEditorBaseline(snapshot, true);
      return { ...api, setSnapshot };
    });
    act(() => {
      result.current.rearm();
      result.current.setSnapshot('{"lines":[{"qty":1}]}');
    });
    expect(result.current.dirty).toBe(false);
  });

  it('still dirties the next edit after rearm on an unchanged form', () => {
    const { result } = renderHook(() => {
      const [snapshot, setSnapshot] = useState('{"lines":[]}');
      const api = useEditorBaseline(snapshot, true);
      return { ...api, setSnapshot };
    });
    act(() => result.current.rearm());
    act(() => result.current.setSnapshot('{"charges":999}'));
    expect(result.current.dirty).toBe(true);
  });

  it('recaptures when the editor becomes ready with a loaded bill', () => {
    const { result, rerender } = renderHook(
      ({ snapshot, ready }) => useEditorBaseline(snapshot, ready),
      { initialProps: { snapshot: '{"lines":[]}', ready: true } },
    );
    rerender({ snapshot: '{"lines":[{"qty":1}]}', ready: false });
    expect(result.current.dirty).toBe(false);
    rerender({ snapshot: '{"lines":[{"qty":2}]}', ready: true });
    expect(result.current.dirty).toBe(false);
    rerender({ snapshot: '{"lines":[{"qty":3}]}', ready: true });
    expect(result.current.dirty).toBe(true);
  });
});
