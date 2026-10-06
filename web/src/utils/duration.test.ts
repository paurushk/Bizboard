import { describe, expect, it } from 'vitest';
import { formatDuration } from './duration';

describe('formatDuration', () => {
  it('shows a dash when there is no value', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(undefined)).toBe('—');
    expect(formatDuration(-5)).toBe('—');
  });
  it('rolls seconds up to minutes, hours and days', () => {
    expect(formatDuration(30)).toBe('< 1 min');
    expect(formatDuration(45 * 60)).toBe('45 min');
    expect(formatDuration(3600)).toBe('1 h');
    expect(formatDuration(3600 + 20 * 60)).toBe('1 h 20 min');
    expect(formatDuration(2 * 86400 + 3 * 3600)).toBe('2 d 3 h');
  });
});
