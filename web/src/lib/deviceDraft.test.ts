import { afterEach, describe, expect, it } from 'vitest';
import {
  DRAFT_TTL_MS,
  clearForUser,
  draftKey,
  legacyPosCartKey,
  readDraft,
  writeDraft,
} from './deviceDraft';

afterEach(() => {
  localStorage.clear();
});

describe('deviceDraft', () => {
  it('round-trips a payload for the same company and user', () => {
    expect(writeDraft(1, 2, 'sales-invoice', { partyId: 9 }).ok).toBe(true);
    const read = readDraft<{ partyId: number }>(1, 2, 'sales-invoice');
    expect(read.ok).toBe(true);
    if (read.ok) expect(read.payload.partyId).toBe(9);
  });

  it('hides a draft from another user', () => {
    writeDraft(1, 2, 'pos-sessions', { n: 1 });
    expect(readDraft(1, 3, 'pos-sessions').ok).toBe(false);
  });

  it('discards a draft older than 36 hours', () => {
    localStorage.setItem(
      draftKey(1, 2, 'sales-invoice'),
      JSON.stringify({ version: 1, savedAt: new Date(Date.now() - DRAFT_TTL_MS - 1000).toISOString(), payload: { a: 1 } }),
    );
    expect(readDraft(1, 2, 'sales-invoice').ok).toBe(false);
    expect(localStorage.getItem(draftKey(1, 2, 'sales-invoice'))).toBeNull();
  });

  it('discards an unknown schema version', () => {
    localStorage.setItem(draftKey(1, 2, 'sales-invoice'), JSON.stringify({ version: 0, savedAt: new Date().toISOString(), payload: {} }));
    const read = readDraft(1, 2, 'sales-invoice');
    expect(read.ok).toBe(false);
    if (!read.ok) expect(read.reason).toBe('version');
  });

  it('reports quota when setItem throws', () => {
    const orig = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('quota');
    };
    try {
      expect(writeDraft(1, 2, 'sales-invoice', { a: 1 })).toEqual({ ok: false, reason: 'quota' });
    } finally {
      Storage.prototype.setItem = orig;
    }
  });

  it('clearForUser removes drafts and the legacy cart key', () => {
    writeDraft(4, 8, 'pos-sessions', { bills: [] });
    writeDraft(4, 8, 'sales-invoice', { lines: [1] });
    localStorage.setItem(legacyPosCartKey(4), '[]');
    clearForUser(4, 8);
    expect(readDraft(4, 8, 'pos-sessions').ok).toBe(false);
    expect(readDraft(4, 8, 'sales-invoice').ok).toBe(false);
    expect(localStorage.getItem(legacyPosCartKey(4))).toBeNull();
  });
});
