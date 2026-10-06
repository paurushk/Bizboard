import { describe, expect, it } from 'vitest';
import {
  companyStepIncompleteNeedsGst,
  preferredInvoiceType,
  resolvedSeriesGstin,
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

  it('uses seriesGstin when the payload includes it', () => {
    const stampOnly = { ...base, gstin: '', seriesGstin: '29ABCDE1234F1ZW' } as Company;
    expect(resolvedSeriesGstin(stampOnly)).toBe('29ABCDE1234F1ZW');
    expect(companyStepIncompleteNeedsGst(stampOnly)).toBe(false);
    const headOfficeOnly = { ...base, gstin: '29AAAAA0000A1ZY' } as Company;
    expect(resolvedSeriesGstin(headOfficeOnly)).toBe('29AAAAA0000A1ZY');
    expect(companyStepIncompleteNeedsGst(headOfficeOnly)).toBe(false);
    const emptySeries = { ...base, gstin: '29AAAAA0000A1ZY', seriesGstin: '' } as Company;
    expect(companyStepIncompleteNeedsGst(emptySeries)).toBe(true);
  });

  it('prefers NON_GST for unregistered and composition', () => {
    expect(preferredInvoiceType('UNREGISTERED')).toBe('NON_GST');
    expect(preferredInvoiceType('COMPOSITION')).toBe('NON_GST');
    expect(preferredInvoiceType('REGULAR')).toBe('GST');
  });
});
