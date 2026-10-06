import { describe, expect, it } from 'vitest';
import { dialogAmountDirty, partyOrLinesDirty, returnDialogDirty } from './moneyFormDirty';

describe('money editor dirty flags', () => {
  it('delivery challan is dirty with a customer or a line, and clean when both are empty', () => {
    expect(partyOrLinesDirty('', 0)).toBe(false);
    expect(partyOrLinesDirty(4, 0)).toBe(true);
    expect(partyOrLinesDirty('', 1)).toBe(true);
  });

  it('a receipt dialog is dirty while open with a customer or a typed amount', () => {
    expect(dialogAmountDirty(false, true, '10')).toBe(false);
    expect(dialogAmountDirty(true, false, '')).toBe(false);
    expect(dialogAmountDirty(true, true, '')).toBe(true);
    expect(dialogAmountDirty(true, false, '25')).toBe(true);
  });

  it('a supplier payment dialog uses the same amount rule', () => {
    expect(dialogAmountDirty(true, false, '0')).toBe(false);
    expect(dialogAmountDirty(true, false, '1')).toBe(true);
  });

  it('a sales return dialog is dirty when a bill or a reason is present', () => {
    expect(returnDialogDirty(true, false, '')).toBe(false);
    expect(returnDialogDirty(true, true, '')).toBe(true);
    expect(returnDialogDirty(false, true, 'damaged')).toBe(false);
  });

  it('a purchase return dialog is clean after the dialog closes', () => {
    expect(returnDialogDirty(false, true, 'short')).toBe(false);
    expect(returnDialogDirty(true, false, 'short')).toBe(true);
  });
});
