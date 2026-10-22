import { describe, expect, it } from 'vitest';
import {
  cleanNationalNumber,
  countryForCallingCode,
  findPhoneCountry,
  isValidPhoneValue,
  joinPhone,
  splitPhone,
} from '@/utils/phone';

const india = findPhoneCountry('IN');

describe('phone utils', () => {
  it('cleans what people type or paste into 10 Indian digits', () => {
    expect(cleanNationalNumber('98765 43210', india)).toBe('9876543210');
    expect(cleanNationalNumber('09876543210', india)).toBe('9876543210');
    expect(cleanNationalNumber('+91 98765-43210', india)).toBe('9876543210');
    expect(cleanNationalNumber('919876543210', india)).toBe('9876543210');
    // A 10-digit number that happens to start with 91 is left alone.
    expect(cleanNationalNumber('9198765432', india)).toBe('9198765432');
    expect(cleanNationalNumber('98765432109999', india)).toBe('9876543210');
    // An 11th digit on a number starting 91 is not the calling code.
    expect(cleanNationalNumber('91987654321', india)).toBe('9198765432');
    expect(cleanNationalNumber('9109876543210', india)).toBe('9876543210');
    expect(cleanNationalNumber('97150123456', findPhoneCountry('AE'))).toBe('50123456');
  });

  it('joins and splits E.164 round-trip', () => {
    expect(joinPhone('IN', '9876543210')).toBe('+919876543210');
    expect(joinPhone('IN', '')).toBe('');
    expect(splitPhone('+919876543210')).toEqual({ iso: 'IN', national: '9876543210' });
    expect(splitPhone('+971501234567')).toEqual({ iso: 'AE', national: '501234567' });
    expect(splitPhone('')).toEqual({ iso: 'IN', national: '' });
    // Legacy 10-digit value with no code is read as India.
    expect(splitPhone('9876543210')).toEqual({ iso: 'IN', national: '9876543210' });
  });

  it('picks the longest calling code', () => {
    expect(countryForCallingCode('+971 50 123 4567')?.iso).toBe('AE');
    expect(countryForCallingCode('+1 415 555 0100')?.iso).toBe('US');
    expect(countryForCallingCode('+999')).toBeUndefined();
  });

  it('validates a complete number for its country', () => {
    expect(isValidPhoneValue('')).toBe(true);
    expect(isValidPhoneValue('+919876543210')).toBe(true);
    expect(isValidPhoneValue('+91987654321')).toBe(false);
    expect(isValidPhoneValue('+915876543210')).toBe(false);
    expect(isValidPhoneValue('9876543210')).toBe(false);
    expect(isValidPhoneValue('+971501234567')).toBe(true);
  });
});
