import { afterEach, describe, expect, it } from 'vitest';
import { isHelpV2Enabled } from '@/config/features';

describe('isHelpV2Enabled', () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it('stays off by default in unit tests', () => {
    expect(isHelpV2Enabled()).toBe(false);
  });

  it('sessionStorage bizboard:e2eHelpV2 turns v2 on without the product flag', () => {
    sessionStorage.setItem('bizboard:e2eHelpV2', '1');
    expect(isHelpV2Enabled()).toBe(true);
  });
});
