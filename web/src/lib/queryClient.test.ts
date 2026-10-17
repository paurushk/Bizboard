import { describe, expect, it } from 'vitest';
import { createQueryClient } from '@/lib/queryClient';

describe('createQueryClient', () => {
  it('marks money queries stale after any successful write, and leaves unrelated ones alone', async () => {
    const qc = createQueryClient();
    const position = qc.getQueryCache().build(qc, { queryKey: ['money-position'], queryFn: async () => 1 });
    const other = qc.getQueryCache().build(qc, { queryKey: ['products'], queryFn: async () => 2 });
    await position.fetch();
    await other.fetch();

    await qc.getMutationCache().build(qc, { mutationFn: async () => 'saved' }).execute(undefined);

    expect(position.state.isInvalidated).toBe(true);
    expect(other.state.isInvalidated).toBe(false);
  });

  it('does not touch money queries when a write fails', async () => {
    const qc = createQueryClient();
    const position = qc.getQueryCache().build(qc, { queryKey: ['money-position'], queryFn: async () => 1 });
    await position.fetch();

    await qc
      .getMutationCache()
      .build(qc, {
        mutationFn: async () => {
          throw new Error('refused');
        },
      })
      .execute(undefined)
      .catch(() => undefined);

    expect(position.state.isInvalidated).toBe(false);
  });
});
