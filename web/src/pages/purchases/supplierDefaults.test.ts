import { beforeEach, describe, expect, it } from 'vitest';
import { loadSupplierDefaults, saveSupplierDefaults } from './supplierDefaults';

describe('supplier defaults', () => {
  beforeEach(() => localStorage.clear());

  it('starts empty and remembers the last choice per supplier and company', () => {
    expect(loadSupplierDefaults(1, 7)).toBeNull();
    saveSupplierDefaults(1, 7, { itcEligibility: 'CLAIMABLE', isReverseCharge: true, paymentTermsDays: 45, tdsSection: '194C', tdsRate: 1 });
    expect(loadSupplierDefaults(1, 7)).toEqual({
      itcEligibility: 'CLAIMABLE',
      isReverseCharge: true,
      paymentTermsDays: 45,
      tdsSection: '194C',
      tdsRate: 1,
    });
    expect(loadSupplierDefaults(1, 8)).toBeNull();
    expect(loadSupplierDefaults(2, 7)).toBeNull();
  });

  it('survives broken storage', () => {
    localStorage.setItem('bizboard:purchase:supplierDefaults:1', '{not json');
    expect(loadSupplierDefaults(1, 7)).toBeNull();
    saveSupplierDefaults(1, 7, { itcEligibility: 'UNREVIEWED', isReverseCharge: false, paymentTermsDays: 0 });
    expect(loadSupplierDefaults(1, 7)?.paymentTermsDays).toBe(0);
  });
});
