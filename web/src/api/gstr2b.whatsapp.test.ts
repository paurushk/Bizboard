import { describe, expect, it } from 'vitest';
import { whatsAppShareUrl } from '@/api/gstr2b';

describe('whatsAppShareUrl', () => {
  it('prefills digits and keeps a text-only link when the phone is missing', () => {
    expect(whatsAppShareUrl('Hello supplier', '+91 98450 11111')).toBe(
      'https://wa.me/919845011111?text=Hello%20supplier',
    );
    expect(whatsAppShareUrl('Hello supplier', '')).toBe('https://wa.me/?text=Hello%20supplier');
    expect(whatsAppShareUrl('Hello supplier', null)).toBe('https://wa.me/?text=Hello%20supplier');
  });
});
