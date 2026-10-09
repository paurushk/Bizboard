import { describe, expect, it } from 'vitest';
import { amountInWords } from '@/utils/amountInWords';

describe('amountInWords', () => {
  it('matches the invoice PDF wording', () => {
    expect(amountInWords(105)).toBe('One Hundred Five Rupees Only');
    expect(amountInWords(59000)).toBe('Fifty Nine Thousand Rupees Only');
    expect(amountInWords('105.50')).toBe('One Hundred Five Rupees and Fifty Paise Only');
    expect(amountInWords(0)).toBe('Zero Rupees Only');
    expect(amountInWords('1.005')).toBe('One Rupees and One Paise Only');
  });
});
