import { useMemo, useRef } from 'react';
import { idempotencyHeaders, newIdempotencyKey } from '@/api/client';

/**
 * SET-11b/SET-27: one `Idempotency-Key` per create gesture and a guard against a second click while
 * the first is still going. The server applies a keyed create once; the guard stops the second
 * request being sent at all, so a double-click cannot show a confusing "already in progress" error.
 *
 *   const save = useIdempotentSave();
 *   mutationFn: () => api.create(payload, save.headers())   // same key until `renew()`
 *   onSuccess: save.renew                                    // next gesture gets a new key
 *   onClick={() => save.once(mutation.mutate)}               // ignored while one is running
 */
export function useIdempotentSave() {
  const key = useRef(newIdempotencyKey());
  const busy = useRef(false);
  return useMemo(
    () => ({
      headers: () => idempotencyHeaders(key.current),
      renew: () => {
        key.current = newIdempotencyKey();
      },
      /** Run `mutate` unless a previous click's request has not finished. */
      once: (mutate: (variables: undefined, options: { onSettled: () => void }) => void) => {
        if (busy.current) return;
        busy.current = true;
        mutate(undefined, {
          onSettled: () => {
            busy.current = false;
          },
        });
      },
    }),
    [],
  );
}
