import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/help', () => ({
  postHelpEvents: vi.fn(),
}));

import { postHelpEvents } from '@/api/help';
import { trackHelpEvent } from './analytics';

describe('help analytics flush', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(postHelpEvents).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('requeues and flushes again 2s after a failed POST', async () => {
    vi.mocked(postHelpEvents).mockRejectedValueOnce(new Error('net')).mockResolvedValueOnce(undefined);
    trackHelpEvent('help_open', { source: 'nav' });
    await vi.advanceTimersByTimeAsync(400);
    expect(postHelpEvents).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2000);
    expect(postHelpEvents).toHaveBeenCalledTimes(2);
  });
});
