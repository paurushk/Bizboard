import { describe, expect, it } from 'vitest';
import { documentSearchQuery, shortDocumentNumber } from './documentNumber';

describe('document numbers', () => {
  it('shows the sequence and financial year while keeping the full number searchable', () => {
    expect(shortDocumentNumber('INV-00013', '2026-05-02')).toBe('INV-13 · 2026-27');
    expect(documentSearchQuery('INV-13')).toBe('INV-00013');
    expect(documentSearchQuery('INV-13 · 2026-27')).toBe('INV-00013');
    expect(documentSearchQuery('INV-00013')).toBe('INV-00013');
  });
});
