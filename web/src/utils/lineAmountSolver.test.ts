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
});
