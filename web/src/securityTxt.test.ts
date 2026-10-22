// WP-SC1: security.txt ships in the build output (Vite copies public/) and has not expired.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('public/.well-known/security.txt', () => {
  const text = readFileSync(resolve(__dirname, '../public/.well-known/security.txt'), 'utf-8');

  it('has the RFC 9116 required fields', () => {
    expect(text).toMatch(/^Contact: \S+/m);
    expect(text).toMatch(/^Expires: \S+/m);
  });

  it('has not expired, so it cannot go stale silently', () => {
    const raw = /^Expires: (\S+)/m.exec(text)?.[1] ?? '';
    expect(new Date(raw).getTime()).toBeGreaterThan(Date.now());
  });
});
