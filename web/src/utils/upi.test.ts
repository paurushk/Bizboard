import { describe, expect, it } from 'vitest';
import {
  buildDunningMessage,
  buildUpiUri,
  buildWhatsAppShareUrl,
  getAgingCohort,
} from './upi';

describe('UPI utility and Smart Dunning Generator (Sprint 1.2)', () => {
  it('builds standard NPCI-compliant UPI Intent URI', () => {
    const uri = buildUpiUri({
      pa: 'merchant@upi',
      pn: 'Ramesh Stores',
      am: '1500.5',
      tn: 'Invoice_INV-101',
    });
    expect(uri).toBe('upi://pay?pa=merchant%40upi&pn=Ramesh%20Stores&am=1500.50&cu=INR&tn=Invoice_INV-101');
  });

  it('returns empty string if VPA is invalid', () => {
    const uri = buildUpiUri({
      pa: 'not-a-vpa',
      am: 100,
    });
    expect(uri).toBe('');
  });

  it('correctly maps days overdue into 4 distinct aging cohorts', () => {
    expect(getAgingCohort(0)).toBe('UPCOMING');
    expect(getAgingCohort(-3)).toBe('UPCOMING');
    expect(getAgingCohort(1)).toBe('OVERDUE_1_15');
    expect(getAgingCohort(15)).toBe('OVERDUE_1_15');
    expect(getAgingCohort(16)).toBe('OVERDUE_16_45');
    expect(getAgingCohort(45)).toBe('OVERDUE_16_45');
    expect(getAgingCohort(46)).toBe('CRITICAL_45_PLUS');
    expect(getAgingCohort(90)).toBe('CRITICAL_45_PLUS');
  });

  it('generates polite reminder message for upcoming/recent due invoices', () => {
    const msg = buildDunningMessage({
      customerName: 'Sunil Traders',
      companyName: 'Bharat Agency',
      invoiceNumber: 'INV-204',
      amount: 4500,
      daysOverdue: 0,
      upiUri: 'upi://pay?pa=bharat@upi&am=4500.00',
    });
    expect(msg).toContain('gentle courtesy reminder');
    expect(msg).toContain('Sunil Traders');
    expect(msg).toContain('₹4500.00');
    expect(msg).toContain('upi://pay?pa=bharat@upi');
  });

  it('generates urgent notification for 1-15 day overdue cohort', () => {
    const msg = buildDunningMessage({
      customerName: 'Kailash Textiles',
      companyName: 'Bharat Agency',
      invoiceNumber: 'INV-301',
      amount: 12000,
      daysOverdue: 7,
    });
    expect(msg).toContain('overdue balance of ₹12000.00');
    expect(msg).toContain('7 days past due');
  });

  it('generates firm credit freeze warning for 16-45 day overdue cohort', () => {
    const msg = buildDunningMessage({
      customerName: 'Kailash Textiles',
      companyName: 'Bharat Agency',
      invoiceNumber: 'INV-301',
      amount: 12000,
      daysOverdue: 25,
    });
    expect(msg).toContain('temporary hold on future billing');
  });

  it('generates critical escalation notice for 45+ day overdue cohort', () => {
    const msg = buildDunningMessage({
      customerName: 'Kailash Textiles',
      companyName: 'Bharat Agency',
      invoiceNumber: 'INV-301',
      amount: 12000,
      daysOverdue: 60,
    });
    expect(msg).toContain('URGENT NOTICE');
    expect(msg).toContain('severely overdue for 60 days');
  });

  it('builds clean WhatsApp click-to-chat URL with country code', () => {
    const url = buildWhatsAppShareUrl('9876543210', 'Hello world');
    expect(url).toContain('https://wa.me/919876543210?text=Hello%20world');
  });
});
