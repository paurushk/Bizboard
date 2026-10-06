import { describe, expect, it } from 'vitest';
import { en } from './en';
import { hi } from './hi';

describe('payroll honesty (GM-62)', () => {
  it('says payslips are not Form 24Q in English and Hindi', () => {
    expect(en.honesty.payrollNot24q).toContain('Form 24Q');
    expect(hi.honesty.payrollNot24q).toContain('Form 24Q');
    expect(hi.honesty.payrollNot24q).not.toBe(en.honesty.payrollNot24q);
  });
});
