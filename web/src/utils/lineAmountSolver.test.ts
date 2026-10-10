import { describe, expect, it } from 'vitest';
import { calculateLineTax } from '@/utils/tax';
import { priceForLineAmount } from '@/utils/lineAmountSolver';

describe('priceForLineAmount', () => {
  it('turns ₹221.26 at 18% intra-state into ₹187.50', () => {
    const solved = priceForLineAmount({
      amount: 221.26,
      quantity: 1,
      discountPercent: 0,
      gstRate: 18,
      intraState: true,
    });
    expect(solved.unitPrice).toBe(187.5);
    expect(calculateLineTax({
      quantity: 1,
      unitPrice: solved.unitPrice,
      discountPercent: 0,
      gstRate: 18,
      intraState: true,
    }).lineTotal).toBe(221.26);
    expect(solved.difference).toBe(0);
  });

  it('splits a non-GST amount across quantity', () => {
    const solved = priceForLineAmount({
      amount: 100,
      quantity: 2,
      gstRate: 0,
      intraState: true,
    });
    expect(solved.unitPrice).toBe(50);
    expect(solved.lineTotal).toBe(100);
  });

  it('does not divide when quantity is 0', () => {
    const solved = priceForLineAmount({
      amount: 80,
      quantity: 0,
      keepUnitPrice: 187.5,
      gstRate: 18,
      intraState: true,
    });
    expect(solved.unitPrice).toBe(187.5);
    expect(solved.lineTotal).toBe(0);
  });

  it('keeps a rupee discount fixed while solving the rate', () => {
    const solved = priceForLineAmount({
      amount: 100,
      quantity: 2,
      discountAmount: 10,
      gstRate: 0,
      intraState: null,
    });
    const forward = calculateLineTax({
      quantity: 2,
      unitPrice: solved.unitPrice,
      discountAmount: 10,
      gstRate: 0,
      intraState: null,
    });
    expect(forward.discountAmount).toBe(10);
    expect(solved.difference).toBe(0);
    expect(solved.lineTotal).toBe(100);
  });

  it('ACT-29 a random quantity, rate, and discount lands on the typed amount or shows the difference', () => {
    let seed = 20261008;
    const next = () => {
      seed = (seed * 1664525 + 1013904223) % 4294967296;
      return seed / 4294967296;
    };
    const rates = [0, 5, 12, 18, 28];
    for (let i = 0; i < 40; i += 1) {
      const quantity = Math.round(next() * 20 * 1000) / 1000 || 1;
      const gstRate = rates[Math.floor(next() * rates.length)];
      const discountPercent = Math.round(next() * 10000) / 100;
      const amount = Math.round((next() * 5000 + 1) * 100) / 100;
      const intraState = next() > 0.5;
      const solved = priceForLineAmount({
        amount,
        quantity,
        discountPercent,
        gstRate,
        intraState,
      });
      const forward = calculateLineTax({
        quantity,
        unitPrice: solved.unitPrice,
        discountPercent,
        gstRate,
        intraState,
      });
      expect(forward.lineTotal).toBeCloseTo(solved.lineTotal, 2);
      const gap = Math.round((amount - forward.lineTotal) * 100) / 100;
      expect(Math.abs(gap) <= 0.01 || Math.abs(gap - solved.difference) < 0.001).toBe(true);
    }
  });

  it('stays within one paise of the typed amount across a spread of totals', () => {
    for (const amount of [10, 50.5, 99.99, 187.5, 221.26, 1000]) {
      const solved = priceForLineAmount({
        amount,
        quantity: 3,
        discountPercent: 5,
        gstRate: 18,
        intraState: true,
      });
      expect(Math.abs(solved.difference)).toBeLessThanOrEqual(0.01);
    }
  });

  it('REVIEW-B7 in tax-inclusive mode the typed amount is the rate times quantity, with no tax taken out', () => {
    const solved = priceForLineAmount({
      amount: 118,
      quantity: 2,
      discountPercent: 0,
      gstRate: 18,
      intraState: true,
      inclusive: true,
    });
    expect(solved.unitPrice).toBe(59);
    expect(solved.lineTotal).toBe(118);
    expect(solved.difference).toBe(0);
  });

  it('REVIEW-B7 inclusive mode keeps a percent discount and ignores cess', () => {
    const solved = priceForLineAmount({
      amount: 90,
      quantity: 1,
      discountPercent: 10,
      gstRate: 28,
      cessRate: 12,
      intraState: false,
      inclusive: true,
    });
    expect(solved.unitPrice).toBe(100);
    expect(solved.lineTotal).toBe(90);
  });

  it('REVIEW-B7 the exclusive answer differs from the inclusive one for the same typed amount', () => {
    const args = { amount: 118, quantity: 1, gstRate: 18, intraState: true } as const;
    expect(priceForLineAmount({ ...args }).unitPrice).toBe(100);
    expect(priceForLineAmount({ ...args, inclusive: true }).unitPrice).toBe(118);
  });

  it('REVIEW-B7 an amount no 2-decimal price can reach is reported as a difference, not hidden', () => {
    const solved = priceForLineAmount({
      amount: 100.01,
      quantity: 1000,
      discountPercent: 0,
      gstRate: 18,
      intraState: true,
    });
    expect(Math.abs(solved.difference)).toBeGreaterThan(0.01);
    expect(solved.lineTotal).toBe(Math.round((100.01 - solved.difference) * 100) / 100);
  });

  it('an unknown place of supply solves without tax', () => {
    const solved = priceForLineAmount({ amount: 100, quantity: 4, gstRate: 18, intraState: null });
    expect(solved.unitPrice).toBe(25);
  });
});
