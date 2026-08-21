import { describe, expect, it } from 'vitest';
import {
  companyStepIncompleteNeedsGst,
  preferredInvoiceType,
  shopDetailsComplete,
} from '@/onboarding/taxHints';
import type { Company } from '@/types/domain';

const base = {
  id: 1,
  name: 'Shop',
  registrationType: 'REGULAR' as const,
  state: 'Karnataka',
  negativeStockPolicy: 'BLOCK' as const,
};

describe('taxHints', () => {
  it('requires GSTIN for Regular shop details step', () => {
    const company = { ...base, address: '1 Road', gstin: '' } as Company;
    expect(shopDetailsComplete(company)).toBe(true);
    expect(companyStepIncompleteNeedsGst(company)).toBe(true);
  });

  it('prefers NON_GST for unregistered and composition', () => {
    expect(preferredInvoiceType('UNREGISTERED')).toBe('NON_GST');
    expect(preferredInvoiceType('COMPOSITION')).toBe('NON_GST');
    expect(preferredInvoiceType('REGULAR')).toBe('GST');
  });
});
