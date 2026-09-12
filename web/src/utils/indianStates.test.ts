import { describe, expect, it } from 'vitest';
import { getStateFromGstin, GSTIN_STATE_CODE_TO_NAME, INDIAN_STATES } from '@/utils/indianStates';

/**
 * QOS-0037 — the GSTIN's first two digits are the GST state code; onboarding /
 * party forms derive the state from it instead of asking twice. This pins the
 * decode.
 */
describe('getStateFromGstin', () => {
  it('decodes the leading state code of a full GSTIN', () => {
    expect(getStateFromGstin('29AAAAA0000A1ZY')).toBe('Karnataka');
    expect(getStateFromGstin('27AAAAA0000A1Z5')).toBe('Maharashtra');
    expect(getStateFromGstin('07AAAAA0000A1Z5')).toBe('Delhi');
  });

  it('works from just the first two digits', () => {
    expect(getStateFromGstin('33')).toBe('Tamil Nadu');
  });

  it('returns undefined for blank / too-short / unknown codes', () => {
    expect(getStateFromGstin('')).toBeUndefined();
    expect(getStateFromGstin('2')).toBeUndefined();
    expect(getStateFromGstin('99XXXXX0000X1ZZ')).toBeUndefined();
  });

  it('every mapped state name is a valid Indian state', () => {
    for (const name of Object.values(GSTIN_STATE_CODE_TO_NAME)) {
      expect(INDIAN_STATES).toContain(name);
    }
  });
});
