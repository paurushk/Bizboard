import { describe, expect, it } from 'vitest';
import { theme } from '@/theme';

function channel(hex: string, start: number) {
  const value = parseInt(hex.slice(start, start + 2), 16) / 255;
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function contrast(foreground: string, background: string) {
  const luminance = (hex: string) => {
    const color = hex.replace('#', '');
    return 0.2126 * channel(color, 0) + 0.7152 * channel(color, 2) + 0.0722 * channel(color, 4);
  };
  const light = luminance(foreground);
  const dark = luminance(background);
  const [hi, lo] = light > dark ? [light, dark] : [dark, light];
  return (hi + 0.05) / (lo + 0.05);
}

describe('ACT-10 text contrast', () => {
  it('keeps primary, body, and error text at 4.5:1 or better', () => {
    const paper = theme.palette.background.paper;
    expect(contrast(theme.palette.primary.contrastText, theme.palette.primary.main)).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#000000', paper)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.palette.error.main, paper)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.palette.secondary.contrastText, theme.palette.secondary.main)).toBeGreaterThanOrEqual(4.5);
  });
});
