import { describe, expect, it } from 'vitest';
import { summarizeGstr3b } from '@/pages/reports/gstr3bSummary';

const base = {
  outward_supplies: { igst: '0.00', cgst: '90.00', sgst: '90.00', cess: '10.00' },
  inward_supplies: { reverse_charge: { igst: '0.00', cgst: '9.00', sgst: '9.00', cess: '2.00' } },
  itc: {
    recommended_claimable: { igst: '0', cgst: '40.00', sgst: '40.00', cess: '0', basis: 'min(books, gstr2b_matched)' },
    books_itc: { igst: '0', cgst: '50.00', sgst: '50.00', cess: '0' },
    reversed_ineligible: {
      reversed: { count: 1, igst: '0', cgst: '9.00', sgst: '9.00', cess: '0', total_tax: '18.00' },
      ineligible: { count: 2, igst: '5.00', cgst: '0', sgst: '0', cess: '0', total_tax: '5.00' },
      needs_ca_confirmation: true,
      gstr2b_flagged: { count: 3 },
    },
  },
  tax_payable_summary: { net_payable_hint: '102.00' },
};

describe('summarizeGstr3b', () => {
  it('uses the backend net payable, which already includes RCM and cess', () => {
    const s = summarizeGstr3b(base);
    expect(s.outwardTax).toBe(190);
    expect(s.rcmTax).toBe(20);
    expect(s.claimableItc).toBe(80);
    // 190 + 20 - 80 = 130 would be the client sum; the backend hint is what is shown
    expect(s.netPayable).toBe(102);
    expect(s.payableToShow).toBe(102);
    expect(s.carryForward).toBe(0);
  });

  it('shows a credit as carry-forward, not as zero payable and nothing else', () => {
    const s = summarizeGstr3b({ ...base, tax_payable_summary: { net_payable_hint: '-250.00' } });
    expect(s.payableToShow).toBe(0);
    expect(s.carryForward).toBe(250);
  });

  it('says not available instead of inventing a figure when the payload has none', () => {
    const s = summarizeGstr3b({ ...base, tax_payable_summary: undefined });
    expect(s.netPayable).toBeNull();
  });

  it('reads the 4(B) block per head and the CA flag', () => {
    const s = summarizeGstr3b(base);
    expect(s.reversed).toMatchObject({ count: 1, total: 18, cgst: 9, sgst: 9 });
    expect(s.ineligible).toMatchObject({ count: 2, total: 5, igst: 5 });
    expect(s.needsCaConfirmation).toBe(true);
    expect(s.gstr2bFlaggedCount).toBe(3);
  });

  it('knows whether any 2B-matched ITC backs the claim', () => {
    expect(summarizeGstr3b(base).hasMatched2b).toBe(true);
    const none = summarizeGstr3b({ ...base, itc: { ...base.itc, recommended_claimable: { igst: '0', basis: 'books_provisional_no_2b' } } });
    expect(none.hasMatched2b).toBe(false);
  });

  it('accepts camelCase payloads too', () => {
    const s = summarizeGstr3b({ taxPayableSummary: { netPayableHint: '7.00' }, outwardSupplies: { cgst: '1' } });
    expect(s.netPayable).toBe(7);
    expect(s.outwardTax).toBe(1);
  });
});
