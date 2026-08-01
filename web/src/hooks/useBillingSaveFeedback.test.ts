import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  primarySaveAction,
  useBillingSaveFeedback,
} from '@/hooks/useBillingSaveFeedback';

describe('primarySaveAction', () => {
  it('labels create / draft-edit as Save & Complete (does not silently Complete under Save)', () => {
    expect(primarySaveAction({ isEdit: false, editingStatus: null })).toEqual({
      mode: 'complete',
      labelKey: 'billing.saveAndComplete',
    });
    expect(primarySaveAction({ isEdit: true, editingStatus: 'DRAFT' })).toEqual({
      mode: 'complete',
      labelKey: 'billing.saveAndComplete',
    });
  });

  it('labels editing a completed document as Save (update only)', () => {
    expect(primarySaveAction({ isEdit: true, editingStatus: 'COMPLETED' })).toEqual({
      mode: 'save',
      labelKey: 'common.save',
    });
  });
});

describe('useBillingSaveFeedback', () => {
  it('BUG-500/501: Save & New keeps success message when form reset runs in the same tick', () => {
    const { result } = renderHook(() => useBillingSaveFeedback());

    act(() => {
      // Mimic onSuccess for complete_new: set flash, then reset fields.
      result.current.flashSaveAndNew('Invoice INV-00001 saved — start the next one');
      // resetForm intentionally does NOT call clearFeedback — prove message survives.
    });

    expect(result.current.message).toBe('Invoice INV-00001 saved — start the next one');
    expect(result.current.error).toBeNull();
  });

  it('BUG-500/501: payment warning survives Save & New alongside success', () => {
    const { result } = renderHook(() => useBillingSaveFeedback());

    act(() => {
      result.current.flashSaveAndNew(
        'Purchase PUR-00001 saved — start the next one',
        'Allocation failed: insufficient balance',
      );
    });

    expect(result.current.message).toBe('Purchase PUR-00001 saved — start the next one');
    expect(result.current.error).toBe('Allocation failed: insufficient balance');
  });

  it('clearFeedback wipes both message and error (document switch / new attempt)', () => {
    const { result } = renderHook(() => useBillingSaveFeedback());

    act(() => {
      result.current.flashSaveAndNew('ok', 'warn');
      result.current.clearFeedback();
    });

    expect(result.current.message).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
