import { getConfig } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

describe('shared test setup', () => {
  it('gives async queries a ceiling above the 1s default so loaded runners do not flake', () => {
    expect(getConfig().asyncUtilTimeout).toBeGreaterThanOrEqual(5000);
  });

  it('still fails (does not hang) when something never appears', async () => {
    const { screen } = await import('@testing-library/react');
    const started = Date.now();
    await expect(screen.findByText('this text is never rendered', {}, { timeout: 300 })).rejects.toBeTruthy();
    expect(Date.now() - started).toBeLessThan(3000);
  });
});
