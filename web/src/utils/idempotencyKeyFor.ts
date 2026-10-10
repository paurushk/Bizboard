import { newIdempotencyKey } from '@/api/client';

/** One key per distinct request body. An identical retry (double click, flaky network)
 * reuses the key so the server replays instead of repeating; a corrected body gets a fresh
 * key, because the server remembers deterministic failures against the old one. */
export function createIdempotencyKeyFor() {
  let last: { fingerprint: string; key: string } | null = null;
  return (body: unknown): string => {
    const fingerprint = JSON.stringify(body);
    if (!last || last.fingerprint !== fingerprint) last = { fingerprint, key: newIdempotencyKey() };
    return last.key;
  };
}
